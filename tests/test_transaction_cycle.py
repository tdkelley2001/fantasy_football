from __future__ import annotations

from dataclasses import replace

import pytest

from fantasy_football.evolving_state import IRPolicy, initialize_evolving_state
from fantasy_football.transaction_cycle import (
    CycleReferenceError,
    compare_sequential_to_feasible,
    enumerate_feasible_cycles,
    execute_sequential_policy_reference,
    validate_operational_policy_equivalence,
)
from fantasy_football.weekly_transactions import (
    WaiverBoundaryPolicy,
    WeeklyTransactionPolicy,
)
from tests.test_roster_value import _overlap_snapshot, _valuation_snapshot
from tests.test_weekly_transactions import _staff_team_one


def _state(snapshot):
    return initialize_evolving_state(
        snapshot, scoring_week=15, ir_policy=IRPolicy.PROJECTION_BASED
    )


def _effect(state):
    return (
        state.roster_entries,
        state.availability,
        state.current_waiver_priority,
        state.initial_window_waiver_priority,
        state.season_acquisition_counts,
        state.matchup_acquisition_counts,
        state.ledger,
    )


def test_exhaustive_cycle_contains_pass_and_contested_ownership_outcomes() -> None:
    snapshot = _valuation_snapshot(competing_teams=2, pool_values=(8.0,))
    state = _state(snapshot)
    result = enumerate_feasible_cycles(snapshot, state, WeeklyTransactionPolicy())
    assert result.complete
    assert result.completed_paths == len(result.terminals)
    assert result.completed_paths == result.unique_terminal_effects
    assert result.unique_terminal_effects >= 2
    assert result.pass_branches > 0
    assert result.legal_acquisition_branches > 0
    owners = {
        next(
            (
                entry.team_id
                for entry in terminal.state.roster_entries
                if entry.player_id == -300
            ),
            None,
        )
        for terminal in result.terminals
    }
    assert {None, 1, 2, 3}.intersection(owners) == owners
    assert None in owners and len(owners - {None}) >= 2
    for terminal in result.terminals:
        player_ids = tuple(entry.player_id for entry in terminal.state.roster_entries)
        assert len(player_ids) == len(set(player_ids))


def test_sequential_reference_matches_operational_free_agent_policy() -> None:
    snapshot = _valuation_snapshot(competing_teams=2, pool_values=(8.0, 6.0))
    state = _state(snapshot)
    comparison = validate_operational_policy_equivalence(
        snapshot, state, WeeklyTransactionPolicy()
    )
    assert comparison.equivalent, comparison.mismatches
    assert comparison.reference.state.ledger == comparison.operational.state.ledger
    assert (
        comparison.reference.state.current_waiver_priority
        == state.current_waiver_priority
    )


def test_sequential_reference_matches_dynamic_waiver_priority() -> None:
    snapshot = _valuation_snapshot(competing_teams=2, pool_values=(8.0,))
    snapshot = _staff_team_one(
        replace(
            snapshot,
            players=tuple(
                replace(player, acquisition_status="WAIVERS")
                if player.player_id == -300
                else player
                for player in snapshot.players
            ),
        )
    )
    policy = WeeklyTransactionPolicy(WaiverBoundaryPolicy.MODELED_WEEKLY_V1)
    comparison = validate_operational_policy_equivalence(
        snapshot, _state(snapshot), policy
    )
    assert comparison.equivalent, comparison.mismatches
    assert comparison.reference.state.current_waiver_priority == (1, 3, 4, 2)
    assert comparison.reference.state.initial_window_waiver_priority == (1, 2, 3, 4)


def test_multiple_pass_reference_matches_operational_overlap() -> None:
    snapshot = _overlap_snapshot()
    comparison = validate_operational_policy_equivalence(
        snapshot, _state(snapshot), WeeklyTransactionPolicy()
    )
    assert comparison.equivalent, comparison.mismatches
    assert comparison.reference.free_agent_passes == 3
    assert (
        sum(
            record.action.value == "add" for record in comparison.reference.state.ledger
        )
        == 2
    )


def test_cache_enabled_and_disabled_exact_results_agree() -> None:
    snapshot = _valuation_snapshot(competing_teams=1, pool_values=(8.0,))
    state = _state(snapshot)
    cached = enumerate_feasible_cycles(
        snapshot, state, WeeklyTransactionPolicy(), use_plan_cache=True
    )
    uncached = enumerate_feasible_cycles(
        snapshot, state, WeeklyTransactionPolicy(), use_plan_cache=False
    )
    assert tuple(_effect(item.state) for item in cached.terminals) == tuple(
        _effect(item.state) for item in uncached.terminals
    )
    assert cached.completed_paths == uncached.completed_paths
    assert cached.unique_terminal_effects == uncached.unique_terminal_effects


def test_sequential_result_is_member_of_feasible_terminal_set() -> None:
    snapshot = _valuation_snapshot(competing_teams=1, pool_values=(8.0,))
    state = _state(snapshot)
    feasible = enumerate_feasible_cycles(snapshot, state, WeeklyTransactionPolicy())
    sequential = execute_sequential_policy_reference(
        snapshot, state, WeeklyTransactionPolicy()
    )
    assert _effect(sequential.state) in {
        _effect(item.state) for item in feasible.terminals
    }
    assert all(item.team_roster_values for item in feasible.terminals)
    comparison = compare_sequential_to_feasible(feasible, sequential)
    assert comparison.sequential_terminal_is_feasible
    assert comparison.feasible_path_count == feasible.completed_paths
    assert comparison.sequential_team_values
    assert all(low <= high for _, low, high in comparison.team_value_ranges)


def test_unknown_boundary_rejected_and_no_network(monkeypatch) -> None:
    snapshot = _valuation_snapshot(pool_values=(8.0,))
    state = _state(snapshot)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("cycle references must not call ESPN")

    monkeypatch.setattr("fantasy_football.espn_adapter.fetch_and_translate", forbidden)
    comparison = validate_operational_policy_equivalence(
        snapshot, state, WeeklyTransactionPolicy()
    )
    assert comparison.equivalent
    with pytest.raises(CycleReferenceError, match="unsupported waiver boundary"):
        enumerate_feasible_cycles(
            snapshot,
            state,
            WeeklyTransactionPolicy(waiver_boundary="arbitrary"),  # type: ignore[arg-type]
        )
    assert state.ledger == ()


def test_reordered_state_produces_same_sequential_terminal() -> None:
    snapshot = _valuation_snapshot(competing_teams=1, pool_values=(8.0, 6.0))
    state = _state(snapshot)
    reordered = replace(
        state,
        roster_entries=tuple(reversed(state.roster_entries)),
        availability=tuple(reversed(state.availability)),
    )
    first = execute_sequential_policy_reference(
        snapshot, state, WeeklyTransactionPolicy()
    )
    second = execute_sequential_policy_reference(
        snapshot, reordered, WeeklyTransactionPolicy()
    )
    assert _effect(first.state) == _effect(second.state)
