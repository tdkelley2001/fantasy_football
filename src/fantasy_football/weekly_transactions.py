"""Deterministic sequential M2.3d essential-acquisition execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import time

from fantasy_football.canonical.model import LeagueSnapshot, SlotKind
from fantasy_football.canonical.validation import validate_snapshot
from fantasy_football.evolving_state import (
    AcquisitionAvailability,
    EvolvingLeagueState,
    TransactionPhase,
    TransactionStateError,
    activate_from_ir,
    acquisition_blocking_ir_players,
    add_player,
    apply_successful_waiver_priority,
    place_on_ir,
    replace_player,
    validate_evolving_state,
)
from fantasy_football.lineup_optimizer import optimize_starting_lineup
from fantasy_football.roster_value import value_roster


class WeeklyTransactionError(ValueError):
    """Raised when the weekly transaction capability cannot execute safely."""


class DecisionOutcome(StrEnum):
    NO_ESSENTIAL_VACANCY = "no_essential_vacancy"
    NO_SUITABLE_CANDIDATE = "no_suitable_candidate"
    NO_LEGAL_PLAN = "no_legal_plan"
    UNRESOLVED_AUTHORIZATION = "unresolved_authorization"
    ACQUIRED = "acquired"


@dataclass(frozen=True, slots=True)
class WeeklyTransactionPolicy:
    waiver_processing_authorized: bool
    waiver_boundary_assumption_id: str | None = None
    reject_incomplete_valuations: bool = True


@dataclass(frozen=True, slots=True)
class CandidateRejectionSummary:
    reason: str
    count: int


@dataclass(frozen=True, slots=True)
class SelectedAcquisition:
    phase: TransactionPhase
    pass_number: int
    team_id: int
    acquired_player_id: int
    dropped_player_ids: tuple[int, ...]
    ir_activated_player_ids: tuple[int, ...]
    ir_placed_player_ids: tuple[int, ...]
    vacancy_count_before: int
    vacancy_count_after: int
    resulting_roster_value: float
    tie_break_key: tuple[object, ...]
    ledger_sequences: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TeamDecision:
    phase: TransactionPhase
    pass_number: int
    team_id: int
    outcome: DecisionOutcome
    vacancy_count_before: int
    candidates_considered: int
    legal_plans: int
    qualifying_plans: int
    rejection_summaries: tuple[CandidateRejectionSummary, ...]
    selected_player_id: int | None


@dataclass(frozen=True, slots=True)
class WeeklyTransactionResult:
    initial_waiver_priority: tuple[int, ...]
    frozen_initial_priority: tuple[int, ...]
    final_waiver_priority: tuple[int, ...]
    waiver_passes: int
    free_agent_passes: int
    waiver_acquisitions: int
    free_agent_acquisitions: int
    candidate_plans_considered: int
    roster_value_evaluations: int
    valuation_seconds: float
    decisions: tuple[TeamDecision, ...]
    acquisitions: tuple[SelectedAcquisition, ...]
    assumptions: tuple[str, ...]
    state: EvolvingLeagueState


@dataclass(frozen=True, slots=True)
class _Plan:
    state: EvolvingLeagueState
    player_id: int
    before_vacancies: int
    after_vacancies: int
    value: float
    tie_key: tuple[object, ...]


def _ordinary_slot_ids(snapshot: LeagueSnapshot, player_id: int) -> tuple[int, ...]:
    player = next(item for item in snapshot.players if item.player_id == player_id)
    return tuple(sorted(
        rule.slot_id for rule in snapshot.rules.lineup_slots
        if rule.kind is not SlotKind.RESERVE
        and rule.capacity > 0
        and rule.slot_id in player.eligible_lineup_slot_ids
    ))


def _team_owned(state: EvolvingLeagueState, team_id: int) -> tuple[int, ...]:
    return tuple(sorted(entry.player_id for entry in state.roster_entries if entry.team_id == team_id))


def _ledger_delta(before: EvolvingLeagueState, after: EvolvingLeagueState):
    return after.ledger[len(before.ledger):]


def _correction_states(
    snapshot: LeagueSnapshot, state: EvolvingLeagueState, team_id: int
) -> tuple[EvolvingLeagueState, ...]:
    """Enumerate reactive IR corrections without manufacturing evidence."""

    results = [state]
    blockers = tuple(
        player_id for player_id in acquisition_blocking_ir_players(state, snapshot)
        if any(entry.player_id == player_id and entry.team_id == team_id for entry in state.roster_entries)
    )
    frontier = [state]
    for blocker in blockers:
        next_frontier: list[EvolvingLeagueState] = []
        for candidate in frontier:
            drops = (None,) + tuple(
                player_id for player_id in _team_owned(candidate, team_id) if player_id != blocker
            )
            for slot_id in _ordinary_slot_ids(snapshot, blocker):
                for drop_id in drops:
                    try:
                        corrected = activate_from_ir(
                            candidate, snapshot, team_id=team_id, player_id=blocker,
                            ordinary_slot_id=slot_id, drop_player_id=drop_id,
                        )
                    except TransactionStateError:
                        continue
                    next_frontier.append(corrected)
        frontier = next_frontier
        if not frontier:
            break
    results.extend(frontier)

    # Necessary placement can free ordinary capacity, but only verified OUT/IR
    # status and canonical reserve eligibility can authorize it.
    reserve_slots = tuple(
        rule.slot_id for rule in snapshot.rules.lineup_slots
        if rule.kind is SlotKind.RESERVE and rule.capacity > 0
    )
    for player_id in _team_owned(state, team_id):
        for reserve_id in reserve_slots:
            try:
                results.append(place_on_ir(
                    state, snapshot, team_id=team_id, player_id=player_id,
                    reserve_slot_id=reserve_id,
                ))
            except TransactionStateError:
                continue
    unique = {tuple(item.roster_entries): item for item in results}
    return tuple(unique[key] for key in sorted(unique, key=repr))


def _enumerate_plans(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    *,
    team_id: int,
    phase: TransactionPhase,
) -> tuple[tuple[_Plan, ...], int, tuple[CandidateRejectionSummary, ...], int, float]:
    baseline = optimize_starting_lineup(
        snapshot, team_id, state.scoring_week, roster_entries=state.roster_entries
    )
    required_status = (
        AcquisitionAvailability.WAIVERS
        if phase is TransactionPhase.WAIVER else AcquisitionAvailability.FREE_AGENT
    )
    available = tuple(sorted(
        item.player_id for item in state.availability if item.status is required_status
    ))
    reasons: dict[str, int] = {}
    plans: list[_Plan] = []
    considered = 0
    evaluations = 0
    valuation_seconds = 0.0
    for player_id in available:
        player_had_structural_option = False
        for corrected in _correction_states(snapshot, state, team_id):
            owned = _team_owned(corrected, team_id)
            operations: list[tuple[int | None, int]] = []
            for slot_id in _ordinary_slot_ids(snapshot, player_id):
                operations.append((None, slot_id))
                operations.extend((drop_id, slot_id) for drop_id in owned)
            for drop_id, slot_id in operations:
                considered += 1
                player_had_structural_option = True
                try:
                    resulting = (
                        add_player(
                            corrected, snapshot, team_id=team_id, player_id=player_id,
                            lineup_slot_id=slot_id, phase=phase,
                        )
                        if drop_id is None else
                        replace_player(
                            corrected, snapshot, team_id=team_id, drop_player_id=drop_id,
                            add_player_id=player_id, lineup_slot_id=slot_id, phase=phase,
                        )
                    )
                except TransactionStateError as exc:
                    text = str(exc)
                    category = "unresolved_authorization" if "unknown" in text or "unresolved" in text else "illegal_plan"
                    reasons[category] = reasons.get(category, 0) + 1
                    continue
                after = optimize_starting_lineup(
                    snapshot, team_id, state.scoring_week, roster_entries=resulting.roster_entries
                )
                if after.vacancy_count >= baseline.vacancy_count:
                    reasons["no_coverage_improvement"] = reasons.get("no_coverage_improvement", 0) + 1
                    continue
                started = time.perf_counter()
                value = value_roster(snapshot, resulting, team_id)
                elapsed = time.perf_counter() - started
                evaluations += 1
                valuation_seconds += elapsed
                if not value.is_complete:
                    reasons["incomplete_valuation"] = reasons.get("incomplete_valuation", 0) + 1
                    continue
                records = _ledger_delta(state, resulting)
                dropped = tuple(sorted(
                    record.player_id for record in records
                    if record.action.value == "drop" and record.player_id is not None
                ))
                activated = tuple(sorted(
                    record.player_id for record in records
                    if record.action.value == "ir_activate" and record.player_id is not None
                ))
                placed = tuple(sorted(
                    record.player_id for record in records
                    if record.action.value == "ir_place" and record.player_id is not None
                ))
                tie_key = (player_id, dropped, activated, placed, slot_id)
                plans.append(_Plan(
                    resulting, player_id, baseline.vacancy_count, after.vacancy_count,
                    value.total_value, tie_key,
                ))
        if not player_had_structural_option:
            reasons["ineligible_for_configured_slots"] = reasons.get("ineligible_for_configured_slots", 0) + 1
    return (
        tuple(plans), considered,
        tuple(CandidateRejectionSummary(reason, count) for reason, count in sorted(reasons.items())),
        evaluations, valuation_seconds,
    )


def _choose(plans: tuple[_Plan, ...]) -> _Plan | None:
    if not plans:
        return None
    return min(plans, key=lambda item: (-item.value, item.tie_key))


def execute_weekly_essential_transactions(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    policy: WeeklyTransactionPolicy,
) -> WeeklyTransactionResult:
    """Execute one immutable sequential weekly waiver/free-agent window."""

    validate_snapshot(snapshot)
    validate_evolving_state(state, snapshot)
    if state.scoring_week < snapshot.first_simulation_week or state.scoring_week > snapshot.final_simulation_week:
        raise WeeklyTransactionError("state scoring week is outside the canonical simulation horizon")
    if not isinstance(policy, WeeklyTransactionPolicy):
        raise WeeklyTransactionError("policy must be WeeklyTransactionPolicy")
    if policy.waiver_processing_authorized and not policy.waiver_boundary_assumption_id:
        raise WeeklyTransactionError("authorized waiver processing requires an explicit boundary assumption ID")
    if not policy.reject_incomplete_valuations:
        raise WeeklyTransactionError("ranking incomplete roster valuations has no approved capability policy")

    initial = state.current_waiver_priority
    frozen = state.initial_window_waiver_priority
    current = state
    decisions: list[TeamDecision] = []
    acquisitions: list[SelectedAcquisition] = []
    total_considered = 0
    total_evaluations = 0
    valuation_seconds = 0.0

    def run_phase(phase: TransactionPhase, order_factory) -> tuple[int, int]:
        nonlocal current, total_considered, total_evaluations, valuation_seconds
        pass_number = 0
        successes = 0
        while True:
            pass_number += 1
            progress = False
            order = tuple(order_factory(current))
            for team_id in order:
                lineup = optimize_starting_lineup(
                    snapshot, team_id, current.scoring_week, roster_entries=current.roster_entries
                )
                if lineup.vacancy_count == 0:
                    decisions.append(TeamDecision(
                        phase, pass_number, team_id, DecisionOutcome.NO_ESSENTIAL_VACANCY,
                        0, 0, 0, 0, (), None,
                    ))
                    continue
                plans, considered, rejections, evaluations, evaluation_seconds = _enumerate_plans(
                    snapshot, current, team_id=team_id, phase=phase,
                )
                total_considered += considered
                total_evaluations += evaluations
                valuation_seconds += evaluation_seconds
                selected = _choose(plans)
                if selected is None:
                    outcome = (
                        DecisionOutcome.UNRESOLVED_AUTHORIZATION
                        if any(item.reason in {"unresolved_authorization", "incomplete_valuation"} for item in rejections)
                        else DecisionOutcome.NO_LEGAL_PLAN if considered else DecisionOutcome.NO_SUITABLE_CANDIDATE
                    )
                    decisions.append(TeamDecision(
                        phase, pass_number, team_id, outcome, lineup.vacancy_count,
                        considered, 0, 0, rejections, None,
                    ))
                    continue
                before = current
                current = selected.state
                if phase is TransactionPhase.WAIVER:
                    current = apply_successful_waiver_priority(current, snapshot, team_id=team_id)
                records = _ledger_delta(before, current)
                dropped = tuple(sorted(record.player_id for record in records if record.action.value == "drop" and record.player_id is not None))
                activated = tuple(sorted(record.player_id for record in records if record.action.value == "ir_activate" and record.player_id is not None))
                placed = tuple(sorted(record.player_id for record in records if record.action.value == "ir_place" and record.player_id is not None))
                acquisitions.append(SelectedAcquisition(
                    phase, pass_number, team_id, selected.player_id, dropped, activated, placed,
                    selected.before_vacancies, selected.after_vacancies, selected.value,
                    selected.tie_key, tuple(record.sequence for record in records),
                ))
                decisions.append(TeamDecision(
                    phase, pass_number, team_id, DecisionOutcome.ACQUIRED,
                    selected.before_vacancies, considered, len(plans), len(plans),
                    rejections, selected.player_id,
                ))
                successes += 1
                progress = True
            if not progress:
                return pass_number, successes

    if policy.waiver_processing_authorized:
        waiver_passes, waiver_successes = run_phase(
            TransactionPhase.WAIVER, lambda current_state: current_state.current_waiver_priority,
        )
    else:
        waiver_passes, waiver_successes = 0, 0
        if any(item.status is AcquisitionAvailability.WAIVERS for item in current.availability):
            for team_id in current.current_waiver_priority:
                vacancy_count = optimize_starting_lineup(
                    snapshot, team_id, current.scoring_week,
                    roster_entries=current.roster_entries,
                ).vacancy_count
                if vacancy_count == 0:
                    continue
                decisions.append(TeamDecision(
                    TransactionPhase.WAIVER, 0, team_id,
                    DecisionOutcome.UNRESOLVED_AUTHORIZATION,
                    vacancy_count,
                    0, 0, 0,
                    (CandidateRejectionSummary("waiver_processing_boundary_unresolved", 1),),
                    None,
                ))

    free_agent_order = tuple(reversed(frozen))
    free_agent_passes, free_agent_successes = run_phase(
        TransactionPhase.FREE_AGENT, lambda _current_state: free_agent_order,
    )
    validate_evolving_state(current, snapshot)
    assumptions = (
        "essential_coverage_improvement_only_v1",
        "highest_resulting_remaining_season_value_v1",
        "reverse_frozen_initial_priority_free_agents_v1",
    ) + ((policy.waiver_boundary_assumption_id,) if policy.waiver_boundary_assumption_id else ())
    return WeeklyTransactionResult(
        initial, frozen, current.current_waiver_priority,
        waiver_passes, free_agent_passes, waiver_successes, free_agent_successes,
        total_considered, total_evaluations, valuation_seconds,
        tuple(decisions), tuple(acquisitions), assumptions, current,
    )
