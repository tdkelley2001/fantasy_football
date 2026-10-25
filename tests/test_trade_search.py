from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

import fantasy_football.trade_search as search_module
from fantasy_football.trade_candidates import TradeShape
from fantasy_football.trade_screening import TradeScreeningConfiguration
from fantasy_football.trade_search import (
    CandidateStatisticalStatus,
    ProgressiveSamplingConfiguration,
    ProgressiveTradeSearchConfiguration,
    ProgressiveTradeSearchError,
    SearchProgressStage,
    SearchStopReason,
    run_progressive_trade_search,
)
from tests.test_monte_carlo import PrescribedModel
from tests.test_scenario_evaluator import _config as _simulation
from tests.test_trade_candidates import _config, _snapshot, _state


def _search(
    *,
    initial=1,
    batch=1,
    maximum=1,
    finalists=1,
    budget=None,
    target=0.01,
    screening=TradeScreeningConfiguration(),
    candidate=None,
):
    return ProgressiveTradeSearchConfiguration(
        _config() if candidate is None else candidate,
        screening,
        ProgressiveSamplingConfiguration(
            0.95, target, initial, batch, maximum, finalists, budget
        ),
    )


def _run(configuration=None, *, simulation=None):
    snapshot = _snapshot()
    state = _state(snapshot)
    configuration = _search() if configuration is None else configuration
    maximum = configuration.sampling.maximum_paths_per_state
    return run_progressive_trade_search(
        snapshot,
        state,
        configuration,
        _simulation(maximum) if simulation is None else simulation,
        PrescribedModel(),
    )


def test_complete_initial_stage_evaluates_every_state_and_all_teams() -> None:
    result = _run()
    assert result.coverage.raw_candidate_combinations == 4
    assert result.coverage.structurally_feasible_candidates == 4
    assert result.coverage.screen_retained_candidates == 4
    assert result.coverage.eligible_unique_states == 4
    assert result.coverage.initially_evaluated_states == 4
    assert result.coverage.unevaluated_states == 0
    assert result.coverage.candidate_coverage_complete
    assert all(item.comparison is not None for item in result.state_evaluations)
    assert all(len(item.comparison.teams) == len(_snapshot().teams) for item in result.state_evaluations)
    assert all(item.rank is not None for item in result.candidates)


def test_screening_disabled_preserves_all_and_enabled_applies_only_explicit_rule() -> None:
    disabled = _run()
    enabled = _run(
        _search(
            screening=TradeScreeningConfiguration(
                True, minimum_counterparty_delta=0.0
            )
        )
    )
    assert disabled.coverage.screen_retained_candidates == 4
    assert enabled.coverage.screen_retained_candidates == 2
    assert all(item.passes_screen for item in enabled.candidates)
    assert disabled.coverage.raw_candidate_combinations == enabled.coverage.raw_candidate_combinations


def test_initial_state_budget_is_explicitly_partial_and_never_fabricates_estimates() -> None:
    result = _run(_search(budget=2))
    assert result.stop_reason is SearchStopReason.INITIAL_STATE_BUDGET_REACHED
    assert result.coverage.initially_evaluated_states == 2
    assert result.coverage.unevaluated_states == 2
    assert not result.coverage.candidate_coverage_complete
    assert not result.coverage.statistical_precision_complete
    unevaluated = [
        item
        for item in result.candidates
        if item.statistical_status is CandidateStatisticalStatus.NOT_EVALUATED
    ]
    assert len(unevaluated) == 2
    assert all(item.rank is None for item in unevaluated)
    assert all(item.requester_championship_difference is None for item in unevaluated)


def test_refinement_extends_path_coverage_without_duplicate_path_ids() -> None:
    result = _run(_search(initial=1, batch=1, maximum=3, finalists=1))
    assert result.coverage.monte_carlo_baseline_paths_computed == 3
    assert result.coverage.monte_carlo_scenario_paths_computed == 12
    assert result.coverage.refined_states == 4
    for item in result.state_evaluations:
        assert item.completed_paths == 3
        assert item.comparison is not None
        assert item.comparison.baseline.batch.path_indices == (0, 1, 2)
        assert item.comparison.hypothetical.batch.path_indices == (0, 1, 2)
        assert len(set(item.comparison.hypothetical.batch.path_indices)) == 3
        assert item.status is CandidateStatisticalStatus.MAXIMUM_PATHS_REACHED


def test_uncertainty_keeps_weak_initial_candidates_plausibly_competitive() -> None:
    result = _run(_search(initial=1, batch=1, maximum=2, finalists=1))
    initial_values = {
        item.requester_championship_difference
        for item in result.candidates
        if item.requester_championship_difference is not None
    }
    assert min(initial_values) < max(initial_values)
    assert len(result.finalist_state_ids) == result.coverage.eligible_unique_states
    assert all(item.selected_for_refinement for item in result.state_evaluations)


def test_data_selected_leader_uses_all_pair_all_look_multiplicity(monkeypatch) -> None:
    observed_counts = []
    real = search_module.paired_championship_difference

    def observed(*args, **kwargs):
        observed_counts.append(kwargs["simultaneous_comparison_count"])
        return real(*args, **kwargs)

    monkeypatch.setattr(search_module, "paired_championship_difference", observed)
    result = _run(_search(initial=1, batch=1, maximum=3, finalists=1))

    # Four possible states give six unordered pairs. Three planned looks protect
    # the family containing every pair at every possible selection/refinement look.
    assert observed_counts
    assert set(observed_counts) == {18}
    assert len(result.competitive_state_ids) > 1


def test_ranking_resolution_is_separate_from_all_team_precision(monkeypatch) -> None:
    monkeypatch.setattr(search_module, "_all_team_precision", lambda *_args: True)
    result = _run(_search(initial=1, batch=1, maximum=1, finalists=1))

    assert result.coverage.statistical_precision_complete
    assert not result.coverage.ranking_resolved
    assert len(result.competitive_state_ids) > 1
    assert result.stop_reason is SearchStopReason.FINALIST_REFINEMENT_COMPLETE


def test_precision_complete_candidate_remains_competitive_with_unequal_coverage(
    monkeypatch,
) -> None:
    precise_scenario = None
    compared_path_counts = []
    real_difference = search_module.paired_championship_difference

    def selective_precision(comparison, _target):
        nonlocal precise_scenario
        scenario_id = comparison.hypothetical.batch.simulation_config_sha256
        if precise_scenario is None:
            precise_scenario = scenario_id
        return scenario_id == precise_scenario

    def observe_overlap(left, right, **kwargs):
        assert left.path_indices == right.path_indices
        compared_path_counts.append(
            (
                left.simulation_config_sha256,
                right.simulation_config_sha256,
                len(left.path_indices),
            )
        )
        return real_difference(left, right, **kwargs)

    monkeypatch.setattr(search_module, "_all_team_precision", selective_precision)
    monkeypatch.setattr(
        search_module, "paired_championship_difference", observe_overlap
    )
    result = _run(_search(initial=1, batch=1, maximum=3, finalists=1))

    precise = [
        item
        for item in result.state_evaluations
        if item.comparison is not None
        and item.comparison.hypothetical.batch.simulation_config_sha256
        == precise_scenario
    ]
    assert len(precise) == 1
    assert precise[0].completed_paths == 1
    assert precise[0].statistically_competitive
    assert any(item.completed_paths == 3 for item in result.state_evaluations)
    precise_comparisons = [
        count
        for left_id, right_id, count in compared_path_counts
        if precise_scenario in (left_id, right_id)
    ]
    assert precise_comparisons
    assert set(precise_comparisons) == {1}
    assert len(result.competitive_state_ids) > 1
    assert not result.coverage.ranking_resolved


def test_ranking_resolves_only_after_all_competitors_are_excluded(monkeypatch) -> None:
    real_difference = search_module.paired_championship_difference

    def exclude_nonleaders(*args, **kwargs):
        result = real_difference(*args, **kwargs)
        return replace(
            result,
            interval=replace(result.interval, upper=-0.01),
        )

    monkeypatch.setattr(
        search_module, "paired_championship_difference", exclude_nonleaders
    )
    monkeypatch.setattr(search_module, "_all_team_precision", lambda *_args: True)
    result = _run(_search(initial=1, batch=1, maximum=2, finalists=1))

    assert result.coverage.candidate_coverage_complete
    assert result.coverage.ranking_resolved
    assert len(result.competitive_state_ids) == 1
    assert sum(item.statistically_competitive for item in result.state_evaluations) == 1
    assert result.stop_reason is SearchStopReason.PRECISION_REACHED


def test_progress_snapshots_are_immutable_coherent_and_provisional() -> None:
    observed = []
    snapshot = _snapshot()
    state = _state(snapshot)
    configuration = _search(initial=1, batch=1, maximum=2, finalists=1)
    result = run_progressive_trade_search(
        snapshot,
        state,
        configuration,
        _simulation(2),
        PrescribedModel(),
        progress_observer=observed.append,
    )

    assert tuple(observed) == result.progress_snapshots
    assert observed[0].stage is SearchProgressStage.CANDIDATES_READY
    assert observed[0].initially_evaluated_states == 0
    assert not observed[0].candidate_coverage_complete
    initial = [item for item in observed if item.stage is SearchProgressStage.INITIAL_EVALUATION]
    assert [item.initially_evaluated_states for item in initial] == [1, 2, 3, 4]
    assert all(not item.ranking_resolved for item in initial[:-1])
    assert any(item.stage is SearchProgressStage.REFINEMENT for item in observed)
    assert observed[-1].stage is SearchProgressStage.FINAL
    assert observed[-1].stop_reason is result.stop_reason
    assert observed[-1].ranking_resolved is result.coverage.ranking_resolved
    assert all(
        len(item.estimates) == item.initially_evaluated_states for item in observed
    )
    with pytest.raises(FrozenInstanceError):
        observed[-1].ranking_resolved = True


def test_equivalent_paths_share_initial_and_refined_evaluations(monkeypatch) -> None:
    candidate = _config(
        counterparties=(2, 3, 4),
        universe=(1, 2, 3, 4, 10, 11, 12, 13),
        shapes=(
            TradeShape(1, 1),
            TradeShape(1, 2),
            TradeShape(2, 1),
            TradeShape(2, 2),
        ),
    )
    calls = 0
    real = search_module._run_batch

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(search_module, "_run_batch", counted)
    result = _run(_search(candidate=candidate))
    assert result.coverage.screen_retained_candidates == 27
    assert result.coverage.eligible_unique_states == 25
    assert result.coverage.candidate_evaluations_avoided_by_state_deduplication == 2
    assert calls == 26  # one shared baseline plus one scenario per unique state
    grouped = {}
    for item in result.candidates:
        grouped.setdefault(item.completed_state_sha256, []).append(item)
    shared = next(values for values in grouped.values() if len(values) > 1)
    assert len({item.state_evaluation_sha256 for item in shared}) == 1


def test_reordered_candidate_inputs_have_identical_results() -> None:
    first = _run(
        _search(
            candidate=_config(
                counterparties=(3, 2), universe=(12, 2, 10, 3, 1, 11)
            )
        )
    )
    second = _run(
        _search(
            candidate=_config(
                counterparties=(2, 3), universe=(1, 2, 3, 10, 11, 12)
            )
        )
    )
    assert first.search_sha256 == second.search_sha256
    assert first.state_evaluations == second.state_evaluations
    assert first.candidates == second.candidates
    assert first.coverage == second.coverage


def test_rank_is_requester_championship_delta_not_screening_attractiveness() -> None:
    result = _run()
    values = [
        item.requester_championship_difference
        for item in result.candidates
        if item.rank is not None
    ]
    assert values == sorted(values, reverse=True)
    assert any(item.screening_outcome.counterparty.delta < 0 for item in result.candidates)


@pytest.mark.parametrize(
    "sampling,match",
    (
        (ProgressiveSamplingConfiguration(1.0, 0.1, 1, 1, 2, 1), "confidence_level"),
        (ProgressiveSamplingConfiguration(0.95, 0.0, 1, 1, 2, 1), "target"),
        (ProgressiveSamplingConfiguration(0.95, 0.1, 0, 1, 2, 1), "initial_paths"),
        (ProgressiveSamplingConfiguration(0.95, 0.1, 3, 1, 2, 1), "cannot exceed"),
        (ProgressiveSamplingConfiguration(0.95, 0.1, 1, 1, 2, 1, 0), "budget"),
    ),
)
def test_invalid_progressive_configuration_fails(sampling, match) -> None:
    with pytest.raises(ProgressiveTradeSearchError, match=match):
        _run(ProgressiveTradeSearchConfiguration(_config(), TradeScreeningConfiguration(), sampling))


def test_different_seed_precision_and_budget_change_search_identity() -> None:
    base = _run()
    seed = _run(simulation=replace(_simulation(1), master_seed=99))
    precision = _run(_search(target=0.02))
    budget = _run(_search(budget=2))
    assert base.search_sha256 != seed.search_sha256
    assert base.search_sha256 != precision.search_sha256
    assert base.search_sha256 != budget.search_sha256


def test_inputs_are_immutable_and_execution_is_offline(monkeypatch) -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    configuration = _search()
    before = (snapshot, state, configuration)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    run_progressive_trade_search(
        snapshot, state, configuration, _simulation(1), PrescribedModel()
    )
    assert (snapshot, state, configuration) == before
