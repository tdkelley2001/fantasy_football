from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable

from tqdm import tqdm

from .config import Config
from .lineup import optimize_lineup
from .pipeline import ProjectionResult
from .postseason import project_postseason
from .regular_season import (
    build_projected_standings,
    project_regular_season,
)
from .trade_config import TradeConfig


# ESPN defaultPositionId values.
EXCLUDED_DEFAULT_POSITION_IDS = {16, 17}  # D/ST, K
EPSILON = 1e-9


@dataclass
class TradeSearchResult:
    all_evaluations: list[dict[str, Any]]
    top_trades: list[dict[str, Any]]
    weekly_impacts: list[dict[str, Any]]
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
    players: dict[int, dict[str, Any]],
) -> list[int]:
    ids = [
        player_id
        for player_id in roster_ids.get(team_id, set())
        if players[player_id].get("default_position_id")
        not in EXCLUDED_DEFAULT_POSITION_IDS
    ]
    return sorted(ids)


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
) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
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
    _, final_standings, postseason_summary = project_postseason(
        standings,
        baseline.teams,
        weekly,
        baseline.settings_payload,
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

    return metrics, postseason_summary


def _classify_trade(
    my_gain: float,
    partner_gain: float,
    threshold: float,
) -> str:
    my_positive = my_gain > EPSILON
    partner_positive = partner_gain > EPSILON
    my_above = my_gain > threshold
    partner_above = partner_gain > threshold

    if my_above and partner_above:
        return "BOTH_ABOVE_THRESHOLD"
    if my_positive and partner_positive:
        return "BOTH_POSITIVE_BELOW_THRESHOLD"
    if my_positive and not partner_positive:
        return "MY_TEAM_ONLY"
    if partner_positive and not my_positive:
        return "PARTNER_ONLY"
    return "NEITHER_POSITIVE"


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

    my_base = frozenset(roster_ids[my_team_id])
    my_tradable = _tradable_player_ids(
        my_team_id,
        roster_ids,
        players,
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
            players,
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

                my_weekly_delta = tuple(
                    score - baseline
                    for score, baseline in zip(
                        my_scores,
                        my_baseline_future,
                        strict=True,
                    )
                )
                partner_weekly_delta = tuple(
                    score - baseline
                    for score, baseline in zip(
                        partner_scores,
                        partner_baseline_future,
                        strict=True,
                    )
                )

                my_total_gain = _sum_scores(my_weekly_delta)
                partner_total_gain = _sum_scores(
                    partner_weekly_delta
                )
                my_avg_gain = my_total_gain / len(future_weeks)
                partner_avg_gain = (
                    partner_total_gain / len(future_weeks)
                )

                my_reg_gain = sum(
                    my_weekly_delta[future_weeks.index(week)]
                    for week in regular_weeks
                )
                partner_reg_gain = sum(
                    partner_weekly_delta[future_weeks.index(week)]
                    for week in regular_weeks
                )
                my_post_gain = sum(
                    my_weekly_delta[future_weeks.index(week)]
                    for week in postseason_weeks
                )
                partner_post_gain = sum(
                    partner_weekly_delta[future_weeks.index(week)]
                    for week in postseason_weeks
                )

                my_reg_avg = (
                    my_reg_gain / len(regular_weeks)
                    if regular_weeks else 0.0
                )
                partner_reg_avg = (
                    partner_reg_gain / len(regular_weeks)
                    if regular_weeks else 0.0
                )
                my_post_avg = (
                    my_post_gain / len(postseason_weeks)
                    if postseason_weeks else 0.0
                )
                partner_post_avg = (
                    partner_post_gain / len(postseason_weeks)
                    if postseason_weeks else 0.0
                )

                mutual_avg_gain = min(my_avg_gain, partner_avg_gain)
                combined_avg_gain = my_avg_gain + partner_avg_gain
                threshold = trade_config.min_avg_weekly_gain
                classification = _classify_trade(
                    my_avg_gain,
                    partner_avg_gain,
                    threshold,
                )

                export_record = {
                    **base_record,
                    "evaluation_status": "VALID",
                    "trade_classification": classification,
                    "invalid_reason": "",
                    "my_avg_weekly_lineup_gain": my_avg_gain,
                    "partner_avg_weekly_lineup_gain": partner_avg_gain,
                    "mutual_avg_weekly_lineup_gain": mutual_avg_gain,
                    "combined_avg_weekly_lineup_gain": combined_avg_gain,
                    "my_total_future_lineup_gain": my_total_gain,
                    "partner_total_future_lineup_gain": partner_total_gain,
                    "mutual_total_future_lineup_gain": min(
                        my_total_gain,
                        partner_total_gain,
                    ),
                    "combined_total_future_lineup_gain": (
                        my_total_gain + partner_total_gain
                    ),
                    "my_regular_season_avg_weekly_gain": my_reg_avg,
                    "partner_regular_season_avg_weekly_gain": partner_reg_avg,
                    "my_regular_season_total_gain": my_reg_gain,
                    "partner_regular_season_total_gain": partner_reg_gain,
                    "my_postseason_avg_weekly_gain": my_post_avg,
                    "partner_postseason_avg_weekly_gain": partner_post_avg,
                    "my_postseason_total_gain": my_post_gain,
                    "partner_postseason_total_gain": partner_post_gain,
                    "my_positive_gain": my_avg_gain > EPSILON,
                    "partner_positive_gain": partner_avg_gain > EPSILON,
                    "both_positive_gain": (
                        my_avg_gain > EPSILON
                        and partner_avg_gain > EPSILON
                    ),
                    "my_above_threshold": my_avg_gain > threshold,
                    "partner_above_threshold": partner_avg_gain > threshold,
                    "both_above_threshold": (
                        my_avg_gain > threshold
                        and partner_avg_gain > threshold
                    ),
                    "my_threshold_margin": my_avg_gain - threshold,
                    "partner_threshold_margin": partner_avg_gain - threshold,
                    "mutual_threshold_margin": (
                        mutual_avg_gain - threshold
                    ),
                    "scenario_reprojected": False,
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

    # Rank valid trades by the weaker side's gain first. This provides the
    # closest-to-mutually-beneficial trades even when none clear the threshold.
    valid_internal.sort(
        key=lambda x: (
            -x["export"]["mutual_avg_weekly_lineup_gain"],
            -x["export"]["combined_avg_weekly_lineup_gain"],
            -x["export"]["my_avg_weekly_lineup_gain"],
            x["export"]["partner_team_id"],
            x["export"]["trade_id"],
        )
    )

    for rank, item in enumerate(valid_internal, start=1):
        item["export"]["rank_by_mutual_gain_within_type"] = rank

    if trade_config.reproject_all:
        scenario_targets = valid_internal
    else:
        scenario_targets = valid_internal[:trade_config.top_n_per_type]

    scenario_desc = (
        f"Reprojecting all valid {trade_type} trades"
        if trade_config.reproject_all
        else f"Reprojecting top {trade_config.top_n_per_type} {trade_type} trades"
    )

    for item in tqdm(
        scenario_targets,
        desc=scenario_desc,
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

        scenario_metrics, postseason_summary = _scenario_metrics(
            baseline,
            replacements,
        )

        my_before = baseline_metrics[my_team_id]
        my_after = scenario_metrics[my_team_id]
        partner_before = baseline_metrics[partner_id]
        partner_after = scenario_metrics[partner_id]

        record.update(
            {
                "scenario_reprojected": True,
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
                "both_final_places_nonworse": (
                    my_after["final_place"] <= my_before["final_place"]
                    and partner_after["final_place"] <= partner_before["final_place"]
                ),
                "projected_champion_after_trade": postseason_summary[
                    "champion_team"
                ],
            }
        )

    # Week-by-week output is intentionally limited to top N; emitting it for
    # every trade would create millions of CSV rows. Aggregate weekly, regular-
    # season, and postseason metrics are still present for every trade.
    weekly_impacts: list[dict[str, Any]] = []
    reg_set = set(regular_weeks)
    post_set = set(postseason_weeks)
    for item in valid_internal[:trade_config.top_n_per_type]:
        record = item["export"]
        partner_id = record["partner_team_id"]

        for week, my_score, partner_score in zip(
            future_weeks,
            item["my_scores"],
            item["partner_scores"],
            strict=True,
        ):
            phase = (
                "REGULAR_SEASON"
                if week in reg_set
                else "POSTSEASON"
                if week in post_set
                else "OTHER"
            )

            weekly_impacts.append(
                {
                    "trade_id": record["trade_id"],
                    "trade_type": trade_type,
                    "team_role": "MY_TEAM",
                    "team_id": my_team_id,
                    "team_name": names[my_team_id],
                    "week": week,
                    "phase": phase,
                    "baseline_projected_points": baseline_weekly[
                        (my_team_id, week)
                    ],
                    "post_trade_projected_points": my_score,
                    "projected_points_change": (
                        my_score - baseline_weekly[(my_team_id, week)]
                    ),
                }
            )
            weekly_impacts.append(
                {
                    "trade_id": record["trade_id"],
                    "trade_type": trade_type,
                    "team_role": "PARTNER",
                    "team_id": partner_id,
                    "team_name": names[partner_id],
                    "week": week,
                    "phase": phase,
                    "baseline_projected_points": baseline_weekly[
                        (partner_id, week)
                    ],
                    "post_trade_projected_points": partner_score,
                    "projected_points_change": (
                        partner_score - baseline_weekly[(partner_id, week)]
                    ),
                }
            )

    valid_exports = [item["export"] for item in valid_internal]
    top_trades = valid_exports[:trade_config.top_n_per_type]

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
        "both_above_threshold": class_counts.get(
            "BOTH_ABOVE_THRESHOLD", 0
        ),
        "both_positive_below_threshold": class_counts.get(
            "BOTH_POSITIVE_BELOW_THRESHOLD", 0
        ),
        "my_team_only_positive": class_counts.get("MY_TEAM_ONLY", 0),
        "partner_only_positive": class_counts.get("PARTNER_ONLY", 0),
        "neither_positive": class_counts.get("NEITHER_POSITIVE", 0),
        "top_results_returned": len(top_trades),
        "scenario_reprojected_count": len(scenario_targets),
        "reproject_all": trade_config.reproject_all,
        "best_mutual_avg_weekly_gain": (
            valid_exports[0]["mutual_avg_weekly_lineup_gain"]
            if valid_exports else None
        ),
    }

    return all_sorted, weekly_impacts, summary


def find_mutually_beneficial_trades(
    *,
    baseline: ProjectionResult,
    config: Config,
    trade_config: TradeConfig,
) -> TradeSearchResult:
    """Evaluate every 1-for-1 and 2-for-2 trade involving MY_TEAM_ID.

    D/ST and kickers are excluded as trade pieces; bench players remain fully
    eligible. Mutual benefit is now a classification rather than a search
    filter, which makes the complete trade distribution available for
    debugging and analysis.
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
    all_weekly: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    all_top: list[dict[str, Any]] = []

    print(
        f"Searching trades for {names[trade_config.my_team_id]} "
        f"(team_id={trade_config.my_team_id})."
    )
    print(
        f"Trade appeal horizon: Weeks {current_week}-{final_week}. "
        "Mutually beneficial threshold: both sides > "
        f"{trade_config.min_avg_weekly_gain:.2f} points/week."
    )
    print(
        "All valid 1-for-1 and 2-for-2 trades will be saved, including "
        "one-sided and negative trades."
    )

    for trade_size in (1, 2):
        evaluations, weekly, summary = _evaluate_all_trades_for_type(
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

        valid = [
            row for row in evaluations
            if row["evaluation_status"] == "VALID"
        ]
        all_top.extend(valid[:trade_config.top_n_per_type])
        all_evaluations.extend(evaluations)
        all_weekly.extend(weekly)
        summaries.append(summary)

    return TradeSearchResult(
        all_evaluations=all_evaluations,
        top_trades=all_top,
        weekly_impacts=all_weekly,
        search_summary=summaries,
    )
