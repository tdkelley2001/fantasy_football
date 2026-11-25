"""Hand-checkable replay of a saved two-period matchup prefix."""

from dataclasses import replace

import pytest

from fantasy_football.app.contracts import JourneyStandingsPoint, JourneyTeamRank
from fantasy_football.app.historical_journey import historical_journey
from fantasy_football.espn_adapter import capture_response
from fantasy_football.snapshot_store import StoredRawResponse
from tests.test_app_service import FixtureStore
from tests.test_weekly_engine import _supported_snapshot


def _fixture(
    *, gap=False, mismatch=False, tie=False, wrong_winner=False, wrong_total=False
):
    snapshot = _supported_snapshot()
    ids = {1: 3, 2: 4}
    snapshot = replace(
        snapshot,
        matchup_periods=tuple(
            replace(period, matchup_period_id=ids[period.matchup_period_id])
            for period in snapshot.matchup_periods
        ),
        fantasy_matchups=tuple(
            replace(match, matchup_period_id=ids[match.matchup_period_id])
            for match in snapshot.fantasy_matchups
        ),
        rules=replace(
            snapshot.rules,
            championship=replace(
                snapshot.rules.championship,
                rounds=tuple(
                    replace(row, matchup_period_id=4)
                    for row in snapshot.rules.championship.rounds
                ),
            ),
            consolation=replace(
                snapshot.rules.consolation,
                rounds=tuple(
                    replace(row, matchup_period_id=4)
                    for row in snapshot.rules.consolation.rounds
                ),
            ),
        ),
        teams=tuple(
            replace(
                team,
                wins=row[0],
                losses=row[1],
                ties=0,
                points_for=row[2],
                points_against=row[3],
                standing=row[4],
            )
            for team, row in zip(
                snapshot.teams,
                (
                    (2, 0, 201 if wrong_total else 200, 150, 1),
                    (1, 1, 170 if tie else 165, 160, 2 if mismatch else 3),
                    (1, 1, 170, 160, 3 if mismatch else 2),
                    (0, 2, 120, 190 if tie else 185, 4),
                ),
                strict=True,
            )
        ),
    )
    games = [
        {
            "id": index,
            "matchupPeriodId": period,
            "winner": "AWAY" if wrong_winner and index == 1 else "HOME",
            "home": {"teamId": home, "totalPoints": pf},
            "away": {"teamId": away, "totalPoints": pa},
        }
        for index, (period, home, away, pf, pa) in enumerate(
            (
                (1, 1, 2, 100, 70),
                (1, 3, 4, 90, 60),
                (2, 1, 3, 100, 80),
                (2, 2, 4, 100 if tie else 95, 60),
            ),
            1,
        )
    ]
    response = capture_response(
        {
            "scoringPeriodId": 15,
            "settings": {
                "scheduleSettings": {
                    "matchupPeriodCount": 3,
                    "matchupPeriods": {
                        "1": list(range(1, 8)),
                        "2": list(range(8, 15)),
                        "3": [15],
                        "4": [16, 17],
                    },
                }
            },
            "schedule": games[:-1] if gap else games,
        },
        source_id="league-initial",
        request_type="league_initial",
        endpoint="https://example.invalid/league",
        view="mMatchup,mSettings,mStandings",
        parameters=(),
        retrieved_at_utc=snapshot.retrieval_finished_at_utc,
    )
    loaded = replace(
        FixtureStore(snapshot).loaded,
        raw_sources=(StoredRawResponse(response, 0, "gzip"),),
    )
    start = JourneyStandingsPoint(
        scoring_week=15,
        matchup_period_id=3,
        basis="snapshot_start",
        status="complete",
        teams=tuple(
            JourneyTeamRank(team_id=team.team_id, rank=team.standing)
            for team in snapshot.teams
        ),
    )
    return loaded, (start, start.model_copy(update={"basis": "projected"}))


def test_replays_only_multiweek_period_ends_and_reconciles_the_boundary():
    loaded, series = _fixture()
    points = historical_journey(loaded, series)
    assert [row.scoring_week for row in points[:14]] == list(range(1, 15))
    assert [row.scoring_week for row in points[:14] if row.status == "complete"] == [
        7,
        14,
    ]
    assert points[0].period_end_scoring_week == 7
    assert [(row.team_id, row.rank) for row in points[6].teams] == [
        (1, 1),
        (3, 2),
        (2, 3),
        (4, 4),
    ]
    assert points[14].historical_boundary == "reconciled"
    assert points[15] == series[1]


@pytest.mark.parametrize(
    "options", [{"gap": True}, {"wrong_winner": True}, {"wrong_total": True}]
)
def test_unverified_prefix_has_only_gaps(options):
    loaded, series = _fixture(**options)
    points = historical_journey(loaded, series)
    assert all(point.status == "unavailable" for point in points[:14])
    assert all(rank.rank is None for point in points[:14] for rank in point.teams)
    assert points[14].historical_boundary == "records_unverified"


@pytest.mark.parametrize("options", [{"mismatch": True}, {"tie": True}])
def test_starting_rank_disagreement_or_tie_keeps_the_paths_separate(options):
    loaded, series = _fixture(**options)
    points = historical_journey(loaded, series)
    assert points[14].historical_boundary == "ranks_unverified"
    if options.get("tie"):
        assert points[13].status == "unresolved"
        assert {
            (row.team_id, row.rank) for row in points[13].teams if row.unresolved_tie
        } == {(2, 2), (3, 2)}
