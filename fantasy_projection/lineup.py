from __future__ import annotations

import math
from collections import Counter
from functools import lru_cache
from typing import Any


STANDARD_STARTER_SLOT_COUNTS = {
    0: 1,
    2: 2,
    4: 2,
    6: 1,
    16: 1,
    17: 1,
    23: 1,
}


def _standard_lineup_scores(
    roster_players: list[dict[str, Any]],
    starter_slots: list[dict[str, Any]],
    projection_lookup: dict[tuple[int, int], float],
    weeks: tuple[int, ...],
) -> tuple[float, ...] | None:
    """Fast exact path for the common QB/2RB/2WR/TE/FLEX/K/DST format."""
    counts = Counter(int(slot["slot_id"]) for slot in starter_slots)
    if dict(counts) != STANDARD_STARTER_SLOT_COUNTS:
        return None

    group_slots = {"QB": 0, "RB": 2, "WR": 4, "TE": 6, "DST": 16, "K": 17}
    groups: dict[str, list[dict[str, Any]]] = {
        name: [] for name in group_slots
    }
    for player in roster_players:
        eligible = set(player["eligible_slots"])
        matching = [
            name for name, slot_id in group_slots.items()
            if slot_id in eligible
        ]
        if len(matching) > 1:
            return None
        # The shortcut assumes precisely RB/WR/TE flex eligibility. Custom
        # eligibility (including flex-only players) needs the general solver.
        if (23 in eligible) != bool(matching and matching[0] in {"RB", "WR", "TE"}):
            return None
        if matching:
            groups[matching[0]].append(player)

    required = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "DST": 1, "K": 1}
    if any(len(groups[name]) < count for name, count in required.items()):
        return None

    totals = []
    for week in weeks:
        values = {
            name: sorted(
                (
                    projection_lookup.get(
                        (player["player_id"], week), 0.0
                    )
                    for player in players
                ),
                reverse=True,
            )
            for name, players in groups.items()
        }
        skill_base = (
            sum(values["RB"][:2])
            + sum(values["WR"][:2])
            + values["TE"][0]
        )
        flex_candidates = [
            values["RB"][2] if len(values["RB"]) > 2 else -math.inf,
            values["WR"][2] if len(values["WR"]) > 2 else -math.inf,
            values["TE"][1] if len(values["TE"]) > 1 else -math.inf,
        ]
        flex = max(flex_candidates)
        if not math.isfinite(flex):
            return None
        totals.append(
            values["QB"][0]
            + skill_base
            + flex
            + values["DST"][0]
            + values["K"][0]
        )
    return tuple(totals)


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


def optimize_lineup_weeks(
    roster_players: list[dict[str, Any]],
    starter_slots: list[dict[str, Any]],
    projection_lookup: dict[tuple[int, int], float],
    weeks: tuple[int, ...],
) -> tuple[float, ...]:
    """Return exact optimal scores for several weeks in one assignment DP.

    Slot eligibility is identical across weeks, while the maximizing player
    assignment may differ by week. Each dynamic-programming state therefore
    carries a vector whose components are independently maximized.
    """
    if not roster_players:
        raise RuntimeError("Cannot optimize an empty roster.")
    if not weeks:
        return ()

    standard = _standard_lineup_scores(
        roster_players,
        starter_slots,
        projection_lookup,
        weeks,
    )
    if standard is not None:
        return standard

    slot_candidates = []
    for slot in starter_slots:
        eligible = [
            index
            for index, player in enumerate(roster_players)
            if slot["slot_id"] in player["eligible_slots"]
        ]
        slot_candidates.append((slot, eligible))
    slot_candidates.sort(
        key=lambda item: (
            len(item[1]),
            item[0]["slot_id"],
            item[0]["slot_instance"],
        )
    )

    impossible = [
        slot for slot, candidates in slot_candidates if not candidates
    ]
    if impossible:
        labels = ", ".join(
            f'{slot["slot_name"]}#{slot["slot_instance"]}'
            for slot in impossible
        )
        raise RuntimeError(
            f"Roster cannot fill starter slot(s): {labels}"
        )

    player_scores = [
        tuple(
            projection_lookup.get((player["player_id"], week), 0.0)
            for week in weeks
        )
        for player in roster_players
    ]
    impossible_scores = tuple(-math.inf for _ in weeks)
    zero_scores = tuple(0.0 for _ in weeks)

    @lru_cache(maxsize=None)
    def solve(slot_index: int, used_mask: int) -> tuple[float, ...]:
        if slot_index == len(slot_candidates):
            return zero_scores

        _, candidates = slot_candidates[slot_index]
        best = list(impossible_scores)
        found = False
        for player_index in candidates:
            bit = 1 << player_index
            if used_mask & bit:
                continue
            remainder = solve(slot_index + 1, used_mask | bit)
            if not math.isfinite(remainder[0]):
                continue
            found = True
            scores = player_scores[player_index]
            for index in range(len(weeks)):
                best[index] = max(best[index], scores[index] + remainder[index])
        return tuple(best) if found else impossible_scores

    result = solve(0, 0)
    if any(not math.isfinite(score) for score in result):
        raise RuntimeError(
            "No legal complete starting lineup could be constructed."
        )
    return result
