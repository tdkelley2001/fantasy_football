from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

import fantasy_football.snapshot_cli as snapshot_cli
from fantasy_football.espn_adapter import AdapterResult, translate_bundle
from fantasy_football.snapshot_store import SnapshotStore, SnapshotStoreError
from tests.adapter_fixtures import source_bundle


UTC = timezone.utc
PUBLISHED = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 18, 15, 30, tzinfo=UTC)
ID_1 = "00000000-0000-4000-8000-000000000001"
ID_2 = "00000000-0000-4000-8000-000000000002"
ID_3 = "00000000-0000-4000-8000-000000000003"


@pytest.fixture
def result() -> AdapterResult:
    return translate_bundle(source_bundle())


@pytest.fixture
def store(tmp_path) -> SnapshotStore:
    repository = SnapshotStore(tmp_path / "snapshots.sqlite3")
    repository.initialize()
    return repository


def _different_identity(result: AdapterResult, *, league_id: int, season: int) -> AdapterResult:
    snapshot = result.snapshot
    weeks = tuple(replace(item, season=season) for item in snapshot.player_weeks)
    return replace(result, snapshot=replace(snapshot, league_id=league_id, season=season, player_weeks=weeks))


def _publish_three(store: SnapshotStore, result: AdapterResult) -> None:
    store.publish(result, snapshot_id=ID_1, published_at_utc=PUBLISHED)
    # Equal publication times exercise the required UUID-descending tie-break.
    store.publish(result, snapshot_id=ID_2, published_at_utc=PUBLISHED)
    store.publish(
        _different_identity(result, league_id=result.snapshot.league_id + 1, season=result.snapshot.season + 1),
        snapshot_id=ID_3,
        published_at_utc=PUBLISHED + timedelta(seconds=2),
    )


def test_empty_and_missing_database_listing(tmp_path, store) -> None:
    assert snapshot_cli.build_listing(store)["available_snapshot_count"] == 0
    missing = SnapshotStore(tmp_path / "missing.sqlite3")
    with pytest.raises(SnapshotStoreError, match="does not exist"):
        snapshot_cli.build_listing(missing)
    assert not missing.path.exists()


def test_listing_is_compact_filterable_and_newest_first_without_loading_sources(store, result, monkeypatch) -> None:
    _publish_three(store, result)
    monkeypatch.setattr(store, "load", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not load")))

    all_rows = snapshot_cli.build_listing(store)
    assert all_rows["available_snapshot_count"] == 3
    assert [item["snapshot_id"] for item in all_rows["snapshots"]] == [ID_3, ID_2, ID_1]
    league_rows = snapshot_cli.build_listing(store, league_id=result.snapshot.league_id)
    assert [item["snapshot_id"] for item in league_rows["snapshots"]] == [ID_2, ID_1]
    season_rows = snapshot_cli.build_listing(store, season=result.snapshot.season + 1)
    assert [item["snapshot_id"] for item in season_rows["snapshots"]] == [ID_3]
    assert all(item["first_simulation_week"] <= item["final_simulation_week"] for item in all_rows["snapshots"])


def test_exact_uuid_precedes_newest_filters_and_newest_is_scoped(store, result) -> None:
    _publish_three(store, result)
    exact = snapshot_cli.select_snapshot(store, snapshot_id=ID_1, league_id=999, season=9999)
    newest = snapshot_cli.select_snapshot(
        store, league_id=result.snapshot.league_id, season=result.snapshot.season
    )

    assert exact.metadata.snapshot_id == ID_1
    assert newest.metadata.snapshot_id == ID_2


def test_invalid_and_empty_selection_fail_without_fallback(store, result) -> None:
    store.publish(result, snapshot_id=ID_1, published_at_utc=PUBLISHED)
    with pytest.raises(SnapshotStoreError, match="not found"):
        snapshot_cli.select_snapshot(store, snapshot_id=ID_2)
    with pytest.raises(snapshot_cli.SnapshotSelectionError, match="canonical lowercase"):
        snapshot_cli.select_snapshot(store, snapshot_id="AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA")
    with pytest.raises(snapshot_cli.SnapshotSelectionError, match="both --league-id and --season"):
        snapshot_cli.select_snapshot(store, league_id=result.snapshot.league_id)
    with pytest.raises(snapshot_cli.SnapshotSelectionError, match="no published snapshots"):
        snapshot_cli.select_snapshot(store, league_id=999, season=2026)


def test_repeated_loads_are_identical_and_inspection_is_deterministic(store, result) -> None:
    store.publish(result, snapshot_id=ID_1, published_at_utc=PUBLISHED)
    first = snapshot_cli.select_snapshot(store, snapshot_id=ID_1)
    second = snapshot_cli.select_snapshot(store, snapshot_id=ID_1)
    first_report = snapshot_cli.build_inspection(first, now_utc=NOW)
    second_report = snapshot_cli.build_inspection(second, now_utc=NOW)

    assert first.canonical_json == second.canonical_json
    assert first.snapshot == second.snapshot
    assert first_report == second_report
    assert snapshot_cli._json_output(first_report) == snapshot_cli._json_output(second_report)
    summary = first_report["summary"]
    assert summary["age_seconds_from_retrieval_completion"] == (
        NOW - first.metadata.retrieval_finished_at_utc
    ).total_seconds()
    assert summary["source_evidence"]["complete"] is True
    assert summary["observed_player_week_count"] == summary["required_player_week_count"]
    assert summary["rule_limitations"]


def test_default_inspection_is_sanitized_and_details_are_explicit(store, result, capsys) -> None:
    store.publish(result, snapshot_id=ID_1, published_at_utc=PUBLISHED)
    loaded = store.load(ID_1)
    private_player_name = next(item.display_name for item in loaded.snapshot.players if item.display_name)
    private_team_name = next(item.display_name for item in loaded.snapshot.teams if item.display_name)

    snapshot_cli._print_inspection(snapshot_cli.build_inspection(loaded, now_utc=NOW))
    summary_output = capsys.readouterr().out
    assert private_player_name not in summary_output
    assert private_team_name not in summary_output
    assert "payload" not in summary_output.lower()

    detailed = snapshot_cli.build_inspection(loaded, details=("teams", "players", "sources"), now_utc=NOW)
    detailed_json = snapshot_cli._json_output(detailed)
    assert private_player_name in detailed_json
    assert private_team_name in detailed_json
    assert "endpoint" in detailed_json
    assert "compressed_payload" not in detailed_json
    assert "payload\"" not in detailed_json


def test_projection_metrics_and_rule_gaps_are_visible(store, result) -> None:
    store.publish(result, snapshot_id=ID_1, published_at_utc=PUBLISHED)
    summary = snapshot_cli.build_inspection(store.load(ID_1), now_utc=NOW)["summary"]
    coverage = summary["projection_coverage"]

    assert coverage.missing_raw_count > 0
    assert coverage.explicit_zero_count > 0
    assert coverage.finite_negative_count > 0
    assert sum(item.coverage.record_count for item in summary["projection_by_week"]) == coverage.record_count
    assert any(item.affected_capabilities for item in summary["rule_limitations"] if item.limitation_type == "rule_gap")


def test_snapshot_and_database_verification_commands(store, result, capsys) -> None:
    store.publish(result, snapshot_id=ID_1, published_at_utc=PUBLISHED)
    database = str(store.path)

    assert snapshot_cli.main(["--database", database, "verify", "--snapshot-id", ID_1, "--json"]) == 0
    snapshot_report = json.loads(capsys.readouterr().out)
    assert snapshot_report["scope"] == "requested_snapshot"
    assert snapshot_report["status"] == "ok"
    assert snapshot_report["verified_source_count"] == len(result.raw_sources)

    assert snapshot_cli.main(["--database", database, "verify", "--database-wide", "--json"]) == 0
    database_report = json.loads(capsys.readouterr().out)
    assert database_report == {
        "foreign_key_violations": [],
        "integrity_messages": ["ok"],
        "scope": "full_database",
        "status": "ok",
    }


def test_corrupt_source_and_invalid_database_wide_selection_return_nonzero(store, result, capsys) -> None:
    store.publish(result, snapshot_id=ID_1, published_at_utc=PUBLISHED)
    connection = sqlite3.connect(store.path)
    connection.execute("DROP TRIGGER raw_responses_no_update")
    connection.execute(
        "UPDATE raw_responses SET compressed_payload=? WHERE snapshot_id=? AND source_id=(SELECT min(source_id) FROM raw_responses WHERE snapshot_id=?)",
        (b"corrupt", ID_1, ID_1),
    )
    connection.commit()
    connection.close()

    assert snapshot_cli.main(["--database", str(store.path), "verify", "--snapshot-id", ID_1]) == 2
    assert "compressed payload is corrupt" in capsys.readouterr().err
    assert snapshot_cli.main(
        ["--database", str(store.path), "verify", "--database-wide", "--snapshot-id", ID_1]
    ) == 2
    assert "cannot be combined" in capsys.readouterr().err


def test_cli_list_and_inspect_json_are_valid_and_do_not_call_network(store, result, monkeypatch, capsys) -> None:
    store.publish(result, snapshot_id=ID_1, published_at_utc=PUBLISHED)

    def network_forbidden(*_args, **_kwargs):
        raise AssertionError("read-only snapshot commands must not retrieve ESPN data")

    monkeypatch.setattr("fantasy_football.espn_adapter.fetch_and_translate", network_forbidden)
    database = str(store.path)
    assert snapshot_cli.main(["--database", database, "list", "--json"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["available_snapshot_count"] == 1
    assert snapshot_cli.main(
        ["--database", database, "inspect", "--snapshot-id", ID_1, "--detail", "rules", "--json"]
    ) == 0
    inspection = json.loads(capsys.readouterr().out)
    assert inspection["summary"]["snapshot_id"] == ID_1
    assert "rules" in inspection["details"]


def test_read_only_operations_do_not_mutate_published_rows(store, result) -> None:
    store.publish(result, snapshot_id=ID_1, published_at_utc=PUBLISHED)

    def persisted_state():
        connection = sqlite3.connect(store.path)
        state = (
            connection.execute("SELECT * FROM snapshots ORDER BY snapshot_id").fetchall(),
            connection.execute("SELECT * FROM canonical_documents ORDER BY snapshot_id").fetchall(),
            connection.execute(
                "SELECT snapshot_id, source_id, payload_sha256, compressed_payload FROM raw_responses ORDER BY snapshot_id, source_id"
            ).fetchall(),
        )
        connection.close()
        return state

    before = persisted_state()
    snapshot_cli.build_listing(store)
    loaded = snapshot_cli.select_snapshot(store, snapshot_id=ID_1)
    snapshot_cli.build_inspection(loaded, details=("all",), now_utc=NOW)
    store.verify(ID_1)
    store.require_database_integrity()
    assert persisted_state() == before


def test_unsupported_detail_and_invalid_inspection_clock_fail(store, result) -> None:
    store.publish(result, snapshot_id=ID_1, published_at_utc=PUBLISHED)
    loaded = store.load(ID_1)
    with pytest.raises(snapshot_cli.SnapshotSelectionError, match="unsupported detail"):
        snapshot_cli.build_inspection(loaded, details=("raw-payloads",), now_utc=NOW)
    with pytest.raises(snapshot_cli.SnapshotSelectionError, match="timezone-aware UTC"):
        snapshot_cli.build_inspection(loaded, now_utc=datetime(2026, 10, 18))
