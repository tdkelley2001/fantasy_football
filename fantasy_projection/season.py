"""Pure deterministic season projection over supplied league states.

No fetching, credentials, UI, or persistence belongs in this module. Player points
are already scored under the league's scoring system by the data adapter.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from math import isfinite
from typing import Any

from .lineup import optimize_lineup


class SeasonModelError(ValueError):
    """An invalid state or unsupported rule, safe to explain to an app user."""


@dataclass(frozen=True)
class SeasonRules:
    regular_periods: int
    period_weeks: dict[int, tuple[int, ...]]
    playoff_team_count: int
    playoff_rounds: tuple[tuple[int, ...], ...]
    playoff_reseed: bool = False
    consolation_ladder: bool = True
    seeding_tiebreak: str = "TOTAL_POINTS_SCORED"
    playoff_tiebreak: str = "HIGHER_SEED"


@dataclass(frozen=True)
class LeagueState:
    league_id: int
    season: int
    first_week: int
    current_week: int
    final_week: int
    rules: SeasonRules
    teams: list[dict[str, Any]]
    rosters: list[dict[str, Any]]
    player_projections: list[dict[str, Any]]
    starter_slots: list[dict[str, Any]]
    schedule_rows: list[dict[str, Any]]
    # Completed postseason games use the same normalized matchup schema.
    postseason_results: list[dict[str, Any]] = field(default_factory=list)
    # Final team-week actuals allow partially completed multi-week rounds.
    actual_weekly_points: list[dict[str, Any]] = field(default_factory=list)
    # A hypothetical state's pre-effective ownership, never inferred from ESPN.
    baseline_rosters: list[dict[str, Any]] | None = None
    available_players: list[dict[str, Any]] = field(default_factory=list)
    # Acquisition/roster settings used by existing move validators, not the engine.
    settings_payload: dict[str, Any] = field(default_factory=dict)
    # Explicit schedule evidence; absent entries must not be inferred from zero points.
    player_bye_weeks: dict[int, tuple[int, ...]] = field(default_factory=dict)

    def with_rosters(self, rosters: list[dict[str, Any]]) -> LeagueState:
        """Create an isolated hypothetical state with a fixed ownership baseline."""
        return replace(deepcopy(self), rosters=deepcopy(rosters),
                       baseline_rosters=deepcopy(self.baseline_rosters
                                                if self.baseline_rosters is not None
                                                else self.rosters))


@dataclass
class SeasonProjection:
    state: LeagueState
    optimal_lineups: list[dict[str, Any]]
    weekly_team_projections: list[dict[str, Any]]
    regular_season_matchups: list[dict[str, Any]]
    projected_standings: list[dict[str, Any]]
    postseason_matchups: list[dict[str, Any]]
    final_standings: list[dict[str, Any]]
    summary: dict[str, Any]
    team_outcomes: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def _unique(rows, key, label):
    keys = [key(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise SeasonModelError(f"Duplicate {label} in league state.")


def validate_state(state: LeagueState, effective_week: int) -> None:
    if not state.teams:
        raise SeasonModelError("The league has no teams.")
    if any(type(w) is not int for w in (state.first_week, state.current_week, state.final_week)) or not (1 <= state.first_week <= state.current_week <= state.final_week + 1):
        raise SeasonModelError("Invalid season scoring-week boundaries.")
    if type(effective_week) is not int or not state.current_week <= effective_week <= state.final_week + 1:
        raise SeasonModelError("Effective week must be between the current week and season end + 1.")
    _unique(state.teams, lambda r: r["team_id"], "team")
    ids = {r["team_id"] for r in state.teams}
    for roster in (state.rosters, state.baseline_rosters):
        if roster is None:
            continue
        _unique(roster, lambda r: r["player_id"], "player ownership")
        if any(r["team_id"] not in ids for r in roster):
            raise SeasonModelError("A roster references an unknown team.")
    _unique(state.player_projections, lambda r: (r["player_id"], r["week"]), "player-week projection")
    _unique(state.actual_weekly_points, lambda r: (r["team_id"], r["week"]), "team-week actual")
    _unique(state.starter_slots, lambda r: (r["slot_id"], r["slot_instance"]), "starter slot")
    if not state.starter_slots:
        raise SeasonModelError("The league has no starter slots.")
    for row in state.player_projections:
        value = row.get("projected_points")
        if value is not None and (not isinstance(value, (int, float)) or not isfinite(value)):
            raise SeasonModelError("Player projections must be finite numbers or missing.")
    for row in state.actual_weekly_points:
        if row["team_id"] not in ids or not state.first_week <= row["week"] <= min(state.current_week, state.final_week):
            raise SeasonModelError("Team-week actuals must be for known teams and completed weeks.")
        if not isinstance(row["points"], (int, float)) or not isfinite(row["points"]):
            raise SeasonModelError("Team-week actuals must be finite numbers.")
    rules = state.rules
    if rules.seeding_tiebreak != "TOTAL_POINTS_SCORED":
        raise SeasonModelError(f"Unsupported seeding tiebreak: {rules.seeding_tiebreak}.")
    if rules.playoff_tiebreak != "HIGHER_SEED":
        raise SeasonModelError(f"Unsupported playoff tiebreak: {rules.playoff_tiebreak}.")
    count = rules.playoff_team_count
    if count not in (0, 2, 4, 6, 8) or count > len(ids):
        raise SeasonModelError("Supported playoff fields are 0, 2, 4, 6, or 8 teams, within league size.")
    required_rounds = {0: 0, 2: 1, 4: 2, 6: 3, 8: 3}[count]
    if len(rules.playoff_rounds) != required_rounds:
        raise SeasonModelError(f"A {count}-team playoff requires {required_rounds} rounds.")
    if count and rules.consolation_ladder and (len(ids) - count) % 2:
        raise SeasonModelError("Odd-sized consolation ladders are not supported.")
    if rules.regular_periods < 1 or any(p not in rules.period_weeks for p in range(1, rules.regular_periods + 1)):
        raise SeasonModelError("Every regular-season period needs an explicit scoring-week mapping.")
    phases = [rules.period_weeks[p] for p in range(1, rules.regular_periods + 1)] + list(rules.playoff_rounds)
    previous = state.first_week - 1
    for weeks in phases:
        if not weeks or tuple(sorted(set(weeks))) != tuple(weeks) or min(weeks) <= previous or max(weeks) > state.final_week:
            raise SeasonModelError("Scoring periods must contain ordered, nonoverlapping weeks within the season.")
        previous = max(weeks)
    if [week for weeks in phases for week in weeks] != list(range(state.first_week, state.final_week + 1)):
        raise SeasonModelError("Configured periods must cover the complete scoring season without gaps.")
    if {r["matchup_period"] for r in state.schedule_rows} != set(range(1, rules.regular_periods + 1)):
        raise SeasonModelError("The regular-season schedule is incomplete.")
    participants = [(r["matchup_period"], team) for r in state.schedule_rows
                    for team in (r["home_team_id"], r["away_team_id"])]
    if len(participants) != len(set(participants)):
        raise SeasonModelError("Multiple matchups per team in one period are not supported.")
    for rows, postseason in ((state.schedule_rows, False), (state.postseason_results, True)):
        _unique(rows, lambda r: (r["matchup_period"], frozenset((r["home_team_id"], r["away_team_id"]))), "matchup")
        for row in rows:
            if row["home_team_id"] not in ids or row["away_team_id"] not in ids or row["home_team_id"] == row["away_team_id"]:
                raise SeasonModelError("A matchup must reference two distinct known teams.")
            period = row["matchup_period"]
            limit = rules.regular_periods + len(rules.playoff_rounds)
            if not (rules.regular_periods < period <= limit if postseason else 1 <= period <= rules.regular_periods):
                raise SeasonModelError("A matchup has an invalid period.")
            if row["winner"] not in ("HOME", "AWAY", "TIE", "UNDECIDED"):
                raise SeasonModelError("Unknown matchup result status.")
            if not postseason and row["winner"] == "UNDECIDED" and max(rules.period_weeks[period]) < state.current_week:
                raise SeasonModelError("A completed regular-season matchup is missing its recorded result.")
            if row["winner"] != "UNDECIDED":
                for side in ("home", "away"):
                    score = row.get(f"actual_{side}_points")
                    if not isinstance(score, (int, float)) or not isfinite(score):
                        raise SeasonModelError("Completed matchups require both actual scores.")


def season_results(state: LeagueState, weekly: list[dict[str, Any]]):
    """Shared standings/bracket stage, also used with cached search lineup scores."""
    from .regular_season import project_regular_season, build_projected_standings
    from .postseason import project_postseason

    games = project_regular_season(state.schedule_rows, state.teams, weekly, state.rules)
    standings = build_projected_standings(state.teams, games, state.rules)
    playoffs, final, summary = project_postseason(standings, state.teams, weekly, state.rules,
                                                state.postseason_results, state.current_week)
    return games, standings, playoffs, final, summary


def project_season(state: LeagueState, effective_week: int | None = None) -> SeasonProjection:
    """Optimize unresolved weeks and play out the schedule without mutating input.

    A week in progress is a full-week projection, not actual points plus a full
    projection. Player locks are not modeled. Earlier finished scoring weeks use
    supplied actuals; finished matchup totals/winners always take precedence.
    """
    effective_week = state.current_week if effective_week is None else effective_week
    validate_state(state, effective_week)
    state = deepcopy(state)
    ids = {t["team_id"]: t["team_name"] for t in state.teams}
    projections = {(p["player_id"], p["week"]): p["projected_points"]
                   for p in state.player_projections if p.get("projected_points") is not None}
    actuals = {(r["team_id"], r["week"]): r["points"] for r in state.actual_weekly_points}
    finished = set()
    for game in state.schedule_rows + state.postseason_results:
        if game["winner"] == "UNDECIDED":
            continue
        period = game["matchup_period"]
        weeks = (state.rules.period_weeks[period] if period <= state.rules.regular_periods
                 else state.rules.playoff_rounds[period - state.rules.regular_periods - 1])
        if max(weeks) > state.current_week:
            raise SeasonModelError("A future matchup cannot have a completed result.")
        finished.update((team, week) for team in (game["home_team_id"], game["away_team_id"]) for week in weeks)
        if len(weeks) == 1:
            for side in ("home", "away"):
                key = (game[f"{side}_team_id"], weeks[0])
                score = game[f"actual_{side}_points"]
                if key in actuals and actuals[key] != score:
                    raise SeasonModelError("Completed matchup and team-week scores disagree.")
                actuals[key] = score
    required = set()
    for game in state.schedule_rows:
        if game["winner"] == "UNDECIDED":
            required.update((team, week) for team in (game["home_team_id"], game["away_team_id"])
                            for week in state.rules.period_weeks[game["matchup_period"]])
    # Past postseason scores are checked against actual bracket participants
    # during bracket resolution. Future lineups are optimized for every team.
    lineups, weekly, diagnostics = [], [], []
    for team_id, name in sorted(ids.items()):
        for week in range(state.first_week, state.final_week + 1):
            key = (team_id, week)
            if key in actuals:
                weekly.append(dict(team_id=team_id, team_name=name, week=week,
                                   projected_points=actuals[key], result_type="ACTUAL"))
                continue
            if key in finished:
                # A multi-week final may have only an aggregate actual score.
                # Do not fabricate its individual weekly scores or lineups.
                continue
            if week < state.current_week:
                if key in required:
                    raise SeasonModelError(f"Missing completed-week score for team {team_id}, week {week}.")
                continue
            ownership = (state.baseline_rosters if week < effective_week and state.baseline_rosters is not None
                         else state.rosters)
            roster = sorted((p for p in ownership if p["team_id"] == team_id), key=lambda p: p["player_id"])
            try:
                total, lineup = optimize_lineup(roster, state.starter_slots, projections, week)
            except RuntimeError as exc:
                raise SeasonModelError(f"Team {team_id}, week {week}: {exc}") from exc
            starters = {r["player_id"] for r in lineup}
            for player in roster:
                if (player["player_id"], week) not in projections:
                    diagnostics.append(dict(code="MISSING_PROJECTION", team_id=team_id, week=week,
                                            player_id=player["player_id"], player_name=player["player_name"],
                                            starter=player["player_id"] in starters, assumed_points=0.0))
            missing = sum((r["player_id"], week) not in projections for r in lineup)
            weekly.append(dict(team_id=team_id, team_name=name, week=week, projected_points=total,
                               result_type="PROJECTED", missing_starters=missing))
            lineups.extend(dict(team_id=team_id, team_name=name, week=week, **row,
                                projection_missing=(row["player_id"], week) not in projections) for row in lineup)
    games, standings, playoffs, final, postseason_summary = season_results(state, weekly)
    final_by_id = {r["team_id"]: r for r in final}
    outcomes = []
    for row in standings:
        finish = final_by_id[row["team_id"]]
        qualified = finish["made_championship_playoffs"]
        outcomes.append(dict(team_id=row["team_id"], team_name=row["team_name"],
                             wins=row["wins"], losses=row["losses"], ties=row["ties"],
                             points_for=row["points_for"], seed=row["seed"], final_place=finish["final_place"],
                             remaining_points=sum(w["projected_points"] for w in weekly
                                                  if w["team_id"] == row["team_id"] and w["week"] >= state.current_week
                                                  and w["result_type"] == "PROJECTED"),
                             made_playoffs=qualified,
                             playoff_result=("NO_PLAYOFFS" if not state.rules.playoff_team_count else
                                             "CHAMPION" if finish["final_place"] == 1 else
                                             "RUNNER_UP" if finish["final_place"] == 2 else
                                             "ELIMINATED" if qualified else "DID_NOT_QUALIFY")))
    summary = dict(league_id=state.league_id, season=state.season, model="DETERMINISTIC",
                   effective_week=effective_week, team_count=len(ids),
                   rostered_player_count=len(state.rosters), player_week_projection_count=len(projections),
                   first_scoring_period=state.first_week, current_scoring_period=state.current_week,
                   final_scoring_period=state.final_week, regular_season_matchup_periods=state.rules.regular_periods,
                   regular_season_final_week=max(state.rules.period_weeks[state.rules.regular_periods]),
                   playoff_seeding_rule=state.rules.seeding_tiebreak,
                   regular_season_champion_team_id=standings[0]["team_id"],
                   regular_season_champion=standings[0]["team_name"],
                   regular_season_champion_record=standings[0]["record"],
                   missing_projection_count=len(diagnostics),
                   missing_starter_projection_count=sum(d["starter"] for d in diagnostics),
                   assumptions=["Current-week scores use full-week projections; player locks and live partial scores are not modeled.",
                                "Missing player projections count as zero and are listed in coverage details.",
                                "Exact projected playoff ties use higher regular-season seed; exact seeding ties use team ID."],
                   **postseason_summary)
    return SeasonProjection(state, lineups, weekly, games, standings, playoffs, final, summary, outcomes, diagnostics)
