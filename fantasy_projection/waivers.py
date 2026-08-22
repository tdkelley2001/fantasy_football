from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from tqdm import tqdm

from .espn import as_int
from .league_data import get_roster_settings
from .pipeline import ProjectionResult
from .trades import (
    EPSILON,
    _phase_lineup_metrics,
    _playoff_path,
    _projected_game_flip_metrics,
    _projection_lookup,
    _score_roster_weeks,
    _scenario_metrics,
    _team_metrics,
    _weekly_lineup_metrics,
)


DEFAULT_POSITION_NAMES = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    16: "D/ST",
}


@dataclass
class WaiverAnalysisResult:
    available_players: list[dict[str, Any]]
    transactions: list[dict[str, Any]]
    marginal_roster_values: list[dict[str, Any]]
    summary: dict[str, Any]


def _position_name(player: dict[str, Any]) -> str:
    position_id = player.get("default_position_id")
    return DEFAULT_POSITION_NAMES.get(
        position_id, f"POSITION_{position_id}"
    )


def _position_limit_allows(
    new_player_ids: frozenset[int],
    *,
    baseline_player_ids: frozenset[int],
    players: dict[int, dict[str, Any]],
    settings_payload: dict[str, Any],
) -> bool:
    limits = get_roster_settings(settings_payload).get(
        "positionLimits", {}
    )
    if not isinstance(limits, dict):
        return True

    before_counts = Counter(
        players[player_id].get("default_position_id")
        for player_id in baseline_player_ids
    )
    after_counts = Counter(
        players[player_id].get("default_position_id")
        for player_id in new_player_ids
    )

    for raw_position_id, raw_limit in limits.items():
        position_id = as_int(raw_position_id)
        limit = as_int(raw_limit)
        if position_id is None or limit is None or limit < 0:
            continue
        if (
            after_counts[position_id] > limit
            and after_counts[position_id] > before_counts[position_id]
        ):
            return False
    return True


def _projection_values(
    player_id: int,
    weeks: tuple[int, ...],
    lookup: dict[tuple[int, int], float],
) -> tuple[float, ...]:
    return tuple(lookup.get((player_id, week), 0.0) for week in weeks)


def _available_player_rows(
    available_players: list[dict[str, Any]],
    *,
    rostered_ids: set[int],
    projection_lookup: dict[tuple[int, int], float],
    future_weeks: tuple[int, ...],
    regular_weeks: tuple[int, ...],
    postseason_weeks: tuple[int, ...],
    starter_slot_ids: set[int],
) -> tuple[list[dict[str, Any]], list[int], Counter[str]]:
    rows = []
    candidates = []
    exclusions: Counter[str] = Counter()

    for player in available_players:
        player_id = int(player["player_id"])
        future = _projection_values(
            player_id, future_weeks, projection_lookup
        )
        regular = _projection_values(
            player_id, regular_weeks, projection_lookup
        )
        postseason = _projection_values(
            player_id, postseason_weeks, projection_lookup
        )
        eligible_starter_slots = sorted(
            set(player.get("eligible_slots", [])) & starter_slot_ids
        )

        reason = ""
        if player_id in rostered_ids:
            reason = "ALREADY_ROSTERED"
        elif not eligible_starter_slots:
            reason = "NO_ELIGIBLE_STARTER_SLOT"
        elif not any(points > EPSILON for points in future):
            reason = "NO_POSITIVE_REMAINING_PROJECTION"

        if reason:
            exclusions[reason] += 1
        else:
            candidates.append(player_id)

        rows.append(
            {
                **player,
                "position": _position_name(player),
                "eligible_starter_slots": ",".join(
                    map(str, eligible_starter_slots)
                ),
                "current_week_projected_points": future[0],
                "avg_remaining_projected_points": (
                    sum(future) / len(future)
                ),
                "total_remaining_projected_points": sum(future),
                "regular_season_projected_points": sum(regular),
                "playoff_window_projected_points": sum(postseason),
                "evaluated_as_add_candidate": not reason,
                "exclusion_reason": reason,
            }
        )

    return rows, candidates, exclusions


def _move_tags(record: dict[str, Any]) -> list[str]:
    tags = []
    if record["team_current_week_lineup_gain"] > EPSILON:
        tags.append("IMMEDIATE_UPGRADE")
    if record["team_total_remaining_season_lineup_gain"] > EPSILON:
        tags.append("ROS_UPGRADE")
    if (
        record["team_positive_weeks"] > 0
        and record["team_median_weekly_lineup_gain"] <= EPSILON
    ):
        tags.append("BYE_OR_DEPTH_IMPROVEMENT")
    if record["team_playoff_window_total_lineup_gain"] > EPSILON:
        tags.append("PLAYOFF_WINDOW_UPGRADE")
    if (
        record["team_playoff_window_total_lineup_gain"] > EPSILON
        and record["team_regular_season_total_lineup_gain"] <= EPSILON
    ):
        tags.append("PLAYOFF_STASH")
    if record["team_projected_game_flips"] > 0:
        tags.append("FLIPS_PROJECTED_GAME")
    if record["team_projected_wins_change"] > 0:
        tags.append("ADDS_PROJECTED_WIN")
    if record["team_regular_seed_improvement"] > 0:
        tags.append("IMPROVES_SEED")
    if record["team_final_place_improvement"] > 0:
        tags.append("IMPROVES_FINAL_POSITION")
    return tags


def _marginal_roster_values(
    transactions: list[dict[str, Any]],
    roster: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    valid = [
        row for row in transactions
        if row["evaluation_status"] == "VALID"
    ]
    by_drop: dict[int, list[dict[str, Any]]] = {}
    for row in valid:
        by_drop.setdefault(row["drop_player_id"], []).append(row)

    result = []
    for player in roster:
        drop_id = int(player["player_id"])
        options = by_drop.get(drop_id, [])
        if not options:
            result.append(
                {
                    "rostered_player_id": drop_id,
                    "rostered_player": player["player_name"],
                    "position": _position_name(player),
                    "marginal_value_status": (
                        "NO_EXECUTABLE_REPLACEMENT"
                    ),
                    "droppable": player.get("droppable", True),
                    "lineup_locked": player.get(
                        "lineup_locked", False
                    ),
                    "roster_locked": player.get(
                        "roster_locked", False
                    ),
                }
            )
            continue

        def replacement_key(row: dict[str, Any]) -> tuple[Any, ...]:
            return (
                row["team_total_remaining_season_lineup_gain"],
                row["team_final_place_improvement"],
                row["team_projected_wins_change"],
                row["team_playoff_window_total_lineup_gain"],
                row["team_current_week_lineup_gain"],
                -row["add_player_id"],
            )

        best = max(options, key=replacement_key)
        same_position = [
            row for row in options if row["same_position_swap"]
        ]
        best_same = (
            max(same_position, key=replacement_key)
            if same_position
            else None
        )

        row = {
            "rostered_player_id": drop_id,
            "rostered_player": player["player_name"],
            "position": _position_name(player),
            "marginal_value_status": "CALCULATED",
            "droppable": player.get("droppable", True),
            "lineup_locked": player.get("lineup_locked", False),
            "roster_locked": player.get("roster_locked", False),
            "best_available_replacement_id": best["add_player_id"],
            "best_available_replacement": best["add_player"],
            "best_replacement_position": best["add_position"],
            "marginal_current_week_lineup_value": (
                -best["team_current_week_lineup_gain"]
            ),
            "marginal_avg_weekly_lineup_value": (
                -best["team_avg_remaining_season_lineup_gain"]
            ),
            "marginal_total_remaining_lineup_value": (
                -best["team_total_remaining_season_lineup_gain"]
            ),
            "marginal_regular_season_lineup_value": (
                -best["team_regular_season_total_lineup_gain"]
            ),
            "marginal_playoff_window_lineup_value": (
                -best["team_playoff_window_total_lineup_gain"]
            ),
            "best_replacement_projected_wins_change": best[
                "team_projected_wins_change"
            ],
            "best_replacement_seed_improvement": best[
                "team_regular_seed_improvement"
            ],
            "best_replacement_final_place_improvement": best[
                "team_final_place_improvement"
            ],
        }
        if best_same is not None:
            row.update(
                {
                    "best_same_position_replacement_id": best_same[
                        "add_player_id"
                    ],
                    "best_same_position_replacement": best_same[
                        "add_player"
                    ],
                    "marginal_avg_value_vs_same_position": (
                        -best_same[
                            "team_avg_remaining_season_lineup_gain"
                        ]
                    ),
                    "marginal_total_value_vs_same_position": (
                        -best_same[
                            "team_total_remaining_season_lineup_gain"
                        ]
                    ),
                }
            )
        result.append(row)

    result.sort(
        key=lambda row: (
            row["marginal_value_status"] != "CALCULATED",
            -row.get("marginal_avg_weekly_lineup_value", 0.0),
            row["position"],
            row["rostered_player"],
        )
    )
    for rank, row in enumerate(result, start=1):
        row["marginal_roster_value_rank"] = rank
    return result


def analyze_waivers(
    *,
    baseline: ProjectionResult,
    my_team_id: int,
    available_players: list[dict[str, Any]],
) -> WaiverAnalysisResult:
    """Evaluate every sensible add/drop against the baseline projection."""
    names = {
        row["team_id"]: row["team_name"] for row in baseline.teams
    }
    if my_team_id not in names:
        raise RuntimeError(
            f"MY_TEAM_ID={my_team_id} was not found in this league."
        )

    current_week = int(baseline.summary["current_scoring_period"])
    final_week = int(baseline.summary["final_scoring_period"])
    regular_end = int(
        baseline.summary["regular_season_matchup_periods"]
    )
    future_weeks = tuple(range(current_week, final_week + 1))
    if not future_weeks:
        raise RuntimeError("No scoring weeks remain to analyze waivers.")
    regular_weeks = tuple(
        week for week in future_weeks if week <= regular_end
    )
    postseason_weeks = tuple(
        week for week in future_weeks if week > regular_end
    )

    my_roster = [
        row for row in baseline.rosters if row["team_id"] == my_team_id
    ]
    drop_candidates = [
        row
        for row in my_roster
        if row.get("droppable", True)
        and not row.get("roster_locked", False)
        and not row.get("lineup_locked", False)
    ]
    baseline_ids = frozenset(
        int(row["player_id"]) for row in my_roster
    )
    rostered_ids = {
        int(row["player_id"]) for row in baseline.rosters
    }
    players = {
        int(row["player_id"]): row for row in baseline.rosters
    }
    for row in available_players:
        players.setdefault(int(row["player_id"]), row)
    projection_lookup = _projection_lookup(baseline.player_projections)
    starter_slot_ids = {
        int(row["slot_id"]) for row in baseline.starter_slots
    }
    (
        available_rows,
        candidate_ids,
        exclusions,
    ) = _available_player_rows(
        available_players,
        rostered_ids=rostered_ids,
        projection_lookup=projection_lookup,
        future_weeks=future_weeks,
        regular_weeks=regular_weeks,
        postseason_weeks=postseason_weeks,
        starter_slot_ids=starter_slot_ids,
    )

    baseline_weekly = {
        (row["team_id"], row["week"]): row["projected_points"]
        for row in baseline.weekly_team_projections
    }
    baseline_scores = tuple(
        baseline_weekly[(my_team_id, week)] for week in future_weeks
    )
    baseline_all_metrics = _team_metrics(baseline)
    baseline_metrics = baseline_all_metrics[my_team_id]
    score_cache: dict[
        tuple[frozenset[int], tuple[int, ...]], tuple[float, ...]
    ] = {}
    scenario_cache: dict[tuple[float, ...], tuple[Any, ...]] = {
        baseline_scores: (
            baseline_all_metrics,
            baseline.summary,
            baseline.regular_season_matchups,
            baseline.postseason_matchups,
        )
    }
    transactions = []
    invalid_lineups = 0
    illegal_position_limits = 0
    total_pairs = len(candidate_ids) * len(drop_candidates)

    progress = tqdm(
        total=total_pairs,
        desc="Evaluating add/drop transactions",
        unit="move",
        dynamic_ncols=True,
    )
    for add_id in candidate_ids:
        add_player = players[add_id]
        add_projections = _projection_values(
            add_id, future_weeks, projection_lookup
        )

        for drop_player in drop_candidates:
            drop_id = int(drop_player["player_id"])
            drop_projections = _projection_values(
                drop_id, future_weeks, projection_lookup
            )
            new_ids = frozenset((baseline_ids - {drop_id}) | {add_id})
            base_record = {
                "add_player_id": add_id,
                "add_player": add_player["player_name"],
                "add_position": _position_name(add_player),
                "add_availability_status": add_player.get(
                    "availability_status"
                ),
                "add_injury_status": add_player.get("injury_status"),
                "add_percent_owned": add_player.get("percent_owned"),
                "add_current_week_projection": add_projections[0],
                "add_total_remaining_projection": sum(add_projections),
                "drop_player_id": drop_id,
                "drop_player": drop_player["player_name"],
                "drop_position": _position_name(drop_player),
                "drop_injury_status": drop_player.get("injury_status"),
                "drop_current_week_projection": drop_projections[0],
                "drop_total_remaining_projection": sum(drop_projections),
                "same_position_swap": (
                    add_player.get("default_position_id")
                    == drop_player.get("default_position_id")
                ),
            }

            if not _position_limit_allows(
                new_ids,
                baseline_player_ids=baseline_ids,
                players=players,
                settings_payload=baseline.settings_payload,
            ):
                illegal_position_limits += 1
                progress.update(1)
                continue

            try:
                after_scores = _score_roster_weeks(
                    new_ids,
                    team_id=my_team_id,
                    team_name=names[my_team_id],
                    weeks=future_weeks,
                    players=players,
                    starter_slots=baseline.starter_slots,
                    projection_lookup=projection_lookup,
                    cache=score_cache,
                )
            except RuntimeError as exc:
                invalid_lineups += 1
                transactions.append(
                    {
                        **base_record,
                        "evaluation_status": "INVALID_LINEUP",
                        "invalid_reason": str(exc),
                    }
                )
                progress.update(1)
                continue

            record = {
                **base_record,
                "evaluation_status": "VALID",
                "invalid_reason": "",
                "current_scoring_week": current_week,
                "remaining_scoring_weeks": len(future_weeks),
                **_weekly_lineup_metrics(
                    "team", baseline_scores, after_scores, future_weeks
                ),
                **_phase_lineup_metrics(
                    "team",
                    "regular_season",
                    baseline_scores,
                    after_scores,
                    future_weeks,
                    regular_weeks,
                ),
                **_phase_lineup_metrics(
                    "team",
                    "playoff_window",
                    baseline_scores,
                    after_scores,
                    future_weeks,
                    postseason_weeks,
                ),
            }

            replacements = {
                (my_team_id, week): score
                for week, score in zip(
                    future_weeks, after_scores, strict=True
                )
            }
            scenario = scenario_cache.get(after_scores)
            if scenario is None:
                scenario = _scenario_metrics(baseline, replacements)
                scenario_cache[after_scores] = scenario
            (
                scenario_metrics,
                postseason_summary,
                scenario_regular_matchups,
                scenario_postseason_matchups,
            ) = scenario
            after_metrics = scenario_metrics[my_team_id]
            record.update(
                {
                    "team_projected_wins_before": baseline_metrics["wins"],
                    "team_projected_wins_after": after_metrics["wins"],
                    "team_projected_wins_change": (
                        after_metrics["wins"] - baseline_metrics["wins"]
                    ),
                    **_projected_game_flip_metrics(
                        "team",
                        my_team_id,
                        baseline.regular_season_matchups,
                        scenario_regular_matchups,
                    ),
                    "team_regular_seed_before": baseline_metrics[
                        "regular_seed"
                    ],
                    "team_regular_seed_after": after_metrics[
                        "regular_seed"
                    ],
                    "team_regular_seed_improvement": (
                        baseline_metrics["regular_seed"]
                        - after_metrics["regular_seed"]
                    ),
                    "team_made_playoffs_before": (
                        baseline_metrics["regular_seed"]
                        <= int(baseline.summary["playoff_team_count"])
                    ),
                    "team_made_playoffs_after": (
                        after_metrics["regular_seed"]
                        <= int(baseline.summary["playoff_team_count"])
                    ),
                    "team_playoff_path_before": _playoff_path(
                        my_team_id, baseline.postseason_matchups
                    ),
                    "team_playoff_path_after": _playoff_path(
                        my_team_id, scenario_postseason_matchups
                    ),
                    "team_final_place_before": baseline_metrics[
                        "final_place"
                    ],
                    "team_final_place_after": after_metrics["final_place"],
                    "team_final_place_improvement": (
                        baseline_metrics["final_place"]
                        - after_metrics["final_place"]
                    ),
                    "projected_champion_before": baseline.summary[
                        "champion_team"
                    ],
                    "projected_champion_after": postseason_summary[
                        "champion_team"
                    ],
                }
            )
            tags = _move_tags(record)
            record.update(
                {
                    "immediate_upgrade": "IMMEDIATE_UPGRADE" in tags,
                    "ros_upgrade": "ROS_UPGRADE" in tags,
                    "bye_or_depth_improvement": (
                        "BYE_OR_DEPTH_IMPROVEMENT" in tags
                    ),
                    "playoff_stash": "PLAYOFF_STASH" in tags,
                    "flips_projected_game": (
                        "FLIPS_PROJECTED_GAME" in tags
                    ),
                    "improves_final_position": (
                        "IMPROVES_FINAL_POSITION" in tags
                    ),
                    "move_tags": " | ".join(tags),
                }
            )
            transactions.append(record)
            progress.update(1)

    progress.close()

    valid = [
        row for row in transactions
        if row["evaluation_status"] == "VALID"
    ]
    valid.sort(
        key=lambda row: (
            -row["team_avg_remaining_season_lineup_gain"],
            -row["team_playoff_window_total_lineup_gain"],
            -row["team_current_week_lineup_gain"],
            row["add_player_id"],
            row["drop_player_id"],
        )
    )
    for rank, row in enumerate(valid, start=1):
        row["rank_by_ros_lineup_gain"] = rank
    invalid = [
        row for row in transactions
        if row["evaluation_status"] != "VALID"
    ]
    transactions = valid + invalid
    marginal_values = _marginal_roster_values(transactions, my_roster)

    tag_counts: Counter[str] = Counter()
    for row in valid:
        tag_counts.update(
            tag for tag in row["move_tags"].split(" | ") if tag
        )

    summary = {
        "team_id": my_team_id,
        "team_name": names[my_team_id],
        "available_players_pulled": len(available_players),
        "available_players_evaluated": len(candidate_ids),
        "available_player_exclusions": dict(exclusions),
        "rostered_players": len(my_roster),
        "rostered_drop_candidates": len(drop_candidates),
        "locked_or_undroppable_players": (
            len(my_roster) - len(drop_candidates)
        ),
        "add_drop_pairs_considered": total_pairs,
        "illegal_position_limit_pairs_skipped": illegal_position_limits,
        "valid_transactions": len(valid),
        "invalid_lineup_transactions": invalid_lineups,
        "tag_counts": dict(tag_counts),
        "marginal_roster_rows": len(marginal_values),
        "marginal_roster_values_calculated": sum(
            row["marginal_value_status"] == "CALCULATED"
            for row in marginal_values
        ),
    }
    return WaiverAnalysisResult(
        available_players=available_rows,
        transactions=transactions,
        marginal_roster_values=marginal_values,
        summary=summary,
    )
