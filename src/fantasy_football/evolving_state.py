"""Immutable deterministic roster and transaction primitives for M2.3b."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import StrEnum
import json
from typing import Iterable

from fantasy_football.canonical.model import (
    InterpretationStatus,
    LeagueSnapshot,
    RosterEntry,
    SCHEMA_VERSION,
    SlotKind,
)
from fantasy_football.canonical.validation import validate_snapshot


class TransactionStateError(ValueError):
    """Raised when modeled state or a proposed transaction is illegal."""


class AcquisitionAvailability(StrEnum):
    ROSTERED = "rostered"
    FREE_AGENT = "free_agent"
    WAIVERS = "waivers"
    HOLD = "hold"
    UNRESOLVED = "unresolved"


class IRPolicy(StrEnum):
    PROJECTION_BASED = "projection_based"
    STRICT = "strict"


class TransactionPhase(StrEnum):
    WAIVER = "waiver"
    FREE_AGENT = "free_agent"
    ROSTER_CORRECTION = "roster_correction"
    IR = "ir"
    CYCLE_BOUNDARY = "cycle_boundary"


class TransactionAction(StrEnum):
    ADD = "add"
    DROP = "drop"
    IR_PLACE = "ir_place"
    IR_ACTIVATE = "ir_activate"
    PRIORITY_MOVE = "priority_move"
    AVAILABILITY_RELEASE = "availability_release"
    CYCLE_ADVANCE = "cycle_advance"


@dataclass(frozen=True, slots=True)
class PlayerAvailability:
    player_id: int
    status: AcquisitionAvailability
    clearance_at_utc: str | None
    hold_until_cycle: int | None
    prohibited_cycle_id: int | None
    source_id: str | None


@dataclass(frozen=True, slots=True)
class TransactionRecord:
    sequence: int
    scoring_week: int
    cycle_id: int
    phase: TransactionPhase
    action: TransactionAction
    team_id: int | None
    player_id: int | None
    related_player_id: int | None
    prior_team_id: int | None
    resulting_team_id: int | None
    prior_slot_id: int | None
    resulting_slot_id: int | None
    prior_availability: AcquisitionAvailability | None
    resulting_availability: AcquisitionAvailability | None
    priority_before: tuple[int, ...]
    priority_after: tuple[int, ...]
    evidence_source_id: str | None
    assumption_ids: tuple[str, ...]

    @property
    def ordering_key(self) -> tuple[int, int, int]:
        phase_order = tuple(TransactionPhase).index(self.phase)
        return (self.scoring_week, phase_order, self.sequence)


@dataclass(frozen=True, slots=True)
class EvolvingLeagueState:
    source_snapshot_id: str
    source_schema_version: int
    season: int
    scoring_week: int
    cycle_id: int
    roster_entries: tuple[RosterEntry, ...]
    availability: tuple[PlayerAvailability, ...]
    current_waiver_priority: tuple[int, ...]
    initial_window_waiver_priority: tuple[int, ...]
    acquisition_counts: tuple[tuple[int, int], ...]
    ir_policy: IRPolicy
    ledger: tuple[TransactionRecord, ...]
    assumption_ids: tuple[str, ...]


def state_to_json(state: EvolvingLeagueState, snapshot: LeagueSnapshot) -> str:
    """Return deterministic, inspectable scenario-state JSON (not canonical snapshot storage)."""

    validate_evolving_state(state, snapshot)
    return json.dumps(asdict(state), indent=2, sort_keys=True, allow_nan=False) + "\n"


def _fail(message: str) -> None:
    raise TransactionStateError(message)


def _slot_map(snapshot: LeagueSnapshot):
    return {item.slot_id: item for item in snapshot.rules.lineup_slots}


def _player_map(snapshot: LeagueSnapshot):
    return {item.player_id: item for item in snapshot.players}


def _availability_map(state: EvolvingLeagueState):
    return {item.player_id: item for item in state.availability}


def _sorted_roster(entries: Iterable[RosterEntry]) -> tuple[RosterEntry, ...]:
    return tuple(sorted(entries, key=lambda item: (item.team_id, item.player_id)))


def _sorted_availability(items: Iterable[PlayerAvailability]) -> tuple[PlayerAvailability, ...]:
    return tuple(sorted(items, key=lambda item: item.player_id))


def _assert_snapshot(state: EvolvingLeagueState, snapshot: LeagueSnapshot) -> None:
    if snapshot.snapshot_id != state.source_snapshot_id or snapshot.schema_version != state.source_schema_version:
        _fail("evolving state source snapshot identity or schema version does not match")


def validate_evolving_state(state: EvolvingLeagueState, snapshot: LeagueSnapshot) -> None:
    """Validate modeled ownership, capacity, availability, priority, and ledger invariants."""

    validate_snapshot(snapshot)
    _assert_snapshot(state, snapshot)
    if state.source_schema_version != SCHEMA_VERSION:
        _fail(f"transaction state requires canonical schema {SCHEMA_VERSION}; schema-v2 cannot authorize drops")
    if not isinstance(state.ir_policy, IRPolicy):
        _fail("ir_policy must be projection_based or strict")
    if not snapshot.first_simulation_week <= state.scoring_week <= snapshot.final_simulation_week:
        _fail(f"scoring_week={state.scoring_week} is outside the snapshot horizon")
    team_ids = {item.team_id for item in snapshot.teams}
    if set(state.current_waiver_priority) != team_ids or len(state.current_waiver_priority) != len(team_ids):
        _fail("current waiver priority must be a complete unique team permutation")
    if set(state.initial_window_waiver_priority) != team_ids or len(state.initial_window_waiver_priority) != len(team_ids):
        _fail("initial window waiver priority must be a complete unique team permutation")
    players = _player_map(snapshot)
    slots = _slot_map(snapshot)
    owners: dict[int, int] = {}
    occupancy: dict[tuple[int, int], int] = {}
    position_counts: dict[tuple[int, int], int] = {}
    for entry in state.roster_entries:
        if entry.player_id not in players or entry.team_id not in team_ids:
            _fail(f"roster entry player={entry.player_id} references an unknown player or team")
        if entry.player_id in owners:
            _fail(f"player {entry.player_id} has duplicate modeled ownership")
        slot = slots.get(entry.lineup_slot_id)
        if slot is None or slot.capacity <= 0:
            _fail(f"player {entry.player_id} occupies unconfigured or zero-capacity slot {entry.lineup_slot_id}")
        if entry.lineup_slot_id not in players[entry.player_id].eligible_lineup_slot_ids:
            _fail(f"player {entry.player_id} is ineligible for occupied slot {entry.lineup_slot_id}")
        owners[entry.player_id] = entry.team_id
        key = (entry.team_id, entry.lineup_slot_id)
        occupancy[key] = occupancy.get(key, 0) + 1
        position_key = (entry.team_id, players[entry.player_id].default_position_id)
        position_counts[position_key] = position_counts.get(position_key, 0) + 1
    for (team_id, slot_id), count in occupancy.items():
        if count > slots[slot_id].capacity:
            _fail(f"team {team_id} slot {slot_id} occupancy {count} exceeds capacity {slots[slot_id].capacity}")
    limits = {item.position_id: item.maximum for item in snapshot.rules.position_limits}
    for (team_id, position_id), count in position_counts.items():
        maximum = limits.get(position_id)
        if maximum is not None and count > maximum:
            _fail(f"team {team_id} position {position_id} count {count} exceeds limit {maximum}")
    availability = _availability_map(state)
    if len(availability) != len(state.availability) or set(availability) != set(players):
        _fail("availability must contain exactly one record for every canonical player")
    for player_id, item in availability.items():
        if item.status is AcquisitionAvailability.ROSTERED and player_id not in owners:
            _fail(f"player {player_id} availability says rostered without ownership")
        if item.status is not AcquisitionAvailability.ROSTERED and player_id in owners:
            _fail(f"owned player {player_id} has non-rostered availability {item.status.value}")
        if item.hold_until_cycle is not None and item.hold_until_cycle < state.cycle_id:
            _fail(f"player {player_id} has an expired holding cycle that was not advanced")
    count_teams = [team_id for team_id, _ in state.acquisition_counts]
    if len(count_teams) != len(set(count_teams)) or set(count_teams) != team_ids:
        _fail("acquisition counts must contain every team exactly once")
    if any(count < 0 for _, count in state.acquisition_counts):
        _fail("acquisition counts cannot be negative")
    if tuple(record.sequence for record in state.ledger) != tuple(range(1, len(state.ledger) + 1)):
        _fail("transaction ledger sequences must be contiguous from one")


def initialize_evolving_state(
    snapshot: LeagueSnapshot,
    *,
    scoring_week: int,
    ir_policy: IRPolicy,
    cycle_id: int = 1,
) -> EvolvingLeagueState:
    validate_snapshot(snapshot)
    if snapshot.schema_version != SCHEMA_VERSION:
        _fail(f"automatic transaction state requires schema {SCHEMA_VERSION}; observed {snapshot.schema_version}")
    if snapshot.snapshot_id is None:
        _fail("evolving transaction state requires a published source snapshot ID")
    priorities = sorted(snapshot.teams, key=lambda item: item.waiver_priority or 0)
    if any(item.waiver_priority is None for item in priorities):
        _fail("waiver priority is missing for one or more teams")
    queue = tuple(item.team_id for item in priorities)
    owned = {item.player_id for item in snapshot.roster_entries}
    availability = []
    status_map = {
        "FREEAGENT": AcquisitionAvailability.FREE_AGENT,
        "WAIVERS": AcquisitionAvailability.WAIVERS,
    }
    for player in snapshot.players:
        status = AcquisitionAvailability.ROSTERED if player.player_id in owned else status_map.get(
            player.acquisition_status, AcquisitionAvailability.UNRESOLVED
        )
        availability.append(PlayerAvailability(player.player_id, status, None, None, None, None))
    state = EvolvingLeagueState(
        snapshot.snapshot_id,
        snapshot.schema_version,
        snapshot.season,
        scoring_week,
        cycle_id,
        snapshot.roster_entries,
        _sorted_availability(availability),
        queue,
        queue,
        tuple((team_id, 0) for team_id in sorted(queue)),
        ir_policy,
        (),
        ("snapshot_frozen_undroppable_v1", "weekly_transaction_window_v1"),
    )
    validate_evolving_state(state, snapshot)
    return state


def _append(
    state: EvolvingLeagueState,
    *,
    phase: TransactionPhase,
    action: TransactionAction,
    team_id: int | None,
    player_id: int | None,
    related_player_id: int | None = None,
    prior_team_id: int | None = None,
    resulting_team_id: int | None = None,
    prior_slot_id: int | None = None,
    resulting_slot_id: int | None = None,
    prior_availability: AcquisitionAvailability | None = None,
    resulting_availability: AcquisitionAvailability | None = None,
    priority_before: tuple[int, ...] | None = None,
    priority_after: tuple[int, ...] | None = None,
    evidence_source_id: str | None = None,
    assumption_ids: tuple[str, ...] = (),
) -> EvolvingLeagueState:
    record = TransactionRecord(
        len(state.ledger) + 1, state.scoring_week, state.cycle_id, phase, action, team_id,
        player_id, related_player_id, prior_team_id, resulting_team_id, prior_slot_id,
        resulting_slot_id, prior_availability, resulting_availability,
        state.current_waiver_priority if priority_before is None else priority_before,
        state.current_waiver_priority if priority_after is None else priority_after,
        evidence_source_id, assumption_ids,
    )
    return replace(state, ledger=state.ledger + (record,))


def _replace_availability(
    state: EvolvingLeagueState, replacement: PlayerAvailability
) -> EvolvingLeagueState:
    items = [replacement if item.player_id == replacement.player_id else item for item in state.availability]
    return replace(state, availability=_sorted_availability(items))


def _validate_drop_permission(snapshot: LeagueSnapshot, player_id: int) -> str | None:
    if snapshot.schema_version < 3:
        _fail("schema-v2 snapshot lacks player-level undroppable evidence")
    enabled = snapshot.rules.undroppable_list_enabled
    if enabled is None:
        _fail("undroppable-list enablement is unknown")
    if enabled is False:
        return snapshot.rules.undroppable_list_source_id
    interpretation = next(
        (item for item in snapshot.rules.interpretations if item.rule_id == "undroppable_player_mapping"),
        None,
    )
    if interpretation is None or interpretation.status is not InterpretationStatus.UNDERSTOOD:
        _fail("player.droppable polarity is not verified for automatic drop authorization")
    player = _player_map(snapshot)[player_id]
    if player.is_undroppable is None:
        _fail(f"player {player_id} undroppable status is unknown")
    if player.is_undroppable:
        _fail(f"player {player_id} is protected by the enabled ESPN undroppable list")
    return player.undroppable_source_id


def drop_player(
    state: EvolvingLeagueState,
    snapshot: LeagueSnapshot,
    *,
    team_id: int,
    player_id: int,
    phase: TransactionPhase = TransactionPhase.ROSTER_CORRECTION,
) -> EvolvingLeagueState:
    validate_evolving_state(state, snapshot)
    entry = next((item for item in state.roster_entries if item.player_id == player_id), None)
    if entry is None or entry.team_id != team_id:
        _fail(f"team {team_id} does not own player {player_id}")
    evidence = _validate_drop_permission(snapshot, player_id)
    prior = _availability_map(state)[player_id]
    held = PlayerAvailability(
        player_id, AcquisitionAvailability.HOLD, None, None, state.cycle_id, evidence
    )
    result = replace(
        state,
        roster_entries=_sorted_roster(item for item in state.roster_entries if item.player_id != player_id),
    )
    result = _replace_availability(result, held)
    result = _append(
        result, phase=phase, action=TransactionAction.DROP, team_id=team_id, player_id=player_id,
        prior_team_id=team_id, prior_slot_id=entry.lineup_slot_id,
        prior_availability=prior.status, resulting_availability=held.status,
        evidence_source_id=evidence, assumption_ids=("same_cycle_drop_reentry_prohibited_v1",),
    )
    validate_evolving_state(result, snapshot)
    return result


def _check_acquisition_count(state: EvolvingLeagueState, snapshot: LeagueSnapshot, team_id: int) -> None:
    counts = dict(state.acquisition_counts)
    limit = snapshot.rules.acquisition.matchup_limit
    if limit is not None and counts[team_id] >= limit:
        _fail(f"team {team_id} has reached acquisition limit {limit}")


def add_player(
    state: EvolvingLeagueState,
    snapshot: LeagueSnapshot,
    *,
    team_id: int,
    player_id: int,
    lineup_slot_id: int,
    phase: TransactionPhase = TransactionPhase.FREE_AGENT,
) -> EvolvingLeagueState:
    validate_evolving_state(state, snapshot)
    players = _player_map(snapshot)
    if team_id not in state.current_waiver_priority or player_id not in players:
        _fail(f"unknown team {team_id} or player {player_id}")
    available = _availability_map(state)[player_id]
    required = AcquisitionAvailability.WAIVERS if phase is TransactionPhase.WAIVER else AcquisitionAvailability.FREE_AGENT
    if available.status is not required:
        _fail(f"player {player_id} is {available.status.value}, not {required.value}")
    if available.prohibited_cycle_id == state.cycle_id:
        _fail(f"player {player_id} is prohibited from reentry in cycle {state.cycle_id}")
    slot = _slot_map(snapshot).get(lineup_slot_id)
    if slot is None or slot.capacity <= 0 or slot.kind is SlotKind.RESERVE:
        _fail(f"lineup slot {lineup_slot_id} is not an ordinary configured destination")
    if lineup_slot_id not in players[player_id].eligible_lineup_slot_ids:
        _fail(f"player {player_id} is ineligible for slot {lineup_slot_id}")
    _check_acquisition_count(state, snapshot, team_id)
    if state.ir_policy is IRPolicy.STRICT:
        reserve_ids = {
            item.slot_id for item in snapshot.rules.lineup_slots if item.kind is SlotKind.RESERVE
        }
        unresolved = tuple(
            sorted(
                item.player_id for item in state.roster_entries
                if item.team_id == team_id and item.lineup_slot_id in reserve_ids
            )
        )
        if unresolved:
            _fail(
                f"team {team_id} strict IR acquisition legality is unresolved for reserve occupant(s) {unresolved}; "
                "separately verified evidence is required"
            )
    owners = {item.player_id: item.team_id for item in state.roster_entries}
    blockers = tuple(
        player for player in acquisition_blocking_ir_players(state, snapshot)
        if owners[player] == team_id
    )
    if blockers:
        _fail(
            f"team {team_id} has projection-based recovered reserve occupant(s) {blockers}; "
            "explicit roster correction is required before acquisition"
        )
    entry = RosterEntry(player_id, team_id, lineup_slot_id, team_id)
    rostered = PlayerAvailability(player_id, AcquisitionAvailability.ROSTERED, None, None, None, available.source_id)
    counts = dict(state.acquisition_counts)
    counts[team_id] += 1
    result = replace(
        state,
        roster_entries=_sorted_roster(state.roster_entries + (entry,)),
        acquisition_counts=tuple(sorted(counts.items())),
    )
    result = _replace_availability(result, rostered)
    result = _append(
        result, phase=phase, action=TransactionAction.ADD, team_id=team_id, player_id=player_id,
        resulting_team_id=team_id, resulting_slot_id=lineup_slot_id,
        prior_availability=available.status, resulting_availability=rostered.status,
        evidence_source_id=available.source_id,
    )
    validate_evolving_state(result, snapshot)
    return result


def replace_player(
    state: EvolvingLeagueState,
    snapshot: LeagueSnapshot,
    *,
    team_id: int,
    drop_player_id: int,
    add_player_id: int,
    lineup_slot_id: int,
    phase: TransactionPhase,
) -> EvolvingLeagueState:
    """Apply a legal drop then add atomically; exceptions leave the input untouched."""

    candidate = drop_player(
        state, snapshot, team_id=team_id, player_id=drop_player_id,
        phase=TransactionPhase.ROSTER_CORRECTION,
    )
    return add_player(
        candidate, snapshot, team_id=team_id, player_id=add_player_id,
        lineup_slot_id=lineup_slot_id, phase=phase,
    )


def place_on_ir(
    state: EvolvingLeagueState,
    snapshot: LeagueSnapshot,
    *,
    team_id: int,
    player_id: int,
    reserve_slot_id: int,
) -> EvolvingLeagueState:
    validate_evolving_state(state, snapshot)
    player = _player_map(snapshot).get(player_id)
    entry = next((item for item in state.roster_entries if item.player_id == player_id), None)
    slot = _slot_map(snapshot).get(reserve_slot_id)
    if player is None or entry is None or entry.team_id != team_id:
        _fail(f"team {team_id} does not own player {player_id}")
    if slot is None or slot.kind is not SlotKind.RESERVE or slot.capacity <= 0:
        _fail(f"slot {reserve_slot_id} is not configured reserve capacity")
    if reserve_slot_id not in player.eligible_lineup_slot_ids:
        _fail(f"player {player_id} is not eligible for reserve slot {reserve_slot_id}")
    if player.injury_status not in {"OUT", "IR"}:
        _fail(f"player {player_id} injury status {player.injury_status!r} does not establish IR placement eligibility")
    replacement = replace(entry, lineup_slot_id=reserve_slot_id)
    result = replace(
        state,
        roster_entries=_sorted_roster(replacement if item.player_id == player_id else item for item in state.roster_entries),
    )
    result = _append(
        result, phase=TransactionPhase.IR, action=TransactionAction.IR_PLACE,
        team_id=team_id, player_id=player_id, prior_team_id=team_id,
        resulting_team_id=team_id, prior_slot_id=entry.lineup_slot_id,
        resulting_slot_id=reserve_slot_id,
    )
    validate_evolving_state(result, snapshot)
    return result


def activate_from_ir(
    state: EvolvingLeagueState,
    snapshot: LeagueSnapshot,
    *,
    team_id: int,
    player_id: int,
    ordinary_slot_id: int,
    drop_player_id: int | None = None,
    evidence_source_id: str | None = None,
) -> EvolvingLeagueState:
    validate_evolving_state(state, snapshot)
    entry = next((item for item in state.roster_entries if item.player_id == player_id), None)
    if entry is None or entry.team_id != team_id:
        _fail(f"team {team_id} does not own player {player_id}")
    if _slot_map(snapshot)[entry.lineup_slot_id].kind is not SlotKind.RESERVE:
        _fail(f"player {player_id} is not currently in reserve")
    if state.ir_policy is IRPolicy.PROJECTION_BASED:
        projection = next(
            item.effective_projection for item in snapshot.player_weeks
            if item.player_id == player_id and item.scoring_week == state.scoring_week
        )
        if projection <= 0:
            _fail(f"player {player_id} lacks the positive projection required by projection_based activation")
    else:
        if evidence_source_id not in {item.source_id for item in snapshot.sources}:
            _fail("strict IR activation requires a valid separately verified evidence source")
    candidate = state if drop_player_id is None else drop_player(
        state, snapshot, team_id=team_id, player_id=drop_player_id,
        phase=TransactionPhase.ROSTER_CORRECTION,
    )
    slot = _slot_map(snapshot).get(ordinary_slot_id)
    player = _player_map(snapshot)[player_id]
    if slot is None or slot.kind is SlotKind.RESERVE or slot.capacity <= 0:
        _fail(f"slot {ordinary_slot_id} is not ordinary configured capacity")
    if ordinary_slot_id not in player.eligible_lineup_slot_ids:
        _fail(f"player {player_id} is ineligible for slot {ordinary_slot_id}")
    current = next(item for item in candidate.roster_entries if item.player_id == player_id)
    replacement = replace(current, lineup_slot_id=ordinary_slot_id)
    result = replace(
        candidate,
        roster_entries=_sorted_roster(replacement if item.player_id == player_id else item for item in candidate.roster_entries),
    )
    result = _append(
        result, phase=TransactionPhase.IR, action=TransactionAction.IR_ACTIVATE,
        team_id=team_id, player_id=player_id, related_player_id=drop_player_id,
        prior_team_id=team_id, resulting_team_id=team_id, prior_slot_id=entry.lineup_slot_id,
        resulting_slot_id=ordinary_slot_id,
        evidence_source_id=evidence_source_id,
        assumption_ids=(f"ir_policy:{state.ir_policy.value}",),
    )
    validate_evolving_state(result, snapshot)
    return result


def acquisition_blocking_ir_players(
    state: EvolvingLeagueState, snapshot: LeagueSnapshot
) -> tuple[int, ...]:
    """Return reserve occupants modeled recovered under the selected policy."""

    validate_evolving_state(state, snapshot)
    if state.ir_policy is IRPolicy.STRICT:
        return ()
    reserve_ids = {
        item.slot_id for item in snapshot.rules.lineup_slots if item.kind is SlotKind.RESERVE
    }
    projections = {
        item.player_id: item.effective_projection
        for item in snapshot.player_weeks
        if item.scoring_week == state.scoring_week
    }
    return tuple(sorted(
        entry.player_id for entry in state.roster_entries
        if entry.lineup_slot_id in reserve_ids and projections[entry.player_id] > 0
    ))


def apply_successful_waiver_priority(
    state: EvolvingLeagueState, snapshot: LeagueSnapshot, *, team_id: int
) -> EvolvingLeagueState:
    validate_evolving_state(state, snapshot)
    before = state.current_waiver_priority
    if team_id not in before:
        _fail(f"unknown waiver-priority team {team_id}")
    after = tuple(item for item in before if item != team_id) + (team_id,)
    result = replace(state, current_waiver_priority=after)
    result = _append(
        result, phase=TransactionPhase.WAIVER, action=TransactionAction.PRIORITY_MOVE,
        team_id=team_id, player_id=None, priority_before=before, priority_after=after,
        assumption_ids=("successful_traditional_claim_moves_to_last",),
    )
    validate_evolving_state(result, snapshot)
    return result


def apply_failed_waiver_claim(
    state: EvolvingLeagueState, snapshot: LeagueSnapshot, *, team_id: int
) -> EvolvingLeagueState:
    """Validate a failed claimant and leave priority/state byte-equivalent."""

    validate_evolving_state(state, snapshot)
    if team_id not in state.current_waiver_priority:
        _fail(f"unknown waiver-priority team {team_id}")
    return state


def reset_waiver_priority(
    state: EvolvingLeagueState, snapshot: LeagueSnapshot, *, ordered_team_ids: tuple[int, ...]
) -> EvolvingLeagueState:
    validate_evolving_state(state, snapshot)
    if snapshot.rules.acquisition.waiver_order_resets is not True:
        _fail("league does not have a verified waiver-order reset")
    if set(ordered_team_ids) != set(state.current_waiver_priority) or len(set(ordered_team_ids)) != len(ordered_team_ids):
        _fail("waiver reset must provide a complete unique team permutation")
    result = replace(
        state,
        current_waiver_priority=ordered_team_ids,
        initial_window_waiver_priority=ordered_team_ids,
    )
    result = _append(
        result, phase=TransactionPhase.CYCLE_BOUNDARY,
        action=TransactionAction.PRIORITY_MOVE, team_id=None, player_id=None,
        priority_before=state.current_waiver_priority, priority_after=ordered_team_ids,
        assumption_ids=("verified_weekly_waiver_reset_boundary",),
    )
    validate_evolving_state(result, snapshot)
    return result


def release_held_player(
    state: EvolvingLeagueState,
    snapshot: LeagueSnapshot,
    *,
    player_id: int,
    evidence_source_id: str,
) -> EvolvingLeagueState:
    """Release a held player only when the caller supplies verified boundary evidence."""

    validate_evolving_state(state, snapshot)
    available = _availability_map(state).get(player_id)
    if available is None or available.status is not AcquisitionAvailability.HOLD:
        _fail(f"player {player_id} is not held")
    if evidence_source_id not in {item.source_id for item in snapshot.sources}:
        _fail(f"unknown release evidence source {evidence_source_id!r}")
    released = PlayerAvailability(
        player_id, AcquisitionAvailability.FREE_AGENT, None, None, None, evidence_source_id
    )
    result = _replace_availability(state, released)
    result = _append(
        result, phase=TransactionPhase.CYCLE_BOUNDARY,
        action=TransactionAction.AVAILABILITY_RELEASE, team_id=None, player_id=player_id,
        prior_availability=available.status, resulting_availability=released.status,
        evidence_source_id=evidence_source_id,
    )
    validate_evolving_state(result, snapshot)
    return result


def advance_cycle(
    state: EvolvingLeagueState,
    snapshot: LeagueSnapshot,
    *,
    cycle_id: int,
    scoring_week: int,
) -> EvolvingLeagueState:
    validate_evolving_state(state, snapshot)
    if cycle_id <= state.cycle_id or scoring_week < state.scoring_week:
        _fail("cycle and scoring week cannot move backward")
    result = replace(state, cycle_id=cycle_id, scoring_week=scoring_week)
    result = _append(
        result, phase=TransactionPhase.CYCLE_BOUNDARY, action=TransactionAction.CYCLE_ADVANCE,
        team_id=None, player_id=None,
        assumption_ids=("weekly_transaction_window_v1",),
    )
    validate_evolving_state(result, snapshot)
    return result
