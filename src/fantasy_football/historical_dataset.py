"""Deterministic M3.1 historical projection research dataset.

This module transforms already retrieved, validated historical observations. It
does not fetch ESPN data, mutate canonical snapshots, or apply projection policy.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
import hashlib
import json
import math
import re
from typing import Sequence

from fantasy_football.historical_projection_audit import (
    HistoricalPlayerWeek,
    HistoricalProjectionAuditError,
    parse_historical_player_page,
)


DATASET_SCHEMA_VERSION = 2
CAPTURE_MANIFEST_SCHEMA = "fantasy_football.pregame_capture.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LIMITATIONS = (
    "Historical ESPN response projections retain unverified pregame provenance.",
    "Policy-imputed zeros are not ESPN forecasts and are ineligible for projection-error calibration.",
    "Position and pro-team wrapper fields lack authenticated point-in-time provenance.",
    "The dataset does not fit, select, or promote an outcome distribution.",
)


class HistoricalDatasetError(ValueError):
    """Raised when research evidence is incomplete or contradictory."""


class EvidenceClassification(str, Enum):
    VERIFIED_LIVE = "verified_live"
    VERIFIED_BY_TESTS = "verified_by_tests"
    UNVERIFIED = "unverified"
    UNSUPPORTED = "unsupported"


class SourceKind(str, Enum):
    ESPN_HISTORICAL_RESPONSE = "espn_historical_current_response"
    IMMUTABLE_PREGAME_CAPTURE = "immutable_pregame_capture"
    SANITIZED_FIXTURE = "sanitized_fixture"


class SourceRole(str, Enum):
    PROJECTION = "projection"
    ACTUAL = "actual"
    SCORING = "scoring"


class ProjectionTemporalProvenance(str, Enum):
    AUTHENTICATED_PREGAME = "authenticated_pregame"
    HISTORICAL_PREGAME_UNVERIFIED = "historical_projection_pregame_provenance_unverified"
    NOT_APPLICABLE = "not_applicable"


class ProjectionValueKind(str, Enum):
    ESPN_VALUE = "espn_value"
    ESPN_EXPLICIT_ZERO = "espn_explicit_zero"
    MISSING = "missing"
    MODEL_POLICY_IMPUTED_ZERO = "model_policy_imputed_zero"


@dataclass(frozen=True, slots=True)
class HistoricalResearchSource:
    source_id: str
    kind: SourceKind
    roles: tuple[SourceRole, ...]
    endpoint: str
    view: str
    parameters_json: str
    retrieved_at_utc: datetime
    payload_sha256: str
    target_season: int
    target_week: int
    evidence_classification: EvidenceClassification
    verification_reference: str | None = None


@dataclass(frozen=True, slots=True, init=False)
class ValidatedPregameCapture:
    """A capture whose manifest and payload were checked at the trust boundary."""

    source_id: str
    target_season: int
    target_week: int
    captured_at_utc: datetime
    observation_period_start_utc: datetime
    payload_sha256: str
    manifest_sha256: str
    endpoint: str
    view: str
    parameters_json: str
    verification_authority: str
    verification_reference: str
    projection_records: tuple[HistoricalPlayerWeek, ...]
    _validation_token: object


@dataclass(frozen=True, slots=True)
class HistoricalResearchInputRecord:
    player_week: HistoricalPlayerWeek
    policy_imputed_projection: float | None = None


@dataclass(frozen=True, slots=True)
class HistoricalResearchSample:
    season: int
    week: int
    observation_period_start_utc: datetime
    observation_period_end_utc: datetime
    projection_source_id: str
    actual_source_id: str
    scoring_source_id: str
    scoring_signature: str
    records: tuple[HistoricalResearchInputRecord, ...]


@dataclass(frozen=True, slots=True)
class HistoricalResearchRow:
    player_id: int
    season: int
    scoring_week: int
    position_id: int
    pro_team_id: int
    raw_projection: float | None
    policy_imputed_projection: float | None
    actual_score: float | None
    actual_stat_breakdown_present: bool
    raw_as_of_metadata_present: bool
    projection_value_kind: ProjectionValueKind
    projection_temporal_provenance: ProjectionTemporalProvenance
    projection_source_id: str
    actual_source_id: str
    scoring_source_id: str
    observation_period_start_utc: datetime
    observation_period_end_utc: datetime
    scoring_signature: str
    eligible_authenticated_pair: bool
    eligible_unverified_exploratory_pair: bool


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    dimension: str
    key: str
    row_count: int
    raw_projection_count: int
    actual_count: int
    paired_count: int
    authenticated_pair_count: int
    unverified_exploratory_pair_count: int
    missing_projection_count: int
    explicit_zero_count: int
    policy_imputed_zero_count: int


@dataclass(frozen=True, slots=True)
class HistoricalResearchDataset:
    schema_version: int
    dataset_sha256: str
    selected_samples: tuple[tuple[int, int], ...]
    scoring_signature: str
    sources: tuple[HistoricalResearchSource, ...]
    validated_pregame_captures: tuple[ValidatedPregameCapture, ...]
    rows: tuple[HistoricalResearchRow, ...]
    coverage: tuple[CoverageSummary, ...]
    limitations: tuple[str, ...]


def _fail(message: str) -> None:
    raise HistoricalDatasetError(message)


def _aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        _fail(f"{field} must be a timezone-aware datetime")


def _finite(value: float | None, field: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value))):
        _fail(f"{field} must be null or a finite number")


def _validate_source(source: HistoricalResearchSource) -> None:
    if not isinstance(source, HistoricalResearchSource):
        _fail(f"source must be HistoricalResearchSource; observed {type(source).__name__}")
    if not isinstance(source.source_id, str) or not source.source_id.strip():
        _fail("source_id must be nonempty")
    if not isinstance(source.kind, SourceKind):
        _fail(f"source {source.source_id!r} kind is invalid")
    if not isinstance(source.evidence_classification, EvidenceClassification):
        _fail(f"source {source.source_id!r} evidence classification is invalid")
    if not isinstance(source.endpoint, str) or not source.endpoint.strip() or not isinstance(source.view, str) or not source.view.strip():
        _fail(f"source {source.source_id!r} endpoint and view must be nonempty")
    if (
        isinstance(source.target_season, bool)
        or not isinstance(source.target_season, int)
        or source.target_season < 2000
        or isinstance(source.target_week, bool)
        or not isinstance(source.target_week, int)
        or source.target_week < 1
    ):
        _fail(f"source {source.source_id!r} has invalid target season/week")
    if not isinstance(source.roles, tuple) or not source.roles or any(not isinstance(role, SourceRole) for role in source.roles) or len(source.roles) != len(set(source.roles)):
        _fail(f"source {source.source_id!r} roles must be nonempty and unique")
    if not isinstance(source.parameters_json, str):
        _fail(f"source {source.source_id!r} parameters_json must be a canonical JSON object")
    try:
        parameters = json.loads(
            source.parameters_json,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        _fail(f"source {source.source_id!r} parameters_json is invalid: {exc}")
    if not isinstance(parameters, dict) or json.dumps(parameters, sort_keys=True, separators=(",", ":")) != source.parameters_json:
        _fail(f"source {source.source_id!r} parameters_json must be a canonical JSON object")
    _aware(source.retrieved_at_utc, f"source {source.source_id!r} retrieved_at_utc")
    if not isinstance(source.payload_sha256, str) or not _SHA256.fullmatch(source.payload_sha256):
        _fail(f"source {source.source_id!r} payload_sha256 must be lowercase SHA-256")
    if source.evidence_classification is EvidenceClassification.VERIFIED_LIVE and source.kind is SourceKind.SANITIZED_FIXTURE:
        _fail(f"source {source.source_id!r} sanitized fixture cannot claim verified_live evidence")


_CAPTURE_VALIDATION_TOKEN = object()
_CAPTURE_MANIFEST_FIELDS = {
    "schema", "source_id", "target_season", "target_week", "captured_at_utc",
    "observation_period_start_utc", "payload_sha256", "endpoint", "view",
    "parameters_json", "verification_authority", "verification_reference",
}


def validate_pregame_capture_manifest(
    manifest_bytes: bytes,
    payload_bytes: bytes,
    *,
    independently_trusted_manifest_sha256: str,
) -> ValidatedPregameCapture:
    """Bind exact capture bytes to an independently provisioned manifest ID.

    The expected digest is the external trust anchor. Calculating it from
    untrusted manifest bytes and passing it back does not establish independent
    authenticity.
    """

    if not isinstance(manifest_bytes, bytes) or not isinstance(payload_bytes, bytes):
        _fail("capture manifest and payload must be bytes")
    if not isinstance(independently_trusted_manifest_sha256, str) or not _SHA256.fullmatch(independently_trusted_manifest_sha256):
        _fail("independently trusted manifest identity must be lowercase SHA-256")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != independently_trusted_manifest_sha256:
        _fail("capture manifest does not match the independently trusted manifest identity")
    try:
        manifest = json.loads(manifest_bytes, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _fail(f"capture manifest is invalid JSON: {exc}")
    if not isinstance(manifest, dict) or set(manifest) != _CAPTURE_MANIFEST_FIELDS:
        _fail("capture manifest fields do not match the v1 contract")
    if _json_bytes(manifest) != manifest_bytes:
        _fail("capture manifest must use canonical JSON encoding")
    if manifest["schema"] != CAPTURE_MANIFEST_SCHEMA:
        _fail(f"unsupported capture manifest schema {manifest['schema']!r}")
    for field in ("source_id", "endpoint", "view", "verification_authority", "verification_reference"):
        if not isinstance(manifest[field], str) or not manifest[field].strip():
            _fail(f"capture manifest {field} must be nonempty")
    if not isinstance(manifest["parameters_json"], str):
        _fail("capture manifest parameters_json must be canonical JSON")
    try:
        parameters = json.loads(manifest["parameters_json"])
    except json.JSONDecodeError as exc:
        _fail(f"capture manifest parameters_json is invalid: {exc}")
    if not isinstance(parameters, dict) or json.dumps(parameters, sort_keys=True, separators=(",", ":")) != manifest["parameters_json"]:
        _fail("capture manifest parameters_json must be a canonical JSON object")
    season, week = manifest["target_season"], manifest["target_week"]
    if isinstance(season, bool) or not isinstance(season, int) or season < 2000 or isinstance(week, bool) or not isinstance(week, int) or week < 1:
        _fail("capture manifest has invalid target season/week")
    try:
        captured_at = datetime.fromisoformat(manifest["captured_at_utc"])
        period_start = datetime.fromisoformat(manifest["observation_period_start_utc"])
    except (TypeError, ValueError) as exc:
        _fail(f"capture manifest has invalid timing: {exc}")
    _aware(captured_at, "capture manifest captured_at_utc")
    _aware(period_start, "capture manifest observation_period_start_utc")
    if captured_at >= period_start:
        _fail("capture manifest does not establish completion before the observation period")
    payload_sha256 = manifest["payload_sha256"]
    if not isinstance(payload_sha256, str) or not _SHA256.fullmatch(payload_sha256):
        _fail("capture manifest payload_sha256 must be lowercase SHA-256")
    if hashlib.sha256(payload_bytes).hexdigest() != payload_sha256:
        _fail("captured payload does not match the manifest payload identity")
    try:
        payload = json.loads(payload_bytes, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        _fail(f"captured payload is invalid JSON: {exc}")
    if not isinstance(payload, dict):
        _fail("captured payload must be an ESPN historical response object")
    try:
        projection_records = parse_historical_player_page(payload, season=season, week=week)
    except HistoricalProjectionAuditError as exc:
        _fail(f"captured payload cannot establish player-week projections: {exc}")
    if not projection_records:
        _fail("captured payload cannot establish an empty player-week universe")
    capture = object.__new__(ValidatedPregameCapture)
    values = {
        "source_id": manifest["source_id"], "target_season": season, "target_week": week,
        "captured_at_utc": captured_at, "observation_period_start_utc": period_start,
        "payload_sha256": payload_sha256, "manifest_sha256": manifest_sha256,
        "endpoint": manifest["endpoint"], "view": manifest["view"],
        "parameters_json": manifest["parameters_json"],
        "verification_authority": manifest["verification_authority"],
        "verification_reference": manifest["verification_reference"],
        "projection_records": projection_records,
        "_validation_token": _CAPTURE_VALIDATION_TOKEN,
    }
    for field, value in values.items():
        object.__setattr__(capture, field, value)
    return capture


def _projection_level(row: HistoricalResearchRow) -> str:
    if row.projection_value_kind is ProjectionValueKind.MODEL_POLICY_IMPUTED_ZERO:
        return "model_policy_imputed_zero"
    value = row.raw_projection
    if value is None:
        return "missing"
    if value == 0:
        return "explicit_zero"
    if value < 0:
        return "negative"
    if value < 5:
        return "low_positive_lt_5"
    if value < 15:
        return "medium_5_to_lt_15"
    return "high_ge_15"


def _summarize(dimension: str, key: str, rows: Sequence[HistoricalResearchRow]) -> CoverageSummary:
    kinds = Counter(row.projection_value_kind for row in rows)
    return CoverageSummary(
        dimension=dimension,
        key=key,
        row_count=len(rows),
        raw_projection_count=sum(row.raw_projection is not None for row in rows),
        actual_count=sum(row.actual_score is not None for row in rows),
        paired_count=sum(row.raw_projection is not None and row.actual_score is not None for row in rows),
        authenticated_pair_count=sum(row.eligible_authenticated_pair for row in rows),
        unverified_exploratory_pair_count=sum(row.eligible_unverified_exploratory_pair for row in rows),
        missing_projection_count=sum(row.raw_projection is None for row in rows),
        explicit_zero_count=kinds[ProjectionValueKind.ESPN_EXPLICIT_ZERO],
        policy_imputed_zero_count=kinds[ProjectionValueKind.MODEL_POLICY_IMPUTED_ZERO],
    )


def _coverage(rows: tuple[HistoricalResearchRow, ...]) -> tuple[CoverageSummary, ...]:
    groups: dict[tuple[str, str], list[HistoricalResearchRow]] = {("overall", "all"): list(rows)}
    for row in rows:
        keys = (
            ("season", str(row.season)),
            ("week", f"{row.season}:{row.scoring_week}"),
            ("position", str(row.position_id)),
            ("projection_level", _projection_level(row)),
        )
        for key in keys:
            groups.setdefault(key, []).append(row)
    return tuple(_summarize(dimension, key, grouped) for (dimension, key), grouped in sorted(groups.items()))


def _temporal_provenance(capture: ValidatedPregameCapture | None) -> ProjectionTemporalProvenance:
    if capture is not None:
        return ProjectionTemporalProvenance.AUTHENTICATED_PREGAME
    return ProjectionTemporalProvenance.HISTORICAL_PREGAME_UNVERIFIED


def build_historical_research_dataset(
    samples: Sequence[HistoricalResearchSample],
    sources: Sequence[HistoricalResearchSource],
    validated_pregame_captures: Sequence[ValidatedPregameCapture] = (),
) -> HistoricalResearchDataset:
    """Build a deterministic research dataset from explicitly selected samples."""

    if not samples:
        _fail("historical research samples must be nonempty")
    source_by_id: dict[str, HistoricalResearchSource] = {}
    for source in sources:
        _validate_source(source)
        source = replace(source, roles=tuple(sorted(source.roles, key=lambda item: item.value)))
        if source.source_id in source_by_id:
            _fail(f"duplicate source_id={source.source_id!r}")
        source_by_id[source.source_id] = source

    capture_by_source: dict[str, ValidatedPregameCapture] = {}
    for capture in validated_pregame_captures:
        if not isinstance(capture, ValidatedPregameCapture) or capture._validation_token is not _CAPTURE_VALIDATION_TOKEN:
            _fail("pregame capture authorization must be produced by validate_pregame_capture_manifest()")
        if capture.source_id in capture_by_source:
            _fail(f"duplicate validated pregame capture for source_id={capture.source_id!r}")
        source = source_by_id.get(capture.source_id)
        if source is None:
            _fail(f"validated pregame capture references unknown source {capture.source_id!r}")
        if source.kind is not SourceKind.IMMUTABLE_PREGAME_CAPTURE:
            _fail(f"validated pregame capture source {capture.source_id!r} is not an immutable capture")
        expected = (source.target_season, source.target_week, source.retrieved_at_utc, source.payload_sha256, source.endpoint, source.view, source.parameters_json)
        observed = (capture.target_season, capture.target_week, capture.captured_at_utc, capture.payload_sha256, capture.endpoint, capture.view, capture.parameters_json)
        if observed != expected:
            _fail(f"validated pregame capture contradicts source metadata for source_id={capture.source_id!r}")
        capture_by_source[capture.source_id] = capture

    selected: set[tuple[int, int]] = set()
    seen_rows: set[tuple[int, int, int]] = set()
    signatures: set[str] = set()
    rows: list[HistoricalResearchRow] = []
    for sample in samples:
        if not isinstance(sample, HistoricalResearchSample):
            _fail(f"sample must be HistoricalResearchSample; observed {type(sample).__name__}")
        sample_key = (sample.season, sample.week)
        if (
            isinstance(sample.season, bool)
            or not isinstance(sample.season, int)
            or sample.season < 2000
            or isinstance(sample.week, bool)
            or not isinstance(sample.week, int)
            or sample.week < 1
        ):
            _fail(f"sample has invalid season/week {sample_key}")
        if sample_key in selected:
            _fail(f"duplicate selected sample season={sample.season}, week={sample.week}")
        selected.add(sample_key)
        _aware(sample.observation_period_start_utc, f"sample {sample_key} observation_period_start_utc")
        _aware(sample.observation_period_end_utc, f"sample {sample_key} observation_period_end_utc")
        if sample.observation_period_start_utc >= sample.observation_period_end_utc:
            _fail(f"sample {sample_key} observation period must have positive duration")
        if not isinstance(sample.scoring_signature, str) or not _SHA256.fullmatch(sample.scoring_signature):
            _fail(f"sample {sample_key} scoring_signature must be lowercase SHA-256")
        signatures.add(sample.scoring_signature)
        referenced = {
            "projection": (sample.projection_source_id, SourceRole.PROJECTION),
            "actual": (sample.actual_source_id, SourceRole.ACTUAL),
            "scoring": (sample.scoring_source_id, SourceRole.SCORING),
        }
        for label, (source_id, role) in referenced.items():
            if not isinstance(source_id, str) or not source_id:
                _fail(f"sample {sample_key} has invalid {label} source ID")
            source = source_by_id.get(source_id)
            if source is None:
                _fail(f"sample {sample_key} references unknown {label} source {source_id!r}")
            if role not in source.roles:
                _fail(f"sample {sample_key} source {source_id!r} lacks {role.value} role")
            if (source.target_season, source.target_week) != sample_key:
                _fail(f"sample {sample_key} source {source_id!r} targets season={source.target_season}, week={source.target_week}")
        projection_source = source_by_id[sample.projection_source_id]
        actual_source = source_by_id[sample.actual_source_id]
        if actual_source.retrieved_at_utc < sample.observation_period_end_utc:
            _fail(f"sample {sample_key} actual source was retrieved before the observation period ended")
        capture = capture_by_source.get(projection_source.source_id)
        if capture is not None and capture.observation_period_start_utc != sample.observation_period_start_utc:
            _fail(f"validated pregame capture has the wrong observation boundary for sample {sample_key}")
        temporal = _temporal_provenance(capture)
        captured_record_by_player = (
            {record.player_id: record for record in capture.projection_records}
            if capture is not None else {}
        )
        if not sample.records:
            _fail(f"sample {sample_key} records must be nonempty")
        if not isinstance(sample.records, tuple):
            _fail(f"sample {sample_key} records must be an immutable tuple")
        for item in sample.records:
            if not isinstance(item, HistoricalResearchInputRecord) or not isinstance(item.player_week, HistoricalPlayerWeek):
                _fail(f"sample {sample_key} contains an invalid research input record")
            record = item.player_week
            row_key = (record.player_id, record.season, record.week)
            if (
                isinstance(record.player_id, bool)
                or not isinstance(record.player_id, int)
                or record.player_id == 0
                or isinstance(record.position_id, bool)
                or not isinstance(record.position_id, int)
                or record.position_id < 1
                or isinstance(record.pro_team_id, bool)
                or not isinstance(record.pro_team_id, int)
                or record.pro_team_id < 0
            ):
                _fail(f"player-week {row_key} has invalid player/position/pro-team identity")
            if not isinstance(record.actual_stat_breakdown_present, bool) or not isinstance(record.as_of_metadata_present, bool):
                _fail(f"player-week {row_key} evidence flags must be Boolean")
            if (record.season, record.week) != sample_key:
                _fail(f"player-week {row_key} does not match sample season={sample.season}, week={sample.week}")
            if row_key in seen_rows:
                _fail(f"duplicate player-week {row_key}")
            seen_rows.add(row_key)
            _finite(record.projection, f"player-week {row_key} projection")
            _finite(record.actual, f"player-week {row_key} actual")
            _finite(item.policy_imputed_projection, f"player-week {row_key} policy_imputed_projection")
            if capture is not None:
                captured = captured_record_by_player.get(record.player_id)
                if captured is None:
                    _fail(f"authenticated capture does not contain player-week {row_key}")
                if (
                    captured.season,
                    captured.week,
                    captured.position_id,
                    captured.pro_team_id,
                    captured.projection,
                ) != (
                    record.season,
                    record.week,
                    record.position_id,
                    record.pro_team_id,
                    record.projection,
                ):
                    _fail(f"player-week {row_key} contradicts the authenticated capture projection evidence")
            if record.projection_status != ("missing" if record.projection is None else "explicit_zero" if record.projection == 0 else "negative" if record.projection < 0 else "positive"):
                _fail(f"player-week {row_key} projection status contradicts raw projection")
            if record.actual_status != ("missing" if record.actual is None else "explicit_zero" if record.actual == 0 else "negative" if record.actual < 0 else "positive"):
                _fail(f"player-week {row_key} actual status contradicts raw actual")
            if record.projection is not None and record.provenance_class != temporal.value:
                _fail(
                    f"player-week {row_key} provenance {record.provenance_class!r} "
                    f"contradicts source determination {temporal.value!r}"
                )
            if item.policy_imputed_projection is not None:
                if record.projection is not None or item.policy_imputed_projection != 0:
                    _fail(f"player-week {row_key} policy imputation must be zero and requires a missing raw projection")
                kind = ProjectionValueKind.MODEL_POLICY_IMPUTED_ZERO
                row_temporal = ProjectionTemporalProvenance.NOT_APPLICABLE
            elif record.projection is None:
                kind = ProjectionValueKind.MISSING
                row_temporal = ProjectionTemporalProvenance.NOT_APPLICABLE
            elif record.projection == 0:
                kind = ProjectionValueKind.ESPN_EXPLICIT_ZERO
                row_temporal = temporal
            else:
                kind = ProjectionValueKind.ESPN_VALUE
                row_temporal = temporal
            authenticated = record.projection is not None and record.actual is not None and row_temporal is ProjectionTemporalProvenance.AUTHENTICATED_PREGAME
            exploratory = record.projection is not None and record.actual is not None and row_temporal is ProjectionTemporalProvenance.HISTORICAL_PREGAME_UNVERIFIED
            rows.append(HistoricalResearchRow(
                player_id=record.player_id,
                season=record.season,
                scoring_week=record.week,
                position_id=record.position_id,
                pro_team_id=record.pro_team_id,
                raw_projection=record.projection,
                policy_imputed_projection=item.policy_imputed_projection,
                actual_score=record.actual,
                actual_stat_breakdown_present=record.actual_stat_breakdown_present,
                raw_as_of_metadata_present=record.as_of_metadata_present,
                projection_value_kind=kind,
                projection_temporal_provenance=row_temporal,
                projection_source_id=sample.projection_source_id,
                actual_source_id=sample.actual_source_id,
                scoring_source_id=sample.scoring_source_id,
                observation_period_start_utc=sample.observation_period_start_utc,
                observation_period_end_utc=sample.observation_period_end_utc,
                scoring_signature=sample.scoring_signature,
                eligible_authenticated_pair=authenticated,
                eligible_unverified_exploratory_pair=exploratory,
            ))
    if len(signatures) != 1:
        _fail(f"selected samples have inconsistent scoring signatures: {sorted(signatures)}")
    ordered_sources = tuple(sorted(source_by_id.values(), key=lambda item: item.source_id))
    ordered_captures = tuple(sorted(capture_by_source.values(), key=lambda item: item.source_id))
    ordered_rows = tuple(sorted(rows, key=lambda item: (item.season, item.scoring_week, item.player_id)))
    selected_samples = tuple(sorted(selected))
    core = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "selected_samples": selected_samples,
        "scoring_signature": next(iter(signatures)),
        "sources": ordered_sources,
        "validated_pregame_captures": ordered_captures,
        "rows": ordered_rows,
    }
    digest = hashlib.sha256(_json_bytes(core)).hexdigest()
    return HistoricalResearchDataset(
        schema_version=DATASET_SCHEMA_VERSION,
        dataset_sha256=digest,
        selected_samples=selected_samples,
        scoring_signature=next(iter(signatures)),
        sources=ordered_sources,
        validated_pregame_captures=ordered_captures,
        rows=ordered_rows,
        coverage=_coverage(ordered_rows),
        limitations=_LIMITATIONS,
    )


def _json_default(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, ValidatedPregameCapture):
        return {field: getattr(value, field) for field in value.__dataclass_fields__ if field != "_validation_token"}
    if hasattr(value, "__dataclass_fields__"):
        return {field: getattr(value, field) for field in value.__dataclass_fields__}
    raise TypeError(f"unsupported research dataset value {type(value).__name__}")


def _json_bytes(value) -> bytes:
    return json.dumps(value, default=_json_default, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def historical_research_dataset_to_json(dataset: HistoricalResearchDataset) -> bytes:
    """Return deterministic UTF-8 JSON; this is research output, not snapshot state."""

    if dataset.coverage != _coverage(dataset.rows) or dataset.limitations != _LIMITATIONS:
        _fail("historical research dataset derived metadata is inconsistent")
    expected = hashlib.sha256(_json_bytes({
        "schema_version": dataset.schema_version,
        "selected_samples": dataset.selected_samples,
        "scoring_signature": dataset.scoring_signature,
        "sources": dataset.sources,
        "validated_pregame_captures": dataset.validated_pregame_captures,
        "rows": dataset.rows,
    })).hexdigest()
    if dataset.schema_version != DATASET_SCHEMA_VERSION or dataset.dataset_sha256 != expected:
        _fail("historical research dataset identity is inconsistent")
    return _json_bytes(dataset)
