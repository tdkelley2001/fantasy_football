"""M5.8 bounded, action-family-neutral search execution and export."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import queue
import threading
import time
import tracemalloc
from collections import Counter
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Callable

from fantasy_football.canonical.model import LeagueSnapshot
from fantasy_football.evolving_state import EvolvingLeagueState, validate_evolving_state
from fantasy_football.monte_carlo import MonteCarloConfig, monte_carlo_run_identity
from fantasy_football.monte_carlo_parallel import ParallelExecutionConfiguration
from fantasy_football.monte_carlo_precision import PrecisionConfiguration
from fantasy_football.player_outcomes import PlayerOutcomeModel
from fantasy_football.trade_search import (
    ProgressiveSamplingConfiguration,
    ProgressiveStateEvaluationResult,
    ProgressiveStateGroupInput,
    SearchProgressStage,
    evaluate_progressive_state_groups,
)
from fantasy_football.unified_actions import (
    UnifiedActionCandidate,
    UnifiedActionCoverage,
    UnifiedActionEnumeration,
    UnifiedActionEvaluationResult,
    UnifiedActionSearchConfiguration,
    UnifiedCompletedStateGroup,
    _attempts,
    _validate_configuration,
    enumerate_unified_action_candidates,
    evaluate_unified_action_states,
)


ORCHESTRATION_SCHEMA_VERSION = 1


class SearchOrchestrationError(ValueError):
    """Raised before or during an invalid bounded search run."""


class SearchExecutionMode(StrEnum):
    SEQUENTIAL_REFERENCE = "sequential_reference"
    BOUNDED_OVERLAP = "bounded_overlap"


class SearchEvaluationMode(StrEnum):
    FIXED = "fixed"
    PROGRESSIVE = "progressive"


class SearchPreset(StrEnum):
    QUICK = "quick"
    BALANCED = "balanced"
    HIGH_PRECISION = "high_precision"
    EXHAUSTIVE = "exhaustive"
    FULL_BOUNDED = "full_bounded"


class OrchestrationStage(StrEnum):
    CONFIGURATION_VALIDATION = "configuration_validation"
    PREFLIGHT = "preflight"
    CANDIDATE_GENERATION = "candidate_generation"
    STATE_GROUPING = "state_grouping"
    INITIAL_EVALUATION = "initial_evaluation"
    PROGRESSIVE_REFINEMENT = "progressive_refinement"
    FINAL = "final"


class OrchestrationStopReason(StrEnum):
    COMPLETE = "complete"
    CANDIDATE_LIMIT = "candidate_limit"
    EVALUATION_LIMIT = "evaluation_limit"
    WALL_CLOCK_LIMIT = "wall_clock_limit"
    STATISTICAL_LIMIT = "statistical_limit"
    NO_CANDIDATES = "no_candidates"


@dataclass(frozen=True, slots=True)
class SearchResourceConfiguration:
    execution_mode: SearchExecutionMode = SearchExecutionMode.SEQUENTIAL_REFERENCE
    worker_count: int = 1
    maximum_in_flight_states: int = 1
    paths_per_worker_task: int = 1
    queue_capacity: int = 64
    candidate_limit: int | None = None
    evaluation_state_limit: int | None = None
    simulation_path_budget: int | None = None
    wall_clock_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class SearchPreflightConfiguration:
    enabled: bool = False
    candidate_sample_size: int = 10
    monte_carlo_sample_paths: int = 2


@dataclass(frozen=True, slots=True)
class SearchExportConfiguration:
    output_directory: str | None = None
    write_json: bool = False
    write_csv: bool = False
    filtered_candidate_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class SearchOrchestrationConfiguration:
    candidate_search: UnifiedActionSearchConfiguration
    evaluation_mode: SearchEvaluationMode
    sampling: ProgressiveSamplingConfiguration
    resources: SearchResourceConfiguration = SearchResourceConfiguration()
    preflight: SearchPreflightConfiguration = SearchPreflightConfiguration()
    export: SearchExportConfiguration = SearchExportConfiguration()


@dataclass(frozen=True, slots=True)
class SearchPreflightResult:
    candidate_sample_count: int
    candidate_seconds: float
    candidate_throughput_per_second: float | None
    monte_carlo_sample_paths: int
    monte_carlo_seconds: float | None
    peak_traced_bytes: int
    extrapolation_reliable: bool
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchProgressSnapshot:
    stage: OrchestrationStage
    candidates_explored: int
    candidates_retained: int
    unique_completed_states: int
    state_evaluations_completed: int
    simulation_paths_completed: int
    queue_occupancy: int | None
    active_workers: int
    candidate_coverage_complete: bool
    statistical_precision_complete: bool
    ranking_resolved: bool
    elapsed_seconds: float
    stop_reason: OrchestrationStopReason | None


@dataclass(frozen=True, slots=True)
class SearchCandidateResult:
    candidate_id: str
    ordering: str
    completed_state_sha256: str
    execution_status: str
    acquisition_status: str
    action_count: int
    evaluated_paths: int
    requester_championship_difference: float | None
    statistically_competitive: bool
    precision_reached: bool
    execution_caveats: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchOrchestrationResult:
    schema_version: int
    run_sha256: str
    configuration: SearchOrchestrationConfiguration
    enumeration: UnifiedActionEnumeration
    candidates: tuple[SearchCandidateResult, ...]
    fixed_evaluation: UnifiedActionEvaluationResult | None
    progressive_evaluation: ProgressiveStateEvaluationResult | None
    preflight: SearchPreflightResult | None
    progress: tuple[SearchProgressSnapshot, ...]
    stop_reason: OrchestrationStopReason
    candidate_coverage_complete: bool
    statistical_precision_complete: bool
    ranking_resolved: bool
    export_paths: tuple[str, ...]


def _fail(message: str) -> None:
    raise SearchOrchestrationError(message)


def _positive(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _fail(f"{label} must be a positive integer")


def _validate(configuration: SearchOrchestrationConfiguration, simulation: MonteCarloConfig) -> None:
    if not isinstance(configuration, SearchOrchestrationConfiguration):
        _fail("configuration must be SearchOrchestrationConfiguration")
    if not isinstance(configuration.evaluation_mode, SearchEvaluationMode):
        _fail("evaluation_mode is unsupported")
    if configuration.candidate_search.maximum_completed_paths is not None:
        _fail(
            "candidate_search maximum_completed_paths must be null; use the "
            "orchestration candidate_limit so coverage has one authority"
        )
    resources = configuration.resources
    if not isinstance(resources.execution_mode, SearchExecutionMode):
        _fail("execution_mode is unsupported")
    for name in (
        "worker_count", "maximum_in_flight_states", "paths_per_worker_task",
        "queue_capacity",
    ):
        _positive(getattr(resources, name), name)
    for name in ("candidate_limit", "evaluation_state_limit", "simulation_path_budget"):
        value = getattr(resources, name)
        if value is not None:
            _positive(value, name)
    if resources.wall_clock_seconds is not None and (
        isinstance(resources.wall_clock_seconds, bool)
        or not isinstance(resources.wall_clock_seconds, (int, float))
        or not math.isfinite(resources.wall_clock_seconds)
        or resources.wall_clock_seconds <= 0
    ):
        _fail("wall_clock_seconds must be finite and positive or null")
    _positive(configuration.preflight.candidate_sample_size, "candidate_sample_size")
    _positive(configuration.preflight.monte_carlo_sample_paths, "monte_carlo_sample_paths")
    if simulation.path_count != configuration.sampling.maximum_paths_per_state:
        _fail("simulation path_count must equal sampling maximum_paths_per_state")
    if resources.simulation_path_budget is not None:
        minimum = configuration.sampling.initial_paths
        if resources.simulation_path_budget < minimum:
            _fail("simulation_path_budget cannot be smaller than initial_paths")
    export = configuration.export
    if (export.write_json or export.write_csv) and export.output_directory is None:
        _fail("enabled exports require output_directory")
    if export.filtered_candidate_ids is not None and len(export.filtered_candidate_ids) != len(set(export.filtered_candidate_ids)):
        _fail("filtered_candidate_ids contain duplicates")


def orchestration_preset(
    preset: SearchPreset,
    candidate_search: UnifiedActionSearchConfiguration,
) -> SearchOrchestrationConfiguration:
    """Return editable convenience settings; presets never alter league rules."""

    values = {
        SearchPreset.QUICK: (50, 25, 100, 1, 25),
        SearchPreset.BALANCED: (100, 100, 500, 2, 100),
        SearchPreset.HIGH_PRECISION: (250, 250, 2000, 2, None),
        SearchPreset.EXHAUSTIVE: (100, 100, 1000, 1, None),
        SearchPreset.FULL_BOUNDED: (100, 100, 1000, 2, 500),
    }
    if not isinstance(preset, SearchPreset):
        _fail("preset is unsupported")
    initial, batch, maximum, workers, state_limit = values[preset]
    return SearchOrchestrationConfiguration(
        candidate_search,
        SearchEvaluationMode.PROGRESSIVE,
        ProgressiveSamplingConfiguration(0.95, 0.05, initial, batch, maximum, 2, state_limit),
        SearchResourceConfiguration(
            SearchExecutionMode.SEQUENTIAL_REFERENCE if workers == 1 else SearchExecutionMode.BOUNDED_OVERLAP,
            workers, workers, 1, 64, None, state_limit, None, None,
        ),
    )


def _bounded_enumeration(snapshot, state, configuration, resources, deadline):
    if resources.candidate_limit is not None:
        configuration = replace(
            configuration, maximum_completed_paths=resources.candidate_limit
        )
    config_sha, baseline_sha = _validate_configuration(snapshot, state, configuration)
    work: queue.Queue[UnifiedActionCandidate | BaseException | None] = queue.Queue(resources.queue_capacity)
    stop = threading.Event()
    rejections: Counter[str] = Counter()

    def produce():
        try:
            for item in _attempts(snapshot, state, configuration, config_sha, baseline_sha, rejections):
                if stop.is_set():
                    break
                work.put(item)
        except BaseException as exc:
            work.put(exc)
        finally:
            work.put(None)

    thread = threading.Thread(target=produce, name="m5.8-candidate-producer", daemon=True)
    thread.start()
    retained: list[UnifiedActionCandidate] = []
    generated = screened = 0
    reason = None
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            reason = OrchestrationStopReason.WALL_CLOCK_LIMIT
            stop.set()
        item = work.get()
        if item is None:
            break
        if isinstance(item, BaseException):
            raise item
        generated += 1
        if not item.screening_passed:
            screened += 1
            continue
        if resources.candidate_limit is not None and len(retained) >= resources.candidate_limit:
            reason = OrchestrationStopReason.CANDIDATE_LIMIT
            stop.set()
            continue
        retained.append(item)
    thread.join()
    retained.sort(key=lambda item: item.candidate_id)
    groups: dict[str, list[UnifiedActionCandidate]] = {}
    for item in retained:
        groups.setdefault(item.completed_state_sha256, []).append(item)
    states = tuple(
        UnifiedCompletedStateGroup(state_id, items[0].completed_scenario.state, tuple(sorted(item.candidate_id for item in items)))
        for state_id, items in sorted(groups.items())
    )
    conditional = sum(item.acquisition_status.value == "conditional_waiver" for item in retained)
    no_acquisition = sum(item.acquisition_status.value == "not_applicable" for item in retained)
    immediate = len(retained) - conditional - no_acquisition
    coverage = UnifiedActionCoverage(
        generated, len(retained), screened, no_acquisition, immediate, conditional,
        len(states), len(retained) - len(states), tuple(sorted(rejections.items())),
        reason is None, "candidate_generation" if reason else None,
        reason.value if reason else None,
    )
    return UnifiedActionEnumeration(config_sha, baseline_sha, tuple(retained), states, coverage), reason


def _preflight(snapshot, state, configuration, simulation, model):
    start = time.perf_counter()
    tracemalloc.start()
    sample_config = replace(
        configuration.candidate_search,
        maximum_completed_paths=configuration.preflight.candidate_sample_size,
    )
    sample = enumerate_unified_action_candidates(snapshot, state, sample_config)
    candidate_seconds = time.perf_counter() - start
    monte_seconds = None
    paths = 0
    if sample.completed_states:
        from fantasy_football.monte_carlo import run_monte_carlo_batch

        paths = configuration.preflight.monte_carlo_sample_paths
        batch = replace(simulation, path_count=paths, initial_evolving_state=sample.completed_states[0].state)
        start_mc = time.perf_counter()
        run_monte_carlo_batch(snapshot, batch, model)
        monte_seconds = time.perf_counter() - start_mc
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    count = len(sample.candidates)
    return SearchPreflightResult(
        count, candidate_seconds,
        count / candidate_seconds if count and candidate_seconds > 0 else None,
        paths, monte_seconds, peak, sample.coverage.complete,
        ("sample branching may not represent the full universe", "adaptive path requirements are unknown before evaluation"),
    )


def _candidate_results(enumeration, fixed, progressive, requester):
    by_state = {}
    if fixed is not None:
        by_state = {item.completed_state_sha256: item.comparison for item in fixed.evaluations}
    progressive_states = {} if progressive is None else {
        item.completed_state_sha256: item for item in progressive.state_evaluations
    }
    results = []
    for candidate in enumeration.candidates:
        comparison = by_state.get(candidate.completed_state_sha256)
        progressive_item = progressive_states.get(candidate.completed_state_sha256)
        if progressive_item is not None:
            comparison = progressive_item.comparison
        team = None if comparison is None else next(item for item in comparison.teams if item.team_id == requester)
        results.append(SearchCandidateResult(
            candidate.candidate_id, candidate.ordering.value, candidate.completed_state_sha256,
            candidate.execution_status.value, candidate.acquisition_status.value,
            len(candidate.actions), 0 if comparison is None else comparison.matched_path_count,
            None if team is None else team.championship.difference,
            False if progressive_item is None else progressive_item.statistically_competitive,
            False if progressive_item is None else progressive_item.precision_reached_all_teams,
            candidate.execution_caveats,
        ))
    return tuple(sorted(results, key=lambda item: item.candidate_id))


def _write_exports(result, configuration):
    export = configuration.export
    if not export.write_json and not export.write_csv:
        return ()
    root = Path(export.output_directory or "").resolve()
    root.mkdir(parents=True, exist_ok=True)
    selected = result.candidates
    if export.filtered_candidate_ids is not None:
        wanted = set(export.filtered_candidate_ids)
        unknown = wanted - {item.candidate_id for item in selected}
        if unknown:
            _fail(f"filtered export references unknown candidates {sorted(unknown)}")
        selected = tuple(item for item in selected if item.candidate_id in wanted)
    paths = []
    if export.write_json:
        path = root / "m5_8_search_results.json"
        selected_state_ids = {item.completed_state_sha256 for item in selected}
        evaluations = ()
        if result.fixed_evaluation is not None:
            evaluations = tuple(
                (item.completed_state_sha256, item.comparison)
                for item in result.fixed_evaluation.evaluations
                if item.completed_state_sha256 in selected_state_ids
            )
        elif result.progressive_evaluation is not None:
            evaluations = tuple(
                (item.completed_state_sha256, item.comparison)
                for item in result.progressive_evaluation.state_evaluations
                if item.completed_state_sha256 in selected_state_ids
                and item.comparison is not None
            )
        payload = {
            "schema_version": ORCHESTRATION_SCHEMA_VERSION,
            "run_sha256": result.run_sha256,
            "scope": "filtered" if export.filtered_candidate_ids is not None else "all",
            "candidate_coverage_complete": result.candidate_coverage_complete,
            "statistical_precision_complete": result.statistical_precision_complete,
            "ranking_resolved": result.ranking_resolved,
            "candidates": [asdict(item) for item in selected],
            "state_evaluations": [
                {
                    "completed_state_sha256": state_id,
                    "matched_path_count": comparison.matched_path_count,
                    "teams": [
                        {
                            "team_id": team.team_id,
                            "championship": asdict(team.championship),
                            "playoff_qualification": asdict(team.playoff_qualification),
                            "final_placements": [
                                asdict(metric) for metric in team.final_placements
                            ],
                        }
                        for team in comparison.teams
                    ],
                }
                for state_id, comparison in evaluations
            ],
        }
        path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str), encoding="utf-8")
        paths.append(str(path))
    if export.write_csv:
        path = root / "m5_8_search_results.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=[field for field in SearchCandidateResult.__dataclass_fields__])
            writer.writeheader()
            for item in selected:
                row = asdict(item)
                row["execution_caveats"] = "|".join(item.execution_caveats)
                writer.writerow(row)
        paths.append(str(path))
    return tuple(paths)


def execute_search_orchestration(
    snapshot: LeagueSnapshot,
    baseline_state: EvolvingLeagueState,
    configuration: SearchOrchestrationConfiguration,
    simulation: MonteCarloConfig,
    model: PlayerOutcomeModel,
    *,
    progress_observer: Callable[[SearchProgressSnapshot], None] | None = None,
) -> SearchOrchestrationResult:
    """Execute the M5.8 reference or bounded pipeline without network access."""

    validate_evolving_state(baseline_state, snapshot)
    _validate(configuration, simulation)
    started = time.monotonic()
    progress: list[SearchProgressSnapshot] = []

    def emit(stage, enumeration=None, evaluated=0, paths=0, complete=False, precision=False, ranking=False, stop=None, queue_size=None):
        item = SearchProgressSnapshot(
            stage,
            0 if enumeration is None else enumeration.coverage.generated_path_count,
            0 if enumeration is None else enumeration.coverage.retained_path_count,
            0 if enumeration is None else enumeration.coverage.unique_completed_state_count,
            evaluated, paths, queue_size,
            configuration.resources.worker_count if stage in {OrchestrationStage.INITIAL_EVALUATION, OrchestrationStage.PROGRESSIVE_REFINEMENT} else 1,
            complete, precision, ranking, time.monotonic() - started, stop,
        )
        progress.append(item)
        if progress_observer is not None:
            progress_observer(item)

    emit(OrchestrationStage.CONFIGURATION_VALIDATION)
    preflight = None
    if configuration.preflight.enabled:
        preflight = _preflight(snapshot, baseline_state, configuration, simulation, model)
        emit(OrchestrationStage.PREFLIGHT)
    deadline = None if configuration.resources.wall_clock_seconds is None else started + configuration.resources.wall_clock_seconds
    if configuration.resources.execution_mode is SearchExecutionMode.SEQUENTIAL_REFERENCE:
        search = configuration.candidate_search
        if configuration.resources.candidate_limit is not None:
            search = replace(search, maximum_completed_paths=configuration.resources.candidate_limit)
        enumeration = enumerate_unified_action_candidates(snapshot, baseline_state, search)
        generation_stop = None if enumeration.coverage.complete else OrchestrationStopReason.CANDIDATE_LIMIT
    else:
        enumeration, generation_stop = _bounded_enumeration(
            snapshot, baseline_state, configuration.candidate_search,
            configuration.resources, deadline,
        )
    emit(OrchestrationStage.CANDIDATE_GENERATION, enumeration, complete=enumeration.coverage.complete, stop=generation_stop)
    emit(OrchestrationStage.STATE_GROUPING, enumeration, complete=enumeration.coverage.complete)

    state_limit = configuration.resources.evaluation_state_limit
    sampling = configuration.sampling
    if state_limit is not None:
        sampling = replace(sampling, unique_state_evaluation_budget=state_limit)
    if configuration.resources.simulation_path_budget is not None:
        sampling = replace(sampling, maximum_paths_per_state=min(sampling.maximum_paths_per_state, configuration.resources.simulation_path_budget))
        simulation = replace(simulation, path_count=sampling.maximum_paths_per_state)
    parallel = None
    if configuration.resources.execution_mode is SearchExecutionMode.BOUNDED_OVERLAP and configuration.resources.worker_count > 1:
        parallel = ParallelExecutionConfiguration(
            configuration.resources.worker_count,
            configuration.resources.paths_per_worker_task,
            max_in_flight_tasks=configuration.resources.maximum_in_flight_states,
        )
    fixed = None
    progressive = None
    if configuration.evaluation_mode is SearchEvaluationMode.FIXED:
        groups = enumeration.completed_states if state_limit is None else enumeration.completed_states[:state_limit]
        subset_ids = {candidate_id for group in groups for candidate_id in group.candidate_ids}
        subset = replace(
            enumeration,
            candidates=tuple(item for item in enumeration.candidates if item.candidate_id in subset_ids),
            completed_states=groups,
        )
        precision = PrecisionConfiguration(
            sampling.confidence_level, sampling.target_paired_half_width,
            sampling.maximum_paths_per_state, sampling.maximum_paths_per_state,
            sampling.maximum_paths_per_state,
        )
        fixed = evaluate_unified_action_states(
            snapshot, baseline_state, subset, simulation, model, precision,
            parallel_execution=parallel,
        ) if groups else None
        evaluated = len(groups)
        paths = evaluated * sampling.maximum_paths_per_state
        precision_complete = (
            evaluated == len(enumeration.completed_states)
            and fixed is not None
            and all(
                all(
                    team.championship.interval.half_width
                    <= sampling.target_paired_half_width
                    for team in item.comparison.teams
                )
                for item in fixed.evaluations
            )
        )
        ranking_resolved = False
        evaluation_stop = (
            OrchestrationStopReason.EVALUATION_LIMIT
            if evaluated < len(enumeration.completed_states)
            else (
                OrchestrationStopReason.COMPLETE
                if precision_complete
                else OrchestrationStopReason.STATISTICAL_LIMIT
            )
        )
    else:
        def observe_progressive(item):
            if item.stage not in {
                SearchProgressStage.INITIAL_EVALUATION,
                SearchProgressStage.REFINEMENT,
            }:
                return
            emit(
                OrchestrationStage.INITIAL_EVALUATION
                if item.stage is SearchProgressStage.INITIAL_EVALUATION
                else OrchestrationStage.PROGRESSIVE_REFINEMENT,
                enumeration,
                item.initially_evaluated_states,
                sum(estimate.completed_paths for estimate in item.estimates),
                item.candidate_coverage_complete,
                item.statistical_precision_complete,
                item.ranking_resolved,
            )

        progressive = evaluate_progressive_state_groups(
            snapshot, baseline_state,
            tuple(ProgressiveStateGroupInput(item.completed_state_sha256, item.state, item.candidate_ids) for item in enumeration.completed_states),
            configuration.candidate_search.requesting_team_id,
            sampling, simulation, model, parallel_execution=parallel,
            progress_observer=observe_progressive,
        )
        evaluated = progressive.initially_evaluated_states
        paths = progressive.scenario_paths_computed
        precision_complete = progressive.statistical_precision_complete
        ranking_resolved = progressive.ranking_resolved
        evaluation_stop = (
            OrchestrationStopReason.COMPLETE
            if precision_complete or ranking_resolved
            else OrchestrationStopReason.STATISTICAL_LIMIT
        )
    if configuration.evaluation_mode is SearchEvaluationMode.FIXED:
        emit(OrchestrationStage.INITIAL_EVALUATION, enumeration, evaluated, paths, enumeration.coverage.complete, precision_complete, ranking_resolved)
    candidates = _candidate_results(
        enumeration, fixed, progressive,
        configuration.candidate_search.requesting_team_id,
    )
    final_stop = generation_stop or (
        OrchestrationStopReason.NO_CANDIDATES if not enumeration.candidates else evaluation_stop
    )
    identity = hashlib.sha256(json.dumps({
        "contract": "m5.8-search-orchestration-v1",
        "snapshot_id": snapshot.snapshot_id,
        "candidate_search_sha256": enumeration.configuration_sha256,
        "baseline_state_sha256": enumeration.baseline_state_sha256,
        "evaluation_mode": configuration.evaluation_mode.value,
        "sampling": asdict(configuration.sampling),
        "monte_carlo_run_identity": monte_carlo_run_identity(
            snapshot, simulation, model
        ),
        "candidate_ids": [item.candidate_id for item in candidates],
    }, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    result = SearchOrchestrationResult(
        ORCHESTRATION_SCHEMA_VERSION, identity, configuration, enumeration,
        candidates, fixed, progressive, preflight, (), final_stop,
        enumeration.coverage.complete,
        precision_complete, ranking_resolved, (),
    )
    exports = _write_exports(result, configuration)
    emit(OrchestrationStage.FINAL, enumeration, evaluated, paths, enumeration.coverage.complete, precision_complete, ranking_resolved, final_stop)
    return replace(result, progress=tuple(progress), export_paths=exports)
