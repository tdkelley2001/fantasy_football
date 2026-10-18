"""Read-only listing, selection, inspection, and verification for published snapshots."""

from __future__ import annotations

import argparse
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
import sys
from typing import Any, Sequence
from uuid import UUID

from fantasy_football.canonical.model import JsonArray, JsonObject
from fantasy_football.config import SettingsError, load_settings
from fantasy_football.quality import SnapshotQualityReport, generate_quality_report
from fantasy_football.snapshot_store import (
    DatabaseIntegrityReport,
    LoadedSnapshot,
    SnapshotListItem,
    SnapshotStore,
    SnapshotStoreError,
)


DETAIL_CHOICES = ("teams", "rosters", "players", "projections", "rules", "matchups", "nfl", "sources")


class SnapshotSelectionError(SnapshotStoreError):
    """Raised when an exact or newest-snapshot selection is invalid or empty."""


def _uuid_text(value: str) -> str:
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise SnapshotSelectionError(f"snapshot UUID is invalid: {value!r}") from exc
    if str(parsed) != value:
        raise SnapshotSelectionError(f"snapshot UUID must use canonical lowercase text: {value!r}")
    return value


def select_snapshot(
    store: SnapshotStore,
    *,
    snapshot_id: str | None = None,
    league_id: int | None = None,
    season: int | None = None,
) -> LoadedSnapshot:
    """Load an exact UUID, or the newest snapshot for an explicit league/season."""

    if snapshot_id is not None:
        return store.load(_uuid_text(snapshot_id), verify_sources=True)
    if league_id is None or season is None:
        raise SnapshotSelectionError(
            "selection requires --snapshot-id or both --league-id and --season"
        )
    if isinstance(league_id, bool) or not isinstance(league_id, int) or league_id <= 0:
        raise SnapshotSelectionError(f"league_id must be a positive integer; observed {league_id!r}")
    if isinstance(season, bool) or not isinstance(season, int) or season < 2000:
        raise SnapshotSelectionError(f"season must be an integer >= 2000; observed {season!r}")
    metadata = store.newest_metadata(league_id, season)
    if metadata is None:
        raise SnapshotSelectionError(
            f"no published snapshots match league_id={league_id} season={season}"
        )
    return store.load(metadata.snapshot_id, verify_sources=True)


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, JsonArray):
        return [_jsonable(item) for item in value.values]
    if isinstance(value, JsonObject):
        return {key: _jsonable(item) for key, item in value.items}
    if is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _json_output(value: object) -> str:
    return json.dumps(_jsonable(value), indent=2, sort_keys=True, allow_nan=False) + "\n"


def _listing_item(item: SnapshotListItem) -> dict[str, object]:
    metadata = item.metadata
    return {
        "snapshot_id": metadata.snapshot_id,
        "league_id": metadata.league_id,
        "season": metadata.season,
        "retrieval_finished_at_utc": metadata.retrieval_finished_at_utc,
        "published_at_utc": metadata.published_at_utc,
        "canonical_schema_version": metadata.canonical_schema_version,
        "first_simulation_week": item.first_simulation_week,
        "final_simulation_week": item.final_simulation_week,
    }


def build_listing(
    store: SnapshotStore,
    *,
    league_id: int | None = None,
    season: int | None = None,
) -> dict[str, object]:
    items = store.list_snapshots(league_id=league_id, season=season)
    return {
        "available_snapshot_count": len(items),
        "filters": {"league_id": league_id, "season": season},
        "snapshots": tuple(_listing_item(item) for item in items),
    }


def _detail_sections(loaded: LoadedSnapshot, requested: tuple[str, ...]) -> dict[str, object]:
    snapshot = loaded.snapshot
    names = DETAIL_CHOICES if "all" in requested else tuple(sorted(set(requested)))
    sections: dict[str, object] = {}
    for name in names:
        if name == "teams":
            sections[name] = snapshot.teams
        elif name == "rosters":
            sections[name] = snapshot.roster_entries
        elif name == "players":
            sections[name] = snapshot.players
        elif name == "projections":
            sections[name] = snapshot.player_weeks
        elif name == "rules":
            sections[name] = {"league_rules": snapshot.rules, "rule_gaps": snapshot.rule_gaps}
        elif name == "matchups":
            sections[name] = {
                "matchup_periods": snapshot.matchup_periods,
                "fantasy_matchups": snapshot.fantasy_matchups,
            }
        elif name == "nfl":
            sections[name] = {"nfl_teams": snapshot.nfl_teams, "nfl_games": snapshot.nfl_games}
        elif name == "sources":
            # Canonical request metadata only. Captured response payloads are never exposed.
            sections[name] = snapshot.sources
        else:
            raise SnapshotSelectionError(f"unsupported detail type: {name!r}")
    return sections


def build_inspection(
    loaded: LoadedSnapshot,
    *,
    details: tuple[str, ...] = (),
    now_utc: datetime | None = None,
) -> dict[str, object]:
    now = datetime.now(timezone.utc) if now_utc is None else now_utc
    if now.tzinfo is None or now.utcoffset() is None or now.utcoffset().total_seconds() != 0:
        raise SnapshotSelectionError("inspection clock must be timezone-aware UTC")
    report: SnapshotQualityReport = generate_quality_report(loaded.snapshot)
    metadata = loaded.metadata
    age_seconds = (now - metadata.retrieval_finished_at_utc).total_seconds()
    summary: dict[str, object] = {
        "snapshot_id": metadata.snapshot_id,
        "league_id": metadata.league_id,
        "season": metadata.season,
        "canonical_schema_version": metadata.canonical_schema_version,
        "retrieval_finished_at_utc": metadata.retrieval_finished_at_utc,
        "published_at_utc": metadata.published_at_utc,
        "age_seconds_from_retrieval_completion": age_seconds,
        "first_simulation_week": report.first_simulation_week,
        "final_simulation_week": report.final_simulation_week,
        "team_count": report.team_count,
        "player_count": report.player_count,
        "rostered_player_count": report.rostered_player_count,
        "unrostered_player_count": report.unrostered_player_count,
        "required_player_week_count": report.required_player_week_count,
        "observed_player_week_count": report.observed_player_week_count,
        "projection_coverage": report.projection_coverage,
        "projection_by_week": report.projection_by_week,
        "fantasy_matchup_count": report.fantasy_matchup_count,
        "nfl_game_count": report.nfl_game_count,
        "source_evidence": {
            "expected_count": metadata.source_count,
            "loaded_and_verified_count": len(loaded.raw_sources),
            "complete": metadata.source_count == len(loaded.raw_sources),
        },
        "rule_limitations": report.rule_limitations,
        "diagnostics": report.diagnostics,
        "integrity": {
            "scope": "requested_snapshot",
            "status": "ok",
            "canonical_sha256": metadata.canonical_sha256,
            "canonical_byte_length": metadata.canonical_byte_length,
        },
    }
    result: dict[str, object] = {"summary": summary}
    if details:
        result["details"] = _detail_sections(loaded, details)
    return result


def _format_age(seconds: float) -> str:
    direction = "old" if seconds >= 0 else "ahead of inspection clock"
    absolute = abs(seconds)
    days, remainder = divmod(int(absolute), 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, _ = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {direction}"


def _print_listing(report: dict[str, object]) -> None:
    print(f"Available snapshots: {report['available_snapshot_count']}")
    for item in report["snapshots"]:  # type: ignore[union-attr]
        print(
            f"{item['snapshot_id']}  league={item['league_id']} season={item['season']} "
            f"weeks={item['first_simulation_week']}-{item['final_simulation_week']} "
            f"retrieved={_jsonable(item['retrieval_finished_at_utc'])} "
            f"published={_jsonable(item['published_at_utc'])} schema={item['canonical_schema_version']}"
        )


def _print_inspection(report: dict[str, object]) -> None:
    summary = report["summary"]
    projection = summary["projection_coverage"]
    print(f"Snapshot: {summary['snapshot_id']}")
    print(f"League/season: {summary['league_id']}/{summary['season']}  schema={summary['canonical_schema_version']}")
    print(f"Retrieved: {_jsonable(summary['retrieval_finished_at_utc'])}")
    print(f"Published: {_jsonable(summary['published_at_utc'])}")
    print(f"Age: {_format_age(summary['age_seconds_from_retrieval_completion'])}")
    print(f"Simulation weeks: {summary['first_simulation_week']}-{summary['final_simulation_week']}")
    print(
        f"Teams: {summary['team_count']}  Players: {summary['player_count']} "
        f"(rostered={summary['rostered_player_count']}, unrostered={summary['unrostered_player_count']})"
    )
    print(
        f"Player-weeks: {summary['observed_player_week_count']}/{summary['required_player_week_count']}  "
        f"raw-present={projection.present_raw_count} missing={projection.missing_raw_count} "
        f"explicit-zero={projection.explicit_zero_count} finite-negative={projection.finite_negative_count} "
        f"positive-effective={projection.positive_effective_count}"
    )
    print("Weekly projection coverage:")
    for item in summary["projection_by_week"]:
        coverage = item.coverage
        print(
            f"  week {item.key}: records={coverage.record_count} present={coverage.present_raw_count} "
            f"missing={coverage.missing_raw_count} zero={coverage.explicit_zero_count} "
            f"negative={coverage.finite_negative_count} positive={coverage.positive_effective_count}"
        )
    print(f"Fantasy matchups: {summary['fantasy_matchup_count']}  NFL games: {summary['nfl_game_count']}")
    evidence = summary["source_evidence"]
    print(
        f"Source evidence: {evidence['loaded_and_verified_count']}/{evidence['expected_count']} "
        f"verified (complete={str(evidence['complete']).lower()})"
    )
    print(f"Integrity: {summary['integrity']['status']} ({summary['integrity']['scope']})")
    limitations = summary["rule_limitations"]
    print(f"Rule limitations: {len(limitations)}")
    for item in limitations:
        capabilities = ",".join(item.affected_capabilities) or "none-recorded"
        print(
            f"  {item.limitation_type}/{item.identifier}: status={item.status}; "
            f"capabilities={capabilities}; source={item.source_id}"
        )
    if "details" in report:
        print("Detailed inspection (explicitly requested):")
        print(_json_output(report["details"]), end="")


def _database_integrity_dict(report: DatabaseIntegrityReport) -> dict[str, object]:
    return {
        "scope": "full_database",
        "status": "ok" if report.ok else "failed",
        "integrity_messages": report.integrity_messages,
        "foreign_key_violations": report.foreign_key_violations,
    }


def _add_selector(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--snapshot-id")
    parser.add_argument("--league-id", type=int)
    parser.add_argument("--season", type=int)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List, inspect, select, and verify immutable snapshots.")
    parser.add_argument("--database", type=Path, help="SQLite path; defaults to SNAPSHOT_DB_PATH configuration.")
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="List compact snapshot metadata newest first.")
    listing.add_argument("--league-id", type=int)
    listing.add_argument("--season", type=int)
    listing.add_argument("--json", action="store_true")

    inspect = commands.add_parser("inspect", help="Inspect one fully verified snapshot.")
    _add_selector(inspect)
    inspect.add_argument("--detail", action="append", choices=DETAIL_CHOICES + ("all",), default=[])
    inspect.add_argument("--json", action="store_true")

    verify = commands.add_parser("verify", help="Verify one snapshot or the complete database.")
    _add_selector(verify)
    verify.add_argument("--database-wide", action="store_true")
    verify.add_argument("--json", action="store_true")
    return parser


def _database_path(explicit: Path | None) -> Path:
    return explicit if explicit is not None else load_settings().snapshot_db_path


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        store = SnapshotStore(_database_path(args.database))
        if args.command == "list":
            report = build_listing(store, league_id=args.league_id, season=args.season)
            print(_json_output(report), end="") if args.json else _print_listing(report)
            return 0
        if args.command == "verify" and args.database_wide:
            if args.snapshot_id is not None or args.league_id is not None or args.season is not None:
                raise SnapshotSelectionError(
                    "--database-wide cannot be combined with snapshot selection options"
                )
            report = _database_integrity_dict(store.require_database_integrity())
            print(_json_output(report), end="") if args.json else print("Full database integrity: ok")
            return 0
        loaded = select_snapshot(
            store,
            snapshot_id=args.snapshot_id,
            league_id=args.league_id,
            season=args.season,
        )
        if args.command == "inspect":
            report = build_inspection(loaded, details=tuple(args.detail))
            print(_json_output(report), end="") if args.json else _print_inspection(report)
            return 0
        metadata = loaded.metadata
        report = {
            "scope": "requested_snapshot",
            "status": "ok",
            "snapshot_id": metadata.snapshot_id,
            "canonical_schema_version": metadata.canonical_schema_version,
            "canonical_sha256": metadata.canonical_sha256,
            "canonical_byte_length": metadata.canonical_byte_length,
            "verified_source_count": len(loaded.raw_sources),
        }
        print(_json_output(report), end="") if args.json else print(
            f"Snapshot integrity: ok  id={metadata.snapshot_id} "
            f"schema={metadata.canonical_schema_version} sources={len(loaded.raw_sources)}"
        )
        return 0
    except (SettingsError, SnapshotStoreError) as exc:
        print(f"Snapshot command failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
