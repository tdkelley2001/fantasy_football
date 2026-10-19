from __future__ import annotations

from dataclasses import replace
import json

import pytest

from fantasy_football.canonical.model import (
    InterpretationStatus,
    RosterEntry,
    SCHEMA_VERSION,
)
from fantasy_football.canonical.serialization import snapshot_from_json, snapshot_to_json
from fantasy_football.evolving_state import (
    AcquisitionAvailability,
    IREligibility,
    IREligibilityEvidence,
    IRPolicy,
    ReleaseAuthorization,
    TransactionPhase,
    TransactionStateError,
    acquisition_blocking_ir_players,
    activate_from_ir,
    add_player,
    advance_cycle,
    apply_failed_waiver_claim,
    apply_successful_waiver_priority,
    drop_player,
    initialize_evolving_state,
    place_on_ir,
    record_ir_eligibility_evidence,
    release_held_player,
    replace_player,
    reset_waiver_priority,
    state_to_json,
    validate_evolving_state,
)
from fantasy_football.lineup_optimizer import optimize_starting_lineup
from fantasy_football.weekly_engine import (
    RealizedPlayerScore,
    initialize_standings,
    resolve_regular_season_week,
)
from tests.canonical_fixtures import canonical_snapshot


def _state(snapshot=None, *, policy=IRPolicy.PROJECTION_BASED):
    snapshot = canonical_snapshot() if snapshot is None else snapshot
    return initialize_evolving_state(snapshot, scoring_week=15, ir_policy=policy)


def _player(snapshot, player_id, **changes):
    return replace(
        snapshot,
        players=tuple(
            replace(item, **changes) if item.player_id == player_id else item
            for item in snapshot.players
        ),
    )


def _v2_payload() -> str:
    data = json.loads(snapshot_to_json(canonical_snapshot()))
    data["schema_version"] = 2
    data["rules"].pop("undroppable_list_enabled")
    data["rules"].pop("undroppable_list_source_id")
    for player in data["players"]:
        player.pop("is_undroppable")
        player.pop("undroppable_source_id")
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def test_schema_v3_round_trip_is_deterministic_and_preserves_three_states() -> None:
    snapshot = canonical_snapshot()
    encoded = snapshot_to_json(snapshot)
    decoded = snapshot_from_json(encoded)
    assert decoded.schema_version == SCHEMA_VERSION == 3
    assert snapshot_to_json(decoded) == encoded
    assert {item.player_id: item.is_undroppable for item in decoded.players} == {
        -101: False, 1: True, 2: False, 3: False, 4: None,
    }


def test_schema_v2_bytes_round_trip_without_synthesizing_v3_fields() -> None:
    payload = _v2_payload()
    snapshot = snapshot_from_json(payload)
    assert snapshot.schema_version == 2
    assert snapshot.rules.undroppable_list_enabled is None
    assert all(item.is_undroppable is None for item in snapshot.players)
    assert snapshot_to_json(snapshot) == payload
    with pytest.raises(TransactionStateError, match="requires schema 3"):
        initialize_evolving_state(snapshot, scoring_week=15, ir_policy=IRPolicy.STRICT)


@pytest.mark.parametrize("field,value", [("undroppable_list_enabled", 1), ("undroppable_list_enabled", "true")])
def test_schema_v3_rejects_malformed_league_boolean(field, value) -> None:
    snapshot = canonical_snapshot()
    with pytest.raises(ValueError, match=field):
        snapshot_to_json(replace(snapshot, rules=replace(snapshot.rules, **{field: value})))


def test_schema_v3_rejects_missing_and_invalid_provenance() -> None:
    snapshot = canonical_snapshot()
    bad = _player(snapshot, 3, undroppable_source_id=None)
    with pytest.raises(ValueError, match="known protection requires provenance"):
        snapshot_to_json(bad)
    bad = _player(snapshot, 3, undroppable_source_id="missing")
    with pytest.raises(ValueError, match="unknown source"):
        snapshot_to_json(bad)


def test_initial_state_separates_ownership_free_agents_waivers_and_unknown() -> None:
    state = _state()
    values = {item.player_id: item.status for item in state.availability}
    assert values[-101] is AcquisitionAvailability.ROSTERED
    assert values[3] is AcquisitionAvailability.FREE_AGENT
    assert values[4] is AcquisitionAvailability.WAIVERS
    assert state.current_waiver_priority == (1, 2, 3, 4)
    assert state.initial_window_waiver_priority == (1, 2, 3, 4)


def test_legal_add_and_drop_are_immutable_and_deterministic() -> None:
    snapshot = canonical_snapshot()
    initial = _state(snapshot)
    before = state_to_json(initial, snapshot)
    added = add_player(initial, snapshot, team_id=1, player_id=3, lineup_slot_id=20)
    assert state_to_json(initial, snapshot) == before
    assert any(item.player_id == 3 and item.team_id == 1 for item in added.roster_entries)
    assert added.ledger[-1].action.value == "add"
    dropped = drop_player(added, snapshot, team_id=1, player_id=3)
    status = {item.player_id: item for item in dropped.availability}[3]
    assert status.status is AcquisitionAvailability.HOLD
    assert status.prohibited_cycle_id == dropped.cycle_id
    assert state_to_json(dropped, snapshot) == state_to_json(
        drop_player(add_player(initial, snapshot, team_id=1, player_id=3, lineup_slot_id=20), snapshot, team_id=1, player_id=3),
        snapshot,
    )


def test_illegal_add_and_drop_protection_states_fail_without_ledger_mutation() -> None:
    snapshot = canonical_snapshot()
    state = _state(snapshot)
    with pytest.raises(TransactionStateError, match="rostered, not free_agent"):
        add_player(state, snapshot, team_id=1, player_id=2, lineup_slot_id=20)
    with pytest.raises(TransactionStateError, match="protected"):
        drop_player(state, snapshot, team_id=1, player_id=1)
    unknown = _player(snapshot, -101, is_undroppable=None, undroppable_source_id=None)
    with pytest.raises(TransactionStateError, match="status is unknown"):
        drop_player(_state(unknown), unknown, team_id=1, player_id=-101)
    assert state.ledger == ()


def test_disabled_list_does_not_apply_player_designation() -> None:
    snapshot = canonical_snapshot()
    snapshot = replace(snapshot, rules=replace(snapshot.rules, undroppable_list_enabled=False))
    result = drop_player(_state(snapshot), snapshot, team_id=1, player_id=1)
    assert all(item.player_id != 1 for item in result.roster_entries)


def test_unverified_raw_polarity_blocks_automatic_drop() -> None:
    snapshot = canonical_snapshot()
    interpretations = tuple(
        replace(item, status=InterpretationStatus.UNVERIFIED, normalized_value=None)
        if item.rule_id == "undroppable_player_mapping" else item
        for item in snapshot.rules.interpretations
    )
    snapshot = replace(snapshot, rules=replace(snapshot.rules, interpretations=interpretations))
    with pytest.raises(TransactionStateError, match="polarity is not verified"):
        drop_player(_state(snapshot), snapshot, team_id=1, player_id=-101)


def test_compound_replace_is_atomic_on_invalid_add() -> None:
    snapshot = canonical_snapshot()
    state = _state(snapshot)
    before = state_to_json(state, snapshot)
    with pytest.raises(TransactionStateError, match="waivers, not free_agent"):
        replace_player(
            state, snapshot, team_id=1, drop_player_id=-101, add_player_id=4,
            lineup_slot_id=16, phase=TransactionPhase.FREE_AGENT,
        )
    assert state_to_json(state, snapshot) == before
    assert state.ledger == ()


def test_capacity_duplicate_ownership_position_and_eligibility_fail() -> None:
    snapshot = canonical_snapshot()
    state = _state(snapshot)
    duplicate = replace(state, roster_entries=state.roster_entries + (RosterEntry(1, 2, 20, 2),))
    with pytest.raises(TransactionStateError, match="duplicate modeled ownership"):
        validate_evolving_state(duplicate, snapshot)
    overflow = replace(state, roster_entries=state.roster_entries + (RosterEntry(3, 1, 16, 1),))
    with pytest.raises(TransactionStateError, match="ineligible"):
        validate_evolving_state(overflow, snapshot)


def test_ir_placement_requires_verified_status_not_projection() -> None:
    snapshot = canonical_snapshot()
    state = _state(snapshot)
    with pytest.raises(TransactionStateError, match="does not establish IR placement eligibility"):
        place_on_ir(state, snapshot, team_id=1, player_id=1, reserve_slot_id=21)
    eligible = _player(snapshot, 1, injury_status="OUT")
    placed = place_on_ir(_state(eligible), eligible, team_id=1, player_id=1, reserve_slot_id=21)
    assert next(item for item in placed.roster_entries if item.player_id == 1).lineup_slot_id == 21


def test_projection_policy_blocks_acquisition_until_explicit_activation() -> None:
    snapshot = _player(canonical_snapshot(), 1, injury_status="OUT")
    placed = place_on_ir(_state(snapshot), snapshot, team_id=1, player_id=1, reserve_slot_id=21)
    assert acquisition_blocking_ir_players(placed, snapshot) == (1,)
    strict = replace(placed, ir_policy=IRPolicy.STRICT)
    assert acquisition_blocking_ir_players(strict, snapshot) == ()
    with pytest.raises(TransactionStateError, match="strict IR acquisition legality is unresolved"):
        add_player(strict, snapshot, team_id=1, player_id=3, lineup_slot_id=20)
    with pytest.raises(TransactionStateError, match="activation eligibility is unresolved"):
        activate_from_ir(strict, snapshot, team_id=1, player_id=1, ordinary_slot_id=0)
    strict = record_ir_eligibility_evidence(
        strict,
        snapshot,
        IREligibilityEvidence(1, 15, IREligibility.INELIGIBLE, snapshot.sources[0].source_id),
    )
    strict_activated = activate_from_ir(
        strict, snapshot, team_id=1, player_id=1, ordinary_slot_id=0,
    )
    assert next(item for item in strict_activated.roster_entries if item.player_id == 1).lineup_slot_id == 0
    activated = activate_from_ir(placed, snapshot, team_id=1, player_id=1, ordinary_slot_id=0)
    assert acquisition_blocking_ir_players(activated, snapshot) == ()
    advanced = advance_cycle(activated, snapshot, cycle_id=2, scoring_week=16)
    assert next(item for item in advanced.roster_entries if item.player_id == 1).lineup_slot_id == 0


def test_ir_activation_with_explicit_drop_and_engine_integration(monkeypatch) -> None:
    snapshot = _player(
        canonical_snapshot(), 1, injury_status="OUT",
        eligible_lineup_slot_ids=(0, 16, 20, 21, 25),
    )
    snapshot = replace(
        snapshot,
        rules=replace(
            snapshot.rules,
            interpretations=tuple(
                replace(item, status=InterpretationStatus.UNDERSTOOD, normalized_value="allow_ties")
                if item.rule_id == "regular_matchup_tie" else item
                for item in snapshot.rules.interpretations
            ),
        ),
    )
    placed = place_on_ir(_state(snapshot), snapshot, team_id=1, player_id=1, reserve_slot_id=21)
    activated = activate_from_ir(
        placed, snapshot, team_id=1, player_id=1, ordinary_slot_id=16, drop_player_id=-101
    )
    lineups = tuple(
        optimize_starting_lineup(snapshot, team_id, 15, roster_entries=activated.roster_entries)
        for team_id in (1, 2, 3, 4)
    )
    scores = tuple(
        RealizedPlayerScore(item.player_id, snapshot.season, 15, float(item.player_id))
        for lineup in lineups for item in lineup.assignments
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("deterministic state integration must not access ESPN")

    monkeypatch.setattr("fantasy_football.espn_adapter.fetch_and_translate", forbidden)
    result = resolve_regular_season_week(
        snapshot, 15, initialize_standings(snapshot), lineups, scores,
        roster_entries=activated.roster_entries,
    )
    assert len(result.matchup_results) == 2
    assert canonical_snapshot().roster_entries == snapshot.roster_entries


def test_waiver_priority_transitions_preserve_initial_frozen_order() -> None:
    snapshot = canonical_snapshot()
    state = _state(snapshot)
    moved = apply_successful_waiver_priority(state, snapshot, team_id=1)
    assert moved.current_waiver_priority == (2, 3, 4, 1)
    assert moved.initial_window_waiver_priority == (1, 2, 3, 4)
    assert state.current_waiver_priority == (1, 2, 3, 4)
    assert apply_failed_waiver_claim(state, snapshot, team_id=2) is state
    reset = reset_waiver_priority(moved, snapshot, ordered_team_ids=(4, 3, 2, 1))
    assert reset.current_waiver_priority == reset.initial_window_waiver_priority == (4, 3, 2, 1)
    with pytest.raises(TransactionStateError, match="complete unique"):
        reset_waiver_priority(moved, snapshot, ordered_team_ids=(1, 1, 2, 3))


def test_holding_requires_player_and_boundary_specific_authorization() -> None:
    snapshot = canonical_snapshot()
    dropped = drop_player(_state(snapshot), snapshot, team_id=1, player_id=-101)
    source_id = snapshot.sources[0].source_id
    with pytest.raises(TransactionStateError, match="prohibited acquisition cycle"):
        release_held_player(
            dropped,
            snapshot,
            player_id=-101,
            authorization=ReleaseAuthorization(
                -101, 1, AcquisitionAvailability.FREE_AGENT, source_id
            ),
        )
    advanced = advance_cycle(dropped, snapshot, cycle_id=2, scoring_week=16)
    assert {item.player_id: item.status for item in advanced.availability}[-101] is AcquisitionAvailability.HOLD
    with pytest.raises(TransactionStateError, match="does not match held player"):
        release_held_player(
            advanced,
            snapshot,
            player_id=-101,
            authorization=ReleaseAuthorization(3, 2, AcquisitionAvailability.FREE_AGENT, source_id),
        )
    released = release_held_player(
        advanced,
        snapshot,
        player_id=-101,
        authorization=ReleaseAuthorization(
            -101, 2, AcquisitionAvailability.WAIVERS, source_id
        ),
    )
    assert {item.player_id: item.status for item in released.availability}[-101] is AcquisitionAvailability.WAIVERS


def test_known_clearance_timestamp_cannot_be_bypassed() -> None:
    snapshot = canonical_snapshot()
    dropped = drop_player(_state(snapshot), snapshot, team_id=1, player_id=-101)
    held = next(item for item in dropped.availability if item.player_id == -101)
    held = replace(held, clearance_at_utc="2026-12-24T12:00:00+00:00", hold_until_cycle=2)
    dropped = replace(
        dropped,
        availability=tuple(held if item.player_id == -101 else item for item in dropped.availability),
    )
    advanced = advance_cycle(dropped, snapshot, cycle_id=2, scoring_week=16)
    authorization = ReleaseAuthorization(
        -101, 2, AcquisitionAvailability.FREE_AGENT, snapshot.sources[0].source_id,
        "2026-12-24T12:00:00+00:00",
    )
    with pytest.raises(TransactionStateError, match="before clearance"):
        release_held_player(
            advanced, snapshot, player_id=-101, authorization=authorization,
            boundary_at_utc="2026-12-24T11:59:59+00:00",
        )
    assert advanced.ledger == dropped.ledger + advanced.ledger[-1:]


def test_strict_ir_evidence_controls_activation_and_acquisition_independently() -> None:
    snapshot = _player(canonical_snapshot(), 1, injury_status="OUT")
    placed = place_on_ir(_state(snapshot, policy=IRPolicy.STRICT), snapshot, team_id=1, player_id=1, reserve_slot_id=21)
    source_id = snapshot.sources[0].source_id
    unrelated = record_ir_eligibility_evidence(
        placed, snapshot, IREligibilityEvidence(2, 15, IREligibility.INELIGIBLE, source_id)
    )
    with pytest.raises(TransactionStateError, match="player=1"):
        activate_from_ir(unrelated, snapshot, team_id=1, player_id=1, ordinary_slot_id=0)

    eligible = record_ir_eligibility_evidence(
        placed, snapshot, IREligibilityEvidence(1, 15, IREligibility.ELIGIBLE, source_id)
    )
    added = add_player(eligible, snapshot, team_id=1, player_id=3, lineup_slot_id=20)
    assert any(item.player_id == 3 for item in added.roster_entries)
    with pytest.raises(TransactionStateError, match="remains IR-eligible"):
        activate_from_ir(eligible, snapshot, team_id=1, player_id=1, ordinary_slot_id=0)

    ineligible = record_ir_eligibility_evidence(
        placed, snapshot, IREligibilityEvidence(1, 15, IREligibility.INELIGIBLE, source_id)
    )
    with pytest.raises(TransactionStateError, match="IR-ineligible"):
        add_player(ineligible, snapshot, team_id=1, player_id=3, lineup_slot_id=20)
    activated = activate_from_ir(ineligible, snapshot, team_id=1, player_id=1, ordinary_slot_id=0)
    assert next(item for item in activated.roster_entries if item.player_id == 1).lineup_slot_id == 0


def test_season_and_matchup_acquisition_limits_are_independent_and_period_aware() -> None:
    snapshot = canonical_snapshot()
    acquisition = replace(snapshot.rules.acquisition, season_limit=3, matchup_limit=1)
    snapshot = replace(snapshot, rules=replace(snapshot.rules, acquisition=acquisition))
    counts = {team_id: 0 for team_id in (1, 2, 3, 4)}
    state = initialize_evolving_state(
        snapshot,
        scoring_week=15,
        ir_policy=IRPolicy.PROJECTION_BASED,
        season_acquisition_counts=counts,
        matchup_acquisition_counts=counts,
    )
    added = add_player(state, snapshot, team_id=1, player_id=3, lineup_slot_id=20)
    with pytest.raises(TransactionStateError, match="matchup-period acquisition limit"):
        add_player(added, snapshot, team_id=1, player_id=4, lineup_slot_id=20, phase=TransactionPhase.WAIVER)
    week16 = advance_cycle(added, snapshot, cycle_id=2, scoring_week=16)
    assert dict(week16.matchup_acquisition_counts)[1] == 0
    week16 = replace(
        week16,
        season_acquisition_counts=tuple((team, 3 if team == 2 else count) for team, count in week16.season_acquisition_counts),
    )
    with pytest.raises(TransactionStateError, match="season acquisition limit"):
        add_player(week16, snapshot, team_id=2, player_id=4, lineup_slot_id=20, phase=TransactionPhase.WAIVER)
    assert dict(week16.matchup_acquisition_counts)[2] == 0
    week17 = advance_cycle(week16, snapshot, cycle_id=3, scoring_week=17)
    assert week17.matchup_acquisition_counts == week16.matchup_acquisition_counts
    assert week17.season_acquisition_counts == week16.season_acquisition_counts


def test_unknown_initial_counts_block_only_finite_limit_authorization() -> None:
    snapshot = canonical_snapshot()
    snapshot = replace(
        snapshot,
        rules=replace(snapshot.rules, acquisition=replace(snapshot.rules.acquisition, season_limit=10)),
    )
    state = _state(snapshot)
    assert dict(state.season_acquisition_counts)[1] is None
    with pytest.raises(TransactionStateError, match="season acquisition count is unknown"):
        add_player(state, snapshot, team_id=1, player_id=3, lineup_slot_id=20)
