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
    IREligibility,
    IRPolicy,
    initialize_evolving_state,
    place_on_ir,
    record_ir_eligibility_evidence,
    validate_eligibility_evidence_artifact,
)
from fantasy_football.lineup_optimizer import optimize_starting_lineup
from fantasy_football.roster_value import value_roster
from fantasy_football.weekly_transactions import (
    DecisionOutcome,
    WaiverBoundaryPolicy,
    WeeklyTransactionError,
    WeeklyTransactionPolicy,
    execute_weekly_essential_transactions,
)
from tests.test_roster_value import _overlap_snapshot, _valuation_snapshot
from tests.test_evolving_state import _eligibility_artifact


def _policy(*, waivers: bool = False) -> WeeklyTransactionPolicy:
    return WeeklyTransactionPolicy(
        waiver_boundary=(
            WaiverBoundaryPolicy.MODELED_WEEKLY_V1
            if waivers else WaiverBoundaryPolicy.UNRESOLVED
        ),
    )


def _state(snapshot):
    return initialize_evolving_state(snapshot, scoring_week=15, ir_policy=IRPolicy.PROJECTION_BASED)


def _staff_team_one(snapshot):
    return replace(
        snapshot,
        players=tuple(
            replace(player, acquisition_status="ONTEAM") if player.player_id == -101 else player
            for player in snapshot.players
        ),
        roster_entries=tuple(sorted(
            snapshot.roster_entries + (RosterEntry(-101, 1, 16, 1),),
            key=lambda item: (item.team_id, item.player_id),
        )),
        player_weeks=tuple(
            replace(
                record, raw_projection=7.0, projection_class=ProjectionClass.PRESENT,
                effective_projection=7.0, effective_source=ProjectionSource.ESPN,
            ) if record.player_id == -101 else record
            for record in snapshot.player_weeks
        ),
    )


def test_free_agent_phase_fills_only_genuine_vacancy_without_mutation() -> None:
    snapshot = _valuation_snapshot(pool_values=(8.0, 6.0))
    state = _state(snapshot)
    result = execute_weekly_essential_transactions(snapshot, state, _policy())
    assert state.ledger == ()
    assert result.free_agent_acquisitions == 1
    assert result.acquisitions[0].team_id == 1
    assert result.acquisitions[0].acquired_player_id == -300
    assert result.acquisitions[0].vacancy_count_before == 1
    assert result.acquisitions[0].vacancy_count_after == 0
    assert result.final_waiver_priority == state.current_waiver_priority
    assert optimize_starting_lineup(
        snapshot, 1, 15, roster_entries=result.state.roster_entries
    ).is_complete
    assert value_roster(snapshot, result.state, 1).weeks[0].mandatory_vacancy_count == 0


def test_fully_staffed_team_does_not_make_speculative_upgrade() -> None:
    snapshot = _valuation_snapshot(pool_values=(20.0,))
    # Restore the canonical team-one D/ST, leaving the much stronger pool player unowned.
    snapshot = _staff_team_one(snapshot)
    state = _state(snapshot)
    result = execute_weekly_essential_transactions(snapshot, state, _policy())
    assert result.free_agent_acquisitions == 0
    assert all(item.outcome is DecisionOutcome.NO_ESSENTIAL_VACANCY for item in result.decisions)
    assert result.state == state


def test_shared_free_agent_goes_to_first_team_in_reverse_frozen_order() -> None:
    snapshot = _valuation_snapshot(competing_teams=2, pool_values=(8.0,))
    state = _state(snapshot)
    result = execute_weekly_essential_transactions(snapshot, state, _policy())
    assert result.free_agent_acquisitions == 1
    # Frozen priority is 1,2,3,4, so immediate free-agent processing is 4,3,2,1.
    assert result.acquisitions[0].team_id == 3
    assert result.acquisitions[0].acquired_player_id == -300
    assert dict((entry.player_id, entry.team_id) for entry in result.state.roster_entries)[-300] == 3


def test_repeated_free_agent_passes_fill_two_overlapping_vacancies() -> None:
    snapshot = _overlap_snapshot()
    state = _state(snapshot)
    result = execute_weekly_essential_transactions(snapshot, state, _policy())
    team_two = tuple(item for item in result.acquisitions if item.team_id == 2)
    assert tuple(item.pass_number for item in team_two) == (1, 2)
    assert {item.acquired_player_id for item in team_two} == {200, 300}
    assert result.free_agent_acquisitions == 2
    assert result.free_agent_passes == 3  # final pass proves that no work remains
    assert optimize_starting_lineup(
        snapshot, 2, 15, roster_entries=result.state.roster_entries
    ).is_complete


def test_ineligible_player_cannot_satisfy_essential_vacancy() -> None:
    snapshot = _valuation_snapshot(pool_values=())
    # Existing unrostered QB has no D/ST eligibility for team one's vacancy.
    snapshot = replace(snapshot, players=tuple(
        replace(player, acquisition_status="FREEAGENT") if player.player_id == 4 else player
        for player in snapshot.players
    ))
    result = execute_weekly_essential_transactions(snapshot, _state(snapshot), _policy())
    assert result.free_agent_acquisitions == 0
    team_one = [item for item in result.decisions if item.team_id == 1 and item.phase.value == "free_agent"]
    assert team_one[-1].outcome in {DecisionOutcome.NO_LEGAL_PLAN, DecisionOutcome.NO_SUITABLE_CANDIDATE}


def test_full_roster_uses_explicit_legal_drop_and_holds_dropped_player() -> None:
    snapshot = _valuation_snapshot(pool_values=(8.0,))
    source_id = snapshot.sources[0].source_id
    zero_dst = Player(-500, "Zero DST", 16, (16, 20), 1, None, "ONTEAM", False, source_id)
    zero_weeks = tuple(PlayerWeek(
        -500, 2026, week, 0.0, ProjectionClass.EXPLICIT_ZERO, 0.0,
        ProjectionSource.ESPN, source_id,
    ) for week in (15, 16, 17))
    snapshot = replace(
        snapshot,
        players=tuple(sorted(
            tuple(replace(player, acquisition_status="ONTEAM") if player.player_id in {2, 3} else player
                  for player in snapshot.players) + (zero_dst,),
            key=lambda item: item.player_id,
        )),
        roster_entries=tuple(sorted(
            snapshot.roster_entries + (
                RosterEntry(-500, 1, 16, 1),
                RosterEntry(2, 1, 20, 1),
                RosterEntry(3, 1, 20, 1),
            ),
            key=lambda item: (item.team_id, item.player_id),
        )),
        player_weeks=tuple(sorted(
            snapshot.player_weeks + zero_weeks,
            key=lambda item: (item.player_id, item.scoring_week),
        )),
    )
    result = execute_weekly_essential_transactions(snapshot, _state(snapshot), _policy())
    acquisition = next(item for item in result.acquisitions if item.team_id == 1)
    assert acquisition.acquired_player_id == -300
    assert acquisition.dropped_player_ids
    availability = {item.player_id: item for item in result.state.availability}
    assert all(availability[player_id].status is AcquisitionAvailability.HOLD for player_id in acquisition.dropped_player_ids)
    assert all(availability[player_id].prohibited_cycle_id == result.state.cycle_id for player_id in acquisition.dropped_player_ids)


def test_necessary_ir_placement_creates_capacity_without_unrelated_reshuffling() -> None:
    snapshot = _valuation_snapshot(pool_values=(8.0,))
    source_id = snapshot.sources[0].source_id
    zero_dst = Player(-500, "Protected Zero DST", 16, (16, 20), 1, None, "ONTEAM", True, source_id)
    snapshot = replace(
        snapshot,
        players=tuple(sorted(
            tuple(
                replace(
                    player,
                    acquisition_status="ONTEAM",
                    injury_status="OUT" if player.player_id == 2 else player.injury_status,
                    eligible_lineup_slot_ids=(0, 20, 21) if player.player_id == 2 else player.eligible_lineup_slot_ids,
                ) if player.player_id in {2, 3} else player
                for player in snapshot.players
            ) + (zero_dst,),
            key=lambda item: item.player_id,
        )),
        roster_entries=tuple(sorted(
            snapshot.roster_entries + (
                RosterEntry(-500, 1, 16, 1),
                RosterEntry(2, 1, 20, 1),
                RosterEntry(3, 1, 20, 1),
            ),
            key=lambda item: (item.team_id, item.player_id),
        )),
        player_weeks=tuple(sorted(
            snapshot.player_weeks + tuple(PlayerWeek(
                -500, 2026, week, 0.0, ProjectionClass.EXPLICIT_ZERO, 0.0,
                ProjectionSource.ESPN, source_id,
            ) for week in (15, 16, 17)),
            key=lambda item: (item.player_id, item.scoring_week),
        )),
    )
    result = execute_weekly_essential_transactions(snapshot, _state(snapshot), _policy())
    acquisition = next(item for item in result.acquisitions if item.team_id == 1)
    assert acquisition.acquired_player_id == -300
    assert acquisition.ir_placed_player_ids == (2,)
    assert acquisition.dropped_player_ids == ()
    assert tuple(record.action.value for record in result.state.ledger[-2:]) == (
        "ir_place", "add",
    )


def test_waiver_phase_uses_dynamic_priority_and_moves_success_to_last() -> None:
    snapshot = _valuation_snapshot(competing_teams=2, pool_values=(8.0,))
    snapshot = _staff_team_one(replace(
        snapshot,
        players=tuple(
            replace(player, acquisition_status="WAIVERS") if player.player_id == -300 else player
            for player in snapshot.players
        ),
    ))
    state = _state(snapshot)
    result = execute_weekly_essential_transactions(snapshot, state, _policy(waivers=True))
    assert result.waiver_acquisitions == 1
    assert result.acquisitions[0].team_id == 2
    assert result.final_waiver_priority == (1, 3, 4, 2)
    assert result.frozen_initial_priority == (1, 2, 3, 4)


def test_waiver_players_are_blocked_without_supported_window() -> None:
    snapshot = _valuation_snapshot(pool_values=(8.0,))
    snapshot = replace(snapshot, players=tuple(
        replace(player, acquisition_status="WAIVERS") if player.player_id == -300 else player
        for player in snapshot.players
    ))
    result = execute_weekly_essential_transactions(snapshot, _state(snapshot), _policy())
    assert result.waiver_acquisitions == 0
    assert any(
        decision.outcome is DecisionOutcome.UNRESOLVED_AUTHORIZATION
        for decision in result.decisions if decision.phase.value == "waiver"
    )


def test_finite_acquisition_limit_blocks_execution_without_mutation() -> None:
    snapshot = _valuation_snapshot(pool_values=(8.0,))
    snapshot = replace(
        snapshot,
        rules=replace(
            snapshot.rules,
            acquisition=replace(snapshot.rules.acquisition, season_limit=0),
        ),
    )
    counts = {team.team_id: 0 for team in snapshot.teams}
    state = initialize_evolving_state(
        snapshot,
        scoring_week=15,
        ir_policy=IRPolicy.PROJECTION_BASED,
        season_acquisition_counts=counts,
    )
    result = execute_weekly_essential_transactions(snapshot, state, _policy())
    assert result.free_agent_acquisitions == 0
    assert result.state == state
    team_one = tuple(
        item for item in result.decisions
        if item.team_id == 1 and item.phase.value == "free_agent"
    )
    assert team_one[-1].outcome is DecisionOutcome.NO_LEGAL_PLAN
    assert any(item.reason == "acquisition_limit" for item in team_one[-1].rejection_summaries)


def _strict_ir_state(eligibility: IREligibility | None):
    snapshot = _valuation_snapshot(pool_values=(8.0,))
    snapshot = replace(snapshot, players=tuple(
        replace(
            player,
            eligible_lineup_slot_ids=tuple(sorted(set(player.eligible_lineup_slot_ids + (21,)))),
            injury_status="OUT",
        ) if player.player_id == 1 else player
        if player.player_id != 4 else replace(player, acquisition_status="WAIVERS")
        for player in snapshot.players
    ))
    claims = [] if eligibility is None else [{
        "kind": "ir", "player_id": 1, "scoring_week": 15,
        "eligibility": eligibility.value,
        "condition": "future_ir_eligibility_observed",
    }]
    if claims:
        snapshot, payload, source_id = _eligibility_artifact(snapshot, claims)
    state = initialize_evolving_state(snapshot, scoring_week=15, ir_policy=IRPolicy.STRICT)
    state = place_on_ir(state, snapshot, team_id=1, player_id=1, reserve_slot_id=21)
    if claims:
        evidence = validate_eligibility_evidence_artifact(
            snapshot, source_id=source_id, payload=payload
        ).ir_determinations[0]
        state = record_ir_eligibility_evidence(state, snapshot, evidence)
    return snapshot, state


def test_strict_ineligible_ir_occupant_is_activated_before_essential_add() -> None:
    snapshot, state = _strict_ir_state(IREligibility.INELIGIBLE)
    result = execute_weekly_essential_transactions(snapshot, state, _policy())
    acquisition = next(item for item in result.acquisitions if item.team_id == 1)
    assert acquisition.acquired_player_id == -300
    assert acquisition.ir_activated_player_ids == (1,)
    assert tuple(record.action.value for record in result.state.ledger[-2:]) == (
        "ir_activate", "add",
    )


def test_strict_eligible_ir_occupant_does_not_block_essential_add() -> None:
    snapshot, state = _strict_ir_state(IREligibility.ELIGIBLE)
    result = execute_weekly_essential_transactions(snapshot, state, _policy())
    acquisition = next(item for item in result.acquisitions if item.team_id == 1)
    assert acquisition.acquired_player_id == -300
    assert acquisition.ir_activated_player_ids == ()


@pytest.mark.parametrize("eligibility", [None, IREligibility.UNKNOWN])
def test_strict_unknown_ir_status_does_not_authorize_correction(eligibility) -> None:
    snapshot, state = _strict_ir_state(eligibility)
    result = execute_weekly_essential_transactions(snapshot, state, _policy())
    assert result.free_agent_acquisitions == 0
    assert result.state == state
    assert any(
        item.outcome is DecisionOutcome.UNRESOLVED_AUTHORIZATION
        for item in result.decisions if item.team_id == 1
    )


def test_arbitrary_waiver_boundary_string_cannot_authorize_processing() -> None:
    snapshot = _valuation_snapshot(pool_values=(8.0,))
    with pytest.raises(WeeklyTransactionError, match="unsupported waiver boundary policy"):
        execute_weekly_essential_transactions(
            snapshot, _state(snapshot),
            WeeklyTransactionPolicy(waiver_boundary="anything"),  # type: ignore[arg-type]
        )


def test_plan_stage_diagnostics_reconcile() -> None:
    snapshot = _valuation_snapshot(pool_values=(8.0, 6.0))
    result = execute_weekly_essential_transactions(snapshot, _state(snapshot), _policy())
    decision = next(item for item in result.decisions if item.outcome is DecisionOutcome.ACQUIRED)
    rejected_attempts = sum(
        item.count for item in decision.rejection_summaries
        if item.reason not in {"ineligible_for_configured_slots", "incomplete_valuation"}
    )
    assert decision.transaction_sequences_attempted == decision.legally_executable_plans + rejected_attempts
    assert decision.legally_executable_plans >= decision.essential_qualified_plans
    assert decision.essential_qualified_plans == (
        decision.valuation_complete_plans + decision.incomplete_valuation_plans
    )
    assert result.unique_legal_resulting_states <= decision.legally_executable_plans


def test_incomplete_valuation_policy_cannot_be_disabled() -> None:
    snapshot = _valuation_snapshot()
    with pytest.raises(WeeklyTransactionError, match="no approved capability policy"):
        execute_weekly_essential_transactions(
            snapshot,
            _state(snapshot),
            WeeklyTransactionPolicy(reject_incomplete_valuations=False),
        )


def test_reordered_state_is_deterministic_and_no_network(monkeypatch) -> None:
    snapshot = _valuation_snapshot(competing_teams=1, pool_values=(8.0, 6.0))
    state = _state(snapshot)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("weekly transactions must not access ESPN")

    monkeypatch.setattr("fantasy_football.espn_adapter.fetch_and_translate", forbidden)
    first = execute_weekly_essential_transactions(snapshot, state, _policy())
    reordered = replace(
        state,
        roster_entries=tuple(reversed(state.roster_entries)),
        availability=tuple(reversed(state.availability)),
    )
    second = execute_weekly_essential_transactions(snapshot, reordered, _policy())
    assert first.acquisitions == second.acquisitions
    assert first.state.roster_entries == second.state.roster_entries
    assert len({entry.player_id for entry in first.state.roster_entries}) == len(first.state.roster_entries)
