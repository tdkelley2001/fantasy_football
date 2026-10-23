from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

import pytest

from fantasy_football.historical_dataset import (
    CAPTURE_MANIFEST_SCHEMA,
    EvidenceClassification,
    HistoricalResearchInputRecord,
    HistoricalResearchSample,
    HistoricalResearchSource,
    ProjectionTemporalProvenance,
    SourceKind,
    SourceRole,
    build_historical_research_dataset,
    validate_pregame_capture_manifest,
)
from fantasy_football.historical_projection_audit import HistoricalPlayerWeek, PROVENANCE_CLASS
from fantasy_football.outcome_distribution_research import (
    CandidateFamily,
    CandidateSpecification,
    Conditioning,
    EvidencePolicy,
    OutcomeResearchError,
    ResearchConfiguration,
    TemporalSplit,
    outcome_distribution_report_to_json,
    research_outcome_distributions,
)


UTC = timezone.utc
SIGNATURE = hashlib.sha256(b"research-scoring").hexdigest()


def _record(player: int, season: int, week: int, projection: float, actual: float, position: int = 2, *, authenticated: bool = False) -> HistoricalPlayerWeek:
    def status(value: float) -> str:
        return "explicit_zero" if value == 0 else "negative" if value < 0 else "positive"

    return HistoricalPlayerWeek(
        player_id=player, season=season, week=week, position_id=position, pro_team_id=10,
        projection=projection, actual=actual, projection_status=status(projection),
        actual_status=status(actual), actual_stat_breakdown_present=True,
        as_of_metadata_present=False,
        provenance_class=(ProjectionTemporalProvenance.AUTHENTICATED_PREGAME.value if authenticated else PROVENANCE_CLASS),
    )


def _payload(records: tuple[HistoricalPlayerWeek, ...]) -> bytes:
    return json.dumps({"players": [{
        "id": row.player_id,
        "player": {
            "id": row.player_id, "defaultPositionId": row.position_id, "proTeamId": row.pro_team_id,
            "stats": [{
                "seasonId": row.season, "scoringPeriodId": row.week, "statSourceId": 1,
                "statSplitTypeId": 1, "appliedTotal": row.projection, "stats": {},
            }],
        },
    } for row in records]}, sort_keys=True, separators=(",", ":")).encode()


def _dataset(periods: tuple[tuple[int, int, tuple[HistoricalPlayerWeek, ...]], ...], *, authenticated: bool = False):
    samples = []
    sources = []
    captures = []
    for season, week, records in periods:
        start = datetime(season, 9, 1, tzinfo=UTC) + timedelta(days=7 * week)
        end = start + timedelta(hours=4)
        projection_id, actual_id, scoring_id = f"p-{season}-{week}", f"a-{season}-{week}", f"s-{season}-{week}"
        parameters = json.dumps({"scoringPeriodId": week}, sort_keys=True, separators=(",", ":"))
        projection_payload = _payload(records)
        projection = HistoricalResearchSource(
            projection_id,
            SourceKind.IMMUTABLE_PREGAME_CAPTURE if authenticated else SourceKind.ESPN_HISTORICAL_RESPONSE,
            (SourceRole.PROJECTION,), "https://example.invalid/league", "kona_player_info", parameters,
            start - timedelta(hours=2) if authenticated else end + timedelta(days=30),
            hashlib.sha256(projection_payload).hexdigest(), season, week,
            EvidenceClassification.VERIFIED_BY_TESTS if authenticated else EvidenceClassification.UNVERIFIED,
            "sanitized-test-manifest" if authenticated else None,
        )
        actual = replace(projection, source_id=actual_id, kind=SourceKind.SANITIZED_FIXTURE,
                         roles=(SourceRole.ACTUAL,), retrieved_at_utc=end + timedelta(days=1),
                         payload_sha256=hashlib.sha256(actual_id.encode()).hexdigest(),
                         evidence_classification=EvidenceClassification.VERIFIED_BY_TESTS)
        scoring = replace(actual, source_id=scoring_id, roles=(SourceRole.SCORING,),
                          view="mSettings", payload_sha256=hashlib.sha256(scoring_id.encode()).hexdigest())
        sources.extend((projection, actual, scoring))
        samples.append(HistoricalResearchSample(
            season, week, start, end, projection_id, actual_id, scoring_id, SIGNATURE,
            tuple(HistoricalResearchInputRecord(row) for row in records),
        ))
        if authenticated:
            manifest = {
                "schema": CAPTURE_MANIFEST_SCHEMA, "source_id": projection_id,
                "target_season": season, "target_week": week,
                "captured_at_utc": projection.retrieved_at_utc.isoformat(),
                "observation_period_start_utc": start.isoformat(),
                "payload_sha256": projection.payload_sha256, "endpoint": projection.endpoint,
                "view": projection.view, "parameters_json": parameters,
                "verification_authority": "sanitized-test-trust-anchor",
                "verification_reference": f"fixture-{season}-{week}",
            }
            manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
            captures.append(validate_pregame_capture_manifest(
                manifest_bytes, projection_payload,
                independently_trusted_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            ))
    return build_historical_research_dataset(tuple(samples), tuple(sources), tuple(captures))


def _config(policy: EvidencePolicy = EvidencePolicy.INCLUDE_UNVERIFIED_EXPLORATORY, **changes) -> ResearchConfiguration:
    base = ResearchConfiguration(
        evidence_policy=policy,
        temporal_split=TemporalSplit(2025, 1),
        projection_bin_edges=(5.0, 15.0),
        minimum_group_size=2,
        minimum_training_rows=4,
        minimum_evaluation_rows=2,
        hybrid_shrinkage_strength=3.0,
        density_bandwidth_floor=0.5,
        normal_quadrature_points=51,
    )
    return replace(base, **changes)


def _research_dataset(*, authenticated: bool = False):
    periods = (
        (2024, 1, tuple(_record(i, 2024, 1, 5.0 + i, value, 2 if i % 2 else 3, authenticated=authenticated)
                        for i, value in enumerate((0.0, 4.0, 8.0, 12.0, -1.0, 18.0), 1))),
        (2025, 1, tuple(_record(i, 2025, 1, 5.0 + i, value, 2 if i % 2 else 3, authenticated=authenticated)
                        for i, value in enumerate((0.0, 7.0, 11.0, 16.0), 101))),
    )
    return _dataset(periods, authenticated=authenticated)


def test_missing_materialized_dataset_reports_insufficiency() -> None:
    report = research_outcome_distributions(None, _config())
    assert not report.evidence_sufficient
    assert report.candidates == ()
    assert report.source_dataset_sha256 is None
    assert "no materialized" in report.recommendation


def test_temporal_holdout_and_unverified_evidence_remain_explicit() -> None:
    report = research_outcome_distributions(_research_dataset(), _config())
    assert report.unverified_exploratory_rows == 10
    assert report.authenticated_rows == 0
    assert len(report.candidates) == 9
    assert report.exploratory_best_candidate_id is not None
    assert report.recommended_candidate_id is None
    assert not report.evidence_sufficient
    assert "Exploratory comparison only" in report.recommendation
    training = [row for row in report.coverage if row.split == "training" and row.season is None and row.position_id is None and row.projection_bin is None]
    evaluation = [row for row in report.coverage if row.split == "evaluation" and row.season is None and row.position_id is None and row.projection_bin is None]
    assert [row.row_count for row in training] == [6]
    assert [row.row_count for row in evaluation] == [4]


def test_authenticated_only_can_make_review_pending_recommendation() -> None:
    report = research_outcome_distributions(
        _research_dataset(authenticated=True),
        _config(EvidencePolicy.AUTHENTICATED_ONLY),
    )
    assert report.authenticated_rows == 10
    assert report.evidence_sufficient
    assert report.recommended_candidate_id == report.exploratory_best_candidate_id
    assert "independent review" in report.recommendation


def test_authenticated_policy_does_not_promote_unverified_rows() -> None:
    report = research_outcome_distributions(_research_dataset(), _config(EvidencePolicy.AUTHENTICATED_ONLY))
    assert report.authenticated_rows == 0
    assert report.unverified_exploratory_rows == 10
    assert report.candidates == ()
    assert "0 training and 0 evaluation" in report.recommendation


def test_all_candidate_families_and_conditioning_levels_are_compared() -> None:
    report = research_outcome_distributions(_research_dataset(), _config())
    assert {item.family for item in report.candidates} == set(CandidateFamily)
    assert {item.conditioning for item in report.candidates} == set(Conditioning)
    assert all(math.isfinite(item.mean_crps) and item.mean_crps >= 0 for item in report.candidates)
    assert all(math.isfinite(item.mean_negative_log_score) for item in report.candidates)


def test_zero_tail_bias_dispersion_and_calibration_diagnostics_are_reported() -> None:
    report = research_outcome_distributions(_research_dataset(), _config())
    for item in report.candidates:
        assert 0 <= item.zero_brier_score <= 1
        assert 0 <= item.interval_50_coverage <= 1
        assert 0 <= item.interval_80_coverage <= 1
        assert 0 <= item.interval_90_coverage <= 1
        assert item.interval_90_mean_width >= item.interval_50_mean_width
        assert math.isfinite(item.mean_error)
        assert item.root_mean_squared_error >= 0
        assert item.relative_error_rows == item.evaluation_rows
        assert item.mean_relative_error is not None and math.isfinite(item.mean_relative_error)
        assert 0 <= item.lower_tail_10_rate <= 1
        assert 0 <= item.upper_tail_90_rate <= 1
        assert len(item.pit_histogram_10) == 10
        assert sum(item.pit_histogram_10) == item.evaluation_rows


def test_sparse_conditioned_groups_fall_back_and_report_counts() -> None:
    report = research_outcome_distributions(
        _research_dataset(),
        _config(minimum_group_size=100),
        (CandidateSpecification("position", CandidateFamily.EMPIRICAL, Conditioning.POSITION),),
    )
    assert report.candidates[0].fallback_rows == 4
    assert report.candidates[0].sparse_partially_pooled_rows == 0


@pytest.mark.parametrize(
    ("local_training_count", "minimum_group_size", "pooled_fallback", "sparse_partial"),
    (
        (0, 2, 1, 0),
        (1, 2, 0, 1),
        (2, 2, 0, 0),
        (3, 2, 0, 0),
    ),
)
def test_hybrid_distinguishes_empty_sparse_threshold_and_dense_groups(
    local_training_count: int,
    minimum_group_size: int,
    pooled_fallback: int,
    sparse_partial: int,
) -> None:
    local = tuple(
        _record(player, 2024, 1, 10.0, 20.0, position=2)
        for player in range(1, local_training_count + 1)
    )
    pooled_context = tuple(
        _record(100 + player, 2024, 1, 10.0, 1.0, position=3)
        for player in range(1, 4)
    )
    evaluation = (_record(999, 2025, 1, 10.0, 20.0, position=2),)
    dataset = _dataset(((2024, 1, local + pooled_context), (2025, 1, evaluation)))
    report = research_outcome_distributions(
        dataset,
        _config(
            minimum_group_size=minimum_group_size,
            minimum_training_rows=1,
            minimum_evaluation_rows=1,
        ),
        (CandidateSpecification(
            "hybrid", CandidateFamily.HYBRID, Conditioning.POSITION_PROJECTION,
        ),),
    )
    result = report.candidates[0]
    assert result.fallback_rows == pooled_fallback
    assert result.sparse_partially_pooled_rows == sparse_partial


def test_sparse_hybrid_uses_local_evidence_while_empirical_and_normal_fall_back() -> None:
    training = (
        _record(1, 2024, 1, 10.0, 20.0, position=2),
        _record(2, 2024, 1, 10.0, 0.0, position=3),
        _record(3, 2024, 1, 10.0, 0.0, position=3),
        _record(4, 2024, 1, 10.0, 0.0, position=3),
    )
    dataset = _dataset(((2024, 1, training), (2025, 1, (_record(9, 2025, 1, 10.0, 20.0, position=2),))))
    candidates = (
        CandidateSpecification("empirical", CandidateFamily.EMPIRICAL, Conditioning.POSITION_PROJECTION),
        CandidateSpecification("hybrid", CandidateFamily.HYBRID, Conditioning.POSITION_PROJECTION),
        CandidateSpecification("normal", CandidateFamily.NORMAL, Conditioning.POSITION_PROJECTION),
    )
    report = research_outcome_distributions(
        dataset,
        _config(minimum_group_size=2, minimum_training_rows=1, minimum_evaluation_rows=1),
        candidates,
    )
    results = {item.candidate_id: item for item in report.candidates}
    assert results["empirical"].fallback_rows == 1
    assert results["normal"].fallback_rows == 1
    assert results["hybrid"].fallback_rows == 0
    assert results["hybrid"].sparse_partially_pooled_rows == 1
    assert results["hybrid"].mean_error != results["empirical"].mean_error


def test_hand_calculated_perfect_empirical_forecast_has_zero_crps() -> None:
    dataset = _dataset((
        (2024, 1, (_record(1, 2024, 1, 10.0, 10.0),)),
        (2025, 1, (_record(2, 2025, 1, 10.0, 10.0),)),
    ))
    report = research_outcome_distributions(
        dataset,
        _config(minimum_group_size=1, minimum_training_rows=1, minimum_evaluation_rows=1),
        (CandidateSpecification("pooled", CandidateFamily.EMPIRICAL, Conditioning.POOLED),),
    )
    assert report.candidates[0].mean_crps == 0
    assert report.candidates[0].mean_error == 0
    assert report.candidates[0].root_mean_squared_error == 0


def test_reordering_rows_and_candidates_is_deterministic() -> None:
    dataset = _research_dataset()
    candidates = tuple(reversed((
        CandidateSpecification("normal", CandidateFamily.NORMAL, Conditioning.POOLED),
        CandidateSpecification("empirical", CandidateFamily.EMPIRICAL, Conditioning.POOLED),
    )))
    left = research_outcome_distributions(dataset, _config(), candidates)
    right = research_outcome_distributions(dataset, _config(), tuple(reversed(candidates)))
    assert outcome_distribution_report_to_json(left) == outcome_distribution_report_to_json(right)


def test_report_identity_detects_tampering() -> None:
    report = research_outcome_distributions(_research_dataset(), _config())
    outcome_distribution_report_to_json(report)
    with pytest.raises(OutcomeResearchError, match="identity is inconsistent"):
        outcome_distribution_report_to_json(replace(report, report_sha256="0" * 64))


@pytest.mark.parametrize(
    "configuration,message",
    (
        (_config(projection_bin_edges=(15.0, 5.0)), "strictly increasing"),
        (_config(minimum_group_size=0), "positive integer"),
        (_config(density_bandwidth_floor=0.0), "positive and finite"),
        (_config(normal_quadrature_points=10), "odd integer"),
    ),
)
def test_invalid_research_configuration_fails(configuration: ResearchConfiguration, message: str) -> None:
    with pytest.raises(OutcomeResearchError, match=message):
        research_outcome_distributions(_research_dataset(), configuration)


def test_no_random_split_network_calls_or_m2_model_changes(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("M3.2 attempted network access")

    monkeypatch.setattr("fantasy_football.historical_projection_audit.League", forbidden)
    first = research_outcome_distributions(_research_dataset(), _config())
    second = research_outcome_distributions(_research_dataset(), _config())
    assert first == second
