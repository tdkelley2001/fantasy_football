from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from statistics import median
from typing import Any, Iterable

from tqdm import tqdm

from .lineup import optimize_lineup
from .pipeline import ProjectionResult
from .postseason import project_postseason
from .regular_season import (
    build_projected_standings,
    project_regular_season,
)
from .trade_config import TradeConfig

EPSILON = 1e-9


@dataclass
class TradeSearchResult:
    all_evaluations: list[dict[str, Any]]
    search_summary: list[dict[str, Any]]


def _team_name_map(
    teams: list[dict[str, Any]],
) -> dict[int, str]:
    return {
        row["team_id"]: row["team_name"]
        for row in teams
    }


def _roster_ids_by_team(
    rosters: list[dict[str, Any]],
) -> dict[int, set[int]]:
    result: dict[int, set[int]] = {}
    for row in rosters:
        result.setdefault(row["team_id"], set()).add(
            row["player_id"]
        )
    return result


def _player_map(
    rosters: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    return {
        row["player_id"]: row
        for row in rosters
    }


def _tradable_player_ids(
    team_id: int,
    roster_ids: dict[int, set[int]],
) -> list[int]:
    """Return every rostered player, including kickers and D/ST."""
    return sorted(roster_ids.get(team_id, set()))


def _packages(
    player_ids: list[int],
    size: int,
) -> list[tuple[int, ...]]:
    if size == 1:
        return [(x,) for x in player_ids]
    return list(combinations(player_ids, size))


def _projection_lookup(
    player_projections: list[dict[str, Any]],
) -> dict[tuple[int, int], float]:
    return {
        (row["player_id"], row["week"]): row[
            "projected_points"
        ]
        for row in player_projections
    }


def _materialize_roster(
    player_ids: Iterable[int],
    players: dict[int, dict[str, Any]],
    *,
    team_id: int,
    team_name: str,
) -> list[dict[str, Any]]:
    rows = []
    for player_id in player_ids:
        row = dict(players[player_id])
        row["team_id"] = team_id
        row["team_name"] = team_name
        rows.append(row)
    return rows


def _score_roster_weeks(
    player_ids: frozenset[int],
    *,
    team_id: int,
    team_name: str,
    weeks: tuple[int, ...],
    players: dict[int, dict[str, Any]],
    starter_slots: list[dict[str, Any]],
    projection_lookup: dict[tuple[int, int], float],
    cache: dict[
        tuple[frozenset[int], tuple[int, ...]],
        tuple[float, ...],
    ],
) -> tuple[float, ...]:
    key = (player_ids, weeks)
    cached = cache.get(key)
    if cached is not None:
        return cached

    roster = _materialize_roster(
        player_ids,
        players,
        team_id=team_id,
        team_name=team_name,
    )

    scores = []
    for week in weeks:
        total, _ = optimize_lineup(
            roster,
            starter_slots,
            projection_lookup,
            week,
        )
        scores.append(total)

    result = tuple(scores)
    cache[key] = result
    return result


def _sum_scores(scores: Iterable[float]) -> float:
    return float(sum(scores))


def _player_label(
    package: tuple[int, ...],
    players: dict[int, dict[str, Any]],
) -> str:
    return " + ".join(
        players[player_id]["player_name"]
        for player_id in package
    )


def _baseline_team_scores(
    baseline: ProjectionResult,
) -> dict[tuple[int, int], float]:
    return {
        (row["team_id"], row["week"]): row[
            "projected_points"
        ]
        for row in baseline.weekly_team_projections
    }


def _team_metrics(
    baseline: ProjectionResult,
) -> dict[int, dict[str, Any]]:
    reg = {
        row["team_id"]: row
        for row in baseline.projected_standings
    }
    final = {
        row["team_id"]: row
        for row in baseline.final_standings
    }

    metrics = {}
    for team_id, reg_row in reg.items():
        final_row = final[team_id]
        metrics[team_id] = {
            "regular_seed": reg_row["seed"],
            "wins": reg_row["wins"],
            "losses": reg_row["losses"],
            "ties": reg_row["ties"],
            "points_for": reg_row["points_for"],
            "final_place": final_row["final_place"],
        }
    return metrics


def _scenario_metrics(
    baseline: ProjectionResult,
    replacement_weekly_scores: dict[tuple[int, int], float],
) -> tuple[
    dict[int, dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Reproject standings/postseason using already-computed lineup scores."""
    weekly = []
    for row in baseline.weekly_team_projections:
        key = (row["team_id"], row["week"])
        copy = dict(row)
        if key in replacement_weekly_scores:
            copy["projected_points"] = replacement_weekly_scores[key]
        weekly.append(copy)

    regular_matchups = project_regular_season(
        baseline.schedule_rows,
        baseline.teams,
        weekly,
        baseline.settings_payload,
    )
    standings = build_projected_standings(
        baseline.teams,
        regular_matchups,
        baseline.settings_payload,
    )
    postseason_matchups, final_standings, postseason_summary = (
        project_postseason(
            standings,
            baseline.teams,
            weekly,
            baseline.settings_payload,
        )
    )

    reg_lookup = {row["team_id"]: row for row in standings}
    final_lookup = {
        row["team_id"]: row
        for row in final_standings
    }

    metrics = {}
    for team_id, row in reg_lookup.items():
        metrics[team_id] = {
            "regular_seed": row["seed"],
            "wins": row["wins"],
            "losses": row["losses"],
            "ties": row["ties"],
            "points_for": row["points_for"],
            "final_place": final_lookup[team_id]["final_place"],
        }

    return (
        metrics,
        postseason_summary,
        regular_matchups,
        postseason_matchups,
    )


def _classify_trade(
    my_gain: float,
    partner_gain: float,
) -> str:
    my_positive = my_gain > EPSILON
    partner_positive = partner_gain > EPSILON

    if my_positive and partner_positive:
        return "BOTH_POSITIVE"
    if my_positive and not partner_positive:
        return "MY_TEAM_ONLY"
    if partner_positive and not my_positive:
        return "PARTNER_ONLY"
    return "NEITHER_POSITIVE"


def _weekly_lineup_metrics(
    prefix: str,
    before: tuple[float, ...],
    after: tuple[float, ...],
    weeks: tuple[int, ...],
) -> dict[str, Any]:
    deltas = tuple(
        0.0 if abs(new - old) <= EPSILON else new - old
        for old, new in zip(before, after, strict=True)
    )
    best_index = max(range(len(deltas)), key=deltas.__getitem__)
    worst_index = min(range(len(deltas)), key=deltas.__getitem__)
    before_total = _sum_scores(before)
    after_total = _sum_scores(after)
    total_gain = after_total - before_total
    if abs(total_gain) <= EPSILON:
        total_gain = 0.0

    return {
        f"{prefix}_current_week_lineup_points_before": before[0],
        f"{prefix}_current_week_lineup_points_after": after[0],
        f"{prefix}_current_week_lineup_gain": deltas[0],
        f"{prefix}_avg_remaining_season_lineup_points_before": (
            before_total / len(before)
        ),
        f"{prefix}_avg_remaining_season_lineup_points_after": (
            after_total / len(after)
        ),
        f"{prefix}_avg_remaining_season_lineup_gain": (
            total_gain / len(deltas)
        ),
        f"{prefix}_total_remaining_season_lineup_points_before": (
            before_total
        ),
        f"{prefix}_total_remaining_season_lineup_points_after": after_total,
        f"{prefix}_total_remaining_season_lineup_gain": total_gain,
        f"{prefix}_median_weekly_lineup_gain": float(median(deltas)),
        f"{prefix}_positive_weeks": sum(x > EPSILON for x in deltas),
        f"{prefix}_negative_weeks": sum(x < -EPSILON for x in deltas),
        f"{prefix}_neutral_weeks": sum(abs(x) <= EPSILON for x in deltas),
        f"{prefix}_best_week": weeks[best_index],
        f"{prefix}_best_week_gain": deltas[best_index],
        f"{prefix}_worst_week": weeks[worst_index],
        f"{prefix}_worst_week_gain": deltas[worst_index],
    }


def _phase_lineup_metrics(
    prefix: str,
    phase: str,
    before: tuple[float, ...],
    after: tuple[float, ...],
    all_weeks: tuple[int, ...],
    phase_weeks: tuple[int, ...],
) -> dict[str, float]:
    before_values = tuple(
        before[all_weeks.index(week)] for week in phase_weeks
    )
    after_values = tuple(
        after[all_weeks.index(week)] for week in phase_weeks
    )
    before_total = _sum_scores(before_values)
    after_total = _sum_scores(after_values)
    total_gain = after_total - before_total
    if abs(total_gain) <= EPSILON:
        total_gain = 0.0
    count = len(phase_weeks)
    return {
        f"{prefix}_{phase}_avg_weekly_lineup_points_before": (
            before_total / count if count else 0.0
        ),
        f"{prefix}_{phase}_avg_weekly_lineup_points_after": (
            after_total / count if count else 0.0
        ),
        f"{prefix}_{phase}_avg_weekly_lineup_gain": (
            total_gain / count if count else 0.0
        ),
        f"{prefix}_{phase}_total_lineup_points_before": before_total,
        f"{prefix}_{phase}_total_lineup_points_after": after_total,
        f"{prefix}_{phase}_total_lineup_gain": total_gain,
    }


def _playoff_path(
    team_id: int,
    matchups: list[dict[str, Any]],
) -> str:
    games = []
    for row in matchups:
        if team_id not in {row["team_a_id"], row["team_b_id"]}:
            continue
        if row["team_a_id"] == team_id:
            opponent = row["team_b"]
        else:
            opponent = row["team_a"]
        outcome = (
            "WIN" if row["winner_team_id"] == team_id else "LOSS"
        )
        games.append(
            (
                int(row["round"]),
                int(row["matchup"]),
                f'{row["bracket"]} R{row["round"]} '
                f'{row["round_name"]} vs {opponent} ({outcome})',
            )
        )

    games.sort()
    return " | ".join(game[2] for game in games) or "NO_PLAYOFF_GAME"


def _projected_game_flip_metrics(
    prefix: str,
    team_id: int,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> dict[str, Any]:
    def result(row: dict[str, Any]) -> str:
        winner = row["winner_team_id"]
        if winner is None:
            return "TIE"
        return "WIN" if winner == team_id else "LOSS"

    after_by_period = {
        row["matchup_period"]: row
        for row in after
        if row["result_type"] == "PROJECTED"
        and team_id in {row["home_team_id"], row["away_team_id"]}
    }
    flips = []
    for row in before:
        if row["result_type"] != "PROJECTED":
            continue
        if team_id not in {row["home_team_id"], row["away_team_id"]}:
            continue
        old_result = result(row)
        new_result = result(after_by_period[row["matchup_period"]])
        if old_result != new_result:
            flips.append(
                (row["matchup_period"], old_result, new_result)
            )

    return {
        f"{prefix}_projected_game_flips": len(flips),
        f"{prefix}_projected_wins_gained_from_flips": sum(
            old != "WIN" and new == "WIN" for _, old, new in flips
        ),
        f"{prefix}_projected_wins_lost_from_flips": sum(
            old == "WIN" and new != "WIN" for _, old, new in flips
        ),
        f"{prefix}_projected_game_flip_details": " | ".join(
            f"Period {period}: {old}_TO_{new}"
            for period, old, new in flips
        ),
    }


def _base_export_record(
    *,
    trade_id: str,
    trade_type: str,
    partner_id: int,
    partner_name: str,
    my_out: tuple[int, ...],
    partner_out: tuple[int, ...],
    players: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "trade_id": trade_id,
        "trade_type": trade_type,
        "partner_team_id": partner_id,
        "partner_team": partner_name,
        "my_give_player_ids": ",".join(map(str, my_out)),
        "my_give": _player_label(my_out, players),
        "my_receive_player_ids": ",".join(map(str, partner_out)),
        "my_receive": _player_label(partner_out, players),
    }


def _evaluate_all_trades_for_type(
    *,
    trade_size: int,
    baseline: ProjectionResult,
    trade_config: TradeConfig,
    roster_ids: dict[int, set[int]],
    players: dict[int, dict[str, Any]],
    projection_lookup: dict[tuple[int, int], float],
    score_cache: dict[
        tuple[frozenset[int], tuple[int, ...]],
        tuple[float, ...],
    ],
    future_weeks: tuple[int, ...],
    regular_weeks: tuple[int, ...],
    postseason_weeks: tuple[int, ...],
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
]:
    """Evaluate every legal package combination for one trade size.

    No mutual-benefit or upper-bound screen is applied. Every 1-for-1 or
    2-for-2 combination involving MY_TEAM_ID is attempted and written to the
    evaluation output. Trades that make a legal starting lineup impossible
    are retained with evaluation_status=INVALID_LINEUP.
    """
    names = _team_name_map(baseline.teams)
    my_team_id = trade_config.my_team_id
    trade_type = "1-for-1" if trade_size == 1 else "2-for-2"
    baseline_weekly = _baseline_team_scores(baseline)
    baseline_metrics = _team_metrics(baseline)

    my_tradable = _tradable_player_ids(
        my_team_id,
        roster_ids,
    )
    my_packages = _packages(my_tradable, trade_size)

    partner_info = []
    total_combinations = 0
    for team in baseline.teams:
        partner_id = team["team_id"]
        if partner_id == my_team_id:
            continue

        partner_tradable = _tradable_player_ids(
            partner_id,
            roster_ids,
        )
        partner_packages = _packages(partner_tradable, trade_size)
        partner_info.append((partner_id, partner_packages))
        total_combinations += len(my_packages) * len(partner_packages)

    my_baseline_future = tuple(
        baseline_weekly[(my_team_id, week)]
        for week in future_weeks
    )

    evaluations: list[dict[str, Any]] = []
    valid_internal: list[dict[str, Any]] = []
    invalid_count = 0
    counter = 0

    progress = tqdm(
        total=total_combinations,
        desc=f"Evaluating all {trade_type} trades",
        unit="trade",
        dynamic_ncols=True,
        leave=True,
    )

    for partner_id, partner_packages in partner_info:
        partner_base = frozenset(roster_ids[partner_id])
        partner_baseline_future = tuple(
            baseline_weekly[(partner_id, week)]
            for week in future_weeks
        )

        for my_out in my_packages:
            my_remaining = roster_ids[my_team_id] - set(my_out)

            for partner_out in partner_packages:
                counter += 1
                trade_id = (
                    f"{trade_type.replace('-', '')}_"
                    f"{partner_id}_{counter:06d}"
                )

                base_record = _base_export_record(
                    trade_id=trade_id,
                    trade_type=trade_type,
                    partner_id=partner_id,
                    partner_name=names[partner_id],
                    my_out=my_out,
                    partner_out=partner_out,
                    players=players,
                )

                my_new_ids = frozenset(
                    my_remaining | set(partner_out)
                )
                partner_new_ids = frozenset(
                    (roster_ids[partner_id] - set(partner_out))
                    | set(my_out)
                )

                try:
                    my_scores = _score_roster_weeks(
                        my_new_ids,
                        team_id=my_team_id,
                        team_name=names[my_team_id],
                        weeks=future_weeks,
                        players=players,
                        starter_slots=baseline.starter_slots,
                        projection_lookup=projection_lookup,
                        cache=score_cache,
                    )
                    partner_scores = _score_roster_weeks(
                        partner_new_ids,
                        team_id=partner_id,
                        team_name=names[partner_id],
                        weeks=future_weeks,
                        players=players,
                        starter_slots=baseline.starter_slots,
                        projection_lookup=projection_lookup,
                        cache=score_cache,
                    )
                except RuntimeError as exc:
                    invalid_count += 1
                    evaluations.append(
                        {
                            **base_record,
                            "evaluation_status": "INVALID_LINEUP",
                            "trade_classification": "INVALID_LINEUP",
                            "invalid_reason": str(exc),
                        }
                    )
                    progress.update(1)
                    continue

                my_weekly_metrics = _weekly_lineup_metrics(
                    "my", my_baseline_future, my_scores, future_weeks
                )
                partner_weekly_metrics = _weekly_lineup_metrics(
                    "partner",
                    partner_baseline_future,
                    partner_scores,
                    future_weeks,
                )
                my_avg_gain = my_weekly_metrics[
                    "my_avg_remaining_season_lineup_gain"
                ]
                partner_avg_gain = partner_weekly_metrics[
                    "partner_avg_remaining_season_lineup_gain"
                ]
                mutual_avg_gain = min(my_avg_gain, partner_avg_gain)
                combined_avg_gain = my_avg_gain + partner_avg_gain
                classification = _classify_trade(
                    my_avg_gain,
                    partner_avg_gain,
                )

                export_record = {
                    **base_record,
                    "evaluation_status": "VALID",
                    "trade_classification": classification,
                    "invalid_reason": "",
                    "current_scoring_week": future_weeks[0],
                    "remaining_scoring_weeks": len(future_weeks),
                    "remaining_regular_season_weeks": len(regular_weeks),
                    "playoff_window_weeks": len(postseason_weeks),
                    **my_weekly_metrics,
                    **partner_weekly_metrics,
                    **_phase_lineup_metrics(
                        "my",
                        "regular_season",
                        my_baseline_future,
                        my_scores,
                        future_weeks,
                        regular_weeks,
                    ),
                    **_phase_lineup_metrics(
                        "partner",
                        "regular_season",
                        partner_baseline_future,
                        partner_scores,
                        future_weeks,
                        regular_weeks,
                    ),
                    **_phase_lineup_metrics(
                        "my",
                        "playoff_window",
                        my_baseline_future,
                        my_scores,
                        future_weeks,
                        postseason_weeks,
                    ),
                    **_phase_lineup_metrics(
                        "partner",
                        "playoff_window",
                        partner_baseline_future,
                        partner_scores,
                        future_weeks,
                        postseason_weeks,
                    ),
                    "mutual_avg_remaining_season_lineup_gain": (
                        mutual_avg_gain
                    ),
                    "combined_avg_remaining_season_lineup_gain": (
                        combined_avg_gain
                    ),
                    "my_positive_gain": my_avg_gain > EPSILON,
                    "partner_positive_gain": partner_avg_gain > EPSILON,
                    "both_positive_gain": (
                        my_avg_gain > EPSILON
                        and partner_avg_gain > EPSILON
                    ),
                }

                evaluations.append(export_record)
                valid_internal.append(
                    {
                        "export": export_record,
                        "my_scores": my_scores,
                        "partner_scores": partner_scores,
                    }
                )
                progress.update(1)

    progress.close()

    # Rank every valid trade by the weaker side's average gain first. The rank
    # is informational only; no trade is removed from the output.
    valid_internal.sort(
        key=lambda x: (
            -x["export"]["mutual_avg_remaining_season_lineup_gain"],
            -x["export"]["combined_avg_remaining_season_lineup_gain"],
            -x["export"]["my_avg_remaining_season_lineup_gain"],
            x["export"]["partner_team_id"],
            x["export"]["trade_id"],
        )
    )

    for rank, item in enumerate(valid_internal, start=1):
        item["export"]["rank_by_mutual_gain_within_type"] = rank

    for item in tqdm(
        valid_internal,
        desc=f"Reprojecting all valid {trade_type} trades",
        unit="trade",
        dynamic_ncols=True,
        leave=True,
    ):
        record = item["export"]
        partner_id = record["partner_team_id"]
        my_scores = item["my_scores"]
        partner_scores = item["partner_scores"]

        replacements: dict[tuple[int, int], float] = {}
        for week, my_score, partner_score in zip(
            future_weeks,
            my_scores,
            partner_scores,
            strict=True,
        ):
            replacements[(my_team_id, week)] = my_score
            replacements[(partner_id, week)] = partner_score

        (
            scenario_metrics,
            postseason_summary,
            scenario_regular_matchups,
            scenario_postseason_matchups,
        ) = _scenario_metrics(baseline, replacements)

        my_before = baseline_metrics[my_team_id]
        my_after = scenario_metrics[my_team_id]
        partner_before = baseline_metrics[partner_id]
        partner_after = scenario_metrics[partner_id]

        record.update(
            {
                "my_projected_wins_before": my_before["wins"],
                "my_projected_wins_after": my_after["wins"],
                "my_projected_wins_change": (
                    my_after["wins"] - my_before["wins"]
                ),
                "partner_projected_wins_before": partner_before["wins"],
                "partner_projected_wins_after": partner_after["wins"],
                "partner_projected_wins_change": (
                    partner_after["wins"] - partner_before["wins"]
                ),
                **_projected_game_flip_metrics(
                    "my",
                    my_team_id,
                    baseline.regular_season_matchups,
                    scenario_regular_matchups,
                ),
                **_projected_game_flip_metrics(
                    "partner",
                    partner_id,
                    baseline.regular_season_matchups,
                    scenario_regular_matchups,
                ),
                "my_regular_seed_before": my_before["regular_seed"],
                "my_regular_seed_after": my_after["regular_seed"],
                "my_regular_seed_improvement": (
                    my_before["regular_seed"] - my_after["regular_seed"]
                ),
                "partner_regular_seed_before": partner_before["regular_seed"],
                "partner_regular_seed_after": partner_after["regular_seed"],
                "partner_regular_seed_improvement": (
                    partner_before["regular_seed"]
                    - partner_after["regular_seed"]
                ),
                "my_final_place_before": my_before["final_place"],
                "my_final_place_after": my_after["final_place"],
                "my_final_place_improvement": (
                    my_before["final_place"] - my_after["final_place"]
                ),
                "partner_final_place_before": partner_before["final_place"],
                "partner_final_place_after": partner_after["final_place"],
                "partner_final_place_improvement": (
                    partner_before["final_place"]
                    - partner_after["final_place"]
                ),
                "my_playoff_path_before": _playoff_path(
                    my_team_id, baseline.postseason_matchups
                ),
                "my_playoff_path_after": _playoff_path(
                    my_team_id, scenario_postseason_matchups
                ),
                "partner_playoff_path_before": _playoff_path(
                    partner_id, baseline.postseason_matchups
                ),
                "partner_playoff_path_after": _playoff_path(
                    partner_id, scenario_postseason_matchups
                ),
                "both_final_places_nonworse": (
                    my_after["final_place"] <= my_before["final_place"]
                    and partner_after["final_place"] <= partner_before["final_place"]
                ),
                "projected_champion_before_trade": baseline.summary[
                    "champion_team"
                ],
                "projected_champion_after_trade": postseason_summary[
                    "champion_team"
                ],
            }
        )

    valid_exports = [item["export"] for item in valid_internal]

    # Put valid trades first in rank order, then invalid lineup combinations.
    invalid_exports = [
        row for row in evaluations
        if row["evaluation_status"] == "INVALID_LINEUP"
    ]
    all_sorted = valid_exports + invalid_exports

    class_counts: dict[str, int] = {}
    for row in valid_exports:
        cls = row["trade_classification"]
        class_counts[cls] = class_counts.get(cls, 0) + 1

    summary = {
        "trade_type": trade_type,
        "total_combinations": total_combinations,
        "valid_trades_evaluated": len(valid_exports),
        "invalid_lineup_trades": invalid_count,
        "both_positive": class_counts.get("BOTH_POSITIVE", 0),
        "my_team_only_positive": class_counts.get("MY_TEAM_ONLY", 0),
        "partner_only_positive": class_counts.get("PARTNER_ONLY", 0),
        "neither_positive": class_counts.get("NEITHER_POSITIVE", 0),
        "fully_reprojected_trades": len(valid_exports),
        "best_mutual_avg_remaining_season_lineup_gain": (
            valid_exports[0][
                "mutual_avg_remaining_season_lineup_gain"
            ]
            if valid_exports else None
        ),
    }

    return all_sorted, summary


def evaluate_all_trades(
    *,
    baseline: ProjectionResult,
    trade_config: TradeConfig,
) -> TradeSearchResult:
    """Evaluate every 1-for-1 and 2-for-2 trade involving MY_TEAM_ID.

    Every rostered player is eligible, including bench players, kickers, and
    D/ST. Every valid trade is fully reprojected through the regular season
    and postseason; no ranking threshold or top-N filter is applied.
    """
    names = _team_name_map(baseline.teams)
    if trade_config.my_team_id not in names:
        raise RuntimeError(
            f"MY_TEAM_ID={trade_config.my_team_id} was not found in the "
            "league. Check teams.csv."
        )

    regular_end = int(
        baseline.summary["regular_season_matchup_periods"]
    )
    current_week = int(
        baseline.summary["current_scoring_period"]
    )
    final_week = int(baseline.summary["final_scoring_period"])

    future_weeks = tuple(range(current_week, final_week + 1))
    if not future_weeks:
        raise RuntimeError("No scoring weeks remain to evaluate trades.")
    regular_weeks = tuple(
        week for week in future_weeks if week <= regular_end
    )
    postseason_weeks = tuple(
        week for week in future_weeks if week > regular_end
    )

    roster_ids = _roster_ids_by_team(baseline.rosters)
    players = _player_map(baseline.rosters)
    projection_lookup = _projection_lookup(
        baseline.player_projections
    )
    score_cache: dict[
        tuple[frozenset[int], tuple[int, ...]],
        tuple[float, ...],
    ] = {}

    all_evaluations: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    print(
        f"Searching trades for {names[trade_config.my_team_id]} "
        f"(team_id={trade_config.my_team_id})."
    )
    print(
        f"Trade evaluation horizon: Weeks {current_week}-{final_week}."
    )
    print(
        "All rostered positions are included. Every valid 1-for-1 and "
        "2-for-2 trade will receive a full standings/playoff projection."
    )

    for trade_size in (1, 2):
        evaluations, summary = _evaluate_all_trades_for_type(
            trade_size=trade_size,
            baseline=baseline,
            trade_config=trade_config,
            roster_ids=roster_ids,
            players=players,
            projection_lookup=projection_lookup,
            score_cache=score_cache,
            future_weeks=future_weeks,
            regular_weeks=regular_weeks,
            postseason_weeks=postseason_weeks,
        )

        all_evaluations.extend(evaluations)
        summaries.append(summary)

    return TradeSearchResult(
        all_evaluations=all_evaluations,
        search_summary=summaries,
    )
