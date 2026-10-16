"""ESPN ingestion adapter. Season computation lives in season.py."""
from __future__ import annotations

from .config import Config
from .espn import EspnClient, as_int, pull_weekly_player_projections
from .league_data import build_starter_slots, normalize_schedule, normalize_rosters, normalize_teams, normalize_season_rules, normalize_actual_weekly_points
from .season import LeagueState, SeasonModelError


def load_league_state(config: Config, *, progress_callback=None) -> LeagueState:
    client = EspnClient(config)

    print("Pulling ESPN league data...")
    if progress_callback:
        progress_callback("Loading ESPN league data", 0, 4, "requests")
    team_payload = client.get_league("mTeam")
    if progress_callback:
        progress_callback("Loading ESPN league data", 1, 4, "requests")
    roster_payload = client.get_league("mRoster")
    if progress_callback:
        progress_callback("Loading ESPN league data", 2, 4, "requests")
    settings_payload = client.get_league("mSettings")
    if progress_callback:
        progress_callback("Loading ESPN league data", 3, 4, "requests")
    matchup_payload = client.get_league("mMatchupScore")

    status = roster_payload.get("status", {})
    first_week = as_int(status.get("firstScoringPeriod"))
    final_week = as_int(status.get("finalScoringPeriod"))
    if first_week is None or final_week is None:
        raise SeasonModelError("ESPN did not supply the season's scoring-week boundaries.")
    current_week = (
        as_int(status.get("currentScoringPeriod"))
        or as_int(roster_payload.get("scoringPeriodId"))
        or as_int(status.get("latestScoringPeriod"))
        or first_week
    )
    if status.get("isSeasonOver"):
        current_week = final_week + 1

    rules = normalize_season_rules(settings_payload)
    schedule_rows = normalize_schedule(matchup_payload)
    # ESPN can still label a just-finished period as current. Move the model's
    # boundary forward only when every scheduled matchup in that period is final.
    for period, weeks in rules.period_weeks.items():
        games = [r for r in schedule_rows if r["matchup_period"] == period]
        if max(weeks) == current_week and games and all(r["winner"] != "UNDECIDED" for r in games):
            current_week += 1
            break

    teams = normalize_teams(team_payload)
    rosters = normalize_rosters(roster_payload, teams)

    print(
        f"Found {len(teams)} teams and "
        f"{len(rosters)} rostered players."
    )

    player_projections = pull_weekly_player_projections(
        client,
        first_week=current_week,
        final_week=final_week,
        progress_callback=progress_callback,
    )

    print(
        f"Found {len(player_projections):,} unique "
        "player-week projections."
    )

    starter_slots = build_starter_slots(settings_payload)
    return LeagueState(
        league_id=config.league_id, season=config.season,
        first_week=first_week, final_week=final_week, current_week=current_week,
        rules=rules, teams=teams, rosters=rosters, player_projections=player_projections,
        starter_slots=starter_slots,
        schedule_rows=[r for r in schedule_rows if r["matchup_period"] <= rules.regular_periods],
        postseason_results=[r for r in schedule_rows if r["matchup_period"] > rules.regular_periods and r["winner"] != "UNDECIDED"],
        actual_weekly_points=normalize_actual_weekly_points(matchup_payload, current_week),
        settings_payload={"settings": {key: settings_payload["settings"].get(key, {})
                                      for key in ("rosterSettings", "acquisitionSettings", "scoringSettings")}},
    )


def load_simulation_state(state, client):
    """Attach confirmed NFL bye weeks for the snapshot's current NFL affiliations."""
    from dataclasses import replace
    from .espn import BASE
    response = client.session.get(f"{BASE}/seasons/{state.season}",
                                  params={"view": "proTeamSchedules_wl"}, timeout=30)
    response.raise_for_status()
    return replace(state, player_bye_weeks=normalize_bye_weeks(state, response.json()))


def normalize_bye_weeks(state, payload):
    nfl_weeks = set(range(1, 18 if state.season <= 2020 else 19))
    teams = {}
    for team in payload.get("settings", {}).get("proTeams", []):
        if not team.get("id"):
            continue
        games = {int(week) for week, rows in team.get("proGamesByScoringPeriod", {}).items()
                 if rows and int(week) in nfl_weeks}
        if len(games) != len(nfl_weeks)-1:
            raise SeasonModelError("Incomplete NFL schedule; cannot confirm bye weeks for simulation.")
        teams[team["id"]] = tuple(sorted(nfl_weeks-games))
    if len(teams) != 32:
        raise SeasonModelError("Expected 32 NFL teams when confirming bye weeks.")
    players = state.rosters + (state.baseline_rosters or []) + state.available_players
    return {p["player_id"]: teams[p["pro_team_id"]] for p in players if p.get("pro_team_id") in teams}
