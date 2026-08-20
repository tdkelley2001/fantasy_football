from __future__ import annotations

from typing import Any

from .espn import as_int
from .league_data import (
    get_schedule_settings,
    matchup_period_scoring_weeks,
)


def project_regular_season(
    schedule_rows: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    weekly_team_projections: list[dict[str, Any]],
    settings_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    names = {
        row["team_id"]: row["team_name"]
        for row in teams
    }
    weekly_lookup = {
        (row["team_id"], row["week"]):
            row["projected_points"]
        for row in weekly_team_projections
    }

    results = []

    for row in schedule_rows:
        period = row["matchup_period"]
        weeks = matchup_period_scoring_weeks(
            settings_payload,
            period,
        )

        home_projection = sum(
            weekly_lookup.get(
                (row["home_team_id"], week),
                0.0,
            )
            for week in weeks
        )
        away_projection = sum(
            weekly_lookup.get(
                (row["away_team_id"], week),
                0.0,
            )
            for week in weeks
        )

        espn_winner = row["espn_winner"]

        if espn_winner in {"HOME", "AWAY", "TIE"}:
            home_points = row["actual_home_points"] or 0.0
            away_points = row["actual_away_points"] or 0.0
            result_type = "ACTUAL"

            if espn_winner == "HOME":
                winner_id = row["home_team_id"]
            elif espn_winner == "AWAY":
                winner_id = row["away_team_id"]
            else:
                winner_id = None
        else:
            home_points = home_projection
            away_points = away_projection
            result_type = "PROJECTED"

            if home_points > away_points:
                winner_id = row["home_team_id"]
            elif away_points > home_points:
                winner_id = row["away_team_id"]
            else:
                winner_id = None

        results.append(
            {
                "matchup_period": period,
                "scoring_weeks": ",".join(map(str, weeks)),
                "home_team_id": row["home_team_id"],
                "home_team": names.get(
                    row["home_team_id"]
                ),
                "home_points": home_points,
                "away_team_id": row["away_team_id"],
                "away_team": names.get(
                    row["away_team_id"]
                ),
                "away_points": away_points,
                "winner_team_id": winner_id,
                "winner_team": names.get(winner_id),
                "result_type": result_type,
            }
        )

    return results


def build_projected_standings(
    teams: list[dict[str, Any]],
    matchup_results: list[dict[str, Any]],
    settings_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    records = {
        team["team_id"]: {
            "team_id": team["team_id"],
            "team_name": team["team_name"],
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "points_for": 0.0,
            "points_against": 0.0,
            "actual_games": 0,
            "projected_games": 0,
        }
        for team in teams
    }

    for matchup in matchup_results:
        home = records[matchup["home_team_id"]]
        away = records[matchup["away_team_id"]]

        home["points_for"] += matchup["home_points"]
        home["points_against"] += matchup["away_points"]
        away["points_for"] += matchup["away_points"]
        away["points_against"] += matchup["home_points"]

        counter = (
            "actual_games"
            if matchup["result_type"] == "ACTUAL"
            else "projected_games"
        )
        home[counter] += 1
        away[counter] += 1

        winner_id = matchup["winner_team_id"]

        if winner_id is None:
            home["ties"] += 1
            away["ties"] += 1
        elif winner_id == matchup["home_team_id"]:
            home["wins"] += 1
            away["losses"] += 1
        else:
            away["wins"] += 1
            home["losses"] += 1

    seeding_rule = get_schedule_settings(
        settings_payload
    ).get("playoffSeedingRule")

    standings = list(records.values())

    # The current league reports TOTAL_POINTS_SCORED as its
    # seeding tiebreak. Division logic can be added later if needed.
    standings.sort(
        key=lambda x: (
            -x["wins"],
            -x["ties"],
            -x["points_for"],
            x["team_id"],
        )
    )

    for seed, row in enumerate(standings, start=1):
        row["seed"] = seed
        row["record"] = (
            f'{row["wins"]}-{row["losses"]}'
            + (
                f'-{row["ties"]}'
                if row["ties"]
                else ""
            )
        )
        row["seeding_rule"] = seeding_rule

    return standings
