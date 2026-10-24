from __future__ import annotations

import json
from pathlib import Path

import pytest

from fantasy_football.config import Settings
from fantasy_football.historical_research_workflow import (
    HistoricalResearchWorkflowError,
    PLAN_SCHEMA,
    load_historical_research_plan,
    materialize_and_evaluate_historical_research,
)


def _plan_payload(**overrides) -> bytes:
    raw = {
        "schema": PLAN_SCHEMA,
        "page_size": 10,
        "samples": [
            {
                "season": 2024, "week": 1,
                "observation_period_start_utc": "2024-09-05T00:00:00+00:00",
                "observation_period_end_utc": "2024-09-10T12:00:00+00:00",
            },
            {
                "season": 2025, "week": 1,
                "observation_period_start_utc": "2025-09-04T00:00:00+00:00",
                "observation_period_end_utc": "2025-09-09T12:00:00+00:00",
            },
        ],
        "research_configuration": {
            "evidence_policy": "include_unverified_exploratory",
            "evaluation_start_season": 2025,
            "evaluation_start_week": 1,
            "projection_bin_edges": [5.0, 15.0],
            "minimum_group_size": 1,
            "minimum_training_rows": 1,
            "minimum_evaluation_rows": 1,
            "hybrid_shrinkage_strength": 2.0,
            "density_bandwidth_floor": 0.5,
            "normal_quadrature_points": 21,
        },
    }
    raw.update(overrides)
    return json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()


def _player(player_id: int, season: int, week: int, projection: float, actual: float) -> dict:
    return {
        "id": player_id,
        "player": {
            "id": player_id, "defaultPositionId": 2, "proTeamId": 10,
            "stats": [
                {"seasonId": season, "scoringPeriodId": week, "statSourceId": 1,
                 "statSplitTypeId": 1, "appliedTotal": projection, "stats": {}},
                {"seasonId": season, "scoringPeriodId": week, "statSourceId": 0,
                 "statSplitTypeId": 1, "appliedTotal": actual, "stats": {"1": actual}},
            ],
        },
    }


def _scoring() -> dict:
    return {"settings": {"scoringSettings": {"scoringItems": [
        {"statId": 1, "points": 1.0, "pointsOverrides": {}},
    ]}}}


class _Request:
    LEAGUE_ENDPOINT = "https://example.invalid/league"

    def __init__(self, season: int):
        self.season = season

    def get_league(self):
        return _scoring()

    def league_get(self, *, params, headers):
        week = params["scoringPeriodId"]
        return {"players": [_player(self.season, self.season, week, 10.0, 8.0)]}


class _League:
    def __init__(self, *, year: int, **kwargs):
        self.espn_request = _Request(year)


def test_plan_requires_explicit_unique_periods_and_temporal_configuration() -> None:
    plan = load_historical_research_plan(_plan_payload())
    assert [(item.season, item.week) for item in plan.samples] == [(2024, 1), (2025, 1)]
    malformed = json.loads(_plan_payload())
    malformed["samples"].append(malformed["samples"][0])
    with pytest.raises(HistoricalResearchWorkflowError, match="duplicates"):
        load_historical_research_plan(json.dumps(malformed).encode())
    malformed = json.loads(_plan_payload())
    malformed["samples"][0]["observation_period_start_utc"] = "2024-09-05"
    with pytest.raises(HistoricalResearchWorkflowError, match="timezone offset"):
        load_historical_research_plan(json.dumps(malformed).encode())


def test_materialization_reuses_m31_contract_and_keeps_outputs_private(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("fantasy_football.historical_research_workflow.League", _League)
    repository = tmp_path / "repo"
    (repository / "outputs").mkdir(parents=True)
    (repository / ".gitignore").write_text("outputs/\n")
    output = repository / "outputs" / "m32-test"
    result = materialize_and_evaluate_historical_research(
        Settings(league_id=1, season=2026, log_level="INFO"),
        load_historical_research_plan(_plan_payload()), output, repository_root=repository,
    )
    assert result.sample_count == 2
    assert result.row_count == result.paired_count == result.unverified_exploratory_pair_count == 2
    assert result.authenticated_pair_count == 0
    assert result.recommended_candidate_id is None
    assert result.exploratory_best_candidate_id is not None
    assert {path.name for path in output.iterdir()} == {
        "historical-research-dataset.json", "outcome-distribution-report.json",
        "raw-player-pages-2024-1.json", "raw-player-pages-2025-1.json",
        "raw-scoring-2024.json", "raw-scoring-2025.json",
        "retrieval-manifest.json",
    }
    assert result.output_directory == str(Path("outputs") / "m32-test")
    dataset = json.loads((output / "historical-research-dataset.json").read_bytes())
    assert dataset["dataset_sha256"] == result.dataset_sha256
    assert all(row["projection_temporal_provenance"] == "historical_projection_pregame_provenance_unverified" for row in dataset["rows"])
    manifest = json.loads((output / "retrieval-manifest.json").read_bytes())
    assert len(manifest["plan_sha256"]) == 64
    assert manifest["plan"]["samples"][0]["season"] == 2024
    assert manifest["samples"][0]["retrieved_at_utc"].endswith("+00:00")


def test_confidential_output_guard_rejects_nonignored_or_reused_locations(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("fantasy_football.historical_research_workflow.League", _League)
    settings = Settings(league_id=1, season=2026, log_level="INFO")
    plan = load_historical_research_plan(_plan_payload())
    (tmp_path / ".gitignore").write_text("outputs/\n")
    with pytest.raises(HistoricalResearchWorkflowError, match="ignored directory"):
        materialize_and_evaluate_historical_research(
            settings, plan, tmp_path / "public", repository_root=tmp_path,
        )
    occupied = tmp_path / "outputs" / "occupied"
    occupied.mkdir(parents=True)
    (occupied / "existing.txt").write_text("do not overwrite")
    with pytest.raises(HistoricalResearchWorkflowError, match="absent or empty"):
        materialize_and_evaluate_historical_research(
            settings, plan, occupied, repository_root=tmp_path,
        )


def test_materialization_makes_no_authenticated_claim_from_current_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("fantasy_football.historical_research_workflow.League", _League)
    repository = tmp_path / "repo"
    (repository / "outputs").mkdir(parents=True)
    (repository / ".gitignore").write_text("outputs/\n")
    result = materialize_and_evaluate_historical_research(
        Settings(league_id=1, season=2026, log_level="INFO"),
        load_historical_research_plan(_plan_payload()),
        repository / "outputs" / "run", repository_root=repository,
    )
    assert result.authenticated_pair_count == 0
    assert "Exploratory comparison only" in result.recommendation


def test_materialization_requires_outputs_to_be_gitignored(tmp_path: Path) -> None:
    (tmp_path / "outputs").mkdir()
    with pytest.raises(HistoricalResearchWorkflowError, match="must explicitly ignore outputs"):
        materialize_and_evaluate_historical_research(
            Settings(league_id=1, season=2026, log_level="INFO"),
            load_historical_research_plan(_plan_payload()),
            tmp_path / "outputs" / "run", repository_root=tmp_path,
        )
