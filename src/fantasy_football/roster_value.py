"""Exact deterministic M2.3c remaining-season roster valuation reference."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
import math
from typing import Iterable

from fantasy_football.canonical.model import LeagueSnapshot, RosterEntry, SlotKind
from fantasy_football.evolving_state import (
    AcquisitionAvailability,
    EvolvingLeagueState,
    PlayerAvailability,
    validate_evolving_state,
)
from fantasy_football.lineup_optimizer import (
    LineupAssignment,
    StartingSlot,
    optimize_candidate_lineup,
    optimize_starting_lineup,
)


class RosterValuationError(ValueError):
    """Raised when V(R) cannot be computed from a coherent supported state."""


class ReplacementAccessContext(StrEnum):
    FUTURE_CONSERVATIVE = "future_conservative"
    CURRENT_WAIVER = "current_waiver"


@dataclass(frozen=True, slots=True, order=True)
class VacancyIdentity:
    team_id: int
    slot: StartingSlot


@dataclass(frozen=True, slots=True)
class CompetingDemand:
    team_id: int
    vacancies: tuple[StartingSlot, ...]


@dataclass(frozen=True, slots=True)
class ReplacementAssignment:
    team_id: int
    slot: StartingSlot
    player_id: int
    effective_projection: float
    acquisition_status: AcquisitionAvailability
    access_rank: int


@dataclass(frozen=True, slots=True)
class WeekRosterValue:
    scoring_week: int
    projected_lineup_points: float
    owned_projected_points: float
    replacement_projected_points: float
    mandatory_vacancy_count: int
    remaining_vacancy_count: int
    owned_assignments: tuple[LineupAssignment, ...]
    replacement_assignments: tuple[ReplacementAssignment, ...]
    competing_demands: tuple[CompetingDemand, ...]
    opponent_replacement_assignments: tuple[ReplacementAssignment, ...]
    inaccessible_player_counts: tuple[tuple[str, int], ...]
    assumptions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RosterValueResult:
    team_id: int
    season: int
    first_scoring_week: int
    final_scoring_week: int
    total_value: float
    weeks: tuple[WeekRosterValue, ...]
    is_complete: bool
    unresolved_inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RosterValueComparison:
    baseline: RosterValueResult
    scenario: RosterValueResult
    delta: float
    current_week_vacancy_improvement: int


@dataclass(frozen=True, slots=True)
class _OpponentState:
    mask: int
    assignments: tuple[tuple[int, int], ...]  # vacancy index, player ID
    exact_improvement: Decimal


def _exact_total(snapshot: LeagueSnapshot, week: int, assignments: Iterable[LineupAssignment]) -> Decimal:
    projections = {
        item.player_id: item.effective_projection for item in snapshot.player_weeks
        if item.season == snapshot.season and item.scoring_week == week
    }
    return sum((Decimal.from_float(projections[item.player_id]) for item in assignments), Decimal(0))


def _state_maps(state: EvolvingLeagueState):
    return (
        {item.player_id: item for item in state.availability},
        {item.player_id: item.team_id for item in state.roster_entries},
    )


def _available_pool(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    *,
    target_team_id: int,
    week: int,
    context: ReplacementAccessContext,
) -> tuple[tuple[int, ...], dict[int, AcquisitionAvailability], tuple[tuple[str, int], ...]]:
    availability, owners = _state_maps(state)
    week_records = {
        item.player_id: item for item in snapshot.player_weeks
        if item.season == snapshot.season and item.scoring_week == week
    }
    included: list[int] = []
    status_by_player: dict[int, AcquisitionAvailability] = {}
    excluded: dict[str, int] = {}
    for player_id in sorted(week_records):
        if player_id in owners or not week_records[player_id].projected_lineup_available:
            continue
        status = availability[player_id].status
        usable = status is AcquisitionAvailability.FREE_AGENT
        if status is AcquisitionAvailability.WAIVERS:
            usable = context is ReplacementAccessContext.CURRENT_WAIVER and week == state.scoring_week
        if usable:
            included.append(player_id)
            status_by_player[player_id] = status
        else:
            excluded[status.value] = excluded.get(status.value, 0) + 1
    return tuple(included), status_by_player, tuple(sorted(excluded.items()))


def _opponent_team_allowed(
    state: EvolvingLeagueState,
    *,
    target_team_id: int,
    opponent_team_id: int,
    status: AcquisitionAvailability,
    context: ReplacementAccessContext,
) -> bool:
    if status is AcquisitionAvailability.FREE_AGENT:
        return True
    if status is not AcquisitionAvailability.WAIVERS or context is not ReplacementAccessContext.CURRENT_WAIVER:
        return False
    priority = {team_id: index for index, team_id in enumerate(state.current_waiver_priority)}
    return priority[opponent_team_id] < priority[target_team_id]


def _allocate_opponents(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    *,
    target_team_id: int,
    week: int,
    pool: tuple[int, ...],
    statuses: dict[int, AcquisitionAvailability],
    context: ReplacementAccessContext,
    target_owned_ids: tuple[int, ...],
    target_vacancy_count: int,
) -> tuple[_OpponentState, tuple[VacancyIdentity, ...], dict[int, object]]:
    opponent_lineups = {
        team.team_id: optimize_starting_lineup(
            snapshot, team.team_id, week, roster_entries=state.roster_entries
        )
        for team in snapshot.teams if team.team_id != target_team_id
    }
    vacancies = tuple(
        VacancyIdentity(team_id, vacancy.slot)
        for team_id, lineup in sorted(opponent_lineups.items())
        for vacancy in lineup.vacancies
    )
    if not vacancies or not pool:
        return _OpponentState(0, (), Decimal(0)), vacancies, opponent_lineups

    owned_by_team = {
        team_id: tuple(
            entry.player_id for entry in state.roster_entries
            if entry.team_id == team_id
            and next(rule for rule in snapshot.rules.lineup_slots if rule.slot_id == entry.lineup_slot_id).kind
            is not SlotKind.RESERVE
        )
        for team_id in opponent_lineups
    }
    base_exact = {
        team_id: _exact_total(snapshot, week, lineup.assignments)
        for team_id, lineup in opponent_lineups.items()
    }
    cache: dict[tuple[int, tuple[int, ...]], tuple[int, Decimal]] = {}

    def team_outcome(team_id: int, assigned: tuple[int, ...]) -> tuple[int, Decimal]:
        key = (team_id, assigned)
        if key not in cache:
            combined = optimize_candidate_lineup(
                snapshot, week, tuple(sorted(owned_by_team[team_id] + assigned)),
                limited_player_ids=frozenset(assigned),
                maximum_limited_players=len(assigned),
            )
            base = opponent_lineups[team_id]
            cache[key] = (
                base.vacancy_count - len(combined.vacant_slots),
                _exact_total(snapshot, week, combined.assignments) - base_exact[team_id],
            )
        return cache[key]

    states: dict[int, list[_OpponentState]] = {0: [_OpponentState(0, (), Decimal(0))]}
    vacancy_indices = {
        team_id: tuple(index for index, vacancy in enumerate(vacancies) if vacancy.team_id == team_id)
        for team_id in opponent_lineups
    }
    for player_id in pool:
        updated = {mask: list(values) for mask, values in states.items()}
        for mask, values in states.items():
            for value in values:
                by_team: dict[int, tuple[int, ...]] = {}
                for vacancy_index, assigned_player in value.assignments:
                    by_team.setdefault(vacancies[vacancy_index].team_id, ())
                    by_team[vacancies[vacancy_index].team_id] += (assigned_player,)
                for team_id, indices in vacancy_indices.items():
                    if not _opponent_team_allowed(
                        state, target_team_id=target_team_id, opponent_team_id=team_id,
                        status=statuses[player_id], context=context,
                    ):
                        continue
                    assigned = tuple(sorted(by_team.get(team_id, ()) + (player_id,)))
                    prior_filled, prior_points = team_outcome(team_id, tuple(sorted(by_team.get(team_id, ()))))
                    filled, points = team_outcome(team_id, assigned)
                    if filled <= prior_filled:
                        continue
                    available_index = next((index for index in indices if not mask & (1 << index)), None)
                    if available_index is None:
                        continue
                    new_mask = mask | (1 << available_index)
                    proposed = _OpponentState(
                        new_mask,
                        tuple(sorted(value.assignments + ((available_index, player_id),))),
                        value.exact_improvement - prior_points + points,
                    )
                    incumbent = updated.get(new_mask, [])
                    if not incumbent or proposed.exact_improvement > incumbent[0].exact_improvement:
                        updated[new_mask] = [proposed]
                    elif proposed.exact_improvement == incumbent[0].exact_improvement:
                        if proposed.assignments not in {item.assignments for item in incumbent}:
                            incumbent.append(proposed)
        states = updated

    max_filled = max(mask.bit_count() for mask in states)
    finalists = [item for mask, values in states.items() if mask.bit_count() == max_filled for item in values]
    max_points = max(item.exact_improvement for item in finalists)
    finalists = [item for item in finalists if item.exact_improvement == max_points]

    def target_outcome(item: _OpponentState):
        consumed = {player_id for _, player_id in item.assignments}
        remaining = tuple(player_id for player_id in pool if player_id not in consumed)
        combined = optimize_candidate_lineup(
            snapshot, week, tuple(sorted(target_owned_ids + remaining)),
            limited_player_ids=frozenset(remaining),
            maximum_limited_players=target_vacancy_count,
        )
        return (_exact_total(snapshot, week, combined.assignments), item.assignments)

    chosen = min(finalists, key=target_outcome)
    return chosen, vacancies, opponent_lineups


def value_roster(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    team_id: int,
    *,
    first_scoring_week: int | None = None,
    access_context: ReplacementAccessContext = ReplacementAccessContext.FUTURE_CONSERVATIVE,
) -> RosterValueResult:
    """Return equal-weighted replacement-adjusted remaining-season V(R)."""

    validate_evolving_state(state, snapshot)
    if team_id not in {team.team_id for team in snapshot.teams}:
        raise RosterValuationError(f"unknown fantasy team {team_id}")
    first_week = state.scoring_week if first_scoring_week is None else first_scoring_week
    if not state.scoring_week <= first_week <= snapshot.final_simulation_week:
        raise RosterValuationError(
            f"valuation first week {first_week} must be within state week {state.scoring_week} "
            f"and snapshot final week {snapshot.final_simulation_week}"
        )
    reserve_ids = {
        item.slot_id for item in snapshot.rules.lineup_slots if item.kind is SlotKind.RESERVE
    }
    owned_ids = tuple(sorted(
        entry.player_id for entry in state.roster_entries
        if entry.team_id == team_id and entry.lineup_slot_id not in reserve_ids
    ))
    players = {item.player_id: item for item in snapshot.players}
    projection_by_key = {
        (item.player_id, item.scoring_week): item.effective_projection for item in snapshot.player_weeks
    }
    weeks: list[WeekRosterValue] = []
    for week in range(first_week, snapshot.final_simulation_week + 1):
        owned = optimize_starting_lineup(snapshot, team_id, week, roster_entries=state.roster_entries)
        pool, statuses, inaccessible = _available_pool(
            snapshot, state, target_team_id=team_id, week=week, context=access_context
        )
        opponent, opponent_vacancies, opponent_lineups = _allocate_opponents(
            snapshot, state, target_team_id=team_id, week=week, pool=pool,
            statuses=statuses, context=access_context, target_owned_ids=owned_ids,
            target_vacancy_count=owned.vacancy_count,
        )
        consumed = {player_id for _, player_id in opponent.assignments}
        remaining = tuple(player_id for player_id in pool if player_id not in consumed)
        combined = optimize_candidate_lineup(
            snapshot, week, tuple(sorted(owned_ids + remaining)),
            limited_player_ids=frozenset(remaining),
            maximum_limited_players=owned.vacancy_count,
        )
        replacement_ids = {item.player_id for item in combined.assignments if item.player_id not in owned_ids}
        opponent_assignments: list[ReplacementAssignment] = []
        for vacancy_index, player_id in opponent.assignments:
            vacancy = opponent_vacancies[vacancy_index]
            team_players = tuple(
                entry.player_id for entry in state.roster_entries
                if entry.team_id == vacancy.team_id and entry.lineup_slot_id not in reserve_ids
            )
            assigned_to = next(
                item.slot for item in optimize_candidate_lineup(
                    snapshot, week, tuple(sorted(team_players + tuple(
                        p for index, p in opponent.assignments
                        if opponent_vacancies[index].team_id == vacancy.team_id
                    )))
                ).assignments if item.player_id == player_id
            )
            opponent_assignments.append(ReplacementAssignment(
                vacancy.team_id, assigned_to, player_id, projection_by_key[(player_id, week)],
                statuses[player_id], 0,
            ))
        target_assignments = tuple(
            ReplacementAssignment(
                team_id, assignment.slot, assignment.player_id, assignment.effective_projection,
                statuses[assignment.player_id],
                1 + sum(
                    1 for item in opponent_assignments
                    if item.slot.lineup_slot_id in players[assignment.player_id].eligible_lineup_slot_ids
                ),
            )
            for assignment in combined.assignments if assignment.player_id in replacement_ids
        )
        replacement_points = combined.total_projected_points - owned.total_projected_points
        weeks.append(WeekRosterValue(
            week,
            combined.total_projected_points,
            owned.total_projected_points,
            replacement_points,
            owned.vacancy_count,
            len(combined.vacant_slots),
            owned.assignments,
            tuple(sorted(target_assignments, key=lambda item: (item.slot, item.player_id))),
            tuple(
                CompetingDemand(team_id_, tuple(item.slot for item in lineup.vacancies))
                for team_id_, lineup in sorted(opponent_lineups.items()) if lineup.vacancies
            ),
            tuple(sorted(opponent_assignments, key=lambda item: (item.team_id, item.slot, item.player_id))),
            inaccessible,
            ("equal_week_weight_v1", "snapshot_time_marginal_replacement_access_v1", "opponents_ahead_conservative_v1"),
        ))
    total = math.fsum(item.projected_lineup_points for item in weeks)
    unresolved = tuple(sorted({
        status for week in weeks for status, count in week.inaccessible_player_counts
        if count and status in {AcquisitionAvailability.HOLD.value, AcquisitionAvailability.UNRESOLVED.value}
    }))
    return RosterValueResult(
        team_id, snapshot.season, first_week, snapshot.final_simulation_week,
        total, tuple(weeks), not unresolved, unresolved,
    )


def compare_roster_values(
    baseline: RosterValueResult,
    scenario: RosterValueResult,
) -> RosterValueComparison:
    if (
        baseline.team_id, baseline.season, baseline.first_scoring_week, baseline.final_scoring_week
    ) != (
        scenario.team_id, scenario.season, scenario.first_scoring_week, scenario.final_scoring_week
    ):
        raise RosterValuationError("roster values must share team, season, and valuation horizon")
    return RosterValueComparison(
        baseline,
        scenario,
        scenario.total_value - baseline.total_value,
        baseline.weeks[0].mandatory_vacancy_count - scenario.weeks[0].mandatory_vacancy_count,
    )


def value_hypothetical_roster(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    team_id: int,
    *,
    roster_entries: tuple[RosterEntry, ...],
    availability: tuple[PlayerAvailability, ...],
    first_scoring_week: int | None = None,
    access_context: ReplacementAccessContext = ReplacementAccessContext.FUTURE_CONSERVATIVE,
) -> RosterValueResult:
    """Value an explicitly supplied structurally legal hypothetical league state.

    This proves canonical coherence only; it does not claim that an ESPN
    transaction sequence producing the roster has been authorized.
    """

    hypothetical = EvolvingLeagueState(
        source_snapshot_id=state.source_snapshot_id,
        source_schema_version=state.source_schema_version,
        season=state.season,
        scoring_week=state.scoring_week,
        cycle_id=state.cycle_id,
        roster_entries=roster_entries,
        availability=availability,
        current_waiver_priority=state.current_waiver_priority,
        initial_window_waiver_priority=state.initial_window_waiver_priority,
        current_matchup_period_id=state.current_matchup_period_id,
        season_acquisition_counts=state.season_acquisition_counts,
        matchup_acquisition_counts=state.matchup_acquisition_counts,
        ir_policy=state.ir_policy,
        ir_eligibility_evidence=state.ir_eligibility_evidence,
        ledger=state.ledger,
        assumption_ids=state.assumption_ids + ("structural_hypothetical_not_transaction_authorization",),
    )
    return value_roster(
        snapshot,
        hypothetical,
        team_id,
        first_scoring_week=first_scoring_week,
        access_context=access_context,
    )
