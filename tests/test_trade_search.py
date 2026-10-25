from __future__ import annotations

from dataclasses import replace

import pytest

import fantasy_football.trade_search as search_module
from fantasy_football.trade_candidates import TradeShape
from fantasy_football.trade_screening import TradeScreeningConfiguration
from fantasy_football.trade_search import (
    CandidateStatisticalStatus,
    ProgressiveSamplingConfiguration,
    ProgressiveTradeSearchConfiguration,
    ProgressiveTradeSearchError,
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
