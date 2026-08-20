from __future__ import annotations

import csv
import json
import math
import os
import time
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import requests
from dotenv import load_dotenv
from tqdm import tqdm


BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
TIMEOUT_SECONDS = 30
REQUEST_PAUSE_SECONDS = 0.10
PLAYER_LIMIT = 2000
NON_STARTER_SLOT_IDS = {20, 21}

UI_POWER_RANK = {
    "SOS (Susan, Only Serendipity)": 1,
    "Kinda Mid": 2,
    "Timberwolves": 3,
    "No Refills": 4,
    "All the Way to the EM-Zone": 5,
    "Big Joe": 6,
    "Ed's Plus 1 Team": 7,
    "Mike's Magic": 8,
    "BK Have it Your Way": 9,
    "Charley's Angels": 10,
    "Flux Capacitors": 11,
    "Kaitlyn's Deluxe Team": 12,
    "CB's Bulls": 13,
    "Cardiac Comebacks": 14,
}


def load_env() -> dict[str, Any]:
    load_dotenv()
    league_id = os.getenv("ESPN_LEAGUE_ID")
    if not league_id:
        raise RuntimeError("ESPN_LEAGUE_ID is missing from .env.")
    return {
        "league_id": int(league_id),
        "season": int(os.getenv("ESPN_SEASON", "2026")),
        "espn_s2": os.getenv("ESPN_S2"),
        "swid": os.getenv("ESPN_SWID"),
        "output_dir": Path(
            os.getenv("POWER_RANK_OUTPUT_DIR", "power_rank_output")
        ),
    }


def as_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class EspnClient:
    def __init__(self, cfg: dict[str, Any]):
        self.league_id = cfg["league_id"]
        self.season = cfg["season"]
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 ESPN Fantasy Power Rank Diagnostic",
                "Accept": "application/json,text/plain,*/*",
            }
        )
        if cfg["espn_s2"] and cfg["swid"]:
            self.session.cookies.update(
                {"espn_s2": cfg["espn_s2"], "SWID": cfg["swid"]}
            )

    @property
    def league_url(self) -> str:
        return (
            f"{BASE}/seasons/{self.season}/segments/0/"
            f"leagues/{self.league_id}"
        )

    def get(
        self,
        view: str,
        scoring_period_id: int | None = None,
        fantasy_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"view": view}
        if scoring_period_id is not None:
            params["scoringPeriodId"] = scoring_period_id

        headers = {}
        if fantasy_filter is not None:
            headers["X-Fantasy-Filter"] = json.dumps(fantasy_filter)

        r = self.session.get(
            self.league_url,
            params=params,
            headers=headers or None,
            timeout=TIMEOUT_SECONDS,
        )
        r.raise_for_status()
        payload = r.json()
        time.sleep(REQUEST_PAUSE_SECONDS)
        return payload


def find_player_nodes(obj: Any) -> Iterable[dict[str, Any]]:
    if isinstance(obj, dict):
        if "id" in obj and ("fullName" in obj or "stats" in obj):
            yield obj
        for value in obj.values():
            yield from find_player_nodes(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from find_player_nodes(value)


def norm_name(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fields = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def starter_slots(settings_payload: dict[str, Any]) -> list[int]:
    counts = settings_payload["settings"]["rosterSettings"]["lineupSlotCounts"]
    slots = []
    for raw_slot, raw_count in counts.items():
        slot = as_int(raw_slot)
        count = as_int(raw_count, 0) or 0
        if slot is None or count <= 0 or slot in NON_STARTER_SLOT_IDS:
            continue
        slots.extend([slot] * count)
    return slots


def optimize_lineup(
    roster: list[dict[str, Any]],
    slot_ids: list[int],
    projection_lookup: dict[tuple[int, int], float],
    week: int,
) -> float:
    slot_candidates = []
    for slot in slot_ids:
        eligible = [
            i for i, player in enumerate(roster)
            if slot in player["eligible_slots"]
        ]
        slot_candidates.append((slot, eligible))

    slot_candidates.sort(key=lambda x: len(x[1]))

    scores = [
        projection_lookup.get((p["player_id"], week), 0.0)
        for p in roster
    ]

    @lru_cache(maxsize=None)
    def solve(slot_index: int, used_mask: int) -> float:
        if slot_index == len(slot_candidates):
            return 0.0

        _, eligible = slot_candidates[slot_index]
        best = -math.inf

        for player_index in eligible:
            bit = 1 << player_index
            if used_mask & bit:
                continue

            best = max(
                best,
                scores[player_index]
                + solve(slot_index + 1, used_mask | bit),
            )

        return best

    result = solve(0, 0)
    if not math.isfinite(result):
        raise RuntimeError(f"No legal lineup for Week {week}.")
    return result


def pull_weekly_projections(
    client: EspnClient,
    first_week: int,
    final_week: int,
) -> list[dict[str, Any]]:
    filt = {
        "players": {
            "limit": PLAYER_LIMIT,
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
        }
    }

    rows = []

    for week in tqdm(
        range(first_week, final_week + 1),
        desc="Pulling weekly projections",
        unit="week",
        dynamic_ncols=True,
    ):
        payload = client.get(
            "kona_player_info",
            scoring_period_id=week,
            fantasy_filter=filt,
        )

        players = {}
        for player in find_player_nodes(payload):
            pid = as_int(player.get("id"))
            if pid is None:
                continue
            old = players.get(pid)
            if old is None or len(player.get("stats", [])) > len(old.get("stats", [])):
                players[pid] = player

        for pid, player in players.items():
            candidates = []
            for stat in player.get("stats", []):
                if not isinstance(stat, dict):
                    continue
                if as_int(stat.get("seasonId")) != client.season:
                    continue
                if as_int(stat.get("scoringPeriodId")) != week:
                    continue
                source = as_int(stat.get("statSourceId"))
                if source in (None, 0):
                    continue
                split = as_int(stat.get("statSplitTypeId"))
                candidates.append(
                    (0 if source == 1 and split == 1 else 1, stat)
                )

            if not candidates:
                continue

            candidates.sort(key=lambda x: x[0])
            stat = candidates[0][1]

            rows.append(
                {
                    "player_id": pid,
                    "week": week,
                    "projected_points": as_float(stat.get("appliedTotal")),
                }
            )

    deduped = {
        (r["player_id"], r["week"]): r
        for r in rows
    }
    return list(deduped.values())


def rank_desc(values: dict[int, float]) -> dict[int, int]:
    ordered = sorted(values.items(), key=lambda x: (-x[1], x[0]))
    return {
        team_id: rank
        for rank, (team_id, _) in enumerate(ordered, start=1)
    }


def spearman(
    target: dict[int, int],
    candidate: dict[int, int],
) -> float | None:
    ids = [t for t in target if t in candidate]
    n = len(ids)
    if n < 2:
        return None

    d2 = sum(
        (target[t] - candidate[t]) ** 2
        for t in ids
    )
    return 1 - (6 * d2) / (n * (n * n - 1))


def compare_ranks(
    metric: str,
    target: dict[int, int],
    candidate: dict[int, int],
) -> dict[str, Any]:
    ids = [t for t in target if t in candidate]
    errors = [abs(target[t] - candidate[t]) for t in ids]

    return {
        "metric": metric,
        "teams_compared": len(ids),
        "exact_rank_matches": sum(target[t] == candidate[t] for t in ids),
        "mean_absolute_rank_error": (
            sum(errors) / len(errors) if errors else None
        ),
        "max_absolute_rank_error": max(errors) if errors else None,
        "spearman_rank_correlation": spearman(target, candidate),
    }


def main() -> int:
    cfg = load_env()
    out = cfg["output_dir"]
    out.mkdir(parents=True, exist_ok=True)

    client = EspnClient(cfg)

    print("Pulling team, roster, and league settings...")
    team_payload = client.get("mTeam")
    roster_payload = client.get("mRoster")
    settings_payload = client.get("mSettings")

    status = roster_payload.get("status", {})
    current_week = (
        as_int(status.get("currentScoringPeriod"))
        or as_int(status.get("latestScoringPeriod"))
        or 1
    )
    final_week = as_int(status.get("finalScoringPeriod")) or 18
    regular_end = (
        as_int(
            settings_payload["settings"]["scheduleSettings"].get(
                "matchupPeriodCount"
            )
        )
        or 14
    )

    teams = []
    for team in team_payload.get("teams", []):
        teams.append(
            {
                "team_id": as_int(team.get("id")),
                "team_name": team.get("name"),
                "currentProjectedRank": as_int(
                    team.get("currentProjectedRank")
                ),
                "draftDayProjectedRank": as_int(
                    team.get("draftDayProjectedRank")
                ),
                "rankCalculatedFinal": as_int(
                    team.get("rankCalculatedFinal")
                ),
                "rankFinal": as_int(team.get("rankFinal")),
            }
        )

    name_to_id = {
        norm_name(t["team_name"]): t["team_id"]
        for t in teams
    }

    target = {}
    for name, rank in UI_POWER_RANK.items():
        team_id = name_to_id.get(norm_name(name))
        if team_id is None:
            raise RuntimeError(f"Could not match team: {name}")
        target[team_id] = rank

    direct_rows = []
    for team in teams:
        direct_rows.append(
            {
                **team,
                "espn_ui_power_rank": target[team["team_id"]],
                "current_rank_matches_ui": (
                    team["currentProjectedRank"]
                    == target[team["team_id"]]
                ),
            }
        )
    write_csv(out / "espn_team_rank_fields.csv", direct_rows)

    roster_by_team: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for team in roster_payload.get("teams", []):
        team_id = as_int(team.get("id"))

        for entry in team.get("roster", {}).get("entries", []):
            player = entry.get("playerPoolEntry", {}).get("player", {})
            pid = as_int(player.get("id"))
            if pid is None:
                continue

            roster_by_team[team_id].append(
                {
                    "player_id": pid,
                    "eligible_slots": [
                        int(x)
                        for x in player.get("eligibleSlots", [])
                        if as_int(x) is not None
                    ],
                    "current_lineup_slot_id": as_int(
                        entry.get("lineupSlotId")
                    ),
                }
            )

    projections = pull_weekly_projections(
        client,
        current_week,
        final_week,
    )
    projection_lookup = {
        (r["player_id"], r["week"]): r["projected_points"]
        for r in projections
    }

    slots = starter_slots(settings_payload)
    starter_slot_set = set(slots)

    weeks_all = list(range(current_week, final_week + 1))
    weeks_regular = list(
        range(current_week, min(regular_end, final_week) + 1)
    )
    weeks_post = list(
        range(max(current_week, regular_end + 1), final_week + 1)
    )

    metrics: dict[str, dict[int, float]] = defaultdict(dict)

    for team in tqdm(
        teams,
        desc="Calculating team metrics",
        unit="team",
        dynamic_ncols=True,
    ):
        team_id = team["team_id"]
        roster = roster_by_team[team_id]

        optimized = {
            w: optimize_lineup(roster, slots, projection_lookup, w)
            for w in weeks_all
        }

        metrics["optimized_current_week"][team_id] = optimized[current_week]
        metrics["optimized_full_remaining_season"][team_id] = sum(
            optimized[w] for w in weeks_all
        )
        metrics["optimized_regular_season"][team_id] = sum(
            optimized[w] for w in weeks_regular
        )
        metrics["optimized_postseason_window"][team_id] = sum(
            optimized[w] for w in weeks_post
        )

        current_starters = [
            p for p in roster
            if p["current_lineup_slot_id"] in starter_slot_set
        ]
        current_bench = [
            p for p in roster
            if p["current_lineup_slot_id"] not in starter_slot_set
        ]

        metrics["current_starters_full_remaining"][team_id] = sum(
            projection_lookup.get((p["player_id"], w), 0.0)
            for p in current_starters
            for w in weeks_all
        )
        metrics["current_bench_full_remaining"][team_id] = sum(
            projection_lookup.get((p["player_id"], w), 0.0)
            for p in current_bench
            for w in weeks_all
        )
        metrics["entire_roster_full_remaining"][team_id] = sum(
            projection_lookup.get((p["player_id"], w), 0.0)
            for p in roster
            for w in weeks_all
        )

    candidate_ranks = {}
    comparison_rows = []

    for name, values in metrics.items():
        ranks = rank_desc(values)
        candidate_ranks[name] = ranks
        comparison_rows.append(compare_ranks(name, target, ranks))

    for name, field in [
        ("espn_currentProjectedRank", "currentProjectedRank"),
        ("espn_draftDayProjectedRank", "draftDayProjectedRank"),
    ]:
        ranks = {
            t["team_id"]: t[field]
            for t in teams
            if t[field] is not None
        }
        comparison_rows.append(compare_ranks(name, target, ranks))

    blend_rows = []

    def test_blend(
        blend_name: str,
        metric_a: str,
        metric_b: str,
        weight_a: float,
    ) -> None:
        values = {
            team_id: (
                weight_a * metrics[metric_a][team_id]
                + (1 - weight_a) * metrics[metric_b][team_id]
            )
            for team_id in target
        }

        ranks = rank_desc(values)
        result = compare_ranks(blend_name, target, ranks)

        blend_rows.append(
            {
                "blend_name": blend_name,
                "metric_a": metric_a,
                "metric_b": metric_b,
                "weight_a": weight_a,
                "weight_b": 1 - weight_a,
                **result,
            }
        )

    for weight_int in range(0, 101, 5):
        w = weight_int / 100

        test_blend(
            "starter_bench_blend",
            "current_starters_full_remaining",
            "current_bench_full_remaining",
            w,
        )
        test_blend(
            "current_week_ros_blend",
            "optimized_current_week",
            "optimized_full_remaining_season",
            w,
        )
        test_blend(
            "regular_postseason_blend",
            "optimized_regular_season",
            "optimized_postseason_window",
            w,
        )

    blend_rows.sort(
        key=lambda r: (
            -(r["spearman_rank_correlation"] or -999),
            r["mean_absolute_rank_error"] or math.inf,
        )
    )

    comparison_rows.sort(
        key=lambda r: (
            -(r["spearman_rank_correlation"] or -999),
            r["mean_absolute_rank_error"] or math.inf,
        )
    )

    details = []
    team_by_id = {t["team_id"]: t for t in teams}

    for team_id, ui_rank in sorted(target.items(), key=lambda x: x[1]):
        team = team_by_id[team_id]

        row = {
            "espn_ui_power_rank": ui_rank,
            "team_id": team_id,
            "team_name": team["team_name"],
            "currentProjectedRank": team["currentProjectedRank"],
            "draftDayProjectedRank": team["draftDayProjectedRank"],
        }

        for name, values in metrics.items():
            row[f"{name}_value"] = values[team_id]
            row[f"{name}_rank"] = candidate_ranks[name][team_id]

        details.append(row)

    write_csv(out / "candidate_metric_comparison.csv", comparison_rows)
    write_csv(out / "team_metric_details.csv", details)
    write_csv(out / "simple_blend_search.csv", blend_rows)

    direct_matches = sum(
        row["current_rank_matches_ui"]
        for row in direct_rows
    )

    lines = [
        "ESPN POWER RANK DIAGNOSTIC",
        "=" * 72,
        "",
        f"Direct currentProjectedRank matches UI: "
        f"{direct_matches}/{len(direct_rows)}",
        "",
        "Top candidate metrics:",
        "",
    ]

    for row in comparison_rows[:15]:
        corr = row["spearman_rank_correlation"]
        mae = row["mean_absolute_rank_error"]

        lines.append(
            f'{row["metric"]:<42} '
            f'corr={corr:.4f} '
            f'MAE={mae:.3f} '
            f'exact={row["exact_rank_matches"]}/{row["teams_compared"]}'
        )

    summary = "\n".join(lines)
    print()
    print(summary)

    (out / "diagnostic_summary.txt").write_text(
        summary,
        encoding="utf-8",
    )

    print()
    print(f"Saved diagnostics to: {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
