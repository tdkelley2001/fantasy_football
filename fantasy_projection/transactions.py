"""Shared ownership and roster validation for hypothetical transactions."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, Iterable

from .season import LeagueState, SeasonModelError

FREE_AGENTS = "FREE_AGENTS"
BENCH_SLOT_ID = 20


@dataclass(frozen=True)
class Transfer:
    player_id: int
    source: int | str
    destination: int | str


@dataclass(frozen=True)
class Transaction:
    transfers: tuple[Transfer, ...]
    effective_week: int


def _settings(state: LeagueState) -> dict[str, Any]:
    return state.settings_payload.get("settings", {}).get("rosterSettings", {})


def _limit(value: Any) -> int | None:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _validate_team_roster(state: LeagueState, team_id: int, rows: list[dict[str, Any]]) -> None:
    settings = _settings(state)
    slot_counts = {int(k): int(v) for k, v in settings.get("lineupSlotCounts", {}).items()}
    # Slot 21 is not an active-roster opening. Existing ESPN placements are
    # ignored for ordinary add/drop capacity, but this engine does not move them.
    active_limit = sum(count for slot, count in slot_counts.items() if slot != 21)
    active = [row for row in rows if row.get("current_lineup_slot_id") != 21]
    if slot_counts and len(active) > active_limit:
        raise SeasonModelError(
            f"Team {team_id} has {len(active)} active-roster players but only {active_limit} slots; "
            f"{len(active) - active_limit} drop(s) required."
        )

    limits = settings.get("positionLimits", {})
    for raw_position, raw_limit in limits.items():
        position, maximum = int(raw_position), _limit(raw_limit)
        if maximum is None:
            continue
        count = sum(row.get("default_position_id") == position for row in rows)
        if count > maximum:
            raise SeasonModelError(
                f"Team {team_id} exceeds the roster limit for position {position} ({count}/{maximum})."
            )


def apply_transaction(state: LeagueState, transaction: Transaction) -> LeagueState:
    """Validate an atomic transaction and return its isolated league state."""
    if not state.current_week <= transaction.effective_week <= state.final_week + 1:
        raise SeasonModelError("Effective week must be between the current week and season end + 1.")
    teams = {int(row["team_id"]): row["team_name"] for row in state.teams}
    rostered = {int(row["player_id"]): dict(row) for row in state.rosters}
    available = {int(row["player_id"]): dict(row) for row in state.available_players}
    ids = [move.player_id for move in transaction.transfers]
    if not ids or len(ids) != len(set(ids)):
        raise SeasonModelError("A transaction must move each selected player exactly once.")

    destinations: dict[int, int | str] = {}
    for move in transaction.transfers:
        if move.source != FREE_AGENTS and move.source not in teams:
            raise SeasonModelError("A transaction references an unknown source team.")
        if move.destination != FREE_AGENTS and move.destination not in teams:
            raise SeasonModelError("A transaction references an unknown destination team.")
        if move.source == move.destination:
            raise SeasonModelError("A player cannot move to its current participant.")
        if move.source == FREE_AGENTS:
            if move.player_id in rostered or move.player_id not in available:
                raise SeasonModelError(f"Player {move.player_id} is not a free agent or waiver player.")
        else:
            player = rostered.get(move.player_id)
            if player is None or int(player["team_id"]) != move.source:
                raise SeasonModelError(f"Team {move.source} does not own player {move.player_id}.")
            if move.destination == FREE_AGENTS:
                if not player.get("droppable", True):
                    raise SeasonModelError(f'{player["player_name"]} is undroppable on ESPN.')
                if player.get("lineup_locked") or player.get("roster_locked"):
                    raise SeasonModelError(f'{player["player_name"]} is currently locked on ESPN.')
        destinations[move.player_id] = move.destination

    rows = []
    new_available = dict(available)
    for player_id, player in rostered.items():
        destination = destinations.get(player_id, player["team_id"])
        if destination == FREE_AGENTS:
            released = dict(player, team_id=None, team_name=None, availability_status="FREEAGENT")
            new_available[player_id] = released
            continue
        moved = dict(player, team_id=destination, team_name=teams[int(destination)])
        if player_id in destinations:
            moved["current_lineup_slot_id"] = BENCH_SLOT_ID
        rows.append(moved)
    for player_id, destination in destinations.items():
        if player_id not in available or destination == FREE_AGENTS:
            continue
        acquired = dict(available[player_id], team_id=destination, team_name=teams[int(destination)],
                        current_lineup_slot_id=BENCH_SLOT_ID, acquisition_type="HYPOTHETICAL",
                        player_status="ONTEAM", droppable=True, lineup_locked=False, roster_locked=False)
        rows.append(acquired)
        new_available.pop(player_id, None)

    for team_id in teams:
        _validate_team_roster(state, team_id, [row for row in rows if int(row["team_id"]) == team_id])
    rows.sort(key=lambda row: (int(row["team_id"]), str(row.get("player_name") or "")))
    result = replace(state, rosters=deepcopy(rows),
                     baseline_rosters=deepcopy(state.baseline_rosters if state.baseline_rosters is not None else state.rosters))
    return replace(result, available_players=sorted(
        new_available.values(), key=lambda row: str(row.get("player_name") or "")
    ))


def trade_transaction(state: LeagueState, *, team_id: int, partner_id: int,
                      give: Iterable[int], receive: Iterable[int], effective_week: int,
                      team_drops: Iterable[int] = (), partner_drops: Iterable[int] = ()) -> Transaction:
    give, receive = tuple(give), tuple(receive)
    team_drops, partner_drops = tuple(team_drops), tuple(partner_drops)
    if not give or not receive:
        raise SeasonModelError("At least one player is required on each side of a trade.")
    return Transaction(tuple([Transfer(pid, team_id, partner_id) for pid in give] +
                             [Transfer(pid, partner_id, team_id) for pid in receive] +
                             [Transfer(pid, team_id, FREE_AGENTS) for pid in team_drops] +
                             [Transfer(pid, partner_id, FREE_AGENTS) for pid in partner_drops]), effective_week)


def waiver_transaction(state: LeagueState, *, team_id: int, add: int,
                       drop: int | None, effective_week: int) -> Transaction:
    moves = [Transfer(add, FREE_AGENTS, team_id)]
    if drop is not None:
        moves.append(Transfer(drop, team_id, FREE_AGENTS))
    return Transaction(tuple(moves), effective_week)
