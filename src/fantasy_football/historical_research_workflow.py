"""Authorized local M3.1 materialization and M3.2 evaluation workflow."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from espn_api.football import League

from fantasy_football.config import Settings, load_settings
from fantasy_football.historical_dataset import (
    EvidenceClassification,
    HistoricalResearchInputRecord,
    HistoricalResearchSample,
    HistoricalResearchSource,
    SourceKind,
    SourceRole,
    build_historical_research_dataset,
    historical_research_dataset_to_json,
)
from fantasy_football.historical_projection_audit import (
    PLAYER_INFO_VIEW,
    historical_player_filter,
    retrieve_historical_week_with_pages,
    scoring_signature,
)
from fantasy_football.outcome_distribution_research import (
    EvidencePolicy,
    ResearchConfiguration,
    TemporalSplit,
    outcome_distribution_report_to_json,
    research_outcome_distributions,
)


PLAN_SCHEMA = "fantasy_football.historical_research_plan.v1"


class HistoricalResearchWorkflowError(RuntimeError):
    """Raised when private materialization cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class SelectedHistoricalPeriod:
    season: int
    week: int
    observation_period_start_utc: datetime
    observation_period_end_utc: datetime


@dataclass(frozen=True, slots=True)
class HistoricalResearchPlan:
    samples: tuple[SelectedHistoricalPeriod, ...]
    page_size: int
    research_configuration: ResearchConfiguration


@dataclass(frozen=True, slots=True)
class MaterializedResearchResult:
    dataset_sha256: str
    report_sha256: str
    sample_count: int
    row_count: int
    paired_count: int
    authenticated_pair_count: int
    unverified_exploratory_pair_count: int
    exploratory_best_candidate_id: str | None
    recommended_candidate_id: str | None
    recommendation: str
    output_directory: str


def _fail(message: str) -> None:
    raise HistoricalResearchWorkflowError(message)


def _aware_iso(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        _fail(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        _fail(f"{field} is invalid: {exc}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(f"{field} must include a timezone offset")
    return parsed


def load_historical_research_plan(payload: bytes) -> HistoricalResearchPlan:
    """Load an explicit private retrieval/evaluation plan from canonical JSON."""

    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail(f"research plan is invalid JSON: {exc}")
    if not isinstance(raw, dict) or raw.get("schema") != PLAN_SCHEMA:
        _fail(f"research plan schema must be {PLAN_SCHEMA!r}")
    samples_raw = raw.get("samples")
    if not isinstance(samples_raw, list) or not samples_raw:
        _fail("research plan samples must be a nonempty list")
    samples = []
    seen = set()
    for index, item in enumerate(samples_raw):
        if not isinstance(item, dict) or set(item) != {"season", "week", "observation_period_start_utc", "observation_period_end_utc"}:
            _fail(f"research plan samples[{index}] fields are invalid")
        season, week = item["season"], item["week"]
        if isinstance(season, bool) or not isinstance(season, int) or season < 2000 or isinstance(week, bool) or not isinstance(week, int) or week < 1:
            _fail(f"research plan samples[{index}] has invalid season/week")
        if (season, week) in seen:
            _fail(f"research plan duplicates season={season}, week={week}")
        seen.add((season, week))
        start = _aware_iso(item["observation_period_start_utc"], f"samples[{index}].observation_period_start_utc")
        end = _aware_iso(item["observation_period_end_utc"], f"samples[{index}].observation_period_end_utc")
        if start >= end:
            _fail(f"research plan samples[{index}] observation period must have positive duration")
        samples.append(SelectedHistoricalPeriod(season, week, start, end))
    page_size = raw.get("page_size")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
        _fail("research plan page_size must be positive")
    config_raw = raw.get("research_configuration")
    if not isinstance(config_raw, dict):
        _fail("research plan research_configuration must be an object")
    try:
        configuration = ResearchConfiguration(
            evidence_policy=EvidencePolicy(config_raw["evidence_policy"]),
            temporal_split=TemporalSplit(
                config_raw["evaluation_start_season"], config_raw["evaluation_start_week"],
            ),
            projection_bin_edges=tuple(config_raw["projection_bin_edges"]),
            minimum_group_size=config_raw["minimum_group_size"],
            minimum_training_rows=config_raw["minimum_training_rows"],
            minimum_evaluation_rows=config_raw["minimum_evaluation_rows"],
            hybrid_shrinkage_strength=config_raw["hybrid_shrinkage_strength"],
            density_bandwidth_floor=config_raw["density_bandwidth_floor"],
            normal_quadrature_points=config_raw.get("normal_quadrature_points", 101),
        )
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"research plan configuration is invalid: {exc}")
    return HistoricalResearchPlan(tuple(sorted(samples, key=lambda item: (item.season, item.week))), page_size, configuration)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _plan_manifest(plan: HistoricalResearchPlan) -> dict[str, object]:
    return {
        "schema": PLAN_SCHEMA,
        "page_size": plan.page_size,
        "samples": [
            {
                "season": item.season,
                "week": item.week,
                "observation_period_start_utc": item.observation_period_start_utc.isoformat(),
                "observation_period_end_utc": item.observation_period_end_utc.isoformat(),
            }
            for item in plan.samples
        ],
        "research_configuration": asdict(plan.research_configuration),
    }


def _private_output_directory(path: Path, repository_root: Path) -> Path:
    root = repository_root.resolve()
    output_root = (root / "outputs").resolve()
    ignore_file = root / ".gitignore"
    ignored_entries = {
        line.strip().lstrip("/")
        for line in ignore_file.read_text(encoding="utf-8").splitlines()
        if ignore_file.is_file() and line.strip() and not line.lstrip().startswith("#")
    } if ignore_file.is_file() else set()
    if "outputs/" not in ignored_entries:
        _fail("repository .gitignore must explicitly ignore outputs/ before private research materialization")
    resolved = path.resolve()
    if resolved == output_root or output_root not in resolved.parents:
        _fail(f"private research output must be a child of ignored directory {output_root}")
    if resolved.exists() and any(resolved.iterdir()):
        _fail(f"private research output directory must be absent or empty: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def materialize_and_evaluate_historical_research(
    settings: Settings,
    plan: HistoricalResearchPlan,
    output_directory: Path,
    *,
    repository_root: Path,
) -> MaterializedResearchResult:
    """Retrieve selected ESPN history, materialize M3.1, and evaluate M3.2."""

    private_dir = _private_output_directory(output_directory, repository_root)
    credentials = settings.credentials
    research_samples = []
    sources = []
    retrieval_samples = []
    league_by_season: dict[int, League] = {}
    scoring_by_season: dict[int, tuple[Mapping[str, object], str]] = {}
    for selected in plan.samples:
        league = league_by_season.get(selected.season)
        if league is None:
            league = League(
                league_id=settings.league_id,
                year=selected.season,
                espn_s2=credentials.espn_s2 if credentials else None,
                swid=credentials.swid if credentials else None,
            )
            league_by_season[selected.season] = league
            raw_league = league.espn_request.get_league()
            signature, _ = scoring_signature(raw_league)
            scoring_by_season[selected.season] = (raw_league, signature)
        raw_league, signature = scoring_by_season[selected.season]
        retrieved_at = datetime.now(timezone.utc)

        def request_page(offset: int, limit: int) -> Mapping[str, object]:
            return league.espn_request.league_get(
                params={"view": PLAYER_INFO_VIEW, "scoringPeriodId": selected.week},
                headers={"x-fantasy-filter": json.dumps(historical_player_filter(offset, limit))},
            )

        records, page_lengths, pages = retrieve_historical_week_with_pages(
            request_page, season=selected.season, week=selected.week, page_size=plan.page_size,
        )
        pages_bytes = _canonical_bytes(pages)
        scoring_bytes = _canonical_bytes(raw_league)
        prefix = f"{selected.season}-{selected.week}"
        observation_source_id = f"historical-player-pages-{prefix}-{hashlib.sha256(pages_bytes).hexdigest()[:12]}"
        scoring_source_id = f"historical-scoring-{prefix}-{hashlib.sha256(scoring_bytes).hexdigest()[:12]}"
        parameters_json = json.dumps({
            "requests": [
                {
                    "params": {"scoringPeriodId": selected.week, "view": PLAYER_INFO_VIEW},
                    "x_fantasy_filter": historical_player_filter(index * plan.page_size, plan.page_size),
                }
                for index in range(len(page_lengths))
            ],
        }, sort_keys=True, separators=(",", ":"))
        sources.extend((
            HistoricalResearchSource(
                observation_source_id, SourceKind.ESPN_HISTORICAL_RESPONSE,
                (SourceRole.PROJECTION, SourceRole.ACTUAL), league.espn_request.LEAGUE_ENDPOINT,
                PLAYER_INFO_VIEW, parameters_json, retrieved_at,
                hashlib.sha256(pages_bytes).hexdigest(), selected.season, selected.week,
                EvidenceClassification.VERIFIED_LIVE,
                "authorized-read-only-current-historical-response",
            ),
            HistoricalResearchSource(
                scoring_source_id, SourceKind.ESPN_HISTORICAL_RESPONSE,
                (SourceRole.SCORING,), league.espn_request.LEAGUE_ENDPOINT, "mSettings",
                json.dumps({"view": "mSettings"}, sort_keys=True, separators=(",", ":")),
                retrieved_at, hashlib.sha256(scoring_bytes).hexdigest(), selected.season,
                selected.week, EvidenceClassification.VERIFIED_LIVE,
                "authorized-read-only-current-scoring-response",
            ),
        ))
        research_samples.append(HistoricalResearchSample(
            selected.season, selected.week, selected.observation_period_start_utc,
            selected.observation_period_end_utc, observation_source_id,
            observation_source_id, scoring_source_id, signature,
            tuple(HistoricalResearchInputRecord(record) for record in records),
        ))
        raw_path = private_dir / f"raw-player-pages-{prefix}.json"
        raw_path.write_bytes(pages_bytes)
        scoring_path = private_dir / f"raw-scoring-{selected.season}.json"
        if not scoring_path.exists():
            scoring_path.write_bytes(scoring_bytes)
        retrieval_samples.append({
            "season": selected.season, "week": selected.week,
            "source_id": observation_source_id, "payload_sha256": hashlib.sha256(pages_bytes).hexdigest(),
            "page_lengths": page_lengths, "row_count": len(records),
            "retrieved_at_utc": retrieved_at.isoformat(),
        })
    dataset = build_historical_research_dataset(tuple(research_samples), tuple(sources))
    report = research_outcome_distributions(dataset, plan.research_configuration)
    (private_dir / "historical-research-dataset.json").write_bytes(historical_research_dataset_to_json(dataset))
    (private_dir / "outcome-distribution-report.json").write_bytes(outcome_distribution_report_to_json(report))
    plan_manifest = _plan_manifest(plan)
    (private_dir / "retrieval-manifest.json").write_bytes(_canonical_bytes({
        "plan_schema": PLAN_SCHEMA,
        "plan": plan_manifest,
        "plan_sha256": hashlib.sha256(_canonical_bytes(plan_manifest)).hexdigest(),
        "dataset_sha256": dataset.dataset_sha256,
        "report_sha256": report.report_sha256,
        "samples": retrieval_samples,
    }))
    overall = next(item for item in dataset.coverage if item.dimension == "overall" and item.key == "all")
    return MaterializedResearchResult(
        dataset_sha256=dataset.dataset_sha256,
        report_sha256=report.report_sha256,
        sample_count=len(plan.samples), row_count=overall.row_count,
        paired_count=overall.paired_count,
        authenticated_pair_count=overall.authenticated_pair_count,
        unverified_exploratory_pair_count=overall.unverified_exploratory_pair_count,
        exploratory_best_candidate_id=report.exploratory_best_candidate_id,
        recommended_candidate_id=report.recommended_candidate_id,
        recommendation=report.recommendation,
        output_directory=str(private_dir.relative_to(repository_root.resolve())),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize private M3.1 history and run M3.2 evaluation.")
    parser.add_argument("--plan", type=Path, required=True, help="Private explicit research-plan JSON.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Empty child directory under ignored outputs/.")
    args = parser.parse_args(argv)
    try:
        plan = load_historical_research_plan(args.plan.read_bytes())
        result = materialize_and_evaluate_historical_research(
            load_settings(), plan, args.output_dir, repository_root=Path.cwd(),
        )
    except Exception as exc:
        print(f"historical research workflow failed: {exc}")
        return 2
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
