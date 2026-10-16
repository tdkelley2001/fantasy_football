"""One-time best-available fills for hypothetical incomplete rosters."""
from __future__ import annotations

from dataclasses import replace

from .lineup import optimize_lineup_weeks
from .season import LeagueState
from .transactions import apply_transaction, waiver_transaction


def fill_open_roster_slots(state: LeagueState, team_ids, *, effective_week: int,
                           target_size: int = 17):
    """Greedily fill teams to target_size by marginal optimized lineup points.

    Each free agent is selected once at the effective week. There is no weekly
    streaming. Candidates that violate ESPN roster limits are ignored.
    """
    state = replace(state, available_players=list(state.available_players))
    weeks = tuple(range(effective_week, state.final_week + 1))
    projection_lookup = {(r["player_id"], r["week"]): r["projected_points"]
                         for r in state.player_projections
                         if r.get("projected_points") is not None}
    additions = []
    for team_id in team_ids:
        while sum(int(r["team_id"]) == int(team_id) for r in state.rosters) < target_size:
            best = None
            for player in state.available_players:
                player_id = int(player["player_id"])
                try:
                    candidate = apply_transaction(state, waiver_transaction(
                        state, team_id=int(team_id), add=player_id, drop=None,
                        effective_week=effective_week))
                    roster = [r for r in candidate.rosters if int(r["team_id"]) == int(team_id)]
                    scores = optimize_lineup_weeks(roster, candidate.starter_slots,
                                                   projection_lookup, weeks)
                except (RuntimeError, ValueError):
                    continue
                rank = (sum(scores), sum(projection_lookup.get((player_id, week), 0.0)
                                         for week in weeks), -player_id)
                if best is None or rank > best[0]:
                    best = (rank, candidate, player)
            if best is None:
                break
            _, state, player = best
            additions.append({"team_id": int(team_id), "player_id": int(player["player_id"]),
                              "player_name": player.get("player_name")})
    return state, additions
