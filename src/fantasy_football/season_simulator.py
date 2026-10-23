"""Pure deterministic coordinator for one complete modeled season path."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum

from fantasy_football.canonical.model import (
    LeagueSnapshot,
    MatchupEntryStatus,
    MatchupPhase,
)
from fantasy_football.canonical.validation import validate_snapshot
from fantasy_football.evolving_state import (
    EvolvingLeagueState,
    IREligibilityEvidence,
    IRPolicy,
    advance_cycle,
    initialize_evolving_state,
    reset_waiver_priority,
    validate_evolving_state,
)
from fantasy_football.lineup_optimizer import OptimizedLineup, optimize_starting_lineup
from fantasy_football.postseason import (
    ConsolationLadderConfiguration,
    PostseasonError,
    PostseasonState,
    final_positions_complete,
    initialize_postseason,
    score_frozen_postseason_week,
)
from fantasy_football.weekly_engine import (
    ModeledStanding,
    RealizedPlayerScore,
    StandingsTable,
    WeeklyTransition,
    initialize_standings,
    rank_standings,
    resolve_regular_season_week,
)
from fantasy_football.weekly_transactions import (
    DecisionOutcome,
    WeeklyTransactionPolicy,
    WeeklyTransactionResult,
    execute_weekly_essential_transactions,
    require_supported_transaction_rules,
)


class SeasonSimulationError(ValueError):
    """Raised when a deterministic season input is invalid or contradictory."""


class SeasonCompletionStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class DeterministicScoreScenario:
    scenario_id: str
    scores: tuple[RealizedPlayerScore, ...]


@dataclass(frozen=True, slots=True)
class FrozenTeamWeek:
    team_id: int
    lineup: OptimizedLineup
    realized_points: float


@dataclass(frozen=True, slots=True)
class SeasonWeekTransition:
    scoring_week: int
    phase: MatchupPhase
    transaction_result: WeeklyTransactionResult
    frozen_team_weeks: tuple[FrozenTeamWeek, ...]
    regular_transition: WeeklyTransition | None
    postseason_state: PostseasonState | None


@dataclass(frozen=True, slots=True)
class FinalTeamSeasonRecord:
    team_id: int
    initial_standing: ModeledStanding
    final_regular_standing: ModeledStanding
    final_regular_rank: int | None
    championship_qualifier: bool | None
    postseason_seed: int | None
    final_placement: int | None


@dataclass(frozen=True, slots=True)
class DeterministicSeasonResult:
    scenario_id: str
    source_snapshot_id: str
    season: int
    status: SeasonCompletionStatus
    unresolved_capabilities: tuple[str, ...]
    initial_standings: tuple[ModeledStanding, ...]
    final_regular_standings: tuple[ModeledStanding, ...]
    final_regular_ranking: StandingsTable
    weeks: tuple[SeasonWeekTransition, ...]
    final_evolving_state: EvolvingLeagueState
    final_postseason_state: PostseasonState | None
    team_records: tuple[FinalTeamSeasonRecord, ...]


def _validate_scenario(
    snapshot: LeagueSnapshot, scenario: DeterministicScoreScenario
) -> dict[tuple[int, int], RealizedPlayerScore]:
    if not isinstance(scenario, DeterministicScoreScenario):
        raise SeasonSimulationError("score scenario must be DeterministicScoreScenario")
    if not isinstance(scenario.scenario_id, str) or not scenario.scenario_id.strip():
        raise SeasonSimulationError(
            "score scenario requires a nonempty stable scenario_id"
        )
    if not isinstance(scenario.scores, tuple):
        raise SeasonSimulationError("score scenario scores must be an immutable tuple")
    players = {item.player_id for item in snapshot.players}
    indexed: dict[tuple[int, int], RealizedPlayerScore] = {}
    for score in scenario.scores:
        if not isinstance(score, RealizedPlayerScore):
            raise SeasonSimulationError(f"invalid realized score record {score!r}")
        if score.player_id not in players:
            raise SeasonSimulationError(
                f"scenario {scenario.scenario_id!r} references unknown player {score.player_id}"
            )
        if score.season != snapshot.season:
            raise SeasonSimulationError(
                f"player {score.player_id} score season {score.season} does not match {snapshot.season}"
            )
        if (
            not snapshot.first_simulation_week
            <= score.scoring_week
            <= snapshot.final_simulation_week
        ):
            raise SeasonSimulationError(
                f"player {score.player_id} score week {score.scoring_week} is outside the simulation horizon"
            )
        if (
            isinstance(score.points, bool)
            or not isinstance(score.points, (int, float))
            or not math.isfinite(score.points)
        ):
            raise SeasonSimulationError(
                f"player {score.player_id} week {score.scoring_week} score must be finite"
            )
        key = (score.player_id, score.scoring_week)
        if key in indexed:
            raise SeasonSimulationError(
                f"duplicate realized score for player {score.player_id}, week {score.scoring_week}"
            )
        indexed[key] = score
    return indexed


def _phase_by_week(snapshot: LeagueSnapshot) -> dict[int, MatchupPhase]:
    result: dict[int, MatchupPhase] = {}
    for period in snapshot.matchup_periods:
        for week in period.scoring_weeks:
            if week in result:
                raise SeasonSimulationError(
                    f"scoring week {week} belongs to multiple matchup periods"
                )
            result[week] = period.phase
    required = set(
        range(snapshot.first_simulation_week, snapshot.final_simulation_week + 1)
    )
    if set(result) != required:
        raise SeasonSimulationError(
            f"matchup periods cover weeks {sorted(result)}, expected {sorted(required)}"
        )
    phases = tuple(result[week] for week in sorted(result))
    if MatchupPhase.POSTSEASON in phases:
        first_postseason = phases.index(MatchupPhase.POSTSEASON)
        if any(item is MatchupPhase.REGULAR for item in phases[first_postseason:]):
            raise SeasonSimulationError(
                "regular-season scoring periods cannot follow postseason periods"
            )
    return result


def _preflight(
    snapshot: LeagueSnapshot,
    scenario: DeterministicScoreScenario,
    transaction_policy: WeeklyTransactionPolicy,
    consolation_configuration: ConsolationLadderConfiguration | None,
) -> dict[tuple[int, int], RealizedPlayerScore]:
    validate_snapshot(snapshot)
    if snapshot.snapshot_id is None:
        raise SeasonSimulationError(
            "season simulation requires a published snapshot ID"
        )
    require_supported_transaction_rules(snapshot)
    if snapshot.rules.acquisition.waiver_order_resets is None:
        raise SeasonSimulationError(
            "waiver-order reset behavior is unresolved for deterministic season simulation"
        )
    if not isinstance(transaction_policy, WeeklyTransactionPolicy):
        raise SeasonSimulationError(
            "transaction_policy must be WeeklyTransactionPolicy"
        )
    phases = _phase_by_week(snapshot)
    first_period = next(
        item
        for item in snapshot.matchup_periods
        if snapshot.first_simulation_week in item.scoring_weeks
    )
    if any(
        item.matchup_period_id == first_period.matchup_period_id
        and item.entry_status is MatchupEntryStatus.PARTIAL
        for item in snapshot.fantasy_matchups
    ):
        raise SeasonSimulationError(
            "simulation must start at a fully completed scoring-week boundary; first period is partial"
        )
    if (
        phases[snapshot.first_simulation_week] is MatchupPhase.POSTSEASON
        and snapshot.rules.championship.enabled is not True
    ):
        raise SeasonSimulationError("postseason horizon requires championship enabled")
    if (
        consolation_configuration is not None
        and snapshot.rules.consolation.enabled is not True
    ):
        raise SeasonSimulationError(
            "explicit consolation configuration requires enabled consolation"
        )
    return _validate_scenario(snapshot, scenario)


def _active_postseason_teams(
    state: PostseasonState, scoring_week: int
) -> tuple[int, ...]:
    return tuple(
        sorted(
            {
                team_id
                for matchup in state.championship_matchups + state.consolation_matchups
                if scoring_week in matchup.scoring_weeks
                and matchup.status.value not in {"complete", "bye"}
                for team_id in (matchup.home_team_id, matchup.away_team_id)
                if team_id is not None
            }
        )
    )


def _regular_teams(snapshot: LeagueSnapshot, scoring_week: int) -> tuple[int, ...]:
    period_ids = {
        item.matchup_period_id
        for item in snapshot.matchup_periods
        if scoring_week in item.scoring_weeks and item.phase is MatchupPhase.REGULAR
    }
    return tuple(
        sorted(
            {
                team_id
                for matchup in snapshot.fantasy_matchups
                if matchup.matchup_period_id in period_ids
                and matchup.entry_status is MatchupEntryStatus.SCHEDULED
                for team_id in (matchup.home_team_id, matchup.away_team_id)
                if team_id is not None
            }
        )
    )


def _freeze_and_score(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    scoring_week: int,
    team_ids: tuple[int, ...],
    score_index: dict[tuple[int, int], RealizedPlayerScore],
) -> tuple[tuple[OptimizedLineup, ...], tuple[FrozenTeamWeek, ...]]:
    lineups = tuple(
        optimize_starting_lineup(
            snapshot,
            team_id,
            scoring_week,
            roster_entries=state.roster_entries,
        )
        for team_id in sorted(team_ids)
    )
    frozen = []
    for lineup in lineups:
        missing = tuple(
            item.player_id
            for item in lineup.assignments
            if (item.player_id, scoring_week) not in score_index
        )
        if missing:
            raise SeasonSimulationError(
                f"team {lineup.team_id} starters {missing} lack realized scores for week {scoring_week}"
            )
        frozen.append(
            FrozenTeamWeek(
                lineup.team_id,
                lineup,
                math.fsum(
                    score_index[(item.player_id, scoring_week)].points
                    for item in lineup.assignments
                ),
            )
        )
    return lineups, tuple(frozen)


def _scenario_week_scores(
    score_index: dict[tuple[int, int], RealizedPlayerScore], scoring_week: int
) -> tuple[RealizedPlayerScore, ...]:
    return tuple(
        sorted(
            (
                score
                for (player_id, week), score in score_index.items()
                if week == scoring_week
            ),
            key=lambda item: item.player_id,
        )
    )


def _incomplete_result(
    *,
    scenario: DeterministicScoreScenario,
    snapshot: LeagueSnapshot,
    reason: str,
    initial_standings: tuple[ModeledStanding, ...],
    standings: tuple[ModeledStanding, ...],
    weeks: list[SeasonWeekTransition],
    evolving_state: EvolvingLeagueState,
    postseason_state: PostseasonState | None,
) -> DeterministicSeasonResult:
    ranking = rank_standings(snapshot, standings)
    return DeterministicSeasonResult(
        scenario.scenario_id,
        snapshot.snapshot_id,
        snapshot.season,
        SeasonCompletionStatus.INCOMPLETE,
        (reason,),
        initial_standings,
        standings,
        ranking,
        tuple(weeks),
        evolving_state,
        postseason_state,
        _team_records(
            snapshot, initial_standings, standings, ranking, postseason_state
        ),
    )


def _team_records(
    snapshot: LeagueSnapshot,
    initial: tuple[ModeledStanding, ...],
    final: tuple[ModeledStanding, ...],
    ranking: StandingsTable,
    postseason: PostseasonState | None,
) -> tuple[FinalTeamSeasonRecord, ...]:
    initial_by_team = {item.team_id: item for item in initial}
    final_by_team = {item.team_id: item for item in final}
    ranks = {item.team_id: item.rank for item in ranking.rows}
    seeds = (
        {} if postseason is None else {item.team_id: item for item in postseason.seeds}
    )
    placements = (
        {}
        if postseason is None
        else {item.team_id: item.place for item in postseason.placements}
    )
    return tuple(
        FinalTeamSeasonRecord(
            team_id,
            initial_by_team[team_id],
            final_by_team[team_id],
            ranks.get(team_id),
            seeds[team_id].championship_qualifier if team_id in seeds else None,
            seeds[team_id].original_seed if team_id in seeds else None,
            placements.get(team_id),
        )
        for team_id in sorted(final_by_team)
    )


def simulate_deterministic_season(
    snapshot: LeagueSnapshot,
    scenario: DeterministicScoreScenario,
    *,
    ir_policy: IRPolicy,
    transaction_policy: WeeklyTransactionPolicy,
    consolation_configuration: ConsolationLadderConfiguration | None = None,
    season_acquisition_counts: dict[int, int] | None = None,
    matchup_acquisition_counts: dict[int, int] | None = None,
    ir_eligibility_evidence: tuple[IREligibilityEvidence, ...] = (),
) -> DeterministicSeasonResult:
    """Execute one settings-driven deterministic path without network or randomness."""

    score_index = _preflight(
        snapshot, scenario, transaction_policy, consolation_configuration
    )
    phases = _phase_by_week(snapshot)
    initial_standings = initialize_standings(snapshot)
    standings = initial_standings
    evolving = initialize_evolving_state(
        snapshot,
        scoring_week=snapshot.first_simulation_week,
        ir_policy=ir_policy,
        season_acquisition_counts=season_acquisition_counts,
        matchup_acquisition_counts=matchup_acquisition_counts,
        ir_eligibility_evidence=ir_eligibility_evidence,
    )
    postseason: PostseasonState | None = None
    weeks: list[SeasonWeekTransition] = []

    for scoring_week in range(
        snapshot.first_simulation_week, snapshot.final_simulation_week + 1
    ):
        if scoring_week != snapshot.first_simulation_week:
            evolving = advance_cycle(
                evolving,
                snapshot,
                cycle_id=evolving.cycle_id + 1,
                scoring_week=scoring_week,
            )
            if snapshot.rules.acquisition.waiver_order_resets is True:
                ranking = rank_standings(snapshot, standings)
                if not ranking.has_unique_order:
                    return _incomplete_result(
                        scenario=scenario,
                        snapshot=snapshot,
                        reason=f"week_{scoring_week}_waiver_reset_ranking_unresolved",
                        initial_standings=initial_standings,
                        standings=standings,
                        weeks=weeks,
                        evolving_state=evolving,
                        postseason_state=postseason,
                    )
                evolving = reset_waiver_priority(
                    evolving,
                    snapshot,
                    ordered_team_ids=tuple(reversed(ranking.require_unique_order())),
                )

        phase = phases[scoring_week]
        if phase is MatchupPhase.POSTSEASON and postseason is None:
            final_ranking = rank_standings(snapshot, standings)
            if not final_ranking.has_unique_order:
                return _incomplete_result(
                    scenario=scenario,
                    snapshot=snapshot,
                    reason="postseason_seeding_unresolved",
                    initial_standings=initial_standings,
                    standings=standings,
                    weeks=weeks,
                    evolving_state=evolving,
                    postseason_state=None,
                )
            try:
                postseason = initialize_postseason(
                    snapshot,
                    standings,
                    consolation_configuration=consolation_configuration,
                )
            except PostseasonError as exc:
                raise SeasonSimulationError(
                    f"postseason initialization failed: {exc}"
                ) from exc

        transaction_result = execute_weekly_essential_transactions(
            snapshot, evolving, transaction_policy
        )
        evolving = transaction_result.state
        logical_transaction_result = replace(transaction_result, valuation_seconds=0.0)
        validate_evolving_state(evolving, snapshot)
        unresolved_teams = {
            item.team_id
            for item in transaction_result.decisions
            if item.outcome is DecisionOutcome.UNRESOLVED_AUTHORIZATION
        }
        materially_unresolved = tuple(
            team_id
            for team_id in sorted(unresolved_teams)
            if optimize_starting_lineup(
                snapshot,
                team_id,
                scoring_week,
                roster_entries=evolving.roster_entries,
            ).vacancy_count
            > 0
        )
        if materially_unresolved:
            return _incomplete_result(
                scenario=scenario,
                snapshot=snapshot,
                reason=(
                    f"week_{scoring_week}_transaction_authorization_unresolved_for_teams_"
                    + "_".join(map(str, materially_unresolved))
                ),
                initial_standings=initial_standings,
                standings=standings,
                weeks=weeks,
                evolving_state=evolving,
                postseason_state=postseason,
            )

        if phase is MatchupPhase.REGULAR:
            team_ids = _regular_teams(snapshot, scoring_week)
        else:
            assert postseason is not None
            team_ids = _active_postseason_teams(postseason, scoring_week)
        lineups, frozen = _freeze_and_score(
            snapshot, evolving, scoring_week, team_ids, score_index
        )
        scores = _scenario_week_scores(score_index, scoring_week)
        regular_transition = None
        if phase is MatchupPhase.REGULAR:
            regular_transition = resolve_regular_season_week(
                snapshot,
                scoring_week,
                standings,
                lineups,
                scores,
                roster_entries=evolving.roster_entries,
            )
            standings = regular_transition.standings
        else:
            assert postseason is not None
            postseason = score_frozen_postseason_week(
                snapshot,
                postseason,
                scoring_week,
                lineups,
                scores,
                roster_entries=evolving.roster_entries,
            )
        weeks.append(
            SeasonWeekTransition(
                scoring_week,
                phase,
                logical_transaction_result,
                frozen,
                regular_transition,
                postseason,
            )
        )

    ranking = rank_standings(snapshot, standings)
    unresolved = ()
    status = SeasonCompletionStatus.COMPLETE
    if postseason is None:
        unresolved = ("postseason_not_in_simulation_horizon",)
        status = SeasonCompletionStatus.INCOMPLETE
    elif not final_positions_complete(postseason, len(snapshot.teams)):
        unresolved = postseason.unresolved_capabilities or (
            "complete_league_placements_unavailable",
        )
        status = SeasonCompletionStatus.INCOMPLETE
    records = _team_records(snapshot, initial_standings, standings, ranking, postseason)
    if status is SeasonCompletionStatus.COMPLETE:
        champions = tuple(item for item in records if item.final_placement == 1)
        if len(champions) != 1:
            raise SeasonSimulationError(
                "complete season must contain exactly one champion"
            )
    return DeterministicSeasonResult(
        scenario.scenario_id,
        snapshot.snapshot_id,
        snapshot.season,
        status,
        tuple(sorted(unresolved)),
        initial_standings,
        standings,
        ranking,
        tuple(weeks),
        evolving,
        postseason,
        records,
    )
