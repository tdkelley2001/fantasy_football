from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from fantasy_football.espn_connectivity import (
    ConnectivityAuditError,
    audit_league,
    render_summary,
)


def _player(player_id: int, team_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        playerId=player_id,
        name=f"Player {player_id}",
        onTeamId=team_id,
        position="RB",
        lineupSlot="RB",
        eligibleSlots=["RB", "RB/WR/TE", "BE"],
    )


def _team(team_id: int, standing: int, player_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        team_id=team_id,
        team_name=f"Team {team_id}",
        standing=standing,
        wins=5,
        losses=1,
        ties=0,
        points_for=700.5,
        roster=[_player(player_id, team_id)],
        owners=[{"id": f"manager-{team_id}", "displayName": "Private Name"}],
    )


def _league() -> SimpleNamespace:
    return SimpleNamespace(
        league_id=123456,
        year=2026,
        current_week=6,
        settings=SimpleNamespace(
            name="Test League",
            team_count=2,
            scoring_format=[
                {"id": 3, "label": "Passing Yards", "abbr": "PY", "points": 0.04}
            ],
        ),
        teams=[_team(1, 1, 101), _team(2, 2, 202)],
    )


def _raw_league_data() -> dict[str, object]:
    return {
        "settings": {
            "rosterSettings": {
                "lineupSlotCounts": {"0": 1, "2": 2, "20": 6, "22": 0}
            }
        }
    }


def _audit(league: SimpleNamespace):
    return audit_league(
        league,
        raw_league_data=_raw_league_data(),
        source_endpoint="https://fantasy.espn.com/apis/v3/games/ffl/test",
        expected_league_id=123456,
        expected_season=2026,
        expected_team_count=2,
    )


def test_audit_reconciles_teams_rosters_and_settings() -> None:
    report = _audit(_league())

    assert report.observed_team_count == 2
    assert report.reported_team_count == 2
    assert report.observed_player_count == 2
    assert report.position_slot_counts == {"QB": 1, "RB": 2, "BE": 6}
    assert report.teams[0].manager_ids == ("manager-1",)
    assert report.teams[0].players[0].eligible_lineup_slots == (
        "RB",
        "RB/WR/TE",
        "BE",
    )


def test_audit_accepts_negative_team_defense_player_id() -> None:
    league = _league()
    defense = league.teams[0].roster[0]
    defense.playerId = -16018
    defense.name = "Team Defense"
    defense.position = "D/ST"
    defense.lineupSlot = "D/ST"
    defense.eligibleSlots = ["D/ST", "BE"]

    report = _audit(league)

    assert report.teams[0].players[0].player_id == -16018


def test_audit_rejects_wrong_expected_team_count() -> None:
    with pytest.raises(ConnectivityAuditError, match="team-count mismatch"):
        audit_league(
            _league(),
            raw_league_data=_raw_league_data(),
            source_endpoint="https://fantasy.espn.com/apis/v3/games/ffl/test",
            expected_league_id=123456,
            expected_season=2026,
            expected_team_count=14,
        )


def test_audit_rejects_duplicate_team_id() -> None:
    league = _league()
    league.teams[1].team_id = 1

    with pytest.raises(ConnectivityAuditError, match="duplicate team_id=1"):
        _audit(league)


def test_audit_rejects_duplicate_player_ownership() -> None:
    league = _league()
    league.teams[1].roster[0].playerId = 101

    with pytest.raises(ConnectivityAuditError, match="duplicate player ownership"):
        _audit(league)


def test_audit_rejects_player_owner_mismatch() -> None:
    league = _league()
    league.teams[1].roster[0].onTeamId = 1

    with pytest.raises(ConnectivityAuditError, match="player ownership mismatch"):
        _audit(league)


def test_audit_rejects_empty_eligible_slots() -> None:
    league = _league()
    league.teams[0].roster[0].eligibleSlots = []

    with pytest.raises(ConnectivityAuditError, match="eligibleSlots is empty"):
        _audit(league)


def test_audit_rejects_missing_scoring_settings() -> None:
    league = deepcopy(_league())
    league.settings.scoring_format = []

    with pytest.raises(ConnectivityAuditError, match="scoring_format"):
        _audit(league)


def test_audit_rejects_unknown_configured_lineup_slot() -> None:
    raw_data = _raw_league_data()
    raw_data["settings"]["rosterSettings"]["lineupSlotCounts"]["999"] = 1

    with pytest.raises(ConnectivityAuditError, match="no verified espn-api mapping"):
        audit_league(
            _league(),
            raw_league_data=raw_data,
            source_endpoint="https://fantasy.espn.com/apis/v3/games/ffl/test",
            expected_league_id=123456,
            expected_season=2026,
            expected_team_count=2,
        )


def test_summary_classifies_findings_without_manager_names() -> None:
    summary = render_summary(_audit(_league()))

    assert "Verified information:" in summary
    assert "Missing or inaccessible information:" in summary
    assert "Requires further investigation:" in summary
    assert "manager-1" in summary
    assert "Private Name" not in summary
