"""Deterministic, human-inspectable JSON for canonical schema version 1."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Callable, Mapping, TypeVar

from fantasy_football.canonical.model import (
    AcquisitionRules,
    ChampionshipRules,
    ConsolationRules,
    FantasyMatchup,
    FantasyTeam,
    InterpretationStatus,
    LeagueRules,
    LeagueSnapshot,
    LineupSlotRule,
    MatchupPeriod,
    MatchupPhase,
    NFLGame,
    NFLTeam,
    Player,
    PlayerWeek,
    PositionLimit,
    PostseasonRound,
    ProjectionClass,
    ProjectionSource,
    RosterEntry,
    RuleGap,
    RuleInterpretation,
    SCHEMA_VERSION,
    ScoringRule,
    SlotKind,
    SourceReference,
    StandingsRules,
    TradeRules,
    ValidationMetadata,
)
from fantasy_football.canonical.validation import CanonicalValidationError, validate_snapshot


class CanonicalSerializationError(ValueError):
    """Raised when JSON cannot be decoded as the supported canonical schema."""


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _encode(item) for key, item in asdict(value).items()}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    return value


def _sort_records(data: dict[str, Any]) -> None:
    keys = {
        "teams": lambda item: item["team_id"],
        "players": lambda item: item["player_id"],
        "roster_entries": lambda item: (item["team_id"], item["player_id"]),
        "player_weeks": lambda item: (item["player_id"], item["season"], item["scoring_week"]),
        "matchup_periods": lambda item: item["matchup_period_id"],
        "fantasy_matchups": lambda item: item["matchup_id"],
        "nfl_teams": lambda item: item["nfl_team_id"],
        "nfl_games": lambda item: (item["scoring_week"], item["game_id"]),
        "sources": lambda item: item["source_id"],
        "rule_gaps": lambda item: item["gap_id"],
    }
    for field, key in keys.items():
        data[field].sort(key=key)
    rules = data["rules"]
    rules["scoring"].sort(key=lambda item: item["stat_id"])
    rules["lineup_slots"].sort(key=lambda item: item["slot_id"])
    rules["position_limits"].sort(key=lambda item: item["position_id"])
    rules["interpretations"].sort(key=lambda item: item["rule_id"])
    rules["championship"]["rounds"].sort(key=lambda item: item["round_number"])
    rules["consolation"]["rounds"].sort(key=lambda item: item["round_number"])
    for source in data["sources"]:
        source["parameters"].sort(key=lambda item: item[0])
    for scoring in rules["scoring"]:
        scoring["overrides"].sort(key=lambda item: item[0])


def snapshot_to_json(snapshot: LeagueSnapshot) -> str:
    """Validate and encode a snapshot with deterministic record and key ordering."""

    validate_snapshot(snapshot)
    data = _encode(snapshot)
    _sort_records(data)
    return json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CanonicalSerializationError(f"{field} must be an object")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise CanonicalSerializationError(f"{field} must be an array")
    return value


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise CanonicalSerializationError(f"{field} must be an ISO-8601 UTC string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CanonicalSerializationError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise CanonicalSerializationError(f"{field} must include UTC timezone information")
    return parsed


def _optional_timestamp(value: Any, field: str) -> datetime | None:
    return None if value is None else _timestamp(value, field)


R = TypeVar("R")


def _records(value: Any, field: str, constructor: Callable[[Mapping[str, Any]], R]) -> tuple[R, ...]:
    return tuple(constructor(_mapping(item, f"{field}[{index}]")) for index, item in enumerate(_list(value, field)))


def _source(data: Mapping[str, Any]) -> SourceReference:
    return SourceReference(
        source_id=data["source_id"], endpoint=data["endpoint"], view=data["view"],
        parameters=tuple((item[0], item[1]) for item in _list(data["parameters"], "source.parameters")),
        retrieved_at_utc=_timestamp(data["retrieved_at_utc"], "source.retrieved_at_utc"),
        payload_sha256=data.get("payload_sha256"),
    )


def _interpretation(data: Mapping[str, Any]) -> RuleInterpretation:
    return RuleInterpretation(
        rule_id=data["rule_id"], raw_field=data["raw_field"], raw_value=data.get("raw_value"),
        normalized_value=data.get("normalized_value"), status=InterpretationStatus(data["status"]), source_id=data["source_id"],
        manual_config_key=data.get("manual_config_key"), manual_config_approval=data.get("manual_config_approval"),
        audited_gap_id=data.get("audited_gap_id"),
    )


def _round(data: Mapping[str, Any]) -> PostseasonRound:
    return PostseasonRound(round_number=data["round_number"], matchup_period_id=data["matchup_period_id"])


def _rules(data: Mapping[str, Any]) -> LeagueRules:
    acquisition = _mapping(data["acquisition"], "rules.acquisition")
    trades = _mapping(data["trades"], "rules.trades")
    standings = _mapping(data["standings"], "rules.standings")
    championship = _mapping(data["championship"], "rules.championship")
    consolation = _mapping(data["consolation"], "rules.consolation")
    return LeagueRules(
        team_count=data["team_count"],
        scoring=_records(data["scoring"], "rules.scoring", lambda item: ScoringRule(
            stat_id=item["stat_id"], points=item["points"], overrides=tuple((row[0], row[1]) for row in _list(item.get("overrides", []), "scoring.overrides")))),
        lineup_slots=_records(data["lineup_slots"], "rules.lineup_slots", lambda item: LineupSlotRule(
            slot_id=item["slot_id"], capacity=item["capacity"], kind=SlotKind(item["kind"]), label=item.get("label"))),
        position_limits=_records(data["position_limits"], "rules.position_limits", lambda item: PositionLimit(**item)),
        lineup_lock_type=data.get("lineup_lock_type"), roster_lock_type=data.get("roster_lock_type"), move_limit=data.get("move_limit"),
        acquisition=AcquisitionRules(
            acquisition_type=acquisition["acquisition_type"], uses_budget=acquisition["uses_budget"], season_limit=acquisition.get("season_limit"),
            matchup_limit=acquisition.get("matchup_limit"), waiver_hours=acquisition.get("waiver_hours"),
            process_days=tuple(acquisition.get("process_days", [])), process_hour_raw=acquisition.get("process_hour_raw"),
            waiver_order_resets=acquisition.get("waiver_order_resets")),
        trades=TradeRules(
            enabled=trades["enabled"], deadline_utc=_optional_timestamp(trades.get("deadline_utc"), "rules.trades.deadline_utc"),
            trade_limit=trades.get("trade_limit"), review_hours=trades.get("review_hours"), veto_votes_required=trades.get("veto_votes_required")),
        standings=StandingsRules(**standings),
        championship=ChampionshipRules(
            enabled=championship["enabled"], qualifier_count=championship["qualifier_count"], reseed=championship.get("reseed"),
            rounds=_records(championship["rounds"], "rules.championship.rounds", _round), matchup_tie_rule_id=championship.get("matchup_tie_rule_id")),
        consolation=ConsolationRules(
            enabled=consolation.get("enabled"), participant_count=consolation.get("participant_count"),
            rounds=_records(consolation["rounds"], "rules.consolation.rounds", _round), structure_rule_id=consolation.get("structure_rule_id")),
        interpretations=_records(data["interpretations"], "rules.interpretations", _interpretation),
    )


def _decode(data: Mapping[str, Any]) -> LeagueSnapshot:
    validation = _mapping(data["validation"], "validation")
    return LeagueSnapshot(
        schema_version=data["schema_version"], snapshot_id=data.get("snapshot_id"), league_id=data["league_id"], league_name=data["league_name"], season=data["season"],
        retrieval_started_at_utc=_timestamp(data["retrieval_started_at_utc"], "retrieval_started_at_utc"),
        retrieval_finished_at_utc=_timestamp(data["retrieval_finished_at_utc"], "retrieval_finished_at_utc"),
        first_simulation_week=data["first_simulation_week"], final_simulation_week=data["final_simulation_week"],
        rules=_rules(_mapping(data["rules"], "rules")),
        teams=_records(data["teams"], "teams", lambda item: FantasyTeam(**item)),
        players=_records(data["players"], "players", lambda item: Player(
            player_id=item["player_id"], display_name=item.get("display_name"), default_position_id=item["default_position_id"],
            eligible_lineup_slot_ids=tuple(item["eligible_lineup_slot_ids"]), nfl_team_id=item["nfl_team_id"],
            injury_status=item.get("injury_status"), acquisition_status=item["acquisition_status"])),
        roster_entries=_records(data["roster_entries"], "roster_entries", lambda item: RosterEntry(**item)),
        player_weeks=_records(data["player_weeks"], "player_weeks", lambda item: PlayerWeek(
            player_id=item["player_id"], season=item["season"], scoring_week=item["scoring_week"], raw_projection=item.get("raw_projection"),
            projection_class=ProjectionClass(item["projection_class"]), effective_projection=item["effective_projection"],
            effective_source=ProjectionSource(item["effective_source"]), source_id=item["source_id"])),
        matchup_periods=_records(data["matchup_periods"], "matchup_periods", lambda item: MatchupPeriod(
            matchup_period_id=item["matchup_period_id"], scoring_weeks=tuple(item["scoring_weeks"]), phase=MatchupPhase(item["phase"]), round_number=item.get("round_number"))),
        fantasy_matchups=_records(data["fantasy_matchups"], "fantasy_matchups", lambda item: FantasyMatchup(**item)),
        nfl_teams=_records(data["nfl_teams"], "nfl_teams", lambda item: NFLTeam(**item)),
        nfl_games=_records(data["nfl_games"], "nfl_games", lambda item: NFLGame(
            game_id=item["game_id"], scoring_week=item["scoring_week"], home_nfl_team_id=item["home_nfl_team_id"],
            away_nfl_team_id=item["away_nfl_team_id"], kickoff_utc=_optional_timestamp(item.get("kickoff_utc"), "nfl_game.kickoff_utc"))),
        sources=_records(data["sources"], "sources", _source),
        rule_gaps=_records(data["rule_gaps"], "rule_gaps", lambda item: RuleGap(
            gap_id=item["gap_id"], reason=item["reason"], source_id=item["source_id"],
            affected_capabilities=tuple(item["affected_capabilities"]), manual_configuration_permitted=item["manual_configuration_permitted"])),
        validation=ValidationMetadata(
            validated_at_utc=_optional_timestamp(validation.get("validated_at_utc"), "validation.validated_at_utc"),
            validator_version=validation["validator_version"], warnings=tuple(validation.get("warnings", []))),
    )


def snapshot_from_json(payload: str) -> LeagueSnapshot:
    """Decode, construct, and fully validate a supported canonical snapshot."""

    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CanonicalSerializationError(f"invalid canonical JSON: {exc.msg}") from exc
    data = _mapping(raw, "snapshot")
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise CanonicalSerializationError(f"unsupported schema_version={version!r}; expected {SCHEMA_VERSION}")
    try:
        snapshot = _decode(data)
        validate_snapshot(snapshot)
    except CanonicalSerializationError:
        raise
    except CanonicalValidationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise CanonicalSerializationError(f"malformed schema-v{SCHEMA_VERSION} snapshot: {exc}") from exc
    return snapshot
