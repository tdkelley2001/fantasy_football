"""M5.2 optional deterministic V(R) screening over exhaustive trade candidates."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
import hashlib
import json
import math

from fantasy_football.canonical.model import LeagueSnapshot
from fantasy_football.evolving_state import (
    EvolvingLeagueState,
    state_to_json,
    validate_evolving_state,
)
from fantasy_football.roster_value import RosterValueResult, value_roster
from fantasy_football.trade_candidates import (
    SingleTradeCandidate,
    TradeCandidateEnumeration,
)


VALUATION_POLICY_ID = "m2.3c-unified-vr-v1"


class TradeScreeningError(ValueError):
    """Raised when screening inputs or a required V(R) result are unsupported."""


class ScreeningFailureReason(StrEnum):
    REQUESTER_DELTA_BELOW_MINIMUM = "requester_delta_below_minimum"
    COUNTERPARTY_DELTA_BELOW_MINIMUM = "counterparty_delta_below_minimum"


@dataclass(frozen=True, slots=True)
class TradeScreeningConfiguration:
    enabled: bool = False
    minimum_requester_delta: float | None = None
    minimum_counterparty_delta: float | None = None
    require_nonnegative_counterparty_delta: bool = False


@dataclass(frozen=True, slots=True)
class ParticipantRosterValueDiagnostic:
    team_id: int
    baseline: RosterValueResult
    completed_scenario: RosterValueResult
    delta: float


@dataclass(frozen=True, slots=True)
class TradeScreeningOutcome:
    candidate: SingleTradeCandidate
    requesting_team: ParticipantRosterValueDiagnostic
    counterparty: ParticipantRosterValueDiagnostic
    passes_screen: bool
    failure_reasons: tuple[ScreeningFailureReason, ...]
    screening_configuration_sha256: str
    valuation_policy_id: str
    assumptions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TradeScreeningCoverage:
    raw_combination_count: int
    structurally_feasible_count: int
    structurally_infeasible_count: int
    assessed_candidate_count: int
    retained_candidate_count: int
    excluded_candidate_count: int
    excluded_by_reason: tuple[tuple[ScreeningFailureReason, int], ...]
    reason_counts_overlap: bool
    complete: bool


@dataclass(frozen=True, slots=True)
class TradeScreeningResult:
    candidate_enumeration: TradeCandidateEnumeration
    configuration: TradeScreeningConfiguration
    screening_configuration_sha256: str
    baseline_state_sha256: str
    valuation_policy_id: str
    outcomes: tuple[TradeScreeningOutcome, ...]
    retained_candidate_ids: tuple[str, ...]
    coverage: TradeScreeningCoverage


def _fail(message: str) -> None:
    raise TradeScreeningError(message)


def _threshold(value: float | None, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(f"{label} must be a finite number or None")
    return float(value)


def _configuration_identity(
    configuration: TradeScreeningConfiguration,
) -> tuple[TradeScreeningConfiguration, str]:
    if not isinstance(configuration, TradeScreeningConfiguration):
        _fail("configuration must be TradeScreeningConfiguration")
    if not isinstance(configuration.enabled, bool):
        _fail("screening enabled must be Boolean")
    if not isinstance(configuration.require_nonnegative_counterparty_delta, bool):
        _fail("require_nonnegative_counterparty_delta must be Boolean")
    requester = _threshold(
        configuration.minimum_requester_delta, "minimum_requester_delta"
    )
    counterparty = _threshold(
        configuration.minimum_counterparty_delta, "minimum_counterparty_delta"
    )
    if configuration.require_nonnegative_counterparty_delta and counterparty is not None:
        _fail(
            "require_nonnegative_counterparty_delta conflicts with "
            "minimum_counterparty_delta"
        )
    if not configuration.enabled and (
        requester is not None
        or counterparty is not None
        or configuration.require_nonnegative_counterparty_delta
    ):
        _fail("screening thresholds require enabled=True")
    normalized = TradeScreeningConfiguration(
        configuration.enabled,
        requester,
        counterparty,
        configuration.require_nonnegative_counterparty_delta,
    )
    digest = hashlib.sha256(
        json.dumps(
            {
                "contract": "m5.2-trade-screening-configuration-v1",
                "valuation_policy_id": VALUATION_POLICY_ID,
                **asdict(normalized),
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return normalized, digest


def _require_complete_value(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    team_id: int,
    *,
    context: str,
) -> RosterValueResult:
    try:
        result = value_roster(snapshot, state, team_id)
    except ValueError as exc:
        raise TradeScreeningError(f"{context}: V(R) failed for team {team_id}: {exc}") from exc
    if not result.is_complete:
        _fail(
            f"{context}: V(R) is incomplete for team {team_id}: "
            f"{list(result.unresolved_inputs)}"
        )
    return result


def _validate_enumeration(
    snapshot: LeagueSnapshot,
    baseline_state: EvolvingLeagueState,
    enumeration: TradeCandidateEnumeration,
) -> str:
    validate_evolving_state(baseline_state, snapshot)
    if not isinstance(enumeration, TradeCandidateEnumeration):
        _fail("candidate_enumeration must be TradeCandidateEnumeration")
    baseline_sha256 = hashlib.sha256(
        state_to_json(baseline_state, snapshot).encode("utf-8")
    ).hexdigest()
    if enumeration.baseline_state_sha256 != baseline_sha256:
        _fail("candidate enumeration baseline state identity does not match supplied state")
    if not enumeration.coverage.complete:
        _fail("candidate enumeration coverage is incomplete")
    if enumeration.coverage.structurally_feasible_count != len(enumeration.candidates):
        _fail("candidate enumeration feasible count does not match candidate records")
    if enumeration.coverage.combination_count != (
        enumeration.coverage.structurally_feasible_count
        + enumeration.coverage.structurally_infeasible_count
    ):
        _fail("candidate enumeration raw coverage does not reconcile")
    seen: set[str] = set()
    for candidate in enumeration.candidates:
        if not isinstance(candidate, SingleTradeCandidate):
            _fail("candidate enumeration contains an invalid candidate record")
        if candidate.candidate_id in seen:
            _fail(f"candidate enumeration duplicates candidate {candidate.candidate_id}")
        seen.add(candidate.candidate_id)
        if (
            candidate.snapshot_id != snapshot.snapshot_id
            or candidate.source_schema_version != snapshot.schema_version
            or candidate.baseline_state_sha256 != baseline_sha256
            or candidate.search_configuration_sha256
            != enumeration.search_configuration_sha256
        ):
            _fail(f"candidate {candidate.candidate_id} identity does not match screening inputs")
        if not candidate.structural_feasible:
            _fail(f"candidate {candidate.candidate_id} is not structurally feasible")
        if (
            candidate.completed_scenario.snapshot_id != candidate.snapshot_id
            or candidate.completed_scenario.explicit_changes != candidate.explicit_changes
        ):
            _fail(
                f"candidate {candidate.candidate_id} completed scenario provenance is inconsistent"
            )
        validate_evolving_state(candidate.completed_scenario.state, snapshot)
    return baseline_sha256


def screen_trade_candidates(
    snapshot: LeagueSnapshot,
    baseline_state: EvolvingLeagueState,
    candidate_enumeration: TradeCandidateEnumeration,
    configuration: TradeScreeningConfiguration = TradeScreeningConfiguration(),
) -> TradeScreeningResult:
    """Compute exact two-sided V(R) diagnostics and apply optional thresholds."""

    normalized, configuration_sha256 = _configuration_identity(configuration)
    baseline_sha256 = _validate_enumeration(
        snapshot, baseline_state, candidate_enumeration
    )
    candidates = tuple(
        sorted(candidate_enumeration.candidates, key=lambda item: item.candidate_id)
    )
    normalized_enumeration = replace(candidate_enumeration, candidates=candidates)
    participant_ids = tuple(
        sorted(
            {
                team_id
                for candidate in candidates
                for team_id in (
                    candidate.requesting_team_id,
                    candidate.counterparty_team_id,
                )
            }
        )
    )
    baseline_values = {
        team_id: _require_complete_value(
            snapshot, baseline_state, team_id, context="baseline"
        )
        for team_id in participant_ids
    }
    outcomes = []
    reason_counts: Counter[ScreeningFailureReason] = Counter()
    for candidate in candidates:
        requester = candidate.requesting_team_id
        counterparty = candidate.counterparty_team_id
        completed = candidate.completed_scenario.state
        requester_after = _require_complete_value(
            snapshot,
            completed,
            requester,
            context=f"candidate {candidate.candidate_id}",
        )
        counterparty_after = _require_complete_value(
            snapshot,
            completed,
            counterparty,
            context=f"candidate {candidate.candidate_id}",
        )
        requester_diagnostic = ParticipantRosterValueDiagnostic(
            requester,
            baseline_values[requester],
            requester_after,
            requester_after.total_value - baseline_values[requester].total_value,
        )
        counterparty_diagnostic = ParticipantRosterValueDiagnostic(
            counterparty,
            baseline_values[counterparty],
            counterparty_after,
            counterparty_after.total_value - baseline_values[counterparty].total_value,
        )
        reasons = []
        if normalized.enabled:
            if (
                normalized.minimum_requester_delta is not None
                and requester_diagnostic.delta < normalized.minimum_requester_delta
            ):
                reasons.append(ScreeningFailureReason.REQUESTER_DELTA_BELOW_MINIMUM)
            counterparty_minimum = (
                0.0
                if normalized.require_nonnegative_counterparty_delta
                else normalized.minimum_counterparty_delta
            )
            if (
                counterparty_minimum is not None
                and counterparty_diagnostic.delta < counterparty_minimum
            ):
                reasons.append(ScreeningFailureReason.COUNTERPARTY_DELTA_BELOW_MINIMUM)
        for reason in reasons:
            reason_counts[reason] += 1
        outcomes.append(
            TradeScreeningOutcome(
                candidate,
                requester_diagnostic,
                counterparty_diagnostic,
                not reasons,
                tuple(reasons),
                configuration_sha256,
                VALUATION_POLICY_ID,
                (
                    "unified_m2.3c_remaining_season_value",
                    "completed_m4_shared_league_state",
                    "screen_is_not_acceptance_probability",
                    "screen_is_not_championship_probability",
                ),
            )
        )
    retained = tuple(
        item.candidate.candidate_id for item in outcomes if item.passes_screen
    )
    excluded_count = len(outcomes) - len(retained)
    coverage = TradeScreeningCoverage(
        candidate_enumeration.coverage.combination_count,
        candidate_enumeration.coverage.structurally_feasible_count,
        candidate_enumeration.coverage.structurally_infeasible_count,
        len(outcomes),
        len(retained),
        excluded_count,
        tuple(sorted(reason_counts.items(), key=lambda item: item[0].value)),
        sum(reason_counts.values()) > excluded_count,
        True,
    )
    return TradeScreeningResult(
        normalized_enumeration,
        normalized,
        configuration_sha256,
        baseline_sha256,
        VALUATION_POLICY_ID,
        tuple(outcomes),
        retained,
        coverage,
    )
