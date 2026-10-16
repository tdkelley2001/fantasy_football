from __future__ import annotations

import json
from pathlib import Path

import pytest

from fantasy_football.future_data_audit import (
    FutureDataAuditError,
    PoolPlayer,
    parse_player_cards,
    parse_pro_team_byes,
    parse_remaining_schedule,
    retrieve_player_pool,
)


def pool_wrap(player_id: int, status: str = "FREEAGENT", owner: int = 0) -> dict:
    return {
        "id": player_id,
        "status": status,
        "onTeamId": owner,
        "player": {"id": player_id},
    }


def card_wrap(
    player_id: int,
    *,
    status: str = "FREEAGENT",
    owner: int = 0,
    stats: list[dict] | None = None,
) -> dict:
    return {
        "id": player_id,
        "status": status,
        "onTeamId": owner,
        "player": {
            "id": player_id,
            "defaultPositionId": 1,
            "eligibleSlots": [0, 20],
            "proTeamId": 3,
            "injuryStatus": "ACTIVE",
            "stats": [] if stats is None else stats,
        },
    }


def projection(week: int, value: float, **overrides: object) -> dict:
    item = {
        "seasonId": 2026,
        "scoringPeriodId": week,
        "statSourceId": 1,
        "statSplitTypeId": 1,
        "appliedTotal": value,
    }
    item.update(overrides)
    return item


def test_sanitized_player_info_fixture_matches_raw_contract() -> None:
    fixture = Path(__file__).parent / "fixtures" / "m03_player_info.json"
    response = json.loads(fixture.read_text(encoding="utf-8"))
    pool = {
        101: PoolPlayer(101, "ONTEAM", 1),
        202: PoolPlayer(202, "FREEAGENT", 0),
    }
    players = parse_player_cards(
        response,
        requested_ids=[101, 202],
        pool_by_id=pool,
        season=2026,
        valid_weeks=[7],
    )
    assert dict(players[0].projections) == {7: 12.25}
    assert dict(players[1].projections) == {7: 0.0}


def test_paginated_pool_requires_short_terminal_page() -> None:
    pages = {
        0: {"players": [pool_wrap(1), pool_wrap(2)]},
        2: {"players": [pool_wrap(3)]},
    }
    players, lengths = retrieve_player_pool(lambda offset, _: pages[offset], page_size=2)
    assert [item.player_id for item in players] == [1, 2, 3]
    assert lengths == (2, 1)


def test_paginated_pool_rejects_duplicate_across_pages() -> None:
    pages = {
        0: {"players": [pool_wrap(1), pool_wrap(2)]},
        2: {"players": [pool_wrap(2)]},
    }
    with pytest.raises(FutureDataAuditError, match="duplicate player IDs across pages"):
        retrieve_player_pool(lambda offset, _: pages[offset], page_size=2)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda wrap: wrap.update(onTeamId=4), "FREEAGENT entry has owner"),
        (lambda wrap: wrap.update(status="UNKNOWN"), "unsupported status"),
        (lambda wrap: wrap.update(player={"id": 99}), "outer and inner player IDs disagree"),
        (lambda wrap: wrap.pop("player"), "must be a mapping"),
    ],
)
def test_pool_rejects_malformed_or_conflicting_records(mutator, message: str) -> None:
    wrap = pool_wrap(1)
    mutator(wrap)
    with pytest.raises(FutureDataAuditError, match=message):
        retrieve_player_pool(lambda *_: {"players": [wrap]}, page_size=2)


def test_projection_missing_zero_and_negative_remain_distinct() -> None:
    pool = {1: PoolPlayer(1, "FREEAGENT", 0)}
    response = {"players": [card_wrap(1, stats=[projection(6, 0), projection(7, -1.5)])]}
    (player,) = parse_player_cards(
        response,
        requested_ids=[1],
        pool_by_id=pool,
        season=2026,
        valid_weeks=[6, 7, 8],
    )
    assert dict(player.projections) == {6: 0.0, 7: -1.5, 8: None}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_projection_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(FutureDataAuditError, match="appliedTotal must be finite"):
        parse_player_cards(
            {"players": [card_wrap(1, stats=[projection(6, value)])]},
            requested_ids=[1],
            pool_by_id={1: PoolPlayer(1, "FREEAGENT", 0)},
            season=2026,
            valid_weeks=[6],
        )


@pytest.mark.parametrize(
    ("response", "requested", "message"),
    [
        ({"players": []}, [1], "omitted requested player IDs"),
        ({"players": [card_wrap(2)]}, [1], "unrequested player_id=2"),
        ({"players": [card_wrap(1), card_wrap(1)]}, [1], "duplicates player_id=1"),
        (
            {"players": [card_wrap(1, stats=[projection(99, 2.0)])]},
            [1],
            "unknown fantasy week 99",
        ),
        (
            {"players": [card_wrap(1, stats=[projection(6, 2.0), projection(6, 3.0)])]},
            [1],
            "duplicate projection for week=6",
        ),
    ],
)
def test_player_cards_reject_bad_associations(response, requested, message: str) -> None:
    pool = {1: PoolPlayer(1, "FREEAGENT", 0), 2: PoolPlayer(2, "FREEAGENT", 0)}
    with pytest.raises(FutureDataAuditError, match=message):
        parse_player_cards(
            response,
            requested_ids=requested,
            pool_by_id=pool,
            season=2026,
            valid_weeks=[6, 7],
        )


def test_player_card_rejects_conflicting_ownership() -> None:
    with pytest.raises(FutureDataAuditError, match="conflicts with pool"):
        parse_player_cards(
            {"players": [card_wrap(1, status="ONTEAM", owner=2)]},
            requested_ids=[1],
            pool_by_id={1: PoolPlayer(1, "ONTEAM", 3)},
            season=2026,
            valid_weeks=[6],
        )


def test_projection_missing_applied_total_is_not_coerced_to_zero() -> None:
    stat = projection(6, 0)
    del stat["appliedTotal"]
    with pytest.raises(FutureDataAuditError, match="lacks appliedTotal"):
        parse_player_cards(
            {"players": [card_wrap(1, stats=[stat])]},
            requested_ids=[1],
            pool_by_id={1: PoolPlayer(1, "FREEAGENT", 0)},
            season=2026,
            valid_weeks=[6],
        )


def pro_schedule(*, conflict: bool = False) -> dict:
    return {
        "settings": {
            "proTeams": [
                {"id": 0, "byeWeek": 0, "proGamesByScoringPeriod": {}},
                {
                    "id": 1,
                    "byeWeek": 7,
                    "proGamesByScoringPeriod": {
                        "6": [{"homeProTeamId": 1, "awayProTeamId": 2}],
                        "7": ([{"homeProTeamId": 1, "awayProTeamId": 2}] if conflict else []),
                    },
                },
            ]
        }
    }


def test_bye_is_explicit_and_checked_against_schedule() -> None:
    assert parse_pro_team_byes(
        pro_schedule(), valid_weeks=[6, 7], expected_team_count=1
    ) == {1: 7}
    with pytest.raises(FutureDataAuditError, match="conflicts with a scheduled game"):
        parse_pro_team_byes(
            pro_schedule(conflict=True), valid_weeks=[6, 7], expected_team_count=1
        )


def test_bye_schedule_reconciles_explicit_nfl_team_count() -> None:
    with pytest.raises(FutureDataAuditError, match="1 distinct NFL teams; expected 2"):
        parse_pro_team_byes(
            pro_schedule(), valid_weeks=[6, 7], expected_team_count=2
        )


def test_bye_schedule_rejects_duplicate_nfl_team_record() -> None:
    response = pro_schedule()
    response["settings"]["proTeams"].append(
        {"id": 1, "byeWeek": 7, "proGamesByScoringPeriod": {}}
    )
    with pytest.raises(FutureDataAuditError, match="duplicates pro team id=1"):
        parse_pro_team_byes(
            response, valid_weeks=[6, 7], expected_team_count=1
        )


def schedule_response(missing: bool = False) -> dict:
    schedule = [
        {"id": 1, "matchupPeriodId": 6, "home": {"teamId": 1}, "away": {"teamId": 2}},
        {"id": 2, "matchupPeriodId": 6, "home": {"teamId": 3}, "away": {"teamId": 4}},
    ]
    if missing:
        schedule.pop()
    return {"schedule": schedule}


def test_remaining_schedule_requires_every_team_once() -> None:
    matchups = parse_remaining_schedule(
        schedule_response(), team_ids={1, 2, 3, 4}, future_weeks=[6], expected_team_count=4
    )
    assert len(matchups) == 2
    with pytest.raises(FutureDataAuditError, match="expected every team exactly once"):
        parse_remaining_schedule(
            schedule_response(missing=True),
            team_ids={1, 2, 3, 4},
            future_weeks=[6],
            expected_team_count=4,
        )


def test_remaining_schedule_rejects_missing_side() -> None:
    response = schedule_response()
    del response["schedule"][0]["away"]
    with pytest.raises(FutureDataAuditError, match="away must be a mapping"):
        parse_remaining_schedule(
            response, team_ids={1, 2, 3, 4}, future_weeks=[6], expected_team_count=4
        )
