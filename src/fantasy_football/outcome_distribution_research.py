"""Deterministic M3.2 player-outcome distribution research.

This module evaluates already materialized M3.1 evidence.  It performs no ESPN
retrieval and does not alter the provisional M2.6 simulation model.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
from statistics import NormalDist, fmean, pstdev
from typing import Sequence

from fantasy_football.historical_dataset import (
    HistoricalResearchDataset,
    ProjectionTemporalProvenance,
    historical_research_dataset_to_json,
)


RESEARCH_SCHEMA_VERSION = 1
_NORMAL = NormalDist()


class OutcomeResearchError(ValueError):
    """Raised when an M3.2 research input or configuration is invalid."""


class EvidencePolicy(str, Enum):
    AUTHENTICATED_ONLY = "authenticated_only"
    INCLUDE_UNVERIFIED_EXPLORATORY = "include_unverified_exploratory"


class CandidateFamily(str, Enum):
    EMPIRICAL = "empirical_residual"
    NORMAL = "normal_residual"
    HYBRID = "hybrid_empirical_partial_pooling"


class Conditioning(str, Enum):
    POOLED = "pooled"
    POSITION = "position"
    PROJECTION = "projection"
    POSITION_PROJECTION = "position_projection"


@dataclass(frozen=True, slots=True)
class TemporalSplit:
    evaluation_start_season: int
    evaluation_start_week: int


@dataclass(frozen=True, slots=True)
class ResearchConfiguration:
    evidence_policy: EvidencePolicy
    temporal_split: TemporalSplit
    projection_bin_edges: tuple[float, ...]
    minimum_group_size: int
    minimum_training_rows: int
    minimum_evaluation_rows: int
    hybrid_shrinkage_strength: float
    density_bandwidth_floor: float
    normal_quadrature_points: int = 101


@dataclass(frozen=True, slots=True)
class CandidateSpecification:
    candidate_id: str
    family: CandidateFamily
    conditioning: Conditioning


@dataclass(frozen=True, slots=True)
class SampleCoverage:
    split: str
    evidence: str
    season: int | None
    week: int | None
    position_id: int | None
    projection_bin: str | None
    row_count: int
    zero_actual_count: int


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    candidate_id: str
    family: CandidateFamily
    conditioning: Conditioning
    evaluation_rows: int
    fallback_rows: int
    mean_crps: float
    mean_negative_log_score: float
    mean_error: float
    root_mean_squared_error: float
    relative_error_rows: int
    mean_relative_error: float | None
    zero_brier_score: float
    interval_50_coverage: float
    interval_50_mean_width: float
    interval_80_coverage: float
    interval_80_mean_width: float
    interval_90_coverage: float
    interval_90_mean_width: float
    lower_tail_10_rate: float
    upper_tail_90_rate: float
    pit_histogram_10: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class OutcomeDistributionResearchReport:
    schema_version: int
    report_sha256: str
    source_dataset_sha256: str | None
    configuration: ResearchConfiguration
    candidates: tuple[CandidateEvaluation, ...]
    coverage: tuple[SampleCoverage, ...]
    authenticated_rows: int
    unverified_exploratory_rows: int
    excluded_rows: int
    evidence_sufficient: bool
    exploratory_best_candidate_id: str | None
    recommended_candidate_id: str | None
    recommendation: str
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Observation:
    season: int
    week: int
    player_id: int
    position_id: int
    projection: float
    actual: float
    authenticated: bool


@dataclass(frozen=True, slots=True)
class _Forecast:
    atoms: tuple[tuple[float, float], ...]
    zero_probability: float
    bandwidth: float


DEFAULT_CANDIDATES = tuple(
    CandidateSpecification(f"{conditioning.value}_{family.value}", family, conditioning)
    for family in (CandidateFamily.EMPIRICAL, CandidateFamily.NORMAL)
    for conditioning in Conditioning
) + (
    CandidateSpecification(
        "position_projection_hybrid_empirical_partial_pooling",
        CandidateFamily.HYBRID,
        Conditioning.POSITION_PROJECTION,
    ),
)


def _fail(message: str) -> None:
    raise OutcomeResearchError(message)


def _validate_configuration(config: ResearchConfiguration) -> None:
    if not isinstance(config, ResearchConfiguration):
        _fail("configuration must be ResearchConfiguration")
    if not isinstance(config.evidence_policy, EvidencePolicy):
        _fail("evidence policy is invalid")
    split = config.temporal_split
    if (
        not isinstance(split, TemporalSplit)
        or isinstance(split.evaluation_start_season, bool)
        or not isinstance(split.evaluation_start_season, int)
        or split.evaluation_start_season < 2000
        or isinstance(split.evaluation_start_week, bool)
        or not isinstance(split.evaluation_start_week, int)
        or split.evaluation_start_week < 1
    ):
        _fail("temporal split must identify a valid season/week boundary")
    edges = config.projection_bin_edges
    if (
        not isinstance(edges, tuple)
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in edges)
        or tuple(sorted(set(float(value) for value in edges))) != tuple(float(value) for value in edges)
    ):
        _fail("projection bin edges must be a strictly increasing finite tuple")
    for field in ("minimum_group_size", "minimum_training_rows", "minimum_evaluation_rows"):
        value = getattr(config, field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            _fail(f"{field} must be a positive integer")
    if not math.isfinite(config.hybrid_shrinkage_strength) or config.hybrid_shrinkage_strength <= 0:
        _fail("hybrid_shrinkage_strength must be positive and finite")
    if not math.isfinite(config.density_bandwidth_floor) or config.density_bandwidth_floor <= 0:
        _fail("density_bandwidth_floor must be positive and finite")
    if config.normal_quadrature_points < 11 or config.normal_quadrature_points % 2 == 0:
        _fail("normal_quadrature_points must be an odd integer of at least 11")


def _bin(value: float, edges: tuple[float, ...]) -> str:
    lower = "-inf"
    for edge in edges:
        if value < edge:
            return f"[{lower},{edge:g})"
        lower = f"{edge:g}"
    return f"[{lower},inf)"


def _group_key(observation: _Observation, conditioning: Conditioning, edges: tuple[float, ...]) -> tuple[object, ...]:
    if conditioning is Conditioning.POOLED:
        return ("all",)
    if conditioning is Conditioning.POSITION:
        return (observation.position_id,)
    projection_bin = _bin(observation.projection, edges)
    if conditioning is Conditioning.PROJECTION:
        return (projection_bin,)
    return (observation.position_id, projection_bin)


def _observations(dataset: HistoricalResearchDataset) -> tuple[_Observation, ...]:
    result = []
    for row in dataset.rows:
        if row.raw_projection is None or row.actual_score is None or row.policy_imputed_projection is not None:
            continue
        authenticated = row.projection_temporal_provenance is ProjectionTemporalProvenance.AUTHENTICATED_PREGAME
        exploratory = row.projection_temporal_provenance is ProjectionTemporalProvenance.HISTORICAL_PREGAME_UNVERIFIED
        if not authenticated and not exploratory:
            continue
        result.append(_Observation(
            season=row.season,
            week=row.scoring_week,
            player_id=row.player_id,
            position_id=row.position_id,
            projection=float(row.raw_projection),
            actual=float(row.actual_score),
            authenticated=authenticated,
        ))
    return tuple(sorted(result, key=lambda item: (item.season, item.week, item.player_id)))


def _atoms_empirical(training: Sequence[_Observation], projection: float) -> tuple[tuple[float, float], ...]:
    count = len(training)
    return tuple(
        (0.0 if item.actual == 0 else projection + item.actual - item.projection, 1.0 / count)
        for item in training
    )


def _atoms_normal(training: Sequence[_Observation], projection: float, points: int) -> tuple[tuple[float, float], ...]:
    zeros = sum(item.actual == 0 for item in training)
    nonzero = [item.actual - item.projection for item in training if item.actual != 0]
    zero_probability = zeros / len(training)
    if not nonzero:
        return ((0.0, 1.0),)
    mean = fmean(nonzero)
    spread = pstdev(nonzero) if len(nonzero) > 1 else 0.0
    if spread == 0:
        nonzero_atoms = ((projection + mean, 1.0 - zero_probability),)
    else:
        weight = (1.0 - zero_probability) / points
        nonzero_atoms = tuple(
            (projection + mean + spread * _NORMAL.inv_cdf((index + 0.5) / points), weight)
            for index in range(points)
        )
    return (((0.0, zero_probability),) if zero_probability else ()) + nonzero_atoms


def _combine_atoms(*weighted: tuple[float, tuple[tuple[float, float], ...]]) -> tuple[tuple[float, float], ...]:
    values: Counter[float] = Counter()
    for mixture_weight, atoms in weighted:
        for value, weight in atoms:
            values[value] += mixture_weight * weight
    total = sum(values.values())
    return tuple((value, weight / total) for value, weight in sorted(values.items()))


def _forecast(
    candidate: CandidateSpecification,
    observation: _Observation,
    training: Sequence[_Observation],
    config: ResearchConfiguration,
) -> tuple[_Forecast, bool]:
    pooled = tuple(training)
    key = _group_key(observation, candidate.conditioning, config.projection_bin_edges)
    group = tuple(item for item in training if _group_key(item, candidate.conditioning, config.projection_bin_edges) == key)
    fallback = len(group) < config.minimum_group_size
    selected = pooled if fallback else group
    if candidate.family is CandidateFamily.EMPIRICAL:
        atoms = _atoms_empirical(selected, observation.projection)
    elif candidate.family is CandidateFamily.NORMAL:
        atoms = _atoms_normal(selected, observation.projection, config.normal_quadrature_points)
    else:
        local = group
        if not local:
            atoms = _atoms_empirical(pooled, observation.projection)
            fallback = True
        else:
            local_weight = len(local) / (len(local) + config.hybrid_shrinkage_strength)
            atoms = _combine_atoms(
                (local_weight, _atoms_empirical(local, observation.projection)),
                (1.0 - local_weight, _atoms_empirical(pooled, observation.projection)),
            )
    zero_probability = sum(weight for value, weight in atoms if value == 0)
    nonzero_values = [value for value, weight in atoms if value != 0 and weight > 0]
    bandwidth = max(config.density_bandwidth_floor, pstdev(nonzero_values) * (len(nonzero_values) ** -0.2) if len(nonzero_values) > 1 else 0.0)
    return _Forecast(atoms=atoms, zero_probability=zero_probability, bandwidth=bandwidth), fallback


def _quantile(forecast: _Forecast, probability: float) -> float:
    cumulative = 0.0
    for value, weight in sorted(forecast.atoms):
        cumulative += weight
        if cumulative >= probability:
            return value
    return forecast.atoms[-1][0]


def _mean(forecast: _Forecast) -> float:
    return math.fsum(value * weight for value, weight in forecast.atoms)


def _crps(forecast: _Forecast, actual: float) -> float:
    first = math.fsum(weight * abs(value - actual) for value, weight in forecast.atoms)
    cumulative_weight = 0.0
    cumulative_weighted_value = 0.0
    second_terms = []
    for value, weight in sorted(forecast.atoms):
        second_terms.append(weight * (value * cumulative_weight - cumulative_weighted_value))
        cumulative_weight += weight
        cumulative_weighted_value += weight * value
    second = math.fsum(second_terms)
    return first - second


def _negative_log_score(forecast: _Forecast, actual: float) -> float:
    if actual == 0 and forecast.zero_probability > 0:
        return -math.log(forecast.zero_probability)
    normalizer = forecast.bandwidth * math.sqrt(2 * math.pi)
    density = math.fsum(
        weight * math.exp(-0.5 * ((actual - value) / forecast.bandwidth) ** 2) / normalizer
        for value, weight in forecast.atoms
        if value != 0
    )
    return -math.log(max(density, 1e-300))


def _pit(forecast: _Forecast, actual: float) -> float:
    below = math.fsum(weight for value, weight in forecast.atoms if value < actual)
    equal = math.fsum(weight for value, weight in forecast.atoms if value == actual)
    return min(1.0, below + 0.5 * equal)


def _coverage(observations: Sequence[_Observation], split: str, edges: tuple[float, ...]) -> tuple[SampleCoverage, ...]:
    groups: Counter[tuple[str, int | None, int | None, int | None, str | None]] = Counter()
    zeros: Counter[tuple[str, int | None, int | None, int | None, str | None]] = Counter()
    for item in observations:
        evidence = "authenticated" if item.authenticated else "unverified_exploratory"
        keys = (
            (evidence, None, None, None, None),
            (evidence, item.season, item.week, None, None),
            (evidence, None, None, item.position_id, None),
            (evidence, None, None, None, _bin(item.projection, edges)),
        )
        for key in keys:
            groups[key] += 1
            zeros[key] += item.actual == 0
    return tuple(
        SampleCoverage(split, *key, count, zeros[key])
        for key, count in sorted(groups.items(), key=lambda pair: tuple("" if value is None else str(value) for value in pair[0]))
    )


def _evaluate_candidate(
    candidate: CandidateSpecification,
    training: Sequence[_Observation],
    evaluation: Sequence[_Observation],
    config: ResearchConfiguration,
) -> CandidateEvaluation:
    forecasts: list[_Forecast] = []
    fallbacks = 0
    for observation in evaluation:
        forecast, fallback = _forecast(candidate, observation, training, config)
        forecasts.append(forecast)
        fallbacks += fallback
    actuals = [item.actual for item in evaluation]
    means = [_mean(forecast) for forecast in forecasts]
    errors = [mean - actual for mean, actual in zip(means, actuals, strict=True)]
    relative_errors = [
        (mean - item.actual) / item.projection
        for mean, item in zip(means, evaluation, strict=True)
        if item.projection != 0
    ]
    pit_counts = [0] * 10
    for forecast, actual in zip(forecasts, actuals, strict=True):
        pit_counts[min(9, int(_pit(forecast, actual) * 10))] += 1
    intervals: dict[float, tuple[float, float]] = {}
    for level in (0.5, 0.8, 0.9):
        tail = (1 - level) / 2
        contained = []
        widths = []
        for forecast, actual in zip(forecasts, actuals, strict=True):
            lower, upper = _quantile(forecast, tail), _quantile(forecast, 1 - tail)
            contained.append(lower <= actual <= upper)
            widths.append(upper - lower)
        intervals[level] = (fmean(contained), fmean(widths))
    return CandidateEvaluation(
        candidate_id=candidate.candidate_id,
        family=candidate.family,
        conditioning=candidate.conditioning,
        evaluation_rows=len(evaluation),
        fallback_rows=fallbacks,
        mean_crps=fmean(_crps(forecast, actual) for forecast, actual in zip(forecasts, actuals, strict=True)),
        mean_negative_log_score=fmean(_negative_log_score(forecast, actual) for forecast, actual in zip(forecasts, actuals, strict=True)),
        mean_error=fmean(errors),
        root_mean_squared_error=math.sqrt(fmean(error * error for error in errors)),
        relative_error_rows=len(relative_errors),
        mean_relative_error=fmean(relative_errors) if relative_errors else None,
        zero_brier_score=fmean((forecast.zero_probability - (actual == 0)) ** 2 for forecast, actual in zip(forecasts, actuals, strict=True)),
        interval_50_coverage=intervals[0.5][0], interval_50_mean_width=intervals[0.5][1],
        interval_80_coverage=intervals[0.8][0], interval_80_mean_width=intervals[0.8][1],
        interval_90_coverage=intervals[0.9][0], interval_90_mean_width=intervals[0.9][1],
        lower_tail_10_rate=fmean(actual < _quantile(forecast, 0.1) for forecast, actual in zip(forecasts, actuals, strict=True)),
        upper_tail_90_rate=fmean(actual > _quantile(forecast, 0.9) for forecast, actual in zip(forecasts, actuals, strict=True)),
        pit_histogram_10=tuple(pit_counts),
    )


def research_outcome_distributions(
    dataset: HistoricalResearchDataset | None,
    configuration: ResearchConfiguration,
    candidates: Sequence[CandidateSpecification] = DEFAULT_CANDIDATES,
) -> OutcomeDistributionResearchReport:
    """Evaluate candidates on a strictly future season/week holdout."""

    _validate_configuration(configuration)
    if not candidates or len({item.candidate_id for item in candidates}) != len(candidates):
        _fail("candidate specifications must be nonempty with unique IDs")
    if any(
        not isinstance(item, CandidateSpecification)
        or not isinstance(item.family, CandidateFamily)
        or not isinstance(item.conditioning, Conditioning)
        or not isinstance(item.candidate_id, str)
        or not item.candidate_id
        for item in candidates
    ):
        _fail("candidate specification is invalid")
    if dataset is not None:
        historical_research_dataset_to_json(dataset)
    all_observations = _observations(dataset) if dataset is not None else ()
    authenticated = tuple(item for item in all_observations if item.authenticated)
    unverified = tuple(item for item in all_observations if not item.authenticated)
    included = authenticated if configuration.evidence_policy is EvidencePolicy.AUTHENTICATED_ONLY else all_observations
    boundary = (configuration.temporal_split.evaluation_start_season, configuration.temporal_split.evaluation_start_week)
    training = tuple(item for item in included if (item.season, item.week) < boundary)
    evaluation = tuple(item for item in included if (item.season, item.week) >= boundary)
    enough = len(training) >= configuration.minimum_training_rows and len(evaluation) >= configuration.minimum_evaluation_rows
    evaluations = tuple(
        sorted(
            (_evaluate_candidate(item, training, evaluation, configuration) for item in candidates),
            key=lambda item: item.candidate_id,
        )
    ) if enough else ()
    best = min(evaluations, key=lambda item: (item.mean_crps, item.mean_negative_log_score, item.candidate_id)).candidate_id if evaluations else None
    authenticated_basis = configuration.evidence_policy is EvidencePolicy.AUTHENTICATED_ONLY
    recommendation_id = best if enough and authenticated_basis else None
    if dataset is None:
        recommendation = "Insufficient evidence: no materialized M3.1 row-level dataset was supplied."
    elif not enough:
        recommendation = f"Insufficient evidence: temporal split produced {len(training)} training and {len(evaluation)} evaluation rows."
    elif not authenticated_basis:
        recommendation = f"Exploratory comparison only: {best} has the lowest held-out CRPS, but unverified historical projections cannot support calibrated-model promotion."
    else:
        recommendation = f"Research recommendation: {best} has the lowest temporally held-out CRPS; independent review is required before M3.3 promotion."
    coverage = _coverage(training, "training", configuration.projection_bin_edges) + _coverage(evaluation, "evaluation", configuration.projection_bin_edges)
    limitations = (
        "No random player-week split is used; the configured season/week boundary defines the holdout.",
        "Unverified historical ESPN projections support exploratory comparison only, not authenticated calibration.",
        "Forecast lead-time effects are not evaluated because M3.1 contains no authenticated lead-time vintages.",
        "Candidate zero mass and signed residual support are evaluated without clamping negative outcomes.",
        "M3.2 does not replace or configure the M2.6 outcome model.",
    )
    core = {
        "schema_version": RESEARCH_SCHEMA_VERSION,
        "source_dataset_sha256": dataset.dataset_sha256 if dataset else None,
        "configuration": configuration,
        "candidates": evaluations,
        "coverage": coverage,
        "authenticated_rows": len(authenticated),
        "unverified_exploratory_rows": len(unverified),
        "excluded_rows": (len(dataset.rows) - len(included)) if dataset else 0,
        "evidence_sufficient": enough and authenticated_basis,
        "exploratory_best_candidate_id": best,
        "recommended_candidate_id": recommendation_id,
        "recommendation": recommendation,
        "limitations": limitations,
    }
    digest = hashlib.sha256(_json_bytes(core)).hexdigest()
    return OutcomeDistributionResearchReport(report_sha256=digest, **core)


def outcome_distribution_report_to_json(report: OutcomeDistributionResearchReport) -> bytes:
    """Serialize a deterministic research report and verify its identity."""

    core = {key: value for key, value in asdict(report).items() if key != "report_sha256"}
    expected = hashlib.sha256(_json_bytes(core)).hexdigest()
    if report.schema_version != RESEARCH_SCHEMA_VERSION or report.report_sha256 != expected:
        _fail("outcome-distribution research report identity is inconsistent")
    return _json_bytes(report)


def _json_default(value):
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"unsupported research value {type(value).__name__}")


def _json_bytes(value) -> bytes:
    return json.dumps(value, default=_json_default, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
