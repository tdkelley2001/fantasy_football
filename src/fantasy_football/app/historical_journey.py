"""Replay source-settled regular-season standings for the Journey display."""

from __future__ import annotations

from fractions import Fraction

from fantasy_football.app.contracts import JourneyStandingsPoint, JourneyTeamRank
from fantasy_football.canonical.model import InterpretationStatus
from fantasy_football.current_week import (
    CurrentWeekEvidenceError,
    reconcile_standings_prefix,
)
from fantasy_football.espn_adapter import EspnAdapterError, _parse_periods
from fantasy_football.snapshot_store import LoadedSnapshot
from fantasy_football.weekly_engine import (
    ModeledStanding,
    WeeklyEngineError,
    rank_standings,
)


def historical_journey(
    loaded: LoadedSnapshot, series: tuple[JourneyStandingsPoint, ...]
) -> tuple[JourneyStandingsPoint, ...]:
    """Show only ranks from a complete prefix reconciled to the snapshot records."""
    snapshot = loaded.snapshot
    source = next(
        (
            item.response
            for item in loaded.raw_sources
            if item.response.source_id == "league-initial"
            and {"mSettings", "mMatchup", "mStandings"}
            <= set(item.response.view.split(","))
        ),
        None,
    )
    if source is None or snapshot.first_simulation_week == 1:
        return series

    root = source.payload
    try:
        horizon, regular_count, period_map = _parse_periods(
            root,
            first_week=snapshot.first_simulation_week,
            final_week=snapshot.final_simulation_week,
        )
    except EspnAdapterError:
        return series
    if horizon != snapshot.matchup_periods:
        return series
    regular = {
        pid: period_map[pid] for pid in range(1, regular_count + 1) if pid in period_map
    }
    weeks = tuple(week for membership in regular.values() for week in membership)
    if len(regular) != regular_count or weeks != tuple(range(1, len(weeks) + 1)):
        return series
    first = snapshot.first_simulation_week
    prior_periods = {
        pid for pid, membership in regular.items() if membership[-1] < first
    }
    schedule = root.get("schedule")
    ranks = {}
    if (
        isinstance(schedule, list)
        and root.get("scoringPeriodId") == first
        and snapshot.rules.standings.scoring_type == "H2H_POINTS"
    ):
        ranks = _replay_prefix(loaded, schedule, prior_periods, regular_count)

    unavailable = tuple(
        JourneyTeamRank(team_id=team.team_id, rank=None)
        for team in sorted(snapshot.teams, key=lambda team: team.team_id)
    )
    points = []
    for pid, membership in regular.items():
        end = membership[-1]
        for week in membership:
            if week >= first:
                break
            ranking = ranks.get(pid) if week == end else None
            points.append(
                JourneyStandingsPoint(
                    scoring_week=week,
                    matchup_period_id=pid,
                    period_end_scoring_week=end,
                    basis="historical_replay",
                    status=("complete" if ranking.has_unique_order else "unresolved")
                    if ranking
                    else "unavailable",
                    teams=tuple(
                        JourneyTeamRank(
                            team_id=row.team_id,
                            rank=row.rank,
                            unresolved_tie=not row.uniquely_ranked,
                        )
                        for row in ranking.rows
                    )
                    if ranking
                    else unavailable,
                )
            )
    if not points:
        return series
    if series and series[0].basis == "snapshot_start":
        current = series[0]
        previous = points[-1]
        if not ranks or previous.status == "unavailable":
            boundary = "records_unverified"
        elif previous.status == current.status == "complete" and {
            row.team_id: row.rank for row in previous.teams
        } == {row.team_id: row.rank for row in current.teams}:
            boundary = "reconciled"
        else:
            boundary = "ranks_unverified"
        series = (
            current.model_copy(update={"historical_boundary": boundary}),
            *series[1:],
        )
    return (*points, *series)


def _replay_prefix(loaded, schedule, prior_periods, regular_count):
    snapshot = loaded.snapshot
    if not all(isinstance(game, dict) for game in schedule):
        return {}
    if any(type(game.get("matchupPeriodId")) is not int for game in schedule):
        return {}
    games = [game for game in schedule if game["matchupPeriodId"] in prior_periods]
    ids = [game.get("id") for game in games]
    if any(type(key) is not int or key <= 0 for key in ids) or len(set(ids)) != len(
        ids
    ):
        return {}
    try:
        reconcile_standings_prefix(snapshot.teams, games, prior_periods, regular_count)
    except (CurrentWeekEvidenceError, OverflowError, TypeError):
        return {}

    records = {
        team.team_id: [0, 0, 0, Fraction(0), Fraction(0)] for team in snapshot.teams
    }
    ranks = {}
    ties_supported = any(
        rule.rule_id == snapshot.rules.standings.matchup_tie_rule_id
        and rule.status is InterpretationStatus.UNDERSTOOD
        and rule.normalized_value == "allow_ties"
        for rule in snapshot.rules.interpretations
    )
    for pid in sorted(prior_periods):
        for game in games:
            if game["matchupPeriodId"] != pid:
                continue
            home, away = game["home"], game["away"]
            scored, conceded = (
                Fraction(str(side["totalPoints"])) for side in (home, away)
            )
            winner = game["winner"]
            if winner != (
                "HOME" if scored > conceded else "AWAY" if scored < conceded else "TIE"
            ):
                return {}
            if winner == "TIE" and not ties_supported:
                return {}
            for side, points, against, win in (
                (home, scored, conceded, "HOME"),
                (away, conceded, scored, "AWAY"),
            ):
                row = records[side["teamId"]]
                row[0] += winner == win
                row[1] += winner not in {win, "TIE"}
                row[2] += winner == "TIE"
                row[3] += points
                row[4] += against
        try:
            ranks[pid] = rank_standings(
                snapshot,
                tuple(
                    ModeledStanding(team, w, l, t, float(pf), float(pa))
                    for team, (w, l, t, pf, pa) in records.items()
                ),
            )
        except (OverflowError, WeeklyEngineError):
            return {}
    return ranks
