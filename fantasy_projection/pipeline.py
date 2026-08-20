from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Config
from .espn import EspnClient, as_int, pull_weekly_player_projections
from .league_data import (
    build_starter_slots,
    get_schedule_settings,
    normalize_regular_season_schedule,
    normalize_rosters,
    normalize_teams,
)
from .lineup import project_weekly_lineups
from .postseason import project_postseason
from .regular_season import (
    build_projected_standings,
    project_regular_season,
)


@dataclass
class ProjectionResult:
    teams: list[dict[str, Any]]
    rosters: list[dict[str, Any]]
    player_projections: list[dict[str, Any]]
    starter_slots: list[dict[str, Any]]
    schedule_rows: list[dict[str, Any]]
    settings_payload: dict[str, Any]
    optimal_lineups: list[dict[str, Any]]
    weekly_team_projections: list[dict[str, Any]]
    regular_season_matchups: list[dict[str, Any]]
    projected_standings: list[dict[str, Any]]
    postseason_matchups: list[dict[str, Any]]
    final_standings: list[dict[str, Any]]
    summary: dict[str, Any]


def project_from_normalized_inputs(
    *,
    config: Config,
    teams: list[dict[str, Any]],
    rosters: list[dict[str, Any]],
    player_projections: list[dict[str, Any]],
    starter_slots: list[dict[str, Any]],
    schedule_rows: list[dict[str, Any]],
    settings_payload: dict[str, Any],
    first_week: int,
    final_week: int,
    current_week: int,
) -> ProjectionResult:
    """Project the entire league from already-normalized inputs.

    This function performs no API requests. The trade engine can alter only
    ``rosters`` and reuse the same projections, schedule, and league settings.
    """
    optimal_lineups, weekly_team_projections = (
        project_weekly_lineups(
            teams,
            rosters,
            player_projections,
            starter_slots,
            first_week=first_week,
            final_week=final_week,
        )
    )

    regular_season_matchups = project_regular_season(
        schedule_rows,
        teams,
        weekly_team_projections,
        settings_payload,
    )

    projected_standings = build_projected_standings(
        teams,
        regular_season_matchups,
        settings_payload,
    )

    (
        postseason_matchups,
        final_standings,
        postseason_summary,
    ) = project_postseason(
        projected_standings,
        teams,
        weekly_team_projections,
        settings_payload,
    )

    schedule_settings = get_schedule_settings(settings_payload)
    regular_champion = projected_standings[0]

    summary = {
        "league_id": config.league_id,
        "season": config.season,
        "team_count": len(teams),
        "rostered_player_count": len(rosters),
        "player_week_projection_count": len(player_projections),
        "first_scoring_period": first_week,
        "current_scoring_period": current_week,
        "final_scoring_period": final_week,
        "regular_season_matchup_periods": as_int(
            schedule_settings.get("matchupPeriodCount")
        ),
        "playoff_seeding_rule": schedule_settings.get(
            "playoffSeedingRule"
        ),
        "regular_season_champion_team_id": regular_champion[
            "team_id"
        ],
        "regular_season_champion": regular_champion["team_name"],
        "regular_season_champion_record": regular_champion["record"],
        **postseason_summary,
    }

    return ProjectionResult(
        teams=teams,
        rosters=rosters,
        player_projections=player_projections,
        starter_slots=starter_slots,
        schedule_rows=schedule_rows,
        settings_payload=settings_payload,
        optimal_lineups=optimal_lineups,
        weekly_team_projections=weekly_team_projections,
        regular_season_matchups=regular_season_matchups,
        projected_standings=projected_standings,
        postseason_matchups=postseason_matchups,
        final_standings=final_standings,
        summary=summary,
    )


def run_projection(config: Config) -> ProjectionResult:
    client = EspnClient(config)

    print("Pulling ESPN league data...")
    team_payload = client.get_league("mTeam")
    roster_payload = client.get_league("mRoster")
    settings_payload = client.get_league("mSettings")
    matchup_payload = client.get_league("mMatchupScore")

    status = roster_payload.get("status", {})
    first_week = as_int(status.get("firstScoringPeriod"), 1) or 1
    final_week = as_int(status.get("finalScoringPeriod"), 18) or 18
    current_week = (
        as_int(status.get("currentScoringPeriod"))
        or as_int(roster_payload.get("scoringPeriodId"))
        or as_int(status.get("latestScoringPeriod"))
        or first_week
    )

    teams = normalize_teams(team_payload)
    rosters = normalize_rosters(roster_payload, teams)

    print(
        f"Found {len(teams)} teams and "
        f"{len(rosters)} rostered players."
    )

    player_projections = pull_weekly_player_projections(
        client,
        first_week=first_week,
        final_week=final_week,
    )

    print(
        f"Found {len(player_projections):,} unique "
        "player-week projections."
    )

    starter_slots = build_starter_slots(settings_payload)
    schedule_rows = normalize_regular_season_schedule(
        matchup_payload,
        settings_payload,
    )

    return project_from_normalized_inputs(
        config=config,
        teams=teams,
        rosters=rosters,
        player_projections=player_projections,
        starter_slots=starter_slots,
        schedule_rows=schedule_rows,
        settings_payload=settings_payload,
        first_week=first_week,
        final_week=final_week,
        current_week=current_week,
    )
