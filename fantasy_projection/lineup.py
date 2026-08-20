from __future__ import annotations

import math
from functools import lru_cache
from typing import Any


def optimize_lineup(
    roster_players: list[dict[str, Any]],
    starter_slots: list[dict[str, Any]],
    projection_lookup: dict[tuple[int, int], float],
    week: int,
) -> tuple[float, list[dict[str, Any]]]:
    """Exact maximum-projection lineup under ESPN slot eligibility."""
    if not roster_players:
        raise RuntimeError("Cannot optimize an empty roster.")

    slot_candidates = []

    for slot in starter_slots:
        eligible = [
            i
            for i, player in enumerate(roster_players)
            if slot["slot_id"] in player["eligible_slots"]
        ]
        slot_candidates.append((slot, eligible))

    # Solve restrictive positions first.
    slot_candidates.sort(
        key=lambda item: (
            len(item[1]),
            item[0]["slot_id"],
            item[0]["slot_instance"],
        )
    )

    impossible = [
        slot
        for slot, candidates in slot_candidates
        if not candidates
    ]
    if impossible:
        labels = ", ".join(
            f'{x["slot_name"]}#{x["slot_instance"]}'
            for x in impossible
        )
        raise RuntimeError(
            f"Roster cannot fill starter slot(s): {labels}"
        )

    scores = [
        projection_lookup.get((p["player_id"], week), 0.0)
        for p in roster_players
    ]

    @lru_cache(maxsize=None)
    def solve(
        slot_index: int,
        used_mask: int,
    ) -> tuple[float, tuple[int, ...]]:
        if slot_index == len(slot_candidates):
            return 0.0, ()

        _, candidates = slot_candidates[slot_index]
        best_score = -math.inf
        best_assignment = None

        for player_index in candidates:
            bit = 1 << player_index
            if used_mask & bit:
                continue

            remainder, assignment = solve(
                slot_index + 1,
                used_mask | bit,
            )
            total = scores[player_index] + remainder

            if total > best_score:
                best_score = total
                best_assignment = (
                    player_index,
                    *assignment,
                )

        if best_assignment is None:
            return -math.inf, ()

        return best_score, best_assignment

    total_score, assignment = solve(0, 0)

    if not math.isfinite(total_score):
        raise RuntimeError(
            "No legal complete starting lineup could be constructed."
        )

    rows = []

    for (slot, _), player_index in zip(
        slot_candidates,
        assignment,
        strict=True,
    ):
        player = roster_players[player_index]
        rows.append(
            {
                "slot_id": slot["slot_id"],
                "slot_name": slot["slot_name"],
                "slot_instance": slot["slot_instance"],
                "player_id": player["player_id"],
                "player_name": player["player_name"],
                "projected_points": scores[player_index],
            }
        )

    rows.sort(
        key=lambda x: (
            x["slot_id"],
            x["slot_instance"],
        )
    )

    return total_score, rows


def project_weekly_lineups(
    teams: list[dict[str, Any]],
    rosters: list[dict[str, Any]],
    player_projections: list[dict[str, Any]],
    starter_slots: list[dict[str, Any]],
    *,
    first_week: int,
    final_week: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    roster_by_team: dict[int, list[dict[str, Any]]] = {}

    for player in rosters:
        roster_by_team.setdefault(
            player["team_id"],
            [],
        ).append(player)

    projection_lookup = {
        (row["player_id"], row["week"]):
            row["projected_points"]
        for row in player_projections
    }

    optimal_lineups = []
    weekly_team_projections = []

    for team in teams:
        team_id = team["team_id"]
        roster = roster_by_team.get(team_id, [])

        for week in range(first_week, final_week + 1):
            total, lineup = optimize_lineup(
                roster,
                starter_slots,
                projection_lookup,
                week,
            )

            weekly_team_projections.append(
                {
                    "team_id": team_id,
                    "team_name": team["team_name"],
                    "week": week,
                    "projected_points": total,
                }
            )

            for row in lineup:
                optimal_lineups.append(
                    {
                        "team_id": team_id,
                        "team_name": team["team_name"],
                        "week": week,
                        **row,
                    }
                )

    return optimal_lineups, weekly_team_projections
