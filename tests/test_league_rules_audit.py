from __future__ import annotations

from copy import deepcopy

import pytest

from fantasy_football.league_rules_audit import (
    LeagueRulesAuditError,
    audit_roster,
    audit_schedule,
    audit_waivers,
    build_report,
    summarize_historical_bracket,
)


def raw_rules() -> dict:
    counts = {str(i): 0 for i in range(24)}
    counts.update({"0": 1, "2": 2, "4": 2, "6": 1, "16": 1, "17": 1, "20": 7, "21": 1, "23": 1})
    teams = []
    for team_id in range(1, 15):
        entries = [{"lineupSlotId": 20} for _ in range(16)]
        if team_id <= 10:
            entries.append({"lineupSlotId": 21, "playerPoolEntry": {"player": {"injuryStatus": "INJURY_RESERVE", "eligibleSlots": [20, 21]}}})
        teams.append({"id": team_id, "waiverRank": team_id, "playoffSeed": team_id, "record": {"overall": {"wins": 7, "losses": 6, "ties": 0, "pointsFor": 1000 + team_id, "pointsAgainst": 900 + team_id}}, "transactionCounter": {"trades": 0}, "roster": {"entries": entries}})
    return {
        "settings": {
            "rosterSettings": {
                "lineupSlotCounts": counts,
                "positionLimits": {"1": 4, "2": 8},
                "isBenchUnlimited": True,
                "isUsingUndroppableList": True,
                "lineupLocktimeType": "INDIVIDUAL_GAME",
                "rosterLocktimeType": "INDIVIDUAL_GAME",
                "moveLimit": -1,
            },
            "acquisitionSettings": {
                "acquisitionType": "WAIVERS_TRADITIONAL",
                "isUsingAcquisitionBudget": False,
                "acquisitionBudget": 100,
                "minimumBid": 1,
                "acquisitionLimit": -1,
                "matchupAcquisitionLimit": -1.0,
                "waiverHours": 24,
                "waiverOrderReset": True,
                "waiverProcessDays": ["MONDAY", "WEDNESDAY"],
                "waiverProcessHour": 11,
                "transactionLockingEnabled": False,
            },
            "tradeSettings": {"deadlineDate": 1796230800000, "revisionHours": 24, "vetoVotesRequired": 8, "max": -1, "allowOutOfUniverse": False},
            "scheduleSettings": {
                "playoffTeamCount": 6,
                "playoffMatchupPeriodLengthByRound": {"1": 1, "2": 1, "3": 2},
                "matchupPeriods": {str(i): [i] for i in range(1, 17)} | {"17": [17, 18]},
                "matchupPeriodCount": 14,
                "playoffReseed": False,
                "playoffSeedingRule": "TOTAL_POINTS_SCORED",
                "consolationLadderDisabled": False,
            },
            "scoringSettings": {"scoringType": "H2H_POINTS", "matchupTieRule": "NONE", "playoffMatchupTieRule": "NONE"},
        },
        "teams": teams,
        "schedule": [],
    }


def historical_rules() -> dict:
    raw = raw_rules()
    raw["teams"] = raw["teams"][:12]
    raw["schedule"] = [
        {"id": 100, "matchupPeriodId": 15, "home": {"teamId": 1}, "winnerByScoringPeriod": []},
        {"id": 101, "matchupPeriodId": 15, "home": {"teamId": 4}, "away": {"teamId": 5}, "winnerByScoringPeriod": ["HOME"]},
        {"id": 102, "matchupPeriodId": 17, "home": {"teamId": 1}, "away": {"teamId": 2}, "winnerByScoringPeriod": ["HOME", "AWAY"]},
    ]
    return raw


def test_complete_rules_report_is_sanitized_and_auditable() -> None:
    report = build_report(raw_rules(), [(2025, historical_rules())], league_id=9, season=2026, endpoint="https://example.invalid", expected_team_count=14, expected_playoff_teams=6)
    assert report.roster["ordinary_capacity"] == 16
    assert report.roster["total_capacity_with_ir"] == 17
    assert report.waivers["current_priority_is_complete_permutation"] is True
    assert report.championship["round_lengths"] == {"1": 1, "2": 1, "3": 2}
    assert report.consolation["expected_participant_count"] == 8
    assert report.manual_configuration


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("settings", "rosterSettings", "lineupSlotCounts", "20"), 8, "lineup slots conflict"),
        (("settings", "acquisitionSettings", "acquisitionType"), "MYSTERY", "unsupported enum"),
        (("settings", "scheduleSettings", "playoffTeamCount"), 7, "playoffTeamCount"),
        (("settings", "scheduleSettings", "playoffMatchupPeriodLengthByRound", "2"), 2, "unsupported playoff round"),
    ],
)
def test_invalid_material_rules_fail_explicitly(path, value, message: str) -> None:
    raw = raw_rules()
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(LeagueRulesAuditError, match=message):
        build_report(raw, [(2025, historical_rules())], league_id=9, season=2026, endpoint="x", expected_team_count=14, expected_playoff_teams=6)


def test_roster_rejects_over_capacity_and_duplicate_team() -> None:
    raw = raw_rules()
    raw["teams"][0]["roster"]["entries"].append({"lineupSlotId": 20})
    with pytest.raises(LeagueRulesAuditError, match="exceed configured capacity"):
        audit_roster(raw, expected_team_count=14)
    raw = raw_rules()
    raw["teams"][1]["id"] = 1
    with pytest.raises(LeagueRulesAuditError, match="duplicate fantasy team ID"):
        audit_roster(raw, expected_team_count=14)


def test_waivers_reject_missing_or_inconsistent_priority() -> None:
    raw = raw_rules()
    del raw["teams"][0]["waiverRank"]
    with pytest.raises(LeagueRulesAuditError, match="waiverRank must be an integer"):
        audit_waivers(raw, expected_team_count=14)
    raw = raw_rules()
    raw["teams"][1]["waiverRank"] = 1
    with pytest.raises(LeagueRulesAuditError, match="unique 1..14 permutation"):
        audit_waivers(raw, expected_team_count=14)


def test_schedule_rejects_invalid_seed_relationships_and_missing_consolation_metadata() -> None:
    raw = raw_rules()
    raw["teams"][1]["playoffSeed"] = 1
    with pytest.raises(LeagueRulesAuditError, match="playoff seeds"):
        audit_schedule(raw, expected_playoff_teams=6)
    raw = raw_rules()
    del raw["settings"]["scheduleSettings"]["consolationLadderDisabled"]
    with pytest.raises(LeagueRulesAuditError, match="consolationLadderDisabled"):
        audit_schedule(raw, expected_playoff_teams=6)


def test_historical_bracket_requires_pairing_evidence() -> None:
    raw = historical_rules()
    raw["schedule"] = []
    with pytest.raises(LeagueRulesAuditError, match="no historical postseason"):
        summarize_historical_bracket(raw, 2025)


def test_contradictory_historical_rule_record_fails() -> None:
    raw = historical_rules()
    raw["schedule"][0]["matchupPeriodId"] = "15"
    with pytest.raises(LeagueRulesAuditError, match="matchupPeriodId must be an integer"):
        summarize_historical_bracket(raw, 2025)
