from __future__ import annotations

from dataclasses import replace
import math

import pytest

import fantasy_football.trade_screening as screening_module
from fantasy_football.roster_value import value_roster
from fantasy_football.trade_candidates import (
    TradeShape,
    enumerate_single_trade_candidates,
)
from fantasy_football.trade_screening import (
    ScreeningFailureReason,
    TradeScreeningConfiguration,
    TradeScreeningError,
    screen_trade_candidates,
)
from tests.test_trade_candidates import _config, _snapshot, _state


def _enumeration(snapshot=None, state=None, **changes):
    snapshot = _snapshot() if snapshot is None else snapshot
    state = _state(snapshot) if state is None else state
    return enumerate_single_trade_candidates(snapshot, state, _config(**changes))


def _outcome(result, outgoing, incoming):
    return next(
        item
        for item in result.outcomes
        if item.candidate.outgoing_player_ids == outgoing
        and item.candidate.incoming_player_ids == incoming
    )


def test_disabled_screen_retains_every_feasible_candidate_with_two_sided_values() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    enumeration = _enumeration(snapshot, state)
    result = screen_trade_candidates(snapshot, state, enumeration)

    assert result.coverage.raw_combination_count == 4
    assert result.coverage.structurally_feasible_count == 4
    assert result.coverage.structurally_infeasible_count == 0
    assert result.coverage.assessed_candidate_count == 4
    assert result.coverage.retained_candidate_count == 4
    assert result.coverage.excluded_candidate_count == 0
    assert result.coverage.complete
    assert result.retained_candidate_ids == tuple(
        item.candidate.candidate_id for item in result.outcomes
    )
    assert {item.requesting_team.delta for item in result.outcomes} == {-18.0, 0.0, 3.0}
    assert {item.counterparty.delta for item in result.outcomes} == {-21.0, -3.0, 0.0}
    assert all(item.failure_reasons == () for item in result.outcomes)
    assert all(item.candidate.structural_feasible for item in result.outcomes)


def test_diagnostics_match_direct_unified_value_calls_on_completed_state() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    result = screen_trade_candidates(snapshot, state, _enumeration(snapshot, state))
    baseline_requester = value_roster(snapshot, state, 1)
    baseline_counterparty = value_roster(snapshot, state, 2)
    for outcome in result.outcomes:
        completed = outcome.candidate.completed_scenario.state
        requester_after = value_roster(snapshot, completed, 1)
        counterparty_after = value_roster(snapshot, completed, 2)
        assert outcome.requesting_team.baseline == baseline_requester
        assert outcome.counterparty.baseline == baseline_counterparty
        assert outcome.requesting_team.completed_scenario == requester_after
        assert outcome.counterparty.completed_scenario == counterparty_after
        assert outcome.requesting_team.delta == (
            requester_after.total_value - baseline_requester.total_value
        )
        assert outcome.counterparty.delta == (
            counterparty_after.total_value - baseline_counterparty.total_value
        )


def test_counterparty_and_requester_thresholds_are_independent_and_opt_in() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    enumeration = _enumeration(snapshot, state)
    counterparty = screen_trade_candidates(
        snapshot,
        state,
        enumeration,
        TradeScreeningConfiguration(True, minimum_counterparty_delta=0.0),
    )
    assert {
        (item.candidate.outgoing_player_ids, item.candidate.incoming_player_ids)
        for item in counterparty.outcomes
        if item.passes_screen
    } == {((10,), (11,)), ((1,), (11,))}
    assert counterparty.coverage.excluded_by_reason == (
        (ScreeningFailureReason.COUNTERPARTY_DELTA_BELOW_MINIMUM, 2),
    )

    requester = screen_trade_candidates(
        snapshot,
        state,
        enumeration,
        TradeScreeningConfiguration(True, minimum_requester_delta=0.0),
    )
    assert requester.coverage.retained_candidate_count == 3
    assert _outcome(requester, (1,), (11,)).failure_reasons == (
        ScreeningFailureReason.REQUESTER_DELTA_BELOW_MINIMUM,
    )
    assert _outcome(requester, (10,), (11,)).passes_screen


def test_nonnegative_convenience_and_combined_failures_reconcile_without_double_counting() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    enumeration = _enumeration(snapshot, state)
    convenient = screen_trade_candidates(
        snapshot,
        state,
        enumeration,
        TradeScreeningConfiguration(True, require_nonnegative_counterparty_delta=True),
    )
    explicit = screen_trade_candidates(
        snapshot,
        state,
        enumeration,
        TradeScreeningConfiguration(True, minimum_counterparty_delta=0.0),
    )
    assert convenient.retained_candidate_ids == explicit.retained_candidate_ids

    combined = screen_trade_candidates(
        snapshot,
        state,
        enumeration,
        TradeScreeningConfiguration(
            True,
            minimum_requester_delta=4.0,
            minimum_counterparty_delta=0.0,
        ),
    )
    assert combined.coverage.retained_candidate_count == 0
    assert combined.coverage.excluded_candidate_count == 4
    assert combined.coverage.excluded_by_reason == (
        (ScreeningFailureReason.COUNTERPARTY_DELTA_BELOW_MINIMUM, 2),
        (ScreeningFailureReason.REQUESTER_DELTA_BELOW_MINIMUM, 4),
    )
    assert combined.coverage.reason_counts_overlap is True
    assert sum(count for _, count in combined.coverage.excluded_by_reason) == 6


def test_threshold_equality_and_next_float_are_not_rounded() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    enumeration = _enumeration(snapshot, state)
    equal = screen_trade_candidates(
        snapshot,
        state,
        enumeration,
        TradeScreeningConfiguration(True, minimum_requester_delta=3.0),
    )
    above = screen_trade_candidates(
        snapshot,
        state,
        enumeration,
        TradeScreeningConfiguration(
            True, minimum_requester_delta=math.nextafter(3.0, math.inf)
        ),
    )
    assert equal.coverage.retained_candidate_count == 2
    assert above.coverage.retained_candidate_count == 0


@pytest.mark.parametrize(
    "configuration,match",
    (
        (TradeScreeningConfiguration(False, minimum_requester_delta=0.0), "enabled=True"),
        (TradeScreeningConfiguration(True, minimum_requester_delta=math.nan), "finite"),
        (TradeScreeningConfiguration(True, minimum_counterparty_delta=math.inf), "finite"),
        (TradeScreeningConfiguration(True, minimum_requester_delta=True), "finite"),
        (
            TradeScreeningConfiguration(
                True,
                minimum_counterparty_delta=0.0,
                require_nonnegative_counterparty_delta=True,
            ),
            "conflicts",
        ),
    ),
)
def test_invalid_or_conflicting_screening_configuration_fails(configuration, match) -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    with pytest.raises(TradeScreeningError, match=match):
        screen_trade_candidates(snapshot, state, _enumeration(snapshot, state), configuration)


def test_asymmetric_multi_partner_completion_and_shared_pool_effects_are_included() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    enumeration = _enumeration(
        snapshot,
        state,
        counterparties=(2, 3),
        universe=(1, 2, 3, 10, 11, 12),
        shapes=(TradeShape(1, 2), TradeShape(2, 1)),
    )
    result = screen_trade_candidates(snapshot, state, enumeration)
    assert result.coverage.assessed_candidate_count == len(enumeration.candidates)
    assert {item.candidate.counterparty_team_id for item in result.outcomes} == {2, 3}
    assert any(item.candidate.completed_scenario.forced_drops for item in result.outcomes)
    assert any(item.candidate.completed_scenario.automatic_additions for item in result.outcomes)
    for outcome in result.outcomes:
        assert outcome.requesting_team.completed_scenario == value_roster(
            snapshot, outcome.candidate.completed_scenario.state, 1
        )


def test_reordered_candidate_input_is_normalized_and_inputs_are_immutable() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    enumeration = _enumeration(snapshot, state)
    reordered = replace(enumeration, candidates=tuple(reversed(enumeration.candidates)))
    original_snapshot = snapshot
    original_state = state
    original_enumeration = enumeration
    first = screen_trade_candidates(snapshot, state, enumeration)
    second = screen_trade_candidates(snapshot, state, reordered)
    assert first == second
    assert snapshot == original_snapshot
    assert state == original_state
    assert enumeration == original_enumeration


def test_mismatched_baseline_and_completed_scenario_provenance_fail_closed() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    enumeration = _enumeration(snapshot, state)
    with pytest.raises(TradeScreeningError, match="baseline state identity"):
        screen_trade_candidates(
            snapshot,
            replace(state, assumption_ids=state.assumption_ids + ("different",)),
            enumeration,
        )
    candidate = enumeration.candidates[0]
    inconsistent = replace(
        candidate,
        completed_scenario=replace(candidate.completed_scenario, explicit_changes=()),
    )
    with pytest.raises(TradeScreeningError, match="provenance is inconsistent"):
        screen_trade_candidates(
            snapshot,
            state,
            replace(enumeration, candidates=(inconsistent,) + enumeration.candidates[1:]),
        )


def test_baseline_values_are_cached_once_per_participant(monkeypatch) -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    enumeration = _enumeration(snapshot, state)
    original = screening_module.value_roster
    calls = []

    def counted(snapshot_arg, state_arg, team_id):
        calls.append((id(state_arg), team_id))
        return original(snapshot_arg, state_arg, team_id)

    monkeypatch.setattr(screening_module, "value_roster", counted)
    screen_trade_candidates(snapshot, state, enumeration)
    baseline_calls = [item for item in calls if item[0] == id(state)]
    assert sorted(team_id for _, team_id in baseline_calls) == [1, 2]
    assert len(calls) == 2 + 2 * len(enumeration.candidates)


def test_incomplete_value_fails_instead_of_becoming_screen_rejection(monkeypatch) -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    enumeration = _enumeration(snapshot, state)
    original = screening_module.value_roster

    def incomplete(snapshot_arg, state_arg, team_id):
        result = original(snapshot_arg, state_arg, team_id)
        return replace(result, is_complete=False, unresolved_inputs=("fixture unresolved",))

    monkeypatch.setattr(screening_module, "value_roster", incomplete)
    with pytest.raises(TradeScreeningError, match=r"V\(R\) is incomplete"):
        screen_trade_candidates(snapshot, state, enumeration)


def test_screening_is_offline_and_never_reclassifies_structural_legality(monkeypatch) -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    enumeration = _enumeration(snapshot, state)

    def no_network(*_args, **_kwargs):
        raise AssertionError("trade screening attempted network access")

    monkeypatch.setattr("socket.create_connection", no_network)
    result = screen_trade_candidates(
        snapshot,
        state,
        enumeration,
        TradeScreeningConfiguration(True, minimum_requester_delta=1000.0),
    )
    assert result.coverage.retained_candidate_count == 0
    assert result.coverage.structurally_feasible_count == len(result.outcomes) == 4
    assert all(item.candidate.structural_feasible for item in result.outcomes)


def test_independent_screening_oracle_matches_threshold_result() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    enumeration = _enumeration(snapshot, state)
    requester_minimum = 0.0
    counterparty_minimum = -4.0
    expected = set()
    baseline_requester = value_roster(snapshot, state, 1).total_value
    baseline_counterparty = value_roster(snapshot, state, 2).total_value
    for candidate in enumeration.candidates:
        completed = candidate.completed_scenario.state
        requester_delta = value_roster(snapshot, completed, 1).total_value - baseline_requester
        counterparty_delta = (
            value_roster(snapshot, completed, 2).total_value - baseline_counterparty
        )
        if requester_delta >= requester_minimum and counterparty_delta >= counterparty_minimum:
            expected.add(candidate.candidate_id)
    result = screen_trade_candidates(
        snapshot,
        state,
        enumeration,
        TradeScreeningConfiguration(
            True,
            minimum_requester_delta=requester_minimum,
            minimum_counterparty_delta=counterparty_minimum,
        ),
    )
    assert set(result.retained_candidate_ids) == expected
    assert result.coverage.assessed_candidate_count == 4
    assert result.coverage.retained_candidate_count + result.coverage.excluded_candidate_count == 4
