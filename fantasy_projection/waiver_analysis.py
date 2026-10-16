from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .season import SeasonModelError, SeasonProjection, project_season
from .transactions import apply_transaction, waiver_transaction
from .trades import (
    _phase_lineup_metrics,
    _playoff_path,
    _projected_game_flip_metrics,
    _projection_lookup,
    _team_metrics,
    _weekly_lineup_metrics,
)
from .waivers import _move_tags, _position_name


@dataclass(frozen=True)
class WaiverSpec:
    my_team_id: int
    add_player_id: int
    drop_player_id: int | None
    effective_week: int


@dataclass
class WaiverComparison:
    spec: WaiverSpec
    waiver_summary: dict[str, Any]
    team_comparison: list[dict[str, Any]]
    weekly_comparison: list[dict[str, Any]]
    lineup_comparison: list[dict[str, Any]]
    league_comparison: list[dict[str, Any]]
    before: SeasonProjection
    after: SeasonProjection




def _weekly_rows(
    before: SeasonProjection,
    after: SeasonProjection,
    team_id: int,
    weeks: tuple[int, ...],
) -> list[dict[str, Any]]:
    old = {
        (row["team_id"], row["week"]): row["projected_points"]
        for row in before.weekly_team_projections
    }
    new = {
        (row["team_id"], row["week"]): row["projected_points"]
        for row in after.weekly_team_projections
    }
    team_name = next(
        row["team_name"] for row in before.state.teams
        if int(row["team_id"]) == team_id
    )
    return [
        {
            "team_id": team_id,
            "team_name": team_name,
            "week": week,
            "projected_points_before": old[(team_id, week)],
            "projected_points_after": new[(team_id, week)],
            "projected_points_change": (
                new[(team_id, week)] - old[(team_id, week)]
            ),
        }
        for week in weeks
    ]


def _lineup_rows(
    before: SeasonProjection,
    after: SeasonProjection,
    team_id: int,
    weeks: tuple[int, ...],
) -> list[dict[str, Any]]:
    def keyed(
        result: SeasonProjection,
    ) -> dict[tuple[int, int, int], dict[str, Any]]:
        return {
            (row["week"], row["slot_id"], row["slot_instance"]): row
            for row in result.optimal_lineups
            if int(row["team_id"]) == team_id and row["week"] in weeks
        }

    old = keyed(before)
    new = keyed(after)
    rows = []
    for key in sorted(old):
        before_row = old[key]
        after_row = new[key]
        rows.append(
            {
                "team_id": team_id,
                "team_name": before_row["team_name"],
                "week": before_row["week"],
                "slot_id": before_row["slot_id"],
                "slot_name": before_row["slot_name"],
                "slot_instance": before_row["slot_instance"],
                "player_id_before": before_row["player_id"],
                "player_before": before_row["player_name"],
                "player_id_after": after_row["player_id"],
                "player_after": after_row["player_name"],
                "projected_points_before": before_row[
                    "projected_points"
                ],
                "projected_points_after": after_row[
                    "projected_points"
                ],
                "projected_points_change": (
                    after_row["projected_points"]
                    - before_row["projected_points"]
                ),
                "starter_changed": (
                    before_row["player_id"] != after_row["player_id"]
                ),
            }
        )
    return rows


def _league_rows(
    before: SeasonProjection,
    after: SeasonProjection,
    my_team_id: int,
) -> list[dict[str, Any]]:
    old = _team_metrics(before)
    new = _team_metrics(after)
    names = {
        int(row["team_id"]): row["team_name"] for row in before.state.teams
    }
    return [
        {
            "team_id": team_id,
            "team_name": names[team_id],
            "is_my_team": team_id == my_team_id,
            "wins_before": old[team_id]["wins"],
            "wins_after": new[team_id]["wins"],
            "wins_change": new[team_id]["wins"] - old[team_id]["wins"],
            "regular_seed_before": old[team_id]["regular_seed"],
            "regular_seed_after": new[team_id]["regular_seed"],
            "regular_seed_improvement": (
                old[team_id]["regular_seed"]
                - new[team_id]["regular_seed"]
            ),
            "final_place_before": old[team_id]["final_place"],
            "final_place_after": new[team_id]["final_place"],
            "final_place_improvement": (
                old[team_id]["final_place"]
                - new[team_id]["final_place"]
            ),
        }
        for team_id in sorted(names)
    ]


def evaluate_waiver(
    *,
    baseline: SeasonProjection,
    my_team_id: int,
    available_players: list[dict[str, Any]],
    add_player_id: int,
    drop_player_id: int | None,
    effective_week: int | None = None,
) -> WaiverComparison:
    """Apply one proposed add/drop and compare full league projections."""
    effective_week = baseline.state.current_week if effective_week is None else effective_week
    spec = WaiverSpec(my_team_id, add_player_id, drop_player_id, effective_week)
    source = replace(baseline.state, available_players=available_players)
    transaction = waiver_transaction(source, team_id=my_team_id, add=add_player_id,
                                     drop=drop_player_id, effective_week=effective_week)
    after = project_season(apply_transaction(source, transaction), effective_week)

    current_week = effective_week
    final_week = int(baseline.summary["final_scoring_period"])
    regular_end = int(
        max(baseline.state.rules.period_weeks[baseline.state.rules.regular_periods])
    )
    weeks = tuple(range(current_week, final_week + 1))
    if not weeks:
        raise SeasonModelError("No scoring weeks remain to evaluate this waiver.")
    regular_weeks = tuple(week for week in weeks if week <= regular_end)
    playoff_weeks = tuple(week for week in weeks if week > regular_end)

    weekly_comparison = _weekly_rows(baseline, after, my_team_id, weeks)
    before_scores = tuple(
        row["projected_points_before"] for row in weekly_comparison
    )
    after_scores = tuple(
        row["projected_points_after"] for row in weekly_comparison
    )
    before_metrics = _team_metrics(baseline)[my_team_id]
    after_metrics = _team_metrics(after)[my_team_id]
    impact = {
        "team_id": my_team_id,
        "team_name": next(
            row["team_name"] for row in baseline.state.teams
            if int(row["team_id"]) == my_team_id
        ),
        **_weekly_lineup_metrics(
            "team", before_scores, after_scores, weeks
        ),
        **_phase_lineup_metrics(
            "team",
            "regular_season",
            before_scores,
            after_scores,
            weeks,
            regular_weeks,
        ),
        **_phase_lineup_metrics(
            "team",
            "playoff_window",
            before_scores,
            after_scores,
            weeks,
            playoff_weeks,
        ),
        "team_projected_wins_before": before_metrics["wins"],
        "team_projected_wins_after": after_metrics["wins"],
        "team_projected_wins_change": (
            after_metrics["wins"] - before_metrics["wins"]
        ),
        **_projected_game_flip_metrics(
            "team",
            my_team_id,
            baseline.regular_season_matchups,
            after.regular_season_matchups,
        ),
        "team_regular_seed_before": before_metrics["regular_seed"],
        "team_regular_seed_after": after_metrics["regular_seed"],
        "team_regular_seed_improvement": (
            before_metrics["regular_seed"]
            - after_metrics["regular_seed"]
        ),
        "team_made_playoffs_before": (
            before_metrics["regular_seed"]
            <= int(baseline.summary["playoff_team_count"])
        ),
        "team_made_playoffs_after": (
            after_metrics["regular_seed"]
            <= int(after.summary["playoff_team_count"])
        ),
        "team_playoff_path_before": _playoff_path(
            my_team_id, baseline.postseason_matchups
        ),
        "team_playoff_path_after": _playoff_path(
            my_team_id, after.postseason_matchups
        ),
        "team_final_place_before": before_metrics["final_place"],
        "team_final_place_after": after_metrics["final_place"],
        "team_final_place_improvement": (
            before_metrics["final_place"]
            - after_metrics["final_place"]
        ),
        "projected_champion_before": baseline.summary["champion_team"],
        "projected_champion_after": after.summary["champion_team"],
    }
    tags = _move_tags(impact)
    impact["move_tags"] = " | ".join(tags)

    rostered = {
        int(row["player_id"]): row for row in baseline.state.rosters
    }
    available = {
        int(row["player_id"]): row for row in available_players
    }
    add = available[spec.add_player_id]
    drop = rostered.get(spec.drop_player_id)
    projection_lookup = _projection_lookup(baseline.state.player_projections)
    add_values = tuple(
        projection_lookup.get((spec.add_player_id, week), 0.0)
        for week in weeks
    )
    drop_values = tuple(
        projection_lookup.get((spec.drop_player_id, week), 0.0) if spec.drop_player_id is not None else 0.0
        for week in weeks
    )
    waiver_summary = {
        "my_team_id": my_team_id,
        "my_team": impact["team_name"],
        "add": {
            "player_id": spec.add_player_id,
            "player_name": add["player_name"],
            "position": _position_name(add),
            "availability_status": add.get("availability_status"),
        },
        "drop": {
            "player_id": spec.drop_player_id,
            "player_name": drop["player_name"] if drop else "Open roster slot",
            "position": _position_name(drop) if drop else None,
        },
        "same_position_swap": (
            bool(drop) and add.get("default_position_id") == drop.get("default_position_id")
        ),
        "comparison_weeks": list(weeks),
        "effective_week": effective_week,
        "add_total_remaining_projection": sum(add_values),
        "drop_total_remaining_projection": sum(drop_values),
        "move_tags": tags,
        "champion_before": baseline.summary["champion_team"],
        "champion_after": after.summary["champion_team"],
        "team_result": impact,
    }

    return WaiverComparison(
        spec=spec,
        waiver_summary=waiver_summary,
        team_comparison=[impact],
        weekly_comparison=weekly_comparison,
        lineup_comparison=_lineup_rows(
            baseline, after, my_team_id, weeks
        ),
        league_comparison=_league_rows(baseline, after, my_team_id),
        before=baseline,
        after=after,
    )
