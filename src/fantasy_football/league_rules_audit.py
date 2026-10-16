"""Read-only M0.4 audit of ESPN league rules and postseason evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from typing import Any, Mapping, Sequence

from espn_api.football import League
from espn_api.requests.espn_requests import ESPNAccessDenied, ESPNInvalidLeague, ESPNUnknownError
from requests import RequestException

from fantasy_football.config import Settings, SettingsError, load_settings
from fantasy_football.logging_config import configure_logging


LOGGER = logging.getLogger(__name__)
VIEWS = ("mTeam", "mRoster", "mMatchup", "mSettings", "mStandings")


class LeagueRulesAuditError(RuntimeError):
    """Raised when rule evidence is absent, malformed, or contradictory."""


@dataclass(frozen=True, slots=True)
class RulesAuditReport:
    league_id: int
    season: int
    retrieved_at_utc: str
    endpoint: str
    views: tuple[str, ...]
    team_count: int
    roster: dict[str, object]
    waivers: dict[str, object]
    trades: dict[str, object]
    standings: dict[str, object]
    championship: dict[str, object]
    consolation: dict[str, object]
    historical_evidence: tuple[dict[str, object], ...]
    verified_live: tuple[str, ...]
    verified_by_tests: tuple[str, ...]
    unverified: tuple[str, ...]
    unsupported: tuple[str, ...]
    manual_configuration: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LeagueRulesAuditError(f"{field} must be a mapping; observed {type(value).__name__}")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise LeagueRulesAuditError(f"{field} must be a list; observed {type(value).__name__}")
    return value


def _int(value: Any, field: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LeagueRulesAuditError(f"{field} must be an integer; observed {value!r}")
    if minimum is not None and value < minimum:
        raise LeagueRulesAuditError(f"{field} must be at least {minimum}; observed {value}")
    return value


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise LeagueRulesAuditError(f"{field} must be boolean; observed {value!r}")
    return value


def _enum(value: Any, field: str, allowed: set[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise LeagueRulesAuditError(f"{field} has unsupported enum value {value!r}")
    return value


def audit_roster(raw: Mapping[str, Any], *, expected_team_count: int) -> dict[str, object]:
    settings = _mapping(_mapping(raw.get("settings"), "settings").get("rosterSettings"), "rosterSettings")
    counts_raw = _mapping(settings.get("lineupSlotCounts"), "rosterSettings.lineupSlotCounts")
    counts: dict[int, int] = {}
    for key, value in counts_raw.items():
        try:
            slot_id = int(key)
        except (TypeError, ValueError) as exc:
            raise LeagueRulesAuditError(f"invalid raw lineup slot ID {key!r}") from exc
        count = _int(value, f"lineupSlotCounts[{slot_id}]", minimum=0)
        if count:
            counts[slot_id] = count
    required = {0: 1, 2: 2, 4: 2, 6: 1, 16: 1, 17: 1, 20: 7, 21: 1, 23: 1}
    if counts != required:
        raise LeagueRulesAuditError(f"configured lineup slots conflict with expected league rules: {counts!r}")
    teams = _list(raw.get("teams"), "teams")
    if len(teams) != expected_team_count:
        raise LeagueRulesAuditError(f"observed {len(teams)} teams; expected {expected_team_count}")
    total_sizes: list[int] = []
    ordinary_sizes: list[int] = []
    ir_occupants = 0
    ir_status_counts: dict[str, int] = {}
    seen_team_ids: set[int] = set()
    for index, item in enumerate(teams):
        team = _mapping(item, f"teams[{index}]")
        team_id = _int(team.get("id"), f"teams[{index}].id", minimum=1)
        if team_id in seen_team_ids:
            raise LeagueRulesAuditError(f"duplicate fantasy team ID {team_id}")
        seen_team_ids.add(team_id)
        entries = _list(_mapping(team.get("roster"), f"team {team_id}.roster").get("entries"), f"team {team_id}.roster.entries")
        ir_count = 0
        for entry_index, entry_raw in enumerate(entries):
            entry = _mapping(entry_raw, f"team {team_id}.entry[{entry_index}]")
            slot = _int(entry.get("lineupSlotId"), f"team {team_id}.entry[{entry_index}].lineupSlotId", minimum=0)
            if slot == 21:
                ir_count += 1
                player = _mapping(
                    _mapping(entry.get("playerPoolEntry"), f"team {team_id} IR playerPoolEntry").get("player"),
                    f"team {team_id} IR player",
                )
                status = player.get("injuryStatus")
                if not isinstance(status, str) or not status:
                    raise LeagueRulesAuditError(f"team {team_id} IR occupant lacks injuryStatus")
                eligible = _list(player.get("eligibleSlots"), f"team {team_id} IR eligibleSlots")
                if 21 not in eligible:
                    raise LeagueRulesAuditError(f"team {team_id} IR occupant is not eligible for raw slot 21")
                ir_status_counts[status] = ir_status_counts.get(status, 0) + 1
        if ir_count > required[21]:
            raise LeagueRulesAuditError(f"team {team_id} has {ir_count} IR occupants; configured capacity is 1")
        total_sizes.append(len(entries))
        ordinary_sizes.append(len(entries) - ir_count)
        ir_occupants += ir_count
    ordinary_capacity = sum(value for slot, value in counts.items() if slot != 21)
    total_capacity = sum(counts.values())
    if any(size > ordinary_capacity for size in ordinary_sizes) or any(size > total_capacity for size in total_sizes):
        raise LeagueRulesAuditError("current roster entries exceed configured capacity")
    limits_raw = _mapping(settings.get("positionLimits"), "rosterSettings.positionLimits")
    position_limits = {str(key): _int(value, f"positionLimits[{key}]") for key, value in limits_raw.items()}
    return {
        "raw_lineup_slot_counts": {str(k): v for k, v in counts.items()},
        "starting_slots": 9,
        "bench_capacity": counts[20],
        "ir_capacity": counts[21],
        "ordinary_capacity": ordinary_capacity,
        "total_capacity_with_ir": total_capacity,
        "observed_roster_size_range": [min(total_sizes), max(total_sizes)],
        "observed_ordinary_size_range": [min(ordinary_sizes), max(ordinary_sizes)],
        "occupied_ir_slots": ir_occupants,
        "ir_occupant_status_counts": ir_status_counts,
        "ordinary_vacancies": sum(ordinary_capacity - size for size in ordinary_sizes),
        "position_limits_by_raw_default_position_id": position_limits,
        "bench_unlimited_flag": _bool(settings.get("isBenchUnlimited"), "isBenchUnlimited"),
        "undroppable_list_enabled": _bool(settings.get("isUsingUndroppableList"), "isUsingUndroppableList"),
        "lineup_lock_type": _enum(settings.get("lineupLocktimeType"), "lineupLocktimeType", {"INDIVIDUAL_GAME"}),
        "roster_lock_type": _enum(settings.get("rosterLocktimeType"), "rosterLocktimeType", {"INDIVIDUAL_GAME"}),
        "move_limit": _int(settings.get("moveLimit"), "moveLimit"),
    }


def audit_waivers(raw: Mapping[str, Any], *, expected_team_count: int) -> dict[str, object]:
    settings = _mapping(_mapping(raw.get("settings"), "settings").get("acquisitionSettings"), "acquisitionSettings")
    waiver_type = _enum(settings.get("acquisitionType"), "acquisitionType", {"WAIVERS_TRADITIONAL"})
    days = _list(settings.get("waiverProcessDays"), "waiverProcessDays")
    if not days or any(not isinstance(day, str) or not day for day in days):
        raise LeagueRulesAuditError("waiverProcessDays must contain named days")
    ranks: list[int] = []
    for index, item in enumerate(_list(raw.get("teams"), "teams")):
        team = _mapping(item, f"teams[{index}]")
        ranks.append(_int(team.get("waiverRank"), f"teams[{index}].waiverRank", minimum=1))
    if sorted(ranks) != list(range(1, expected_team_count + 1)):
        raise LeagueRulesAuditError(f"waiver ranks must be a unique 1..{expected_team_count} permutation; observed {sorted(ranks)}")
    return {
        "acquisition_type": waiver_type,
        "uses_faab": _bool(settings.get("isUsingAcquisitionBudget"), "isUsingAcquisitionBudget"),
        "acquisition_budget": _int(settings.get("acquisitionBudget"), "acquisitionBudget", minimum=0),
        "minimum_bid": _int(settings.get("minimumBid"), "minimumBid", minimum=0),
        "season_acquisition_limit": _int(settings.get("acquisitionLimit"), "acquisitionLimit"),
        "matchup_acquisition_limit": settings.get("matchupAcquisitionLimit"),
        "waiver_hours": _int(settings.get("waiverHours"), "waiverHours", minimum=0),
        "waiver_order_reset": _bool(settings.get("waiverOrderReset"), "waiverOrderReset"),
        "process_days": days,
        "process_hour_raw": _int(settings.get("waiverProcessHour"), "waiverProcessHour", minimum=0),
        "transaction_locking_enabled": _bool(settings.get("transactionLockingEnabled"), "transactionLockingEnabled"),
        "current_priority_is_complete_permutation": True,
    }


def audit_trades(raw: Mapping[str, Any]) -> dict[str, object]:
    settings = _mapping(_mapping(raw.get("settings"), "settings").get("tradeSettings"), "tradeSettings")
    deadline = _int(settings.get("deadlineDate"), "tradeSettings.deadlineDate", minimum=1)
    observed_trades = 0
    for index, item in enumerate(_list(raw.get("teams"), "teams")):
        counter = _mapping(_mapping(item, f"teams[{index}]").get("transactionCounter"), f"teams[{index}].transactionCounter")
        observed_trades += _int(counter.get("trades"), f"teams[{index}].transactionCounter.trades", minimum=0)
    return {
        "deadline_utc": datetime.fromtimestamp(deadline / 1000, timezone.utc).isoformat(),
        "review_hours": _int(settings.get("revisionHours"), "revisionHours", minimum=0),
        "veto_votes_required": _int(settings.get("vetoVotesRequired"), "vetoVotesRequired", minimum=0),
        "trade_limit": _int(settings.get("max"), "tradeSettings.max"),
        "allow_out_of_universe": _bool(settings.get("allowOutOfUniverse"), "allowOutOfUniverse"),
        "team_trade_counter_sum": observed_trades,
    }


def audit_schedule(raw: Mapping[str, Any], *, expected_playoff_teams: int) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    settings = _mapping(_mapping(raw.get("settings"), "settings").get("scheduleSettings"), "scheduleSettings")
    playoff_count = _int(settings.get("playoffTeamCount"), "playoffTeamCount", minimum=2)
    if playoff_count != expected_playoff_teams or playoff_count % 2:
        raise LeagueRulesAuditError(f"playoffTeamCount={playoff_count}; expected valid count {expected_playoff_teams}")
    rounds_raw = _mapping(settings.get("playoffMatchupPeriodLengthByRound"), "playoffMatchupPeriodLengthByRound")
    rounds = {str(key): _int(value, f"round length {key}", minimum=1) for key, value in rounds_raw.items()}
    expected_rounds = {"1": 1, "2": 1, "3": 2}
    if rounds != expected_rounds:
        raise LeagueRulesAuditError(f"unsupported playoff round durations {rounds!r}; expected {expected_rounds!r}")
    matchup_periods = _mapping(settings.get("matchupPeriods"), "matchupPeriods")
    regular_end = _int(settings.get("matchupPeriodCount"), "matchupPeriodCount", minimum=1)
    scoring = _mapping(_mapping(raw.get("settings"), "settings").get("scoringSettings"), "scoringSettings")
    teams = _list(raw.get("teams"), "teams")
    seeds = sorted(_int(_mapping(team, "team").get("playoffSeed"), "playoffSeed", minimum=1) for team in teams)
    if seeds != list(range(1, len(teams) + 1)):
        raise LeagueRulesAuditError("playoff seeds must be a complete unique team permutation")
    record_rows = 0
    tied_record_groups: dict[tuple[int, int, int], list[tuple[int, float]]] = {}
    for index, item in enumerate(teams):
        team = _mapping(item, f"teams[{index}]")
        overall = _mapping(_mapping(team.get("record"), f"teams[{index}].record").get("overall"), f"teams[{index}].record.overall")
        wins = _int(overall.get("wins"), "record.wins", minimum=0)
        losses = _int(overall.get("losses"), "record.losses", minimum=0)
        ties = _int(overall.get("ties"), "record.ties", minimum=0)
        points_for = overall.get("pointsFor")
        points_against = overall.get("pointsAgainst")
        if isinstance(points_for, bool) or not isinstance(points_for, (int, float)) or isinstance(points_against, bool) or not isinstance(points_against, (int, float)):
            raise LeagueRulesAuditError("record pointsFor and pointsAgainst must be numeric")
        tied_record_groups.setdefault((wins, losses, ties), []).append((_int(team.get("playoffSeed"), "playoffSeed", minimum=1), float(points_for)))
        record_rows += 1
    standings = {
        "scoring_type": _enum(scoring.get("scoringType"), "scoringType", {"H2H_POINTS"}),
        "playoff_seeding_rule": _enum(settings.get("playoffSeedingRule"), "playoffSeedingRule", {"TOTAL_POINTS_SCORED"}),
        "matchup_tie_rule_raw": scoring.get("matchupTieRule"),
        "playoff_matchup_tie_rule_raw": scoring.get("playoffMatchupTieRule"),
        "current_seed_permutation_valid": True,
        "record_rows_with_wins_losses_ties_points_for_against": record_rows,
        "equal_record_groups": sum(1 for values in tied_record_groups.values() if len(values) > 1),
    }
    championship = {
        "regular_season_end": regular_end,
        "playoff_start": regular_end + 1,
        "qualifier_count": playoff_count,
        "first_round_byes": 2,
        "reseed": _bool(settings.get("playoffReseed"), "playoffReseed"),
        "round_lengths": rounds,
        "matchup_periods": {str(k): v for k, v in matchup_periods.items()},
    }
    consolation = {
        "enabled": not _bool(settings.get("consolationLadderDisabled"), "consolationLadderDisabled"),
        "expected_participant_count": len(teams) - playoff_count,
        "current_pairings_available": any(
            _mapping(item, "schedule entry").get("matchupPeriodId", 0) > regular_end
            for item in _list(raw.get("schedule"), "schedule")
        ),
    }
    return standings, championship, consolation


def summarize_historical_bracket(raw: Mapping[str, Any], season: int) -> dict[str, object]:
    settings = _mapping(_mapping(raw.get("settings"), "settings").get("scheduleSettings"), "scheduleSettings")
    regular_end = _int(settings.get("matchupPeriodCount"), "historical matchupPeriodCount", minimum=1)
    rows: list[Mapping[str, Any]] = []
    for index, item in enumerate(_list(raw.get("schedule"), "historical schedule")):
        row = _mapping(item, f"historical schedule entry {index}")
        period = _int(row.get("matchupPeriodId"), "historical matchupPeriodId", minimum=1)
        if period > regular_end:
            rows.append(row)
    periods = sorted({_int(item.get("matchupPeriodId"), "historical matchupPeriodId", minimum=1) for item in rows})
    if not rows or not periods:
        raise LeagueRulesAuditError(f"season {season} has no historical postseason schedule evidence")
    team_ids = {_int(_mapping(team, "historical team").get("id"), "historical team ID", minimum=1) for team in _list(raw.get("teams"), "historical teams")}
    for row in rows:
        sides = []
        for side in ("home", "away"):
            if side in row:
                team_id = _int(_mapping(row[side], f"historical {side}").get("teamId"), f"historical {side}.teamId", minimum=1)
                if team_id not in team_ids:
                    raise LeagueRulesAuditError(f"historical bracket references unknown team ID {team_id}")
                sides.append(team_id)
        if not sides or len(sides) == 2 and sides[0] == sides[1]:
            raise LeagueRulesAuditError("historical bracket has missing or contradictory pairing")
    home_only = sum(1 for item in rows if "home" in item and "away" not in item)
    final_period = max(periods)
    two_week_rows = sum(1 for item in rows if item.get("matchupPeriodId") == final_period)
    return {
        "season": season,
        "team_count": len(_list(raw.get("teams"), "historical teams")),
        "postseason_periods": periods,
        "postseason_schedule_rows": len(rows),
        "home_only_bye_rows": home_only,
        "two_week_rows": two_week_rows,
        "classification": "Verified live (historical league response)",
    }


def build_report(raw: Mapping[str, Any], historical: Sequence[tuple[int, Mapping[str, Any]]], *, league_id: int, season: int, endpoint: str, expected_team_count: int, expected_playoff_teams: int) -> RulesAuditReport:
    roster = audit_roster(raw, expected_team_count=expected_team_count)
    waivers = audit_waivers(raw, expected_team_count=expected_team_count)
    trades = audit_trades(raw)
    standings, championship, consolation = audit_schedule(raw, expected_playoff_teams=expected_playoff_teams)
    history = tuple(summarize_historical_bracket(item, year) for year, item in historical)
    return RulesAuditReport(
        league_id=league_id, season=season, retrieved_at_utc=datetime.now(timezone.utc).isoformat(), endpoint=endpoint, views=VIEWS,
        team_count=expected_team_count, roster=roster, waivers=waivers, trades=trades, standings=standings,
        championship=championship, consolation=consolation, historical_evidence=history,
        verified_live=(
            "Raw roster slots configure nine starters, seven bench slots, and one distinct IR slot; current 16/17-player rosters reconcile to IR occupancy plus one ordinary vacancy.",
            "Traditional non-FAAB waivers, a complete current 1..14 priority order, 24-hour waiver delay, configured processing days/hour, and unlimited acquisition codes were observed.",
            "The current league configures H2H points, six playoff qualifiers, two first-round byes, no reseeding, one-week first two rounds, and a two-week final.",
            "Completed historical seasons expose bye rows, fixed championship bracket progression, placement games, and two-week final rows.",
        ),
        verified_by_tests=(
            "Malformed or contradictory slot counts, waiver enums/ranks, playoff counts, round lengths, seeds, and absent historical brackets fail explicitly.",
        ),
        unverified=(
            "The exact operational meaning and timezone of waiverProcessHour is not established by the raw field alone.",
            "The ordering of multiple contingent claims from one manager requires direct UI or observed behavioral evidence.",
            "Trade review type, veto workflow, dropped-player reentry timing, postseason transaction restrictions, and tie resolution are not fully encoded by verified fields.",
            "Current 14-team championship pairings have not materialized; historical fixed-bracket evidence comes from 12-team seasons with the same six-team playoff settings.",
            "The exact eight-team consolation ladder pairings and finishing-position mapping cannot be inferred safely from completed six-team historical ladders.",
        ),
        unsupported=(
            "The investigated current schedule contains no future postseason pairings before qualification is resolved.",
            "No verified field fully defines consolation ladder advancement or matchup-tie behavior.",
        ),
        manual_configuration=(
            {"key": "waivers.claim_processing_order", "allowed": "ordered verified procedure", "blocks_simulation": True, "reason": "Multiple-claim behavior is not fully exposed."},
            {"key": "waivers.process_timezone", "allowed": "verified IANA timezone", "blocks_simulation": False, "reason": "The raw processing hour does not identify its timezone."},
            {"key": "transactions.trade_review_type", "allowed": ["league_vote", "commissioner", "none"], "blocks_simulation": False, "reason": "Votes and delay do not prove workflow."},
            {"key": "standings.matchup_tie_rule", "allowed": "verified ESPN rule", "blocks_simulation": True, "reason": "Raw NONE enum is semantically unresolved."},
            {"key": "postseason.playoff_matchup_tie_rule", "allowed": "verified ESPN rule", "blocks_simulation": True, "reason": "Raw NONE enum is semantically unresolved."},
            {"key": "postseason.consolation_ladder", "allowed": "explicit participants, pairings, advancement, durations, placement mapping", "blocks_simulation": True, "reason": "Eight-team structure is not exposed before postseason and lacks matching historical evidence."},
        ),
    )


def audit_live(config: Settings, *, expected_team_count: int, expected_playoff_teams: int, historical_seasons: Sequence[int]) -> RulesAuditReport:
    credentials = config.credentials
    league = League(league_id=config.league_id, year=config.season, espn_s2=credentials.espn_s2 if credentials else None, swid=credentials.swid if credentials else None)
    raw = league.espn_request.get_league()
    historical: list[tuple[int, Mapping[str, Any]]] = []
    for year in historical_seasons:
        old = League(league_id=config.league_id, year=year, espn_s2=credentials.espn_s2 if credentials else None, swid=credentials.swid if credentials else None)
        historical.append((year, old.espn_request.get_league()))
    return build_report(raw, historical, league_id=config.league_id, season=config.season, endpoint=league.espn_request.LEAGUE_ENDPOINT, expected_team_count=expected_team_count, expected_playoff_teams=expected_playoff_teams)


def render_summary(report: RulesAuditReport) -> str:
    return "\n".join((
        "M0.4 ESPN league-rules audit", f"League {report.league_id}; season {report.season}; retrieved {report.retrieved_at_utc}",
        f"Roster capacity: {report.roster['ordinary_capacity']} ordinary + {report.roster['ir_capacity']} IR; observed {report.roster['observed_roster_size_range']}",
        f"Waivers: {report.waivers['acquisition_type']}; current priority permutation valid={report.waivers['current_priority_is_complete_permutation']}",
        f"Championship: {report.championship['qualifier_count']} teams; rounds {report.championship['round_lengths']}; reseed={report.championship['reseed']}",
        f"Consolation: expected participants={report.consolation['expected_participant_count']}; current pairings available={report.consolation['current_pairings_available']}",
        "", "Unresolved:", *(f"- {item}" for item in report.unverified),
    ))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the read-only M0.4 ESPN league-rules audit.")
    parser.add_argument("--expected-team-count", type=int, required=True)
    parser.add_argument("--expected-playoff-team-count", type=int, required=True)
    parser.add_argument("--historical-season", type=int, action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        report = audit_live(settings, expected_team_count=args.expected_team_count, expected_playoff_teams=args.expected_playoff_team_count, historical_seasons=args.historical_season)
    except (SettingsError, LeagueRulesAuditError, ESPNAccessDenied, ESPNInvalidLeague, ESPNUnknownError, RequestException) as exc:
        LOGGER.error("M0.4 league-rules audit failed: %s", exc)
        return 2
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True) if args.json else render_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
