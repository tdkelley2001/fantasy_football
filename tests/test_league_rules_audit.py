from __future__ import annotations

import pytest

from fantasy_football.league_rules_audit import (
    LeagueRulesAuditError,
    audit_roster,
    audit_schedule,
    audit_waivers,
    build_report,
    summarize_historical_bracket,
)


def raw_rules(
    *,
    team_count: int = 14,
    slots: dict[int, int] | None = None,
    playoff_count: int = 6,
    round_lengths: tuple[int, ...] = (1, 1, 2),
    consolation_disabled: bool | None = False,
    acquisition_type: str = "WAIVERS_TRADITIONAL",
) -> dict:
    positive_slots = slots or {0: 1, 2: 2, 4: 2, 6: 1, 16: 1, 17: 1, 20: 7, 21: 1, 23: 1}
    counts = {str(index): 0 for index in range(24)}
    counts.update({str(key): value for key, value in positive_slots.items()})
    teams = []
    for team_id in range(1, team_count + 1):
        entries = []
        for slot_id, capacity in positive_slots.items():
            for _ in range(capacity):
                entry = {"lineupSlotId": slot_id}
                if slot_id == 21:
                    entry["playerPoolEntry"] = {"player": {"injuryStatus": "INJURY_RESERVE", "eligibleSlots": [20, 21]}}
                entries.append(entry)
        teams.append(
            {
                "id": team_id,
                "waiverRank": team_id,
                "playoffSeed": team_id,
                "record": {"overall": {"wins": 7, "losses": 6, "ties": 0, "pointsFor": 1000 + team_id, "pointsAgainst": 900 + team_id}},
                "transactionCounter": {"trades": 0},
                "roster": {"entries": entries},
            }
        )
    matchup_periods = {str(week): [week] for week in range(1, 15)}
    scoring_week = 15
    for index, duration in enumerate(round_lengths, start=15):
        matchup_periods[str(index)] = list(range(scoring_week, scoring_week + duration))
        scoring_week += duration
    schedule_settings = {
        "playoffTeamCount": playoff_count,
        "playoffMatchupPeriodLengthByRound": {str(index): value for index, value in enumerate(round_lengths, start=1)},
        "matchupPeriods": matchup_periods,
        "matchupPeriodCount": 14,
        "playoffReseed": False,
        "playoffSeedingRule": "TOTAL_POINTS_SCORED",
    }
    if consolation_disabled is not None:
        schedule_settings["consolationLadderDisabled"] = consolation_disabled
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
                "acquisitionType": acquisition_type,
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
            "scheduleSettings": schedule_settings,
            "scoringSettings": {"scoringType": "H2H_POINTS", "matchupTieRule": "NONE", "playoffMatchupTieRule": "NONE"},
        },
        "teams": teams,
        "schedule": [],
    }


def _side(team_id: int, total: float = 100.0, *, final: bool = False) -> dict:
    result = {"teamId": team_id, "totalPoints": total}
    if final:
        result["pointsByScoringPeriod"] = {"17": total - 40, "18": 40.0}
    return result


def _row(row_id: int, period: int, seeds: tuple[int, ...], winner: str = "UNDECIDED") -> dict:
    row = {"id": row_id, "matchupPeriodId": period, "winner": winner, "home": _side(seeds[0], 110.0, final=period == 17)}
    if len(seeds) == 2:
        row["away"] = _side(seeds[1], 100.0, final=period == 17)
    return row


def historical_rules() -> dict:
    raw = raw_rules(team_count=12)
    for team in raw["teams"]:
        team["rankCalculatedFinal"] = team["playoffSeed"]
    raw["schedule"] = [
        _row(101, 15, (1,)), _row(102, 15, (2,)), _row(103, 15, (4, 5), "HOME"), _row(104, 15, (3, 6), "HOME"),
        _row(105, 15, (7, 8), "HOME"), _row(106, 15, (9, 10), "HOME"), _row(107, 15, (11, 12), "HOME"),
        _row(201, 16, (1, 4), "HOME"), _row(202, 16, (2, 3), "HOME"), _row(203, 16, (5, 6), "HOME"),
        _row(204, 16, (7, 9), "HOME"), _row(205, 16, (8, 11), "HOME"), _row(206, 16, (10, 12), "HOME"),
        _row(301, 17, (1, 2), "HOME"), _row(302, 17, (3, 4), "HOME"), _row(303, 17, (5, 6), "HOME"),
        _row(304, 17, (7, 8), "HOME"), _row(305, 17, (9, 10), "HOME"), _row(306, 17, (11, 12), "HOME"),
    ]
    return raw


@pytest.mark.parametrize(
    ("team_count", "slots", "playoff_count", "rounds", "consolation_disabled"),
    [
        (8, {0: 1, 2: 2, 4: 2, 6: 1, 20: 5}, 4, (1, 2), True),
        (10, {0: 2, 2: 2, 4: 3, 6: 1, 20: 4, 23: 2, 24: 1}, 8, (1, 1, 1), False),
        (14, {0: 1, 2: 2, 4: 2, 6: 1, 20: 7, 21: 2, 23: 1}, 6, (1, 1, 2), False),
    ],
)
def test_multiple_valid_structures_are_discovered(team_count, slots, playoff_count, rounds, consolation_disabled) -> None:
    raw = raw_rules(team_count=team_count, slots=slots, playoff_count=playoff_count, round_lengths=rounds, consolation_disabled=consolation_disabled)
    report = build_report(raw, [], league_id=9, season=2026, endpoint="https://example.invalid")
    assert report.team_count == team_count
    assert report.roster["bench_capacity"] == slots.get(20, 0)
    assert report.roster["ir_capacity"] == slots.get(21, 0)
    assert report.championship["qualifier_count"] == playoff_count
    assert report.championship["round_lengths"] == {str(i): value for i, value in enumerate(rounds, 1)}
    assert report.consolation["enabled"] is (not consolation_disabled)


def test_expected_team_count_is_optional_identity_check_only() -> None:
    raw = raw_rules(team_count=10, playoff_count=4, round_lengths=(1, 2))
    assert audit_roster(raw)["total_capacity"] == 17
    with pytest.raises(LeagueRulesAuditError, match="identity check"):
        audit_roster(raw, expected_team_count=14)


def test_unknown_valid_settings_are_reported_without_fallback() -> None:
    raw = raw_rules(acquisition_type="FUTURE_ESPN_MODE")
    raw["settings"]["scoringSettings"]["scoringType"] = "FUTURE_SCORING_MODE"
    raw["settings"]["rosterSettings"]["lineupSlotCounts"]["99"] = 1
    for team in raw["teams"]:
        team["roster"]["entries"].append({"lineupSlotId": 99})
    report = build_report(raw, [], league_id=9, season=2026, endpoint="x")
    assert report.waivers["acquisition_type_raw"] == "FUTURE_ESPN_MODE"
    assert report.waivers["interpretation_status"] == "valid_but_unverified"
    assert report.standings["interpretation_status"] == "valid_but_unsupported"
    assert report.roster["unknown_slot_ids"] == [99]


def test_no_ir_and_missing_consolation_flag_are_valid_but_explicit() -> None:
    raw = raw_rules(team_count=8, slots={0: 1, 2: 2, 4: 2, 20: 5}, playoff_count=4, round_lengths=(1, 2), consolation_disabled=None)
    report = build_report(raw, [], league_id=9, season=2026, endpoint="x")
    assert report.roster["ir_capacity"] == 0
    assert report.consolation["enabled"] is None
    assert report.consolation["interpretation_status"] == "valid_but_unverified"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw: raw["settings"]["rosterSettings"]["lineupSlotCounts"].update({"20": -1}), "at least 0"),
        (lambda raw: raw["teams"].__setitem__(1, {**raw["teams"][1], "id": 1}), "duplicate fantasy team ID"),
        (lambda raw: raw["settings"]["scheduleSettings"].update({"playoffTeamCount": 99}), "exceeds team count"),
        (lambda raw: raw["settings"]["scheduleSettings"].update({"playoffTeamCount": 1}), "cannot form"),
        (lambda raw: raw["settings"]["scheduleSettings"]["matchupPeriods"].update({"15": [14]}), "multiple matchup periods"),
        (lambda raw: raw["settings"]["scheduleSettings"]["playoffMatchupPeriodLengthByRound"].update({"2": 2}), "duration 2 conflicts"),
    ],
)
def test_malformed_or_contradictory_structures_fail(mutate, message: str) -> None:
    raw = raw_rules()
    mutate(raw)
    with pytest.raises(LeagueRulesAuditError, match=message):
        build_report(raw, [], league_id=9, season=2026, endpoint="x")


def test_waiver_priority_is_dynamic_and_must_be_complete_if_present() -> None:
    raw = raw_rules(team_count=8, playoff_count=4, round_lengths=(1, 2))
    assert audit_waivers(raw)["current_priority_is_complete_permutation"] is True
    raw["teams"][1]["waiverRank"] = 1
    with pytest.raises(LeagueRulesAuditError, match="unique 1..8 permutation"):
        audit_waivers(raw)
    raw = raw_rules(team_count=8, playoff_count=4, round_lengths=(1, 2))
    for team in raw["teams"]:
        del team["waiverRank"]
    assert audit_waivers(raw)["current_priority_is_complete_permutation"] is None


def test_historical_fixture_reconstructs_postseason_relationships() -> None:
    evidence = summarize_historical_bracket(historical_rules(), 2025)
    assert evidence["playoff_entrant_seeds"] == [1, 2, 3, 4, 5, 6]
    assert evidence["first_postseason_period_bye_seeds"] == [1, 2]
    assert evidence["first_round_winner_seeds"] == [3, 4]
    assert evidence["bye_winner_pairings_next_period"] == [[1, 4], [2, 3]]
    assert evidence["championship_pairings_by_period"]["17"] == [[1, 2], [3, 4], [5, 6]]
    assert evidence["consolation_pairings_by_period"]["17"] == [[7, 8], [9, 10], [11, 12]]
    assert evidence["championship_placement_pairings_by_final_rank"] == [[1, 2], [3, 4], [5, 6]]
    first_transitions = evidence["winner_loser_transitions_by_period"]["15"]
    assert {
        "source_seed_pair": [4, 5],
        "winner_seed": 4,
        "winner_next_pair": [1, 4],
        "loser_seed": 5,
        "loser_next_pair": [5, 6],
    } in first_transitions
    assert {
        "source_seed_pair": [7, 8],
        "winner_seed": 7,
        "winner_next_pair": [7, 9],
        "loser_seed": 8,
        "loser_next_pair": [8, 11],
    } in first_transitions
    assert evidence["multiweek_aggregate_side_checks"] == 12
    assert evidence["reseed_setting"] is False


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw: raw["schedule"].clear(), "no historical postseason"),
        (lambda raw: raw["schedule"][0].update({"matchupPeriodId": "15"}), "must be an integer"),
        (lambda raw: raw["schedule"][2]["away"].update({"teamId": 99}), "invalid team reference"),
        (lambda raw: raw["schedule"][13]["home"]["pointsByScoringPeriod"].update({"18": 41.0}), "does not equal scoring-period sum"),
        (lambda raw: raw["schedule"][2].update({"winner": "AWAY"}), "winner conflicts with aggregate points"),
        (lambda raw: raw["schedule"][3]["home"].update({"teamId": 4}), "multiple matchups"),
    ],
)
def test_historical_contradictions_fail_explicitly(mutate, message: str) -> None:
    raw = historical_rules()
    mutate(raw)
    with pytest.raises(LeagueRulesAuditError, match=message):
        summarize_historical_bracket(raw, 2025)


def test_schedule_discovers_byes_and_disabled_consolation() -> None:
    raw = raw_rules(team_count=10, playoff_count=6, round_lengths=(1, 1, 2), consolation_disabled=True)
    _, championship, consolation = audit_schedule(raw)
    assert championship["derived_first_round_byes"] == 2
    assert consolation == {
        "enabled": False,
        "participant_count_if_all_nonqualifiers": 4,
        "current_pairings_available": False,
        "interpretation_status": "valid_and_understood",
    }
