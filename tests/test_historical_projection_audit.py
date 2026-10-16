from __future__ import annotations

import pytest

from fantasy_football.historical_projection_audit import (
    HistoricalProjectionAuditError,
    PROVENANCE_CLASS,
    compare_playercard,
    parse_historical_player_page,
    retrieve_historical_week,
    scoring_signature,
    summarize_sample,
)


def stat(source: int, value: float, *, season: int = 2025, week: int = 8, **extra: object) -> dict:
    result = {
        "seasonId": season,
        "scoringPeriodId": week,
        "statSourceId": source,
        "statSplitTypeId": 1,
        "appliedTotal": value,
        "stats": {"1": 10} if source == 0 else {},
    }
    result.update(extra)
    return result


def player(player_id: int, stats: list[dict], *, position: int = 1) -> dict:
    return {
        "id": player_id,
        "status": "FREEAGENT",
        "onTeamId": 0,
        "player": {
            "id": player_id,
            "defaultPositionId": position,
            "proTeamId": 3,
            "stats": stats,
        },
    }


def response(*players: dict) -> dict:
    return {"players": list(players)}


def scoring(points: float = 0.1) -> dict:
    return {
        "settings": {
            "scoringSettings": {
                "scoringItems": [
                    {"statId": 3, "points": points, "pointsOverrides": {}},
                    {"statId": 4, "points": 4, "pointsOverrides": {}},
                ]
            }
        }
    }


def test_projection_and_actual_are_matched_by_source() -> None:
    (record,) = parse_historical_player_page(
        response(player(10, [stat(1, 12.5), stat(0, 8.0)])), season=2025, week=8
    )
    assert record.projection == 12.5
    assert record.actual == 8.0
    assert record.projection_status == "positive"
    assert record.actual_stat_breakdown_present is True
    assert record.provenance_class == PROVENANCE_CLASS


def test_missing_zero_and_missing_actual_remain_distinct() -> None:
    records = parse_historical_player_page(
        response(
            player(1, [stat(0, 3.0)]),
            player(2, [stat(1, 0.0), stat(0, 0.0)]),
            player(3, [stat(1, 4.0)]),
        ),
        season=2025,
        week=8,
    )
    assert [(item.projection_status, item.actual_status) for item in records] == [
        ("missing", "positive"),
        ("explicit_zero", "explicit_zero"),
        ("positive", "missing"),
    ]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda item: item.update({"seasonId": 2024}), "weekly stat association"),
        (lambda item: item.update({"scoringPeriodId": 7}), "weekly stat association"),
        (lambda item: item.update({"statSourceId": 9}), "unsupported statSourceId"),
        (lambda item: item.pop("appliedTotal"), "lacks appliedTotal"),
        (lambda item: item.update({"appliedTotal": float("nan")}), "finite number"),
    ],
)
def test_wrong_associations_and_malformed_stats_fail(mutate, message: str) -> None:
    item = stat(1, 5.0)
    mutate(item)
    with pytest.raises(HistoricalProjectionAuditError, match=message):
        parse_historical_player_page(response(player(1, [item])), season=2025, week=8)


@pytest.mark.parametrize("source", [0, 1])
def test_duplicate_projection_or_actual_fails(source: int) -> None:
    with pytest.raises(HistoricalProjectionAuditError, match="duplicate historical"):
        parse_historical_player_page(
            response(player(1, [stat(source, 5.0), stat(source, 6.0)])),
            season=2025,
            week=8,
        )


def test_season_total_is_not_interpreted_as_weekly_projection() -> None:
    season_total = stat(1, 200.0, week=0)
    season_total["statSplitTypeId"] = 0
    (record,) = parse_historical_player_page(
        response(player(1, [season_total, stat(0, 7.0)])), season=2025, week=8
    )
    assert record.projection is None
    assert record.actual == 7.0


def test_as_of_shaped_metadata_does_not_authenticate_pregame_timing() -> None:
    (record,) = parse_historical_player_page(
        response(player(1, [stat(1, 5.0, updatedDate=123456), stat(0, 6.0)])),
        season=2025,
        week=8,
    )
    assert record.as_of_metadata_present is True
    assert record.provenance_class == PROVENANCE_CLASS


def test_pagination_rejects_duplicate_players() -> None:
    pages = {
        0: response(player(1, [stat(1, 5.0)]), player(2, [stat(1, 6.0)])),
        2: response(player(2, [stat(1, 6.0)])),
    }
    with pytest.raises(HistoricalProjectionAuditError, match="duplicate player IDs across pages"):
        retrieve_historical_week(lambda offset, _: pages[offset], season=2025, week=8, page_size=2)


def test_scoring_signatures_detect_scoring_system_mismatch() -> None:
    signature_a, count_a = scoring_signature(scoring(0.1))
    signature_b, count_b = scoring_signature(scoring(0.2))
    assert count_a == count_b == 2
    assert signature_a != signature_b


def test_summary_reports_hindsight_signal_without_claiming_leakage_free() -> None:
    records = parse_historical_player_page(
        response(*(player(index, [stat(1, 10.0), stat(0, 10.0)]) for index in range(1, 6))),
        season=2025,
        week=8,
    )
    summary = summarize_sample(
        records,
        season=2025,
        week=8,
        regular_season_end=14,
        retrieved_at_utc="2026-10-16T00:00:00+00:00",
        endpoint="https://example.invalid",
        scoring_signature_value="abc",
        scoring_item_count=2,
        page_size=250,
        page_lengths=(5,),
        repeat_first_page_stable=True,
    )
    assert summary.exact_projection_actual_matches == 5
    assert summary.hindsight_exact_tracking_signal == "potential_hindsight_contamination"


def test_summary_classifies_negative_projection_separately_from_low_positive() -> None:
    records = parse_historical_player_page(
        response(
            player(1, [stat(1, -2.5), stat(0, 3.0)]),
            player(2, [stat(1, 2.5), stat(0, 1.0)]),
        ),
        season=2025,
        week=8,
    )
    summary = summarize_sample(
        records,
        season=2025,
        week=8,
        regular_season_end=14,
        retrieved_at_utc="2026-10-16T00:00:00+00:00",
        endpoint="https://example.invalid",
        scoring_signature_value="abc",
        scoring_item_count=2,
        page_size=250,
        page_lengths=(2,),
        repeat_first_page_stable=True,
    )

    assert summary.counts_by_projection_magnitude == {
        "low_positive_lt_5": 1,
        "negative": 1,
    }


def test_playercard_comparison_handles_multiweek_response() -> None:
    week_1 = parse_historical_player_page(response(player(1, [stat(1, 5.0, week=1), stat(0, 6.0, week=1)])), season=2025, week=1)
    week_8 = parse_historical_player_page(response(player(1, [stat(1, 7.0), stat(0, 8.0)])), season=2025, week=8)
    card = response(player(1, [stat(1, 5.0, week=1), stat(0, 6.0, week=1), stat(1, 7.0), stat(0, 8.0)]))
    result = compare_playercard({1: week_1, 8: week_8}, card, season=2025)
    assert result["compared_player_weeks"] == 2
    assert result["exact_projection_actual_agreements"] == 2
    assert result["proves_pregame_timing"] is False


def test_wrapper_player_identity_and_actual_breakdown_are_validated() -> None:
    malformed = player(1, [stat(0, 5.0)])
    malformed["player"]["id"] = 2
    with pytest.raises(HistoricalProjectionAuditError, match="IDs disagree"):
        parse_historical_player_page(response(malformed), season=2025, week=8)
    malformed = player(1, [stat(0, 5.0)])
    malformed["player"]["stats"][0]["stats"] = []
    with pytest.raises(HistoricalProjectionAuditError, match="breakdown must be a mapping"):
        parse_historical_player_page(response(malformed), season=2025, week=8)
