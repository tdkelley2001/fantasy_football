"""Sequential, path-indexed provisional repeated-season simulation for M2.6."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from fantasy_football.canonical.model import LeagueSnapshot
from fantasy_football.evolving_state import IRPolicy
from fantasy_football.player_outcomes import PlayerOutcomeModel, projection_class_counts
from fantasy_football.postseason import ConsolationLadderConfiguration
from fantasy_football.season_simulator import (
    DEFAULT_POSTSEASON_TRANSACTION_POLICY,
    DeterministicSeasonResult,
    PostseasonTransactionParticipationPolicy,
    SeasonCompletionStatus,
    simulate_deterministic_season,
)
from fantasy_football.weekly_transactions import WeeklyTransactionPolicy


class MonteCarloError(ValueError):
    """Raised for invalid configuration, path execution, or reconciliation."""


@dataclass(frozen=True, slots=True)
class MonteCarloConfig:
    master_seed: int
    path_count: int
    first_path_index: int
    ir_policy: IRPolicy
    transaction_policy: WeeklyTransactionPolicy
    postseason_transaction_policy: PostseasonTransactionParticipationPolicy = (
        DEFAULT_POSTSEASON_TRANSACTION_POLICY
    )
    consolation_configuration: ConsolationLadderConfiguration | None = None
    require_complete: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.master_seed, bool) or not isinstance(self.master_seed, int):
            raise MonteCarloError("master_seed must be an integer")
        if isinstance(self.path_count, bool) or not isinstance(self.path_count, int) or self.path_count <= 0:
            raise MonteCarloError("path_count must be a positive integer")
        if (
            isinstance(self.first_path_index, bool)
            or not isinstance(self.first_path_index, int)
            or self.first_path_index < 0
        ):
            raise MonteCarloError("first_path_index must be a nonnegative integer")
        if not isinstance(self.ir_policy, IRPolicy):
            raise MonteCarloError("ir_policy must be IRPolicy")
        if not isinstance(self.transaction_policy, WeeklyTransactionPolicy):
            raise MonteCarloError("transaction_policy must be WeeklyTransactionPolicy")
        if not isinstance(self.require_complete, bool):
            raise MonteCarloError("require_complete must be bool")

    @property
    def path_indices(self) -> tuple[int, ...]:
        return tuple(range(self.first_path_index, self.first_path_index + self.path_count))


@dataclass(frozen=True, slots=True)
class PathTeamOutcome:
    team_id: int
    playoff_qualified: bool | None
    final_placement: int | None
    final_regular_rank: int | None
    regular_wins: int
    regular_points_for: float


@dataclass(frozen=True, slots=True)
class MonteCarloPathSummary:
    path_index: int
    scenario_id: str
    scenario_sha256: str
    status: SeasonCompletionStatus
    unresolved_capabilities: tuple[str, ...]
    teams: tuple[PathTeamOutcome, ...]


@dataclass(frozen=True, slots=True)
class TeamMonteCarloAggregate:
    team_id: int
    completed_paths: int
    championship_wins: int
    championship_frequency: float | None
    playoff_qualifications: int
    playoff_frequency: float | None
    runner_up_finishes: int
    placement_counts: tuple[tuple[int, int], ...]
    average_final_placement: float | None
    average_regular_rank: float | None
    average_regular_wins: float | None
    average_regular_points_for: float | None


@dataclass(frozen=True, slots=True)
class MonteCarloBatchResult:
    snapshot_id: str
    league_id: int
    season: int
    model_id: str
    model_parameters: tuple[tuple[str, str | int | float | bool], ...]
    master_seed: int
    path_indices: tuple[int, ...]
    requested_paths: int
    completed_paths: int
    incomplete_paths: int
    invalid_paths: int
    paths: tuple[MonteCarloPathSummary, ...]
    teams: tuple[TeamMonteCarloAggregate, ...]
    reconciliation_complete: bool
    incomplete_capabilities: tuple[tuple[str, int], ...]
    assumptions: tuple[str, ...]
    projection_class_counts: tuple[tuple[str, int], ...]


def _scenario_digest(result) -> str:
    payload = tuple(
        (item.player_id, item.season, item.scoring_week, item.points)
        for item in result.scores
    )
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def run_monte_carlo_path(
    snapshot: LeagueSnapshot,
    config: MonteCarloConfig,
    model: PlayerOutcomeModel,
    path_index: int,
    *,
    retain_result: bool = False,
) -> tuple[MonteCarloPathSummary, DeterministicSeasonResult | None]:
    if path_index not in config.path_indices:
        raise MonteCarloError(f"path_index={path_index} is outside configured range")
    try:
        scenario = model.generate_scenario(
            snapshot, master_seed=config.master_seed, path_index=path_index
        )
        season = simulate_deterministic_season(
            snapshot,
            scenario,
            ir_policy=config.ir_policy,
            transaction_policy=config.transaction_policy,
            postseason_transaction_policy=config.postseason_transaction_policy,
            consolation_configuration=config.consolation_configuration,
        )
    except ValueError as exc:
        raise MonteCarloError(f"invalid path {path_index}: {exc}") from exc
    teams = tuple(
        PathTeamOutcome(
            item.team_id,
            item.championship_qualifier,
            item.final_placement,
            item.final_regular_rank,
            item.final_regular_standing.wins,
            item.final_regular_standing.points_for,
        )
        for item in season.team_records
    )
    summary = MonteCarloPathSummary(
        path_index,
        scenario.scenario_id,
        _scenario_digest(scenario),
        season.status,
        season.unresolved_capabilities,
        teams,
    )
    if config.require_complete and season.status is not SeasonCompletionStatus.COMPLETE:
        raise MonteCarloError(
            f"path {path_index} is capability-incomplete: {season.unresolved_capabilities}"
        )
    return summary, season if retain_result else None


def _aggregate(
    snapshot: LeagueSnapshot,
    config: MonteCarloConfig,
    model: PlayerOutcomeModel,
    paths: tuple[MonteCarloPathSummary, ...],
) -> MonteCarloBatchResult:
    team_ids = tuple(sorted(item.team_id for item in snapshot.teams))
    complete = tuple(item for item in paths if item.status is SeasonCompletionStatus.COMPLETE)
    incomplete = tuple(item for item in paths if item.status is SeasonCompletionStatus.INCOMPLETE)
    complete_output = len(complete) == len(paths)
    aggregates = []
    for team_id in team_ids:
        outcomes = tuple(
            next(item for item in path.teams if item.team_id == team_id)
            for path in complete
        )
        placements = tuple(item.final_placement for item in outcomes)
        if any(item is None for item in placements):
            raise MonteCarloError(f"complete paths lack final placement for team {team_id}")
        placement_counts = tuple(
            (place, sum(value == place for value in placements))
            for place in range(1, len(team_ids) + 1)
        )
        denominator = len(paths) if complete_output else 0
        champions = sum(item.final_placement == 1 for item in outcomes)
        playoffs = sum(item.playoff_qualified is True for item in outcomes)
        aggregates.append(
            TeamMonteCarloAggregate(
                team_id,
                len(outcomes),
                champions,
                champions / denominator if denominator else None,
                playoffs,
                playoffs / denominator if denominator else None,
                sum(item.final_placement == 2 for item in outcomes),
                placement_counts,
                math.fsum(item.final_placement for item in outcomes) / len(outcomes)
                if outcomes
                else None,
                math.fsum(item.final_regular_rank for item in outcomes) / len(outcomes)
                if outcomes and all(item.final_regular_rank is not None for item in outcomes)
                else None,
                math.fsum(item.regular_wins for item in outcomes) / len(outcomes)
                if outcomes
                else None,
                math.fsum(item.regular_points_for for item in outcomes) / len(outcomes)
                if outcomes
                else None,
            )
        )
    if complete:
        if sum(item.championship_wins for item in aggregates) != len(complete):
            raise MonteCarloError("championship totals do not reconcile")
        for place in range(1, len(team_ids) + 1):
            if sum(dict(item.placement_counts)[place] for item in aggregates) != len(complete):
                raise MonteCarloError(f"placement {place} totals do not reconcile")
        qualifier_count = snapshot.rules.championship.qualifier_count
        if qualifier_count is None or sum(item.playoff_qualifications for item in aggregates) != len(complete) * qualifier_count:
            raise MonteCarloError("playoff qualification totals do not reconcile")
    capabilities: dict[str, int] = {}
    for path in incomplete:
        for capability in path.unresolved_capabilities:
            capabilities[capability] = capabilities.get(capability, 0) + 1
    return MonteCarloBatchResult(
        snapshot.snapshot_id or "",
        snapshot.league_id,
        snapshot.season,
        model.model_id,
        model.parameters,
        config.master_seed,
        tuple(item.path_index for item in paths),
        len(paths),
        len(complete),
        len(incomplete),
        0,
        paths,
        tuple(aggregates),
        complete_output,
        tuple(sorted(capabilities.items())),
        (
            "provisional_not_empirically_calibrated",
            "conditionally_independent_player_weeks_v1",
            "fixed_requested_path_denominator_required_for_frequencies",
        ),
        projection_class_counts(snapshot),
    )


def run_monte_carlo_batch(
    snapshot: LeagueSnapshot,
    config: MonteCarloConfig,
    model: PlayerOutcomeModel,
) -> MonteCarloBatchResult:
    if not getattr(model, "model_id", None) or not hasattr(model, "generate_scenario"):
        raise MonteCarloError("model does not satisfy PlayerOutcomeModel")
    paths = tuple(
        run_monte_carlo_path(snapshot, config, model, path_index)[0]
        for path_index in config.path_indices
    )
    return _aggregate(snapshot, config, model, paths)


def combine_monte_carlo_batches(
    snapshot: LeagueSnapshot,
    config: MonteCarloConfig,
    model: PlayerOutcomeModel,
    batches: tuple[MonteCarloBatchResult, ...],
) -> MonteCarloBatchResult:
    paths = tuple(sorted((path for batch in batches for path in batch.paths), key=lambda item: item.path_index))
    if tuple(item.path_index for item in paths) != config.path_indices:
        raise MonteCarloError("combined batches do not exactly cover configured path range")
    if len({item.path_index for item in paths}) != len(paths):
        raise MonteCarloError("combined batches contain duplicate path IDs")
    for batch in batches:
        if (
            batch.snapshot_id != snapshot.snapshot_id
            or batch.model_id != model.model_id
            or batch.model_parameters != model.parameters
            or batch.master_seed != config.master_seed
        ):
            raise MonteCarloError("combined batch identity does not match")
    return _aggregate(snapshot, config, model, paths)
