from __future__ import annotations

from dataclasses import replace

import pytest

from fantasy_football.canonical.model import (
    Player,
    PlayerWeek,
    ProjectionClass,
    ProjectionSource,
    RosterEntry,
)
from fantasy_football.evolving_state import (
    AcquisitionAvailability,
    IRPolicy,
    initialize_evolving_state,
)
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


def _compound_ir_cycle_fixture():
    snapshot = _overlap_snapshot(pool_specs=((200, (23,), 9.0),))
    source_id = snapshot.sources[0].source_id
    blocker = Player(
        13, "Recovered QB", 1, (0, 21), 1, "ACTIVE", "ONTEAM", True, source_id
    )
    snapshot = replace(
        snapshot,
        lineup_slot_namespace=replace(
            snapshot.lineup_slot_namespace,
            observed_slot_ids=tuple(
                sorted(set(snapshot.lineup_slot_namespace.observed_slot_ids + (21,)))
            ),
        ),
        rules=replace(
            snapshot.rules,
            lineup_slots=tuple(
                replace(rule, capacity=2) if rule.slot_id == 21 else rule
                for rule in snapshot.rules.lineup_slots
            ),
        ),
        players=tuple(
            sorted(
                tuple(
                    replace(
                        player,
                        injury_status="OUT",
                        is_undroppable=True,
                        eligible_lineup_slot_ids=tuple(
                            sorted(set(player.eligible_lineup_slot_ids + (21,)))
                        ),
                    )
                    if player.player_id == 11
                    else replace(player, acquisition_status="WAIVERS")
                    if player.player_id == 12
                    else player
                    for player in snapshot.players
                )
                + (blocker,),
                key=lambda item: item.player_id,
            )
        ),
        roster_entries=tuple(
            sorted(
                tuple(
                    entry for entry in snapshot.roster_entries if entry.player_id != 12
                )
                + (RosterEntry(13, 1, 21, 1),),
                key=lambda item: (item.team_id, item.player_id),
            )
        ),
        player_weeks=tuple(
            sorted(
                tuple(
                    replace(
                        record,
                        raw_projection=0.0,
                        projection_class=ProjectionClass.EXPLICIT_ZERO,
                        effective_projection=0.0,
                    )
                    if record.player_id == 11
                    else record
                    for record in snapshot.player_weeks
                )
                + tuple(
                    PlayerWeek(
                        13,
                        2026,
                        week,
                        13.0,
                        ProjectionClass.PRESENT,
                        13.0,
                        ProjectionSource.ESPN,
                        source_id,
                    )
                    for week in (15, 16, 17)
                ),
                key=lambda item: (item.player_id, item.scoring_week),
            )
        ),
    )
    return snapshot, replace(
        _state(snapshot),
        current_waiver_priority=(4, 3, 2, 1),
        initial_window_waiver_priority=(4, 3, 2, 1),
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


def test_unresolved_waiver_boundary_excludes_authorization_not_legal_free_agents() -> (
    None
):
    snapshot = _valuation_snapshot(pool_values=(8.0,))
    snapshot = replace(
        snapshot,
        players=tuple(
            replace(player, acquisition_status="WAIVERS")
            if player.player_id == -300
            else player
            for player in snapshot.players
        ),
    )
    result = enumerate_feasible_cycles(
        snapshot, _state(snapshot), WeeklyTransactionPolicy()
    )
    assert result.legal_enumeration_complete
    assert result.unsupported_authorization_branches_excluded > 0
    assert all(
        all(entry.player_id != -300 for entry in terminal.state.roster_entries)
        for terminal in result.terminals
    )


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


def test_incomplete_value_preserves_feasible_branch_but_blocks_policy_certification(
    monkeypatch,
) -> None:
    snapshot = _valuation_snapshot(competing_teams=1, pool_values=(8.0,))
    state = replace(
        _state(snapshot),
        current_waiver_priority=(2, 3, 4, 1),
        initial_window_waiver_priority=(2, 3, 4, 1),
    )
    from fantasy_football import transaction_cycle

    actual_value_roster = transaction_cycle.value_roster

    def controlled_incomplete_value(snapshot_arg, state_arg, team_id):
        result = actual_value_roster(snapshot_arg, state_arg, team_id)
        if team_id == 1 and any(
            entry.player_id == -300 and entry.team_id == 1
            for entry in state_arg.roster_entries
        ):
            return replace(
                result,
                is_complete=False,
                unresolved_inputs=("controlled_material_future_access",),
            )
        return result

    monkeypatch.setattr(transaction_cycle, "value_roster", controlled_incomplete_value)
    feasible = enumerate_feasible_cycles(snapshot, state, WeeklyTransactionPolicy())
    acquired_terminals = tuple(
        terminal
        for terminal in feasible.terminals
        if any(
            entry.player_id == -300 and entry.team_id == 1
            for entry in terminal.state.roster_entries
        )
    )
    assert feasible.legal_enumeration_complete
    assert feasible.incomplete_valuation_branch_count > 0
    assert feasible.all_terminal_valuations_complete is False
    assert feasible.unresolved_terminal_valuation_count > 0
    assert acquired_terminals
    assert any(item.contains_incomplete_plan_valuation for item in acquired_terminals)

    sequential = execute_sequential_policy_reference(
        snapshot, state, WeeklyTransactionPolicy()
    )
    assert sequential.determination_complete is False
    assert sequential.unresolved_decisions
    assert sequential.state == state
    comparison = validate_operational_policy_equivalence(
        snapshot, state, WeeklyTransactionPolicy()
    )
    assert comparison.equivalent is False
    assert "reference_sequential_policy_unresolved" in comparison.mismatches


def test_immaterial_unresolved_player_preserves_complete_cycle_values() -> None:
    snapshot = _valuation_snapshot(pool_values=(8.0,))
    state = _state(snapshot)
    state = replace(
        state,
        availability=tuple(
            replace(item, status=AcquisitionAvailability.UNRESOLVED)
            if item.player_id == 4
            else item
            for item in state.availability
        ),
    )
    result = enumerate_feasible_cycles(snapshot, state, WeeklyTransactionPolicy())
    assert result.legal_enumeration_complete
    assert result.all_terminal_valuations_complete
    assert result.incomplete_valuation_branch_count == 0


@pytest.mark.parametrize("candidate_count", [1, 2, 3, 4, 5])
def test_seeded_tiny_policy_trace_equivalence(candidate_count: int) -> None:
    values = tuple(float(10 - index) for index in range(candidate_count))
    snapshot = _valuation_snapshot(competing_teams=0, pool_values=values)
    comparison = validate_operational_policy_equivalence(
        snapshot, _state(snapshot), WeeklyTransactionPolicy()
    )
    assert comparison.equivalent, comparison.mismatches
    assert comparison.reference_trace == comparison.operational_trace


def test_compound_ir_cycle_trace_matches_operational_execution() -> None:
    snapshot, state = _compound_ir_cycle_fixture()
    comparison = validate_operational_policy_equivalence(
        snapshot, state, WeeklyTransactionPolicy()
    )
    assert comparison.equivalent, comparison.mismatches
    assert comparison.reference_trace == comparison.operational_trace
    selected = comparison.reference_trace[0]
    assert selected[3] == 200
    assert selected[5] == (11,)
    assert selected[6] == (13,)
    assert tuple(item[0] for item in selected[8]) == (
        "ir_place",
        "ir_activate",
        "add",
    )
    availability = {
        item.player_id: item for item in comparison.reference.state.availability
    }
    assert all(
        availability[player_id].status is AcquisitionAvailability.HOLD
        for player_id in selected[4]
    )
