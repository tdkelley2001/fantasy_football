"""Read-only M0.4 discovery of ESPN league rules and postseason evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import math
from numbers import Real
from typing import Any, Mapping, Sequence

from espn_api.football import League
from espn_api.football.constant import POSITION_MAP
from espn_api.requests.espn_requests import ESPNAccessDenied, ESPNInvalidLeague, ESPNUnknownError
from requests import RequestException

from fantasy_football.config import Settings, SettingsError, load_settings
from fantasy_football.logging_config import configure_logging

LOGGER = logging.getLogger(__name__)
VIEWS = ("mTeam", "mRoster", "mMatchup", "mSettings", "mStandings")
UNDERSTOOD_ACQUISITION_TYPES = {"WAIVERS_TRADITIONAL", "WAIVERS_CONTINUOUS", "WAIVERS_FREE_AGENT_BUDGET", "FREE_AGENTS_ONLY"}
UNDERSTOOD_SEEDING_RULES = {"TOTAL_POINTS_SCORED", "HEAD_TO_HEAD_RECORD"}


class LeagueRulesAuditError(RuntimeError):
    """Raised only when source data is malformed or internally contradictory."""


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
    capabilities: tuple[dict[str, str], ...]
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


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
        raise LeagueRulesAuditError(f"{field} must be a finite number; observed {value!r}")
    return float(value)


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise LeagueRulesAuditError(f"{field} must be boolean; observed {value!r}")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LeagueRulesAuditError(f"{field} must be non-empty text; observed {value!r}")
    return value.strip()


def _raw_settings(raw: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    return _mapping(_mapping(raw.get("settings"), "settings").get(name), f"settings.{name}")


def _teams(raw: Mapping[str, Any], expected_team_count: int | None = None) -> tuple[list[Mapping[str, Any]], set[int]]:
    result: list[Mapping[str, Any]] = []
    ids: set[int] = set()
    for index, value in enumerate(_list(raw.get("teams"), "teams")):
        team = _mapping(value, f"teams[{index}]")
        team_id = _int(team.get("id"), f"teams[{index}].id", minimum=1)
        if team_id in ids:
            raise LeagueRulesAuditError(f"duplicate fantasy team ID {team_id}")
        ids.add(team_id)
        result.append(team)
    if not result:
        raise LeagueRulesAuditError("teams must not be empty")
    if expected_team_count is not None and len(result) != expected_team_count:
        raise LeagueRulesAuditError(f"identity check observed {len(result)} teams; explicitly expected {expected_team_count}")
    return result, ids


def _slot_counts(settings: Mapping[str, Any]) -> dict[int, int]:
    result: dict[int, int] = {}
    for key, value in _mapping(settings.get("lineupSlotCounts"), "rosterSettings.lineupSlotCounts").items():
        try:
            slot_id = int(key)
        except (TypeError, ValueError) as exc:
            raise LeagueRulesAuditError(f"invalid raw lineup slot ID {key!r}") from exc
        if slot_id < 0 or str(slot_id) != str(key):
            raise LeagueRulesAuditError(f"invalid raw lineup slot ID {key!r}")
        count = _int(value, f"lineupSlotCounts[{slot_id}]", minimum=0)
        if count:
            result[slot_id] = count
    if not result:
        raise LeagueRulesAuditError("lineupSlotCounts contains no positive capacity")
    return result


def audit_roster(raw: Mapping[str, Any], *, expected_team_count: int | None = None) -> dict[str, object]:
    settings = _raw_settings(raw, "rosterSettings")
    counts = _slot_counts(settings)
    teams, _ = _teams(raw, expected_team_count)
    bench_capacity = counts.get(20, 0)
    ir_capacity = counts.get(21, 0)
    starter_capacity = sum(count for slot, count in counts.items() if slot not in {20, 21})
    ordinary_capacity = starter_capacity + bench_capacity
    total_capacity = sum(counts.values())
    total_sizes: list[int] = []
    ordinary_sizes: list[int] = []
    ir_occupants = 0
    ir_status_counts: dict[str, int] = {}
    for team in teams:
        team_id = _int(team.get("id"), "team.id", minimum=1)
        entries = _list(_mapping(team.get("roster"), f"team {team_id}.roster").get("entries"), f"team {team_id}.roster.entries")
        occupied: dict[int, int] = {}
        for index, value in enumerate(entries):
            entry = _mapping(value, f"team {team_id}.entry[{index}]")
            slot = _int(entry.get("lineupSlotId"), f"team {team_id}.entry[{index}].lineupSlotId", minimum=0)
            if slot not in counts:
                raise LeagueRulesAuditError(f"team {team_id} uses slot {slot} with no configured positive capacity")
            occupied[slot] = occupied.get(slot, 0) + 1
            if occupied[slot] > counts[slot]:
                raise LeagueRulesAuditError(f"team {team_id} has {occupied[slot]} occupants in slot {slot}; configured capacity is {counts[slot]}")
            if slot == 21:
                player = _mapping(_mapping(entry.get("playerPoolEntry"), f"team {team_id} IR playerPoolEntry").get("player"), f"team {team_id} IR player")
                status = _text(player.get("injuryStatus"), f"team {team_id} IR injuryStatus")
                if 21 not in _list(player.get("eligibleSlots"), f"team {team_id} IR eligibleSlots"):
                    raise LeagueRulesAuditError(f"team {team_id} IR occupant is not eligible for raw slot 21")
                ir_occupants += 1
                ir_status_counts[status] = ir_status_counts.get(status, 0) + 1
        ordinary = len(entries) - occupied.get(21, 0)
        if ordinary > ordinary_capacity or len(entries) > total_capacity:
            raise LeagueRulesAuditError(f"team {team_id} roster exceeds configured capacity")
        total_sizes.append(len(entries))
        ordinary_sizes.append(ordinary)
    limits_raw = _mapping(settings.get("positionLimits", {}), "rosterSettings.positionLimits")
    return {
        "raw_lineup_slot_counts": {str(key): value for key, value in sorted(counts.items())},
        "slot_labels": {str(key): POSITION_MAP.get(key) for key in sorted(counts)},
        "unknown_slot_ids": [key for key in sorted(counts) if key not in POSITION_MAP],
        "starter_capacity": starter_capacity,
        "bench_capacity": bench_capacity,
        "ir_capacity": ir_capacity,
        "ordinary_capacity": ordinary_capacity,
        "total_capacity": total_capacity,
        "observed_roster_size_range": [min(total_sizes), max(total_sizes)],
        "observed_ordinary_size_range": [min(ordinary_sizes), max(ordinary_sizes)],
        "occupied_ir_slots": ir_occupants,
        "ir_occupant_status_counts": ir_status_counts,
        "ordinary_vacancies": sum(ordinary_capacity - size for size in ordinary_sizes),
        "position_limits_by_raw_default_position_id": {str(key): _int(value, f"positionLimits[{key}]") for key, value in limits_raw.items()},
        "bench_unlimited_flag": _bool(settings.get("isBenchUnlimited"), "isBenchUnlimited"),
        "undroppable_list_enabled": _bool(settings.get("isUsingUndroppableList"), "isUsingUndroppableList"),
        "lineup_lock_type_raw": _text(settings.get("lineupLocktimeType"), "lineupLocktimeType"),
        "roster_lock_type_raw": _text(settings.get("rosterLocktimeType"), "rosterLocktimeType"),
        "move_limit": _int(settings.get("moveLimit"), "moveLimit"),
    }


def audit_waivers(raw: Mapping[str, Any], *, expected_team_count: int | None = None) -> dict[str, object]:
    settings = _raw_settings(raw, "acquisitionSettings")
    teams, _ = _teams(raw, expected_team_count)
    acquisition_type = _text(settings.get("acquisitionType"), "acquisitionType")
    ranks_present = ["waiverRank" in team for team in teams]
    if any(ranks_present) and not all(ranks_present):
        raise LeagueRulesAuditError("waiverRank is present for only some teams")
    priority_valid: bool | None = None
    if all(ranks_present):
        ranks = [_int(team.get("waiverRank"), "team.waiverRank", minimum=1) for team in teams]
        if sorted(ranks) != list(range(1, len(teams) + 1)):
            raise LeagueRulesAuditError(f"waiver ranks must be a unique 1..{len(teams)} permutation; observed {sorted(ranks)}")
        priority_valid = True
    days = _list(settings.get("waiverProcessDays", []), "waiverProcessDays")
    if any(not isinstance(day, str) or not day.strip() for day in days):
        raise LeagueRulesAuditError("waiverProcessDays must contain non-empty named days")
    return {
        "acquisition_type_raw": acquisition_type,
        "interpretation_status": "valid_and_understood" if acquisition_type in UNDERSTOOD_ACQUISITION_TYPES else "valid_but_unverified",
        "uses_faab": _bool(settings.get("isUsingAcquisitionBudget"), "isUsingAcquisitionBudget"),
        "acquisition_budget": _int(settings.get("acquisitionBudget"), "acquisitionBudget", minimum=0),
        "minimum_bid": _int(settings.get("minimumBid"), "minimumBid", minimum=0),
        "season_acquisition_limit": _int(settings.get("acquisitionLimit"), "acquisitionLimit"),
        "matchup_acquisition_limit": _number(settings.get("matchupAcquisitionLimit"), "matchupAcquisitionLimit"),
        "waiver_hours": _int(settings.get("waiverHours"), "waiverHours", minimum=0),
        "waiver_order_reset": _bool(settings.get("waiverOrderReset"), "waiverOrderReset"),
        "process_days": days,
        "process_hour_raw": _int(settings.get("waiverProcessHour"), "waiverProcessHour", minimum=0),
        "transaction_locking_enabled": _bool(settings.get("transactionLockingEnabled"), "transactionLockingEnabled"),
        "current_priority_is_complete_permutation": priority_valid,
    }


def audit_trades(raw: Mapping[str, Any]) -> dict[str, object]:
    settings = _raw_settings(raw, "tradeSettings")
    teams, _ = _teams(raw)
    deadline = _int(settings.get("deadlineDate"), "tradeSettings.deadlineDate", minimum=1)
    observed_trades = 0
    for index, team in enumerate(teams):
        counter = _mapping(team.get("transactionCounter"), f"teams[{index}].transactionCounter")
        observed_trades += _int(counter.get("trades"), f"teams[{index}].transactionCounter.trades", minimum=0)
    return {
        "deadline_utc": datetime.fromtimestamp(deadline / 1000, timezone.utc).isoformat(),
        "review_hours": _int(settings.get("revisionHours"), "revisionHours", minimum=0),
        "veto_votes_required": _int(settings.get("vetoVotesRequired"), "vetoVotesRequired", minimum=0),
        "trade_limit": _int(settings.get("max"), "tradeSettings.max"),
        "allow_out_of_universe": _bool(settings.get("allowOutOfUniverse"), "allowOutOfUniverse"),
        "team_trade_counter_sum": observed_trades,
    }


def _matchup_periods(settings: Mapping[str, Any]) -> dict[int, tuple[int, ...]]:
    result: dict[int, tuple[int, ...]] = {}
    used_weeks: set[int] = set()
    for raw_key, raw_value in _mapping(settings.get("matchupPeriods"), "matchupPeriods").items():
        try:
            period = int(raw_key)
        except (TypeError, ValueError) as exc:
            raise LeagueRulesAuditError(f"invalid matchup-period ID {raw_key!r}") from exc
        if period <= 0 or str(period) != str(raw_key) or period in result:
            raise LeagueRulesAuditError(f"invalid or duplicate matchup-period ID {raw_key!r}")
        weeks = tuple(_int(week, f"matchupPeriods[{period}] week", minimum=1) for week in _list(raw_value, f"matchupPeriods[{period}]"))
        if not weeks or len(set(weeks)) != len(weeks):
            raise LeagueRulesAuditError(f"matchup period {period} has empty or duplicate scoring weeks")
        overlap = used_weeks.intersection(weeks)
        if overlap:
            raise LeagueRulesAuditError(f"scoring weeks occur in multiple matchup periods: {sorted(overlap)}")
        used_weeks.update(weeks)
        result[period] = weeks
    return dict(sorted(result.items()))


def audit_schedule(raw: Mapping[str, Any]) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    settings = _raw_settings(raw, "scheduleSettings")
    teams, _ = _teams(raw)
    team_count = len(teams)
    playoff_count = _int(settings.get("playoffTeamCount"), "playoffTeamCount", minimum=0)
    if playoff_count > team_count:
        raise LeagueRulesAuditError(f"playoffTeamCount={playoff_count} exceeds team count {team_count}")
    if playoff_count == 1:
        raise LeagueRulesAuditError("playoffTeamCount=1 cannot form a championship matchup")
    rounds: dict[int, int] = {}
    for key, value in _mapping(settings.get("playoffMatchupPeriodLengthByRound", {}), "playoffMatchupPeriodLengthByRound").items():
        try:
            round_id = int(key)
        except (TypeError, ValueError) as exc:
            raise LeagueRulesAuditError(f"invalid playoff round ID {key!r}") from exc
        rounds[round_id] = _int(value, f"round length {key}", minimum=1)
    if rounds and sorted(rounds) != list(range(1, len(rounds) + 1)):
        raise LeagueRulesAuditError("playoff round IDs must be contiguous starting at 1")
    expected_round_count = (playoff_count - 1).bit_length() if playoff_count else 0
    if len(rounds) != expected_round_count:
        raise LeagueRulesAuditError(
            f"playoffTeamCount={playoff_count} requires {expected_round_count} elimination rounds; observed {len(rounds)}"
        )
    periods = _matchup_periods(settings)
    regular_end = _int(settings.get("matchupPeriodCount"), "matchupPeriodCount", minimum=1)
    postseason_periods = {period: weeks for period, weeks in periods.items() if period > regular_end}
    if playoff_count and len(rounds) != len(postseason_periods):
        raise LeagueRulesAuditError(f"{len(rounds)} playoff rounds conflict with {len(postseason_periods)} postseason matchup periods")
    for (round_id, duration), (_, weeks) in zip(sorted(rounds.items()), sorted(postseason_periods.items())):
        if duration != len(weeks):
            raise LeagueRulesAuditError(f"playoff round {round_id} duration {duration} conflicts with {len(weeks)} scoring periods")
    scoring = _raw_settings(raw, "scoringSettings")
    scoring_type = _text(scoring.get("scoringType"), "scoringType")
    seeding_rule = _text(settings.get("playoffSeedingRule"), "playoffSeedingRule")
    seeds = sorted(_int(team.get("playoffSeed"), "playoffSeed", minimum=1) for team in teams)
    if seeds != list(range(1, team_count + 1)):
        raise LeagueRulesAuditError("playoff seeds must be a complete unique team permutation")
    tied_records: dict[tuple[int, int, int], int] = {}
    for team in teams:
        overall = _mapping(_mapping(team.get("record"), "team.record").get("overall"), "team.record.overall")
        key = (_int(overall.get("wins"), "record.wins", minimum=0), _int(overall.get("losses"), "record.losses", minimum=0), _int(overall.get("ties"), "record.ties", minimum=0))
        _number(overall.get("pointsFor"), "record.pointsFor")
        _number(overall.get("pointsAgainst"), "record.pointsAgainst")
        tied_records[key] = tied_records.get(key, 0) + 1
    next_power = 1 << (playoff_count - 1).bit_length() if playoff_count else 0
    consolation_flag = settings.get("consolationLadderDisabled")
    consolation_enabled = None if consolation_flag is None else not _bool(consolation_flag, "consolationLadderDisabled")
    current_pairings = any(_int(_mapping(value, f"schedule[{index}]").get("matchupPeriodId"), f"schedule[{index}].matchupPeriodId", minimum=1) > regular_end for index, value in enumerate(_list(raw.get("schedule"), "schedule")))
    standings = {
        "scoring_type_raw": scoring_type,
        "interpretation_status": "valid_and_understood" if scoring_type == "H2H_POINTS" and seeding_rule in UNDERSTOOD_SEEDING_RULES else "valid_but_unsupported",
        "playoff_seeding_rule_raw": seeding_rule,
        "matchup_tie_rule_raw": scoring.get("matchupTieRule"),
        "playoff_matchup_tie_rule_raw": scoring.get("playoffMatchupTieRule"),
        "current_seed_permutation_valid": True,
        "record_rows_with_wins_losses_ties_points_for_against": team_count,
        "equal_record_groups": sum(1 for count in tied_records.values() if count > 1),
    }
    championship = {
        "regular_season_end": regular_end,
        "playoff_start": min(postseason_periods) if postseason_periods else None,
        "qualifier_count": playoff_count,
        "derived_first_round_byes": next_power - playoff_count if playoff_count else 0,
        "reseed": _bool(settings.get("playoffReseed"), "playoffReseed"),
        "round_lengths": {str(key): value for key, value in sorted(rounds.items())},
        "matchup_periods": {str(key): list(value) for key, value in periods.items()},
        "interpretation_status": "valid_and_understood" if playoff_count == 0 or bool(rounds) else "valid_but_unverified",
    }
    consolation = {
        "enabled": consolation_enabled,
        "participant_count_if_all_nonqualifiers": team_count - playoff_count,
        "current_pairings_available": current_pairings,
        "interpretation_status": "valid_but_unverified" if consolation_enabled is None or consolation_enabled else "valid_and_understood",
    }
    return standings, championship, consolation


def _winner(row: Mapping[str, Any], field: str) -> int | None:
    marker = _text(row.get("winner"), f"{field}.winner")
    if marker == "UNDECIDED":
        return None
    if marker not in {"HOME", "AWAY"}:
        raise LeagueRulesAuditError(f"{field}.winner has unsupported structural value {marker!r}")
    return _int(_mapping(row.get(marker.lower()), f"{field}.{marker.lower()}").get("teamId"), f"{field} winner teamId", minimum=1)


def summarize_historical_bracket(raw: Mapping[str, Any], season: int) -> dict[str, object]:
    settings = _raw_settings(raw, "scheduleSettings")
    regular_end = _int(settings.get("matchupPeriodCount"), "historical matchupPeriodCount", minimum=1)
    playoff_count = _int(settings.get("playoffTeamCount"), "historical playoffTeamCount", minimum=0)
    periods = _matchup_periods(settings)
    teams, team_ids = _teams(raw)
    seed_by_team = {team["id"]: _int(team.get("playoffSeed"), "historical playoffSeed", minimum=1) for team in teams}
    if sorted(seed_by_team.values()) != list(range(1, len(teams) + 1)):
        raise LeagueRulesAuditError("historical playoff seeds are not a complete permutation")
    final_rank_by_team = {team["id"]: _int(team.get("rankCalculatedFinal"), "historical rankCalculatedFinal", minimum=1) for team in teams}
    if sorted(final_rank_by_team.values()) != list(range(1, len(teams) + 1)):
        raise LeagueRulesAuditError("historical final ranks are not a complete permutation")
    rows_by_period: dict[int, list[dict[str, object]]] = {}
    seen_row_ids: set[int] = set()
    aggregate_checks = 0
    for index, value in enumerate(_list(raw.get("schedule"), "historical schedule")):
        row = _mapping(value, f"historical schedule[{index}]")
        period = _int(row.get("matchupPeriodId"), f"historical schedule[{index}].matchupPeriodId", minimum=1)
        if period <= regular_end:
            continue
        row_id = _int(row.get("id"), f"historical schedule[{index}].id", minimum=1)
        if row_id in seen_row_ids:
            raise LeagueRulesAuditError(f"historical schedule duplicates row ID {row_id}")
        seen_row_ids.add(row_id)
        side_ids: list[int] = []
        totals_by_team: dict[int, float] = {}
        for side_name in ("home", "away"):
            if side_name not in row:
                continue
            side = _mapping(row[side_name], f"historical row {row_id}.{side_name}")
            team_id = _int(side.get("teamId"), f"historical row {row_id}.{side_name}.teamId", minimum=1)
            if team_id not in team_ids or team_id in side_ids:
                raise LeagueRulesAuditError(f"historical row {row_id} has invalid team reference {team_id}")
            side_ids.append(team_id)
            if "totalPoints" in side:
                totals_by_team[team_id] = _number(side.get("totalPoints"), f"historical row {row_id}.{side_name}.totalPoints")
            scoring_weeks = periods.get(period)
            if scoring_weeks and len(scoring_weeks) > 1:
                points = _mapping(side.get("pointsByScoringPeriod"), f"historical row {row_id}.{side_name}.pointsByScoringPeriod")
                values = [_number(points.get(str(week)), f"historical row {row_id}.{side_name}.week {week}") for week in scoring_weeks]
                total = _number(side.get("totalPoints"), f"historical row {row_id}.{side_name}.totalPoints")
                if not math.isclose(sum(values), total, abs_tol=1e-6):
                    raise LeagueRulesAuditError(f"historical row {row_id}.{side_name} totalPoints does not equal scoring-period sum")
                aggregate_checks += 1
        if not side_ids:
            raise LeagueRulesAuditError(f"historical row {row_id} has no participants")
        winner = _winner(row, f"historical row {row_id}")
        if winner is not None and winner not in side_ids:
            raise LeagueRulesAuditError(f"historical row {row_id} winner is not a participant")
        if winner is not None and len(totals_by_team) == 2 and totals_by_team[winner] < max(totals_by_team.values()):
            raise LeagueRulesAuditError(f"historical row {row_id} winner conflicts with aggregate points")
        rows_by_period.setdefault(period, []).append({"row_id": row_id, "team_ids": tuple(side_ids), "seed_pair": tuple(seed_by_team[team_id] for team_id in side_ids), "winner_team_id": winner})
    if not rows_by_period:
        raise LeagueRulesAuditError(f"season {season} has no historical postseason schedule evidence")
    for period, rows in rows_by_period.items():
        appearances = [team_id for row in rows for team_id in row["team_ids"]]
        if len(appearances) != len(set(appearances)):
            raise LeagueRulesAuditError(f"historical period {period} places a team in multiple matchups")
    championship_ids = {team_id for team_id, seed in seed_by_team.items() if seed <= playoff_count}
    consolation_ids = team_ids - championship_ids
    championship_pairings: dict[str, list[list[int]]] = {}
    consolation_pairings: dict[str, list[list[int]]] = {}
    bye_seeds: list[int] = []
    for period, rows in sorted(rows_by_period.items()):
        champ: list[list[int]] = []
        cons: list[list[int]] = []
        for row in rows:
            ids = set(row["team_ids"])
            pair = list(row["seed_pair"])
            if ids <= championship_ids:
                champ.append(pair)
                if period == min(rows_by_period) and len(pair) == 1:
                    bye_seeds.append(pair[0])
            elif ids <= consolation_ids:
                cons.append(pair)
            else:
                raise LeagueRulesAuditError(f"historical period {period} mixes championship and consolation teams")
        championship_pairings[str(period)] = sorted(champ)
        consolation_pairings[str(period)] = sorted(cons)
    first_period = min(rows_by_period)
    first_championship = [row for row in rows_by_period[first_period] if set(row["team_ids"]) <= championship_ids]
    first_winner_seeds = sorted(seed_by_team[row["winner_team_id"]] for row in first_championship if row["winner_team_id"] is not None and len(row["team_ids"]) == 2)
    next_period = sorted(rows_by_period)[1] if len(rows_by_period) > 1 else None
    bye_winner_pairings: list[list[int]] = []
    if next_period is not None and bye_seeds:
        for row in rows_by_period[next_period]:
            pair = set(row["seed_pair"])
            if pair.intersection(bye_seeds) and pair.intersection(first_winner_seeds):
                bye_winner_pairings.append(sorted(pair))
        if set(seed for pair in bye_winner_pairings for seed in pair).intersection(first_winner_seeds) != set(first_winner_seeds):
            raise LeagueRulesAuditError("historical first-round winner does not advance to a bye recipient")
    final_period = max(rows_by_period)
    placement_pairs: list[list[int]] = []
    for row in rows_by_period[final_period]:
        if set(row["team_ids"]) <= championship_ids:
            placement_pairs.append(sorted(final_rank_by_team[team_id] for team_id in row["team_ids"]))
    transition_evidence: dict[str, list[dict[str, object]]] = {}
    ordered_periods = sorted(rows_by_period)
    for period, following in zip(ordered_periods, ordered_periods[1:]):
        next_pairs = [list(row["seed_pair"]) for row in rows_by_period[following]]
        transitions: list[dict[str, object]] = []
        for row in rows_by_period[period]:
            if len(row["team_ids"]) != 2 or row["winner_team_id"] is None:
                continue
            winner_seed = seed_by_team[row["winner_team_id"]]
            loser_seed = next(seed_by_team[team_id] for team_id in row["team_ids"] if team_id != row["winner_team_id"])
            winner_next = [pair for pair in next_pairs if winner_seed in pair]
            loser_next = [pair for pair in next_pairs if loser_seed in pair]
            if len(winner_next) != 1 or len(loser_next) != 1:
                raise LeagueRulesAuditError(f"historical period {period} has incoherent advancement relationships")
            transitions.append({
                "source_seed_pair": list(row["seed_pair"]),
                "winner_seed": winner_seed,
                "winner_next_pair": winner_next[0],
                "loser_seed": loser_seed,
                "loser_next_pair": loser_next[0],
            })
        transition_evidence[str(period)] = transitions
    return {
        "season": season,
        "team_count": len(teams),
        "playoff_qualifier_count": playoff_count,
        "playoff_entrant_seeds": sorted(seed_by_team[team_id] for team_id in championship_ids),
        "first_postseason_period_bye_seeds": sorted(bye_seeds),
        "first_round_winner_seeds": first_winner_seeds,
        "bye_winner_pairings_next_period": sorted(bye_winner_pairings),
        "championship_pairings_by_period": championship_pairings,
        "consolation_pairings_by_period": consolation_pairings,
        "final_rank_by_seed": {str(seed_by_team[team_id]): final_rank_by_team[team_id] for team_id in sorted(team_ids, key=seed_by_team.get)},
        "championship_placement_pairings_by_final_rank": sorted(placement_pairs),
        "winner_loser_transitions_by_period": transition_evidence,
        "decided_winner_count": len({row["winner_team_id"] for rows in rows_by_period.values() for row in rows if row["winner_team_id"] is not None}),
        "multiweek_aggregate_side_checks": aggregate_checks,
        "reseed_setting": _bool(settings.get("playoffReseed"), "historical playoffReseed"),
        "classification": "Verified live (historical league response; relationships reconstructed by repository code)",
    }


def _capabilities(roster: Mapping[str, object], waivers: Mapping[str, object], standings: Mapping[str, object], championship: Mapping[str, object], consolation: Mapping[str, object]) -> tuple[dict[str, str], ...]:
    return (
        {"area": "roster_capacity", "status": "valid_but_unverified" if roster["unknown_slot_ids"] else "valid_and_understood", "reason": "Unknown positive slot IDs require semantic mapping." if roster["unknown_slot_ids"] else "All positive raw slot IDs have known labels."},
        {"area": "waiver_system", "status": str(waivers["interpretation_status"]), "reason": "Raw acquisition type is preserved; only established enums are interpreted."},
        {"area": "standings", "status": str(standings["interpretation_status"]), "reason": "Raw scoring and tiebreak enums are preserved without substitution."},
        {"area": "championship", "status": str(championship["interpretation_status"]), "reason": "Counts, byes, periods, and durations are derived from ESPN settings."},
        {"area": "consolation", "status": str(consolation["interpretation_status"]), "reason": "Enablement can be recorded even when advancement semantics are unavailable."},
    )


def build_report(raw: Mapping[str, Any], historical: Sequence[tuple[int, Mapping[str, Any]]], *, league_id: int, season: int, endpoint: str, expected_team_count: int | None = None) -> RulesAuditReport:
    teams, _ = _teams(raw, expected_team_count)
    roster = audit_roster(raw, expected_team_count=expected_team_count)
    waivers = audit_waivers(raw, expected_team_count=expected_team_count)
    trades = audit_trades(raw)
    standings, championship, consolation = audit_schedule(raw)
    history = tuple(summarize_historical_bracket(item, year) for year, item in historical)
    return RulesAuditReport(
        league_id=league_id, season=season, retrieved_at_utc=datetime.now(timezone.utc).isoformat(), endpoint=endpoint, views=VIEWS,
        team_count=len(teams), roster=roster, waivers=waivers, trades=trades, standings=standings, championship=championship, consolation=consolation,
        capabilities=_capabilities(roster, waivers, standings, championship, consolation), historical_evidence=history,
        verified_live=(
            "Current raw roster, waiver, trade, standings, schedule, playoff, and consolation settings were structurally validated and recorded without a league template.",
            "Current-league quantities are derived from retrieved settings; optional expected team count is an identity check only.",
            "Completed historical responses expose entrants, seed pairings, byes, winners, final ranks, and multiweek score components for independent reconstruction.",
        ),
        verified_by_tests=(
            "Multiple valid league sizes, slot structures, flex counts, IR choices, playoff counts, round durations, and consolation choices are accepted.",
            "Malformed capacities, identifiers, references, ranks, periods, pairings, and aggregates fail explicitly.",
            "Unknown but structurally valid enums and slots remain recorded as unsupported or unverified instead of being replaced.",
        ),
        unverified=(
            "The exact operational meaning and timezone of waiverProcessHour is not established by the raw field alone.",
            "The ordering of multiple contingent claims from one manager requires direct UI or observed behavioral evidence.",
            "Trade review type, veto workflow, dropped-player reentry timing, postseason transaction restrictions, and tie resolution are not fully encoded by verified fields.",
            "The current eight-team consolation ladder cannot be inferred from completed historical six-team ladders.",
        ),
        unsupported=("The current schedule contains no future postseason pairings before qualification is resolved.", "No verified current field fully defines consolation advancement or raw NONE matchup-tie behavior."),
        manual_configuration=(
            {"key": "waivers.claim_processing_order", "allowed": "ordered verified procedure", "blocks_simulation": True, "reason": "Multiple-claim behavior is not fully exposed."},
            {"key": "waivers.process_timezone", "allowed": "verified IANA timezone", "blocks_simulation": False, "reason": "The raw processing hour does not identify its timezone."},
            {"key": "transactions.trade_review_type", "allowed": ["league_vote", "commissioner", "none"], "blocks_simulation": False, "reason": "Votes and delay do not prove workflow."},
            {"key": "standings.matchup_tie_rule", "allowed": "verified ESPN rule", "blocks_simulation": True, "reason": "Raw NONE enum is semantically unresolved."},
            {"key": "postseason.playoff_matchup_tie_rule", "allowed": "verified ESPN rule", "blocks_simulation": True, "reason": "Raw NONE enum is semantically unresolved."},
            {"key": "postseason.consolation_ladder", "allowed": "explicit participants, pairings, advancement, durations, placement mapping", "blocks_simulation": True, "reason": "The current eight-team structure is not yet exposed."},
        ),
    )


def audit_live(config: Settings, *, historical_seasons: Sequence[int], expected_team_count: int | None = None) -> RulesAuditReport:
    credentials = config.credentials
    league = League(league_id=config.league_id, year=config.season, espn_s2=credentials.espn_s2 if credentials else None, swid=credentials.swid if credentials else None)
    raw = league.espn_request.get_league()
    historical: list[tuple[int, Mapping[str, Any]]] = []
    for year in historical_seasons:
        old = League(league_id=config.league_id, year=year, espn_s2=credentials.espn_s2 if credentials else None, swid=credentials.swid if credentials else None)
        historical.append((year, old.espn_request.get_league()))
    return build_report(raw, historical, league_id=config.league_id, season=config.season, endpoint=league.espn_request.LEAGUE_ENDPOINT, expected_team_count=expected_team_count)


def render_summary(report: RulesAuditReport) -> str:
    return "\n".join((
        "M0.4 ESPN league-rules discovery", f"League {report.league_id}; season {report.season}; teams discovered={report.team_count}",
        f"Roster capacity: starters={report.roster['starter_capacity']}, bench={report.roster['bench_capacity']}, IR={report.roster['ir_capacity']}",
        f"Waivers: {report.waivers['acquisition_type_raw']} ({report.waivers['interpretation_status']})",
        f"Playoffs: qualifiers={report.championship['qualifier_count']}, derived byes={report.championship['derived_first_round_byes']}, rounds={report.championship['round_lengths']}",
        f"Consolation: enabled={report.consolation['enabled']} ({report.consolation['interpretation_status']})",
        "", "Capability assessment:", *(f"- {item['area']}: {item['status']} - {item['reason']}" for item in report.capabilities),
        "", "Unresolved:", *(f"- {item}" for item in report.unverified),
    ))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the read-only M0.4 ESPN league-rules discovery.")
    parser.add_argument("--expected-team-count", type=int, help="Optional identity check; not a supported-structure restriction.")
    parser.add_argument("--historical-season", type=int, action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        report = audit_live(settings, historical_seasons=args.historical_season, expected_team_count=args.expected_team_count)
    except (SettingsError, LeagueRulesAuditError, ESPNAccessDenied, ESPNInvalidLeague, ESPNUnknownError, RequestException) as exc:
        LOGGER.error("M0.4 league-rules discovery failed: %s", exc)
        return 2
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True) if args.json else render_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
