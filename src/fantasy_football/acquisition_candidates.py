"""M5.5 exhaustive standalone immediate acquisition candidate reference."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from typing import Iterator

from fantasy_football.canonical.model import LeagueSnapshot, SlotKind
from fantasy_football.canonical.validation import validate_snapshot
from fantasy_football.evolving_state import (
    AcquisitionAvailability,
    EvolvingLeagueState,
    TransactionPhase,
    TransactionStateError,
    add_player,
    apply_successful_waiver_priority,
    replace_player,
    state_to_json,
    validate_evolving_state,
)
from fantasy_football.weekly_transactions import (
    WaiverBoundaryPolicy,
    WeeklyTransactionError,
    require_supported_transaction_rules,
)


class AcquisitionCandidateError(ValueError):
    """Raised when an immediate-acquisition search contract is invalid."""


class AcquisitionCategory(StrEnum):
    FREE_AGENT = "free_agent"
    WAIVER_CLAIM = "waiver_claim"
    HELD = "held"
    UNRESOLVED = "unresolved"
    ROSTERED = "rostered"


class AcquisitionDisposition(StrEnum):
    AUTHORIZED_IMMEDIATE = "authorized_immediate"
    CONDITIONAL_WAIVER = "conditional_waiver"
    UNRESOLVED = "unresolved"
    PROHIBITED = "prohibited"
    STRUCTURALLY_INFEASIBLE = "structurally_infeasible"


@dataclass(frozen=True, slots=True)
class ImmediateAcquisitionSearchConfiguration:
    requesting_team_id: int
    acquisition_player_ids: tuple[int, ...]
    eligible_drop_player_ids: tuple[int, ...] | None = None
    include_add_only: bool = True
    include_drop_and_add: bool = True
    acquisition_status_filter: tuple[AcquisitionAvailability, ...] | None = None
    waiver_boundary: WaiverBoundaryPolicy = WaiverBoundaryPolicy.UNRESOLVED


@dataclass(frozen=True, slots=True)
class WaiverPriorityDiagnostic:
    requesting_team_position: int
    higher_priority_team_ids: tuple[int, ...]
    priority_before: tuple[int, ...]
    priority_after_if_successful: tuple[int, ...] | None
    competitive_claim_behavior_resolved: bool


@dataclass(frozen=True, slots=True)
class ImmediateAcquisitionCandidate:
    candidate_id: str
    snapshot_id: str
    source_schema_version: int
    baseline_state_sha256: str
    search_configuration_sha256: str
    requesting_team_id: int
    acquired_player_id: int
    dropped_player_id: int | None
    destination_slot_id: int
    availability: AcquisitionAvailability
    category: AcquisitionCategory
    disposition: AcquisitionDisposition
    structurally_feasible: bool
    waiver_priority: WaiverPriorityDiagnostic
    required_assumptions: tuple[str, ...]
    unresolved_evidence: tuple[str, ...]
    execution_caveats: tuple[str, ...]
    rejection_reason: str | None
    resulting_state: EvolvingLeagueState | None


@dataclass(frozen=True, slots=True)
class ImmediateAcquisitionCoverage:
    declared_acquisition_player_count: int
    eligible_acquisition_player_count: int
    declared_drop_player_count: int
    raw_combination_count: int
    structurally_feasible_count: int
    structurally_infeasible_count: int
    authorized_immediate_count: int
    conditional_waiver_count: int
    unresolved_count: int
    prohibited_count: int
    disposition_counts: tuple[tuple[str, int], ...]
    rejection_reason_counts: tuple[tuple[str, int], ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class ImmediateAcquisitionEnumeration:
    search_configuration_sha256: str
    baseline_state_sha256: str
    candidates: tuple[ImmediateAcquisitionCandidate, ...]
    coverage: ImmediateAcquisitionCoverage


@dataclass(frozen=True, slots=True)
class _ValidatedSearch:
    configuration_sha256: str
    baseline_state_sha256: str
    team_id: int
    declared_acquisition_ids: tuple[int, ...]
    acquisition_ids: tuple[int, ...]
    drop_ids: tuple[int, ...]
    destinations: tuple[tuple[int, tuple[int, ...]], ...]
    include_add_only: bool
    include_drop_and_add: bool
    waiver_boundary: WaiverBoundaryPolicy


def _fail(message: str) -> None:
    raise AcquisitionCandidateError(message)


def _ids(values: tuple[int, ...], label: str, *, allow_empty: bool) -> tuple[int, ...]:
    if not isinstance(values, tuple):
        _fail(f"{label} must be a tuple")
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item == 0
        for item in values
    ):
        _fail(f"{label} must contain nonzero integer player IDs")
    if len(values) != len(set(values)):
        _fail(f"{label} contains duplicate player IDs")
    if not allow_empty and not values:
        _fail(f"{label} must be nonempty")
    return tuple(sorted(values))


def _validate_search(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    configuration: ImmediateAcquisitionSearchConfiguration,
) -> _ValidatedSearch:
    validate_snapshot(snapshot)
    validate_evolving_state(state, snapshot)
    if not isinstance(configuration, ImmediateAcquisitionSearchConfiguration):
        _fail("configuration must be ImmediateAcquisitionSearchConfiguration")
    if snapshot.snapshot_id is None:
        _fail("acquisition enumeration requires an identified canonical snapshot")
    team_ids = {item.team_id for item in snapshot.teams}
    if (
        isinstance(configuration.requesting_team_id, bool)
        or not isinstance(configuration.requesting_team_id, int)
        or configuration.requesting_team_id not in team_ids
    ):
        _fail(f"requesting team {configuration.requesting_team_id!r} is unknown")
    if not isinstance(configuration.include_add_only, bool) or not isinstance(
        configuration.include_drop_and_add, bool
    ):
        _fail("action inclusion flags must be Boolean")
    if not configuration.include_add_only and not configuration.include_drop_and_add:
        _fail("at least one acquisition action type must be enabled")
    if not isinstance(configuration.waiver_boundary, WaiverBoundaryPolicy):
        _fail(f"unsupported waiver boundary {configuration.waiver_boundary!r}")

    known_players = {item.player_id for item in snapshot.players}
    declared_acquisitions = _ids(
        configuration.acquisition_player_ids,
        "acquisition_player_ids",
        allow_empty=False,
    )
    unknown = set(declared_acquisitions) - known_players
    if unknown:
        _fail(f"acquisition_player_ids contain unknown players {sorted(unknown)}")
    owners = {item.player_id: item.team_id for item in state.roster_entries}
    owned = tuple(sorted(item for item, owner in owners.items() if owner == configuration.requesting_team_id))
    if configuration.eligible_drop_player_ids is None:
        drops = owned
    else:
        drops = _ids(
            configuration.eligible_drop_player_ids,
            "eligible_drop_player_ids",
            allow_empty=True,
        )
        incorrect = tuple(item for item in drops if owners.get(item) != configuration.requesting_team_id)
        if incorrect:
            _fail(
                f"eligible drop players are not owned by team {configuration.requesting_team_id}: "
                f"{list(incorrect)}"
            )

    availability = {item.player_id: item.status for item in state.availability}
    status_filter = configuration.acquisition_status_filter
    if status_filter is not None:
        if not isinstance(status_filter, tuple):
            _fail("acquisition_status_filter must be a tuple or None")
        if any(not isinstance(item, AcquisitionAvailability) for item in status_filter):
            _fail("acquisition_status_filter contains an unsupported status")
        if len(status_filter) != len(set(status_filter)):
            _fail("acquisition_status_filter contains duplicates")
        acquisitions = tuple(
            item
            for item in declared_acquisitions
            if availability[item] in set(status_filter)
        )
    else:
        acquisitions = declared_acquisitions

    if (
        configuration.waiver_boundary is WaiverBoundaryPolicy.MODELED_WEEKLY_V1
        and any(
            availability[player_id] is AcquisitionAvailability.WAIVERS
            for player_id in acquisitions
        )
    ):
        try:
            require_supported_transaction_rules(snapshot)
        except WeeklyTransactionError as exc:
            _fail(str(exc))

    player_map = {item.player_id: item for item in snapshot.players}
    ordinary_slots = {
        item.slot_id
        for item in snapshot.rules.lineup_slots
        if item.kind is not SlotKind.RESERVE and item.capacity > 0
    }
    destinations = tuple(
        (
            player_id,
            tuple(sorted(ordinary_slots.intersection(player_map[player_id].eligible_lineup_slot_ids))),
        )
        for player_id in acquisitions
    )
    if any(not slots for _, slots in destinations):
        missing = [player_id for player_id, slots in destinations if not slots]
        _fail(f"acquisition players have no configured ordinary destination: {missing}")

    normalized = {
        "contract": "m5.5-immediate-acquisition-search-v1",
        "snapshot_id": snapshot.snapshot_id,
        "source_schema_version": snapshot.schema_version,
        "requesting_team_id": configuration.requesting_team_id,
        "acquisition_player_ids": declared_acquisitions,
        "eligible_drop_player_ids": None if configuration.eligible_drop_player_ids is None else drops,
        "include_add_only": configuration.include_add_only,
        "include_drop_and_add": configuration.include_drop_and_add,
        "acquisition_status_filter": None if status_filter is None else tuple(sorted(item.value for item in status_filter)),
        "waiver_boundary": configuration.waiver_boundary.value,
    }
    configuration_sha256 = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    baseline_sha256 = hashlib.sha256(state_to_json(state, snapshot).encode()).hexdigest()
    return _ValidatedSearch(
        configuration_sha256,
        baseline_sha256,
        configuration.requesting_team_id,
        declared_acquisitions,
        acquisitions,
        drops,
        destinations,
        configuration.include_add_only,
        configuration.include_drop_and_add,
        configuration.waiver_boundary,
    )


def _category(status: AcquisitionAvailability) -> AcquisitionCategory:
    return {
        AcquisitionAvailability.FREE_AGENT: AcquisitionCategory.FREE_AGENT,
        AcquisitionAvailability.WAIVERS: AcquisitionCategory.WAIVER_CLAIM,
        AcquisitionAvailability.HOLD: AcquisitionCategory.HELD,
        AcquisitionAvailability.UNRESOLVED: AcquisitionCategory.UNRESOLVED,
        AcquisitionAvailability.ROSTERED: AcquisitionCategory.ROSTERED,
    }[status]


def _candidate_id(snapshot: LeagueSnapshot, search: _ValidatedSearch, player_id: int, drop_id: int | None, slot_id: int) -> str:
    payload = {
        "contract": "m5.5-immediate-acquisition-candidate-v1",
        "snapshot_id": snapshot.snapshot_id,
        "source_schema_version": snapshot.schema_version,
        "baseline_state_sha256": search.baseline_state_sha256,
        "search_configuration_sha256": search.configuration_sha256,
        "requesting_team_id": search.team_id,
        "acquired_player_id": player_id,
        "dropped_player_id": drop_id,
        "destination_slot_id": slot_id,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _classify_failure(message: str) -> AcquisitionDisposition:
    if any(token in message for token in ("unknown", "unresolved", "evidence", "polarity")):
        return AcquisitionDisposition.UNRESOLVED
    if any(token in message for token in ("protected", "limit", "prohibited", "does not own")):
        return AcquisitionDisposition.PROHIBITED
    return AcquisitionDisposition.STRUCTURALLY_INFEASIBLE


def _attempt(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    search: _ValidatedSearch,
    player_id: int,
    drop_id: int | None,
    slot_id: int,
) -> ImmediateAcquisitionCandidate:
    availability = next(item for item in state.availability if item.player_id == player_id)
    category = _category(availability.status)
    priority = state.current_waiver_priority
    position = priority.index(search.team_id)
    priority_diagnostic = WaiverPriorityDiagnostic(
        position + 1,
        priority[:position],
        priority,
        None,
        False,
    )
    assumptions: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    caveats = ("espn_transaction_not_executed",)
    reason = None
    resulting = None
    structural = False

    if availability.status is AcquisitionAvailability.ROSTERED:
        disposition = AcquisitionDisposition.PROHIBITED
        reason = "player is already rostered and is not a standalone acquisition"
    elif availability.status in {AcquisitionAvailability.HOLD, AcquisitionAvailability.UNRESOLVED}:
        disposition = AcquisitionDisposition.UNRESOLVED
        reason = f"player acquisition availability is {availability.status.value}"
        unresolved = ("player_specific_acquisition_availability",)
    else:
        phase = (
            TransactionPhase.WAIVER
            if availability.status is AcquisitionAvailability.WAIVERS
            else TransactionPhase.FREE_AGENT
        )
        try:
            candidate = (
                add_player(
                    state,
                    snapshot,
                    team_id=search.team_id,
                    player_id=player_id,
                    lineup_slot_id=slot_id,
                    phase=phase,
                )
                if drop_id is None
                else replace_player(
                    state,
                    snapshot,
                    team_id=search.team_id,
                    drop_player_id=drop_id,
                    add_player_id=player_id,
                    lineup_slot_id=slot_id,
                    phase=phase,
                )
            )
            structural = True
            if phase is TransactionPhase.FREE_AGENT:
                disposition = AcquisitionDisposition.AUTHORIZED_IMMEDIATE
                resulting = candidate
                caveats += ("immediate_free_agent_action_authorized_by_modeled_state",)
            elif search.waiver_boundary is WaiverBoundaryPolicy.MODELED_WEEKLY_V1:
                disposition = AcquisitionDisposition.CONDITIONAL_WAIVER
                resulting = apply_successful_waiver_priority(
                    candidate, snapshot, team_id=search.team_id
                )
                assumptions = ("modeled_weekly_waiver_boundary_v1",)
                caveats += (
                    "conditional_successful_claim_scenario_not_guaranteed_pickup",
                    "higher_priority_manager_claim_behavior_unresolved",
                )
                priority_diagnostic = WaiverPriorityDiagnostic(
                    position + 1,
                    priority[:position],
                    priority,
                    resulting.current_waiver_priority,
                    False,
                )
            else:
                disposition = AcquisitionDisposition.UNRESOLVED
                unresolved = ("waiver_processing_boundary",)
                reason = "waiver processing boundary is unresolved"
                caveats += ("conditional_claim_not_materialized",)
        except TransactionStateError as exc:
            reason = str(exc)
            disposition = _classify_failure(reason)
            unresolved = (
                ("transaction_authorization",)
                if disposition is AcquisitionDisposition.UNRESOLVED
                else ()
            )

    return ImmediateAcquisitionCandidate(
        _candidate_id(snapshot, search, player_id, drop_id, slot_id),
        snapshot.snapshot_id or "",
        snapshot.schema_version,
        search.baseline_state_sha256,
        search.configuration_sha256,
        search.team_id,
        player_id,
        drop_id,
        slot_id,
        availability.status,
        category,
        disposition,
        structural,
        priority_diagnostic,
        assumptions,
        unresolved,
        tuple(sorted(caveats)),
        reason,
        resulting,
    )


def _candidate_attempts(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    search: _ValidatedSearch,
) -> Iterator[ImmediateAcquisitionCandidate]:
    destinations = dict(search.destinations)
    for player_id in search.acquisition_ids:
        drop_options: tuple[int | None, ...] = ()
        if search.include_add_only:
            drop_options += (None,)
        if search.include_drop_and_add:
            drop_options += search.drop_ids
        for drop_id in drop_options:
            for slot_id in destinations[player_id]:
                yield _attempt(snapshot, state, search, player_id, drop_id, slot_id)


def enumerate_immediate_acquisition_candidates(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    configuration: ImmediateAcquisitionSearchConfiguration,
) -> ImmediateAcquisitionEnumeration:
    """Enumerate every declared acquisition/drop/destination plan exactly once."""

    search = _validate_search(snapshot, state, configuration)
    candidates = list(_candidate_attempts(snapshot, state, search))
    candidates.sort(
        key=lambda item: (
            item.acquired_player_id,
            item.dropped_player_id is not None,
            0 if item.dropped_player_id is None else item.dropped_player_id,
            item.destination_slot_id,
        )
    )
    dispositions = Counter(item.disposition.value for item in candidates)
    reasons = Counter(
        item.rejection_reason for item in candidates if item.rejection_reason is not None
    )
    structural_count = sum(item.structurally_feasible for item in candidates)
    raw_count = len(candidates)
    if raw_count != sum(dispositions.values()):
        _fail("internal exhaustive disposition reconciliation failed")
    coverage = ImmediateAcquisitionCoverage(
        len(search.declared_acquisition_ids),
        len(search.acquisition_ids),
        len(search.drop_ids),
        raw_count,
        structural_count,
        raw_count - structural_count,
        dispositions[AcquisitionDisposition.AUTHORIZED_IMMEDIATE.value],
        dispositions[AcquisitionDisposition.CONDITIONAL_WAIVER.value],
        dispositions[AcquisitionDisposition.UNRESOLVED.value],
        dispositions[AcquisitionDisposition.PROHIBITED.value],
        tuple(
            (item.value, dispositions[item.value])
            for item in AcquisitionDisposition
        ),
        tuple(sorted(reasons.items())),
        True,
    )
    return ImmediateAcquisitionEnumeration(
        search.configuration_sha256,
        search.baseline_state_sha256,
        tuple(candidates),
        coverage,
    )


def iter_immediate_acquisition_candidates(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    configuration: ImmediateAcquisitionSearchConfiguration,
) -> Iterator[ImmediateAcquisitionCandidate]:
    """Yield the exhaustive stable plan stream without retaining coverage counters."""

    search = _validate_search(snapshot, state, configuration)
    yield from _candidate_attempts(snapshot, state, search)

