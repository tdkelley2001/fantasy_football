from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from fantasy_football.historical_dataset import (
    EvidenceClassification,
    HistoricalDatasetError,
    HistoricalResearchInputRecord,
    HistoricalResearchSample,
    HistoricalResearchSource,
    ProjectionTemporalProvenance,
    ProjectionValueKind,
    SourceKind,
    SourceRole,
    build_historical_research_dataset,
    historical_research_dataset_to_json,
)
from fantasy_football.historical_projection_audit import (
    PROVENANCE_CLASS,
    HistoricalPlayerWeek,
)


UTC = timezone.utc
PERIOD_START = datetime(2025, 9, 7, 17, tzinfo=UTC)
PERIOD_END = PERIOD_START + timedelta(hours=12)
SIGNATURE = hashlib.sha256(b"scoring").hexdigest()


def _source(
    source_id: str,
    *,
    roles: tuple[SourceRole, ...],
    kind: SourceKind = SourceKind.ESPN_HISTORICAL_RESPONSE,
    retrieved_at: datetime | None = None,
    evidence: EvidenceClassification = EvidenceClassification.UNVERIFIED,
    season: int = 2025,
    week: int = 1,
    verification_reference: str | None = None,
) -> HistoricalResearchSource:
    return HistoricalResearchSource(
        source_id=source_id,
        kind=kind,
        roles=roles,
        endpoint="https://example.invalid/league",
        view="kona_player_info" if SourceRole.SCORING not in roles else "mSettings",
        parameters_json=json.dumps({"scoringPeriodId": week}, sort_keys=True, separators=(",", ":")),
        retrieved_at_utc=retrieved_at or PERIOD_END + timedelta(days=30),
        payload_sha256=hashlib.sha256(source_id.encode()).hexdigest(),
        target_season=season,
        target_week=week,
        evidence_classification=evidence,
        verification_reference=verification_reference,
    )


def _record(
    player_id: int,
    projection: float | None,
    actual: float | None,
    *,
    season: int = 2025,
    week: int = 1,
    position_id: int = 2,
    provenance: str = PROVENANCE_CLASS,
) -> HistoricalPlayerWeek:
    def status(value: float | None) -> str:
        if value is None:
            return "missing"
        if value == 0:
            return "explicit_zero"
        if value < 0:
            return "negative"
        return "positive"

    return HistoricalPlayerWeek(
        player_id=player_id,
        season=season,
        week=week,
        position_id=position_id,
        pro_team_id=10,
        projection=projection,
        actual=actual,
        projection_status=status(projection),
        actual_status=status(actual),
        actual_stat_breakdown_present=actual is not None,
        as_of_metadata_present=False,
        provenance_class=provenance,
    )


def _sample(*records: HistoricalResearchInputRecord, season: int = 2025, week: int = 1) -> HistoricalResearchSample:
    return HistoricalResearchSample(
        season=season,
        week=week,
        observation_period_start_utc=PERIOD_START,
        observation_period_end_utc=PERIOD_END,
        projection_source_id=f"projection-{season}-{week}",
        actual_source_id=f"actual-{season}-{week}",
        scoring_source_id=f"scoring-{season}-{week}",
        scoring_signature=SIGNATURE,
        records=tuple(records),
    )


def _sources(*, season: int = 2025, week: int = 1) -> tuple[HistoricalResearchSource, ...]:
    return (
        _source(f"projection-{season}-{week}", roles=(SourceRole.PROJECTION,), season=season, week=week),
        _source(f"actual-{season}-{week}", roles=(SourceRole.ACTUAL,), season=season, week=week),
        _source(f"scoring-{season}-{week}", roles=(SourceRole.SCORING,), season=season, week=week),
    )


def test_unverified_historical_pairs_remain_exploratory_and_deterministic() -> None:
    sample = _sample(
        HistoricalResearchInputRecord(_record(3, 0.0, 4.0)),
        HistoricalResearchInputRecord(_record(1, 12.0, 9.0)),
        HistoricalResearchInputRecord(_record(2, None, 5.0)),
    )
    dataset = build_historical_research_dataset((sample,), tuple(reversed(_sources())))
    assert [row.player_id for row in dataset.rows] == [1, 2, 3]
    assert dataset.rows[0].projection_temporal_provenance is ProjectionTemporalProvenance.HISTORICAL_PREGAME_UNVERIFIED
    assert dataset.rows[0].eligible_unverified_exploratory_pair
    assert not dataset.rows[0].eligible_authenticated_pair
    assert dataset.rows[1].projection_value_kind is ProjectionValueKind.MISSING
    assert dataset.rows[2].projection_value_kind is ProjectionValueKind.ESPN_EXPLICIT_ZERO
    assert historical_research_dataset_to_json(dataset) == historical_research_dataset_to_json(
        build_historical_research_dataset((replace(sample, records=tuple(reversed(sample.records))),), _sources())
    )


def test_policy_imputed_zero_is_visible_but_never_a_forecast_pair() -> None:
    sample = _sample(HistoricalResearchInputRecord(_record(1, None, 7.0), policy_imputed_projection=0.0))
    dataset = build_historical_research_dataset((sample,), _sources())
    row = dataset.rows[0]
    assert row.raw_projection is None
    assert row.projection_value_kind is ProjectionValueKind.MODEL_POLICY_IMPUTED_ZERO
    assert row.projection_temporal_provenance is ProjectionTemporalProvenance.NOT_APPLICABLE
    assert not row.eligible_authenticated_pair
    assert not row.eligible_unverified_exploratory_pair
    assert dataset.coverage[0].policy_imputed_zero_count == 1
    assert dataset.coverage[0].missing_projection_count == 1


@pytest.mark.parametrize("imputed", (1.0, -1.0))
def test_policy_imputation_must_be_zero_and_cannot_replace_raw_values(imputed: float) -> None:
    with pytest.raises(HistoricalDatasetError, match="policy imputation must be zero"):
        build_historical_research_dataset(
            (_sample(HistoricalResearchInputRecord(_record(1, None, 7.0), imputed)),),
            _sources(),
        )
    with pytest.raises(HistoricalDatasetError, match="requires a missing raw projection"):
        build_historical_research_dataset(
            (_sample(HistoricalResearchInputRecord(_record(1, 0.0, 7.0), 0.0)),),
            _sources(),
        )


def test_authenticated_pregame_requires_verified_timestamped_capture() -> None:
    projection = _source(
        "projection-2025-1",
        roles=(SourceRole.PROJECTION,),
        kind=SourceKind.IMMUTABLE_PREGAME_CAPTURE,
        retrieved_at=PERIOD_START - timedelta(hours=2),
        evidence=EvidenceClassification.VERIFIED_LIVE,
        verification_reference="immutable-capture-manifest:sample-1",
    )
    record = _record(1, 10.0, 8.0, provenance=ProjectionTemporalProvenance.AUTHENTICATED_PREGAME.value)
    dataset = build_historical_research_dataset(
        (_sample(HistoricalResearchInputRecord(record)),),
        (projection, *_sources()[1:]),
    )
    assert dataset.rows[0].eligible_authenticated_pair
    assert not dataset.rows[0].eligible_unverified_exploratory_pair


def test_fixture_or_post_start_timestamp_cannot_authenticate_pregame_projection() -> None:
    fixture_claim = _source(
        "projection-2025-1",
        roles=(SourceRole.PROJECTION,),
        kind=SourceKind.IMMUTABLE_PREGAME_CAPTURE,
        retrieved_at=PERIOD_START - timedelta(hours=1),
        evidence=EvidenceClassification.VERIFIED_BY_TESTS,
        verification_reference="fixture",
    )
    with pytest.raises(HistoricalDatasetError, match="requires verified_live"):
        build_historical_research_dataset((_sample(HistoricalResearchInputRecord(_record(1, 2.0, 3.0))),), (fixture_claim, *_sources()[1:]))
    late = replace(fixture_claim, evidence_classification=EvidenceClassification.VERIFIED_LIVE, retrieved_at_utc=PERIOD_START)
    with pytest.raises(HistoricalDatasetError, match="not completed before"):
        build_historical_research_dataset((_sample(HistoricalResearchInputRecord(_record(1, 2.0, 3.0))),), (late, *_sources()[1:]))


def test_historical_as_of_flag_does_not_promote_current_response() -> None:
    record = replace(_record(1, 2.0, 3.0), as_of_metadata_present=True)
    dataset = build_historical_research_dataset((_sample(HistoricalResearchInputRecord(record)),), _sources())
    assert dataset.rows[0].projection_temporal_provenance is ProjectionTemporalProvenance.HISTORICAL_PREGAME_UNVERIFIED
    assert dataset.rows[0].raw_as_of_metadata_present
    assert dataset.rows[0].actual_stat_breakdown_present


def test_actual_source_must_follow_observation_period() -> None:
    sources = list(_sources())
    sources[1] = replace(sources[1], retrieved_at_utc=PERIOD_END - timedelta(seconds=1))
    with pytest.raises(HistoricalDatasetError, match="actual source was retrieved before"):
        build_historical_research_dataset((_sample(HistoricalResearchInputRecord(_record(1, 2.0, 3.0))),), sources)


def test_mismatched_and_duplicate_player_weeks_fail() -> None:
    wrong = _sample(HistoricalResearchInputRecord(_record(1, 2.0, 3.0, week=2)))
    with pytest.raises(HistoricalDatasetError, match="does not match sample"):
        build_historical_research_dataset((wrong,), _sources())
    duplicate = _sample(
        HistoricalResearchInputRecord(_record(1, 2.0, 3.0)),
        HistoricalResearchInputRecord(_record(1, 4.0, 5.0)),
    )
    with pytest.raises(HistoricalDatasetError, match="duplicate player-week"):
        build_historical_research_dataset((duplicate,), _sources())


def test_incorrect_record_provenance_and_value_status_fail() -> None:
    bad_provenance = replace(_record(1, 2.0, 3.0), provenance_class="authenticated_pregame")
    with pytest.raises(HistoricalDatasetError, match="contradicts source determination"):
        build_historical_research_dataset((_sample(HistoricalResearchInputRecord(bad_provenance)),), _sources())
    bad_status = replace(_record(1, None, 3.0), projection_status="explicit_zero")
    with pytest.raises(HistoricalDatasetError, match="status contradicts"):
        build_historical_research_dataset((_sample(HistoricalResearchInputRecord(bad_status)),), _sources())


def test_source_role_target_digest_and_canonical_parameters_are_validated() -> None:
    sample = _sample(HistoricalResearchInputRecord(_record(1, 2.0, 3.0)))
    projection, actual, scoring = _sources()
    with pytest.raises(HistoricalDatasetError, match="lacks projection role"):
        build_historical_research_dataset((sample,), (replace(projection, roles=(SourceRole.ACTUAL,)), actual, scoring))
    with pytest.raises(HistoricalDatasetError, match="targets season=2025, week=2"):
        build_historical_research_dataset((sample,), (replace(projection, target_week=2), actual, scoring))
    with pytest.raises(HistoricalDatasetError, match="lowercase SHA-256"):
        build_historical_research_dataset((sample,), (replace(projection, payload_sha256="bad"), actual, scoring))
    with pytest.raises(HistoricalDatasetError, match="canonical JSON object"):
        build_historical_research_dataset((sample,), (replace(projection, parameters_json='{ "x": 1 }'), actual, scoring))


def test_scoring_configuration_must_be_consistent_across_selected_samples() -> None:
    first = _sample(HistoricalResearchInputRecord(_record(1, 2.0, 3.0)))
    second = replace(
        _sample(HistoricalResearchInputRecord(_record(1, 2.0, 3.0, week=2)), week=2),
        scoring_signature=hashlib.sha256(b"different").hexdigest(),
    )
    with pytest.raises(HistoricalDatasetError, match="inconsistent scoring signatures"):
        build_historical_research_dataset((first, second), (*_sources(), *_sources(week=2)))


def test_coverage_reconciles_by_season_week_position_and_projection_level() -> None:
    records = (
        HistoricalResearchInputRecord(_record(1, 20.0, 18.0, position_id=1)),
        HistoricalResearchInputRecord(_record(2, 0.0, 0.0, position_id=2)),
        HistoricalResearchInputRecord(_record(3, None, 1.0, position_id=2)),
        HistoricalResearchInputRecord(_record(4, -1.0, -2.0, position_id=3)),
    )
    dataset = build_historical_research_dataset((_sample(*records),), _sources())
    by_key = {(item.dimension, item.key): item for item in dataset.coverage}
    assert by_key[("overall", "all")].row_count == 4
    assert by_key[("season", "2025")].row_count == 4
    assert by_key[("week", "2025:1")].paired_count == 3
    assert by_key[("position", "2")].row_count == 2
    assert by_key[("projection_level", "explicit_zero")].explicit_zero_count == 1
    assert by_key[("projection_level", "negative")].paired_count == 1
    assert sum(item.row_count for item in dataset.coverage if item.dimension == "position") == 4


def test_dataset_serialization_rejects_tampered_identity() -> None:
    dataset = build_historical_research_dataset(
        (_sample(HistoricalResearchInputRecord(_record(1, 2.0, 3.0))),),
        _sources(),
    )
    payload = historical_research_dataset_to_json(dataset)
    assert json.loads(payload)["dataset_sha256"] == dataset.dataset_sha256
    with pytest.raises(HistoricalDatasetError, match="identity is inconsistent"):
        historical_research_dataset_to_json(replace(dataset, dataset_sha256="0" * 64))
    with pytest.raises(HistoricalDatasetError, match="derived metadata is inconsistent"):
        historical_research_dataset_to_json(replace(dataset, coverage=()))


def test_selected_sample_order_and_source_role_order_do_not_change_dataset() -> None:
    first = _sample(HistoricalResearchInputRecord(_record(1, 2.0, 3.0)))
    second = _sample(
        HistoricalResearchInputRecord(_record(1, 4.0, 5.0, week=2)),
        week=2,
    )
    week_one_sources = _sources()
    sources = (
        replace(week_one_sources[0], roles=(SourceRole.ACTUAL, SourceRole.PROJECTION)),
        *week_one_sources[1:],
        *_sources(week=2),
    )
    left = build_historical_research_dataset((first, second), sources)
    reordered_sources = tuple(
        replace(source, roles=tuple(reversed(source.roles))) for source in reversed(sources)
    )
    right = build_historical_research_dataset((second, first), reordered_sources)
    assert historical_research_dataset_to_json(left) == historical_research_dataset_to_json(right)


def test_builder_is_credential_free_and_does_not_call_espn(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("M3.1 deterministic builder attempted network access")

    monkeypatch.setattr("fantasy_football.historical_projection_audit.League", forbidden)
    dataset = build_historical_research_dataset(
        (_sample(HistoricalResearchInputRecord(_record(1, 2.0, 3.0))),),
        _sources(),
    )
    assert len(dataset.rows) == 1


def test_malformed_source_enums_and_nonfinite_values_fail() -> None:
    projection, actual, scoring = _sources()
    sample = _sample(HistoricalResearchInputRecord(_record(1, 2.0, 3.0)))
    with pytest.raises(HistoricalDatasetError, match="kind is invalid"):
        build_historical_research_dataset((sample,), (replace(projection, kind="historical"), actual, scoring))
    with pytest.raises(HistoricalDatasetError, match="projection must be null or a finite number"):
        malformed = replace(_record(1, 2.0, 3.0), projection=float("nan"))
        build_historical_research_dataset((_sample(HistoricalResearchInputRecord(malformed)),), _sources())
