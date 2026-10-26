from __future__ import annotations

import json
from dataclasses import replace

import pytest

from fantasy_football.search_orchestration import (
    OrchestrationStage,
    OrchestrationStopReason,
    SearchEvaluationMode,
    SearchExecutionMode,
    SearchExportConfiguration,
    SearchOrchestrationConfiguration,
    SearchOrchestrationError,
    SearchPreflightConfiguration,
    SearchResourceConfiguration,
    execute_search_orchestration,
)
from fantasy_football.trade_candidates import TradeShape
from fantasy_football.trade_search import ProgressiveSamplingConfiguration
from fantasy_football.trade_search import (
    ProgressiveTradeSearchConfiguration,
    run_progressive_trade_search,
)
from fantasy_football.trade_screening import TradeScreeningConfiguration
from fantasy_football.unified_actions import (
    ActionFamily,
    ActionOrdering,
    UnifiedActionSearchConfiguration,
)
from tests.test_scenario_evaluator import (
    PrescribedModel,
    _config as simulation_config,
    _scenario_snapshot_with_bench,
)
from tests.test_unified_actions import _state
from tests.test_trade_candidates import _config as accepted_trade_config
from tests.test_trade_candidates import _snapshot as accepted_trade_snapshot
from tests.test_trade_candidates import _state as accepted_trade_state


def _candidate_search() -> UnifiedActionSearchConfiguration:
    return UnifiedActionSearchConfiguration(
        requesting_team_id=1,
        action_families=(ActionFamily.TRADE, ActionFamily.ACQUISITION),
        action_orderings=(
            ActionOrdering.STANDALONE_TRADE,
            ActionOrdering.STANDALONE_ACQUISITION,
        ),
        counterparty_team_ids=(2,),
        tradeable_player_ids=(1, 2, 10, 11),
        acquisition_player_ids=(-101,),
        eligible_drop_player_ids=(10,),
        trade_shapes=(TradeShape(1, 1),),
        maximum_total_action_count=2,
    )


def _configuration(mode=SearchExecutionMode.SEQUENTIAL_REFERENCE, **resource_changes):
    resources = SearchResourceConfiguration(mode, 1, 1, 2)
    resources = replace(resources, **resource_changes)
    return SearchOrchestrationConfiguration(
        _candidate_search(),
        SearchEvaluationMode.PROGRESSIVE,
        ProgressiveSamplingConfiguration(0.95, 0.99, 1, 1, 2, 1),
        resources,
    )


def _run(configuration):
    snapshot = _scenario_snapshot_with_bench()
    return execute_search_orchestration(
        snapshot,
        _state(snapshot),
        configuration,
        simulation_config(2),
        PrescribedModel(),
    )


def test_reference_and_bounded_modes_have_exact_candidate_and_state_parity() -> None:
    reference = _run(_configuration())
    bounded = _run(_configuration(SearchExecutionMode.BOUNDED_OVERLAP))
    assert tuple(item.candidate_id for item in reference.candidates) == tuple(
        item.candidate_id for item in bounded.candidates
    )
    assert tuple(item.completed_state_sha256 for item in reference.candidates) == tuple(
        item.completed_state_sha256 for item in bounded.candidates
    )
    assert reference.progressive_evaluation == bounded.progressive_evaluation
    assert reference.candidate_coverage_complete
    assert bounded.candidate_coverage_complete


def test_multiple_numerical_workers_preserve_path_indexed_results() -> None:
    sequential = _run(_configuration())
    parallel = _run(_configuration(
        SearchExecutionMode.BOUNDED_OVERLAP,
        worker_count=2,
        maximum_in_flight_states=1,
    ))
    assert sequential.progressive_evaluation is not None
    assert parallel.progressive_evaluation is not None
    left = {
        item.completed_state_sha256: (
            item.completed_paths,
            None if item.comparison is None else item.comparison.baseline.batch.paths,
            None if item.comparison is None else item.comparison.hypothetical.batch.paths,
        ) for item in sequential.progressive_evaluation.state_evaluations
    }
    right = {
        item.completed_state_sha256: (
            item.completed_paths,
            None if item.comparison is None else item.comparison.baseline.batch.paths,
            None if item.comparison is None else item.comparison.hypothetical.batch.paths,
        ) for item in parallel.progressive_evaluation.state_evaluations
    }
    assert left == right


def test_candidate_and_evaluation_limits_are_disclosed() -> None:
    candidate_limited = _run(_configuration(candidate_limit=2))
    bounded_limited = _run(_configuration(
        SearchExecutionMode.BOUNDED_OVERLAP, candidate_limit=2
    ))
    assert len(candidate_limited.candidates) == 2
    assert tuple(item.candidate_id for item in candidate_limited.candidates) == tuple(
        item.candidate_id for item in bounded_limited.candidates
    )
    assert not candidate_limited.candidate_coverage_complete
    assert candidate_limited.stop_reason is OrchestrationStopReason.CANDIDATE_LIMIT

    evaluation_limited = _run(_configuration(evaluation_state_limit=1))
    assert evaluation_limited.progressive_evaluation is not None
    assert not evaluation_limited.progressive_evaluation.candidate_coverage_complete
    assert not evaluation_limited.ranking_resolved


def test_progress_is_immutable_coherent_and_does_not_claim_percentages() -> None:
    observed = []
    snapshot = _scenario_snapshot_with_bench()
    result = execute_search_orchestration(
        snapshot,
        _state(snapshot),
        _configuration(),
        simulation_config(2),
        PrescribedModel(),
        progress_observer=observed.append,
    )
    assert tuple(observed) == result.progress
    assert result.progress[-1].stop_reason is result.stop_reason
    assert result.progress[-1].candidates_retained == len(result.candidates)
    with pytest.raises(Exception):
        result.progress[-1].candidates_retained = 0


def test_json_and_csv_exports_include_all_and_filtered_scopes(tmp_path) -> None:
    all_result = _run(replace(
        _configuration(),
        export=SearchExportConfiguration(str(tmp_path), True, True),
    ))
    assert len(all_result.export_paths) == 2
    payload = json.loads((tmp_path / "m5_8_search_results.json").read_text())
    assert payload["schema_version"] == 1
    assert payload["scope"] == "all"
    assert len(payload["candidates"]) == len(all_result.candidates)
    assert payload["state_evaluations"]
    assert {
        team["team_id"]
        for evaluation in payload["state_evaluations"]
        for team in evaluation["teams"]
    } == {1, 2, 3, 4}

    selected = all_result.candidates[0].candidate_id
    filtered = _run(replace(
        _configuration(),
        export=SearchExportConfiguration(str(tmp_path), True, False, (selected,)),
    ))
    filtered_payload = json.loads((tmp_path / "m5_8_search_results.json").read_text())
    assert filtered_payload["scope"] == "filtered"
    assert [item["candidate_id"] for item in filtered_payload["candidates"]] == [selected]
    assert {
        item["completed_state_sha256"]
        for item in filtered_payload["state_evaluations"]
    } == {filtered.candidates[0].completed_state_sha256}
    assert filtered.run_sha256 == all_result.run_sha256


def test_optional_preflight_reports_measured_not_invented_values() -> None:
    without = _run(_configuration())
    assert without.preflight is None
    with_preflight = _run(replace(
        _configuration(),
        preflight=SearchPreflightConfiguration(True, 2, 1),
    ))
    assert with_preflight.preflight is not None
    assert with_preflight.preflight.candidate_sample_count <= 2
    assert with_preflight.preflight.candidate_seconds >= 0
    assert with_preflight.preflight.peak_traced_bytes > 0


def test_fixed_mode_remains_available_without_progressive_ranking_claim() -> None:
    configuration = replace(
        _configuration(),
        evaluation_mode=SearchEvaluationMode.FIXED,
        sampling=ProgressiveSamplingConfiguration(0.95, 0.99, 1, 1, 2, 1),
    )
    result = _run(configuration)
    assert result.fixed_evaluation is not None
    assert result.progressive_evaluation is None
    assert not result.ranking_resolved
    assert all(item.evaluated_paths == 2 for item in result.candidates)


@pytest.mark.parametrize(
    "resources, message",
    [
        (SearchResourceConfiguration(queue_capacity=0), "queue_capacity"),
        (SearchResourceConfiguration(candidate_limit=0), "candidate_limit"),
        (SearchResourceConfiguration(wall_clock_seconds=0), "wall_clock_seconds"),
    ],
)
def test_invalid_resources_fail_before_search(resources, message) -> None:
    with pytest.raises(SearchOrchestrationError, match=message):
        _run(replace(_configuration(), resources=resources))


def test_reordered_candidate_inputs_preserve_statistical_results() -> None:
    original = _run(_configuration())
    search = replace(
        _candidate_search(),
        counterparty_team_ids=tuple(reversed(_candidate_search().counterparty_team_ids)),
        tradeable_player_ids=tuple(reversed(_candidate_search().tradeable_player_ids)),
    )
    reordered = _run(replace(_configuration(), candidate_search=search))
    assert original.candidates == reordered.candidates
    assert original.progressive_evaluation == reordered.progressive_evaluation
    assert original.run_sha256 == reordered.run_sha256


def test_progress_reports_initial_and_refinement_evaluation_stages() -> None:
    result = _run(_configuration())
    stages = tuple(item.stage for item in result.progress)
    assert OrchestrationStage.INITIAL_EVALUATION in stages
    assert OrchestrationStage.PROGRESSIVE_REFINEMENT in stages


def test_generic_progressive_state_evaluation_matches_accepted_m54_trade_policy() -> None:
    snapshot = accepted_trade_snapshot()
    state = accepted_trade_state(snapshot)
    sampling = ProgressiveSamplingConfiguration(0.95, 0.99, 1, 1, 2, 1)
    accepted = run_progressive_trade_search(
        snapshot,
        state,
        ProgressiveTradeSearchConfiguration(
            accepted_trade_config(), TradeScreeningConfiguration(), sampling
        ),
        simulation_config(2),
        PrescribedModel(),
    )
    trade_config = accepted_trade_config()
    unified = UnifiedActionSearchConfiguration(
        trade_config.requesting_team_id,
        (ActionFamily.TRADE,),
        (ActionOrdering.STANDALONE_TRADE,),
        trade_config.counterparty_team_ids,
        trade_config.player_universe_ids,
        trade_shapes=trade_config.trade_shapes,
        maximum_total_action_count=1,
    )
    generic = execute_search_orchestration(
        snapshot,
        state,
        SearchOrchestrationConfiguration(
            unified, SearchEvaluationMode.PROGRESSIVE, sampling
        ),
        simulation_config(2),
        PrescribedModel(),
    )
    assert generic.progressive_evaluation is not None
    accepted_by_state = {
        item.completed_state_sha256: item.comparison
        for item in accepted.state_evaluations
    }
    generic_by_state = {
        item.completed_state_sha256: item.comparison
        for item in generic.progressive_evaluation.state_evaluations
    }
    assert generic_by_state == accepted_by_state
    assert generic.progressive_evaluation.competitive_state_ids == accepted.competitive_state_ids
    assert generic.progressive_evaluation.ranking_resolved == accepted.coverage.ranking_resolved
