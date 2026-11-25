"""Application serialization for projection-fed season analysis."""

from fantasy_football.app.contracts import (
    JourneyStandingsPoint,
    JourneyTeamRank,
    ProjectedBaselineResult,
    ProjectedChampionshipRound,
    ProjectedObservedScore,
    ProjectedSeasonWeek,
)
from fantasy_football.automatic_rosters import automatic_policy_from_loaded_snapshot
from fantasy_football.canonical.model import LeagueSnapshot, MatchupPhase
from fantasy_football.canonical.validation import validated_snapshot
from fantasy_football.evolving_state import IRPolicy
from fantasy_football.postseason import PostseasonState
from fantasy_football.projected_season import prepare_projected_season
from fantasy_football.season_simulator import DeterministicSeasonResult
from fantasy_football.weekly_engine import WeeklyEngineError, rank_standings
from fantasy_football.weekly_transactions import (
    WaiverBoundaryPolicy,
    WeeklyTransactionPolicy,
)


def prepare_projection_request(loaded, request, *, observed_lineup=False):
    return prepare_projected_season(
        loaded.snapshot,
        tuple(item.response for item in loaded.raw_sources),
        IRPolicy(request.ir_policy),
        WeeklyTransactionPolicy(
            WaiverBoundaryPolicy(request.waiver_boundary),
            request.reject_incomplete_valuations,
            automatic_rosters=automatic_policy_from_loaded_snapshot(
                loaded, request.standings_fallback_seed
            ),
        ),
        observed_lineup=observed_lineup,
    )


def project_baseline(loaded, request) -> ProjectedBaselineResult:
    with validated_snapshot(loaded.snapshot):
        inputs = prepare_projection_request(loaded, request)
        result, observations = inputs.execute()
        standings_series = _standings_series(
            inputs.snapshot, result, request.standings_fallback_seed
        )
    postseason = result.final_postseason_state
    return projected_season_result(
        loaded.metadata.canonical_sha256,
        inputs,
        result,
        observations,
        standings_series=standings_series,
        championship_rounds=_projected_rounds(inputs.snapshot, postseason),
        consolation_rounds=_projected_rounds(
            inputs.snapshot, postseason, consolation=True
        ),
    )


def _projected_rounds(
    snapshot: LeagueSnapshot,
    postseason: PostseasonState | None,
    *,
    consolation: bool = False,
) -> tuple[ProjectedChampionshipRound, ...]:
    rules = snapshot.rules.consolation if consolation else snapshot.rules.championship
    if rules.enabled is not True:
        return ()
    periods = {
        period.matchup_period_id: period.scoring_weeks
        for period in snapshot.matchup_periods
        if period.phase is MatchupPhase.POSTSEASON
    }
    graph = None
    if postseason is not None:
        graph = (
            postseason.consolation_graph
            if consolation
            else postseason.championship_graph
        )
    nodes = graph.nodes if graph is not None else ()
    if (
        consolation
        and postseason is not None
        and postseason.consolation_configuration is not None
    ):
        # Explicit ladder transitions replace the generic graph after opening pairings.
        nodes = tuple(node for node in nodes if node.round_number == 1)
    return tuple(
        ProjectedChampionshipRound(
            round_number=round_.round_number,
            matchup_period_id=round_.matchup_period_id,
            scoring_weeks=periods.get(round_.matchup_period_id, ()),
            nodes=tuple(
                node for node in nodes if node.round_number == round_.round_number
            ),
        )
        for round_ in sorted(rules.rounds, key=lambda row: row.round_number)
    )


def _standings_series(
    snapshot: LeagueSnapshot,
    result: DeterministicSeasonResult,
    fallback_seed: int | None,
) -> tuple[JourneyStandingsPoint, ...]:
    periods = {
        week: period.matchup_period_id
        for period in snapshot.matchup_periods
        if period.phase is MatchupPhase.REGULAR
        for week in period.scoring_weeks
        if snapshot.first_simulation_week <= week <= snapshot.final_simulation_week
    }
    teams = sorted(snapshot.teams, key=lambda team: team.team_id)
    points = []
    first = snapshot.first_simulation_week
    if first in periods:
        observed = tuple(
            JourneyTeamRank(
                team_id=team.team_id,
                rank=team.standing
                if team.standing is not None and 1 <= team.standing <= len(teams)
                else None,
            )
            for team in teams
        )
        known = sum(row.rank is not None for row in observed)
        points.append(
            JourneyStandingsPoint(
                scoring_week=first,
                matchup_period_id=periods[first],
                basis="snapshot_start",
                status="complete"
                if known == len(teams)
                else "unresolved"
                if known
                else "unavailable",
                teams=observed,
            )
        )
    trace = {week.scoring_week: week.regular_transition for week in result.weeks}
    for scoring_week, period in sorted(periods.items()):
        transition = trace.get(scoring_week)
        ranking = transition.ranking if transition else None
        if transition and fallback_seed is not None:
            try:
                ranking = rank_standings(
                    snapshot, transition.standings, fallback_seed=fallback_seed
                )
            except WeeklyEngineError:
                # The configured fallback can be unsupported for this weekly table.
                ranking = None
        rows = (
            tuple(
                JourneyTeamRank(
                    team_id=row.team_id,
                    rank=row.rank,
                    unresolved_tie=not row.uniquely_ranked,
                )
                for row in ranking.rows
            )
            if ranking
            else tuple(
                JourneyTeamRank(team_id=team.team_id, rank=None) for team in teams
            )
        )
        points.append(
            JourneyStandingsPoint(
                scoring_week=scoring_week,
                matchup_period_id=period,
                basis="projected",
                status=("complete" if ranking.has_unique_order else "unresolved")
                if ranking
                else "unavailable",
                teams=rows,
            )
        )
    return tuple(points)


def projected_season_result(
    canonical_sha256,
    inputs,
    result,
    observations,
    *,
    standings_series=None,
    championship_rounds=None,
    consolation_rounds=None,
):
    snapshot = inputs.snapshot
    current = inputs.current
    observed_week = current.evidence.scoring_period if current else None
    projection_sources = {
        row.player_id: row.source_id
        for row in snapshot.player_weeks
        if observed_week is not None
        and row.scoring_week == observed_week
        and row.raw_projection is not None
    }
    observations = tuple(
        ProjectedObservedScore(
            player_id=pid,
            scoring_week=observed_week,
            points=score.points,
            basis=score.basis,
            observed_points=score.observed_points,
            source_id=score.source_id,
            projection_source_id=projection_sources.get(pid)
            if score.basis in {"projection", "projected_final"}
            else None,
        )
        for pid, score in observations
    )
    postseason = result.final_postseason_state
    champion = (
        next((p.team_id for p in postseason.placements if p.place == 1), None)
        if postseason
        else None
    )
    projected_rows = tuple(
        row
        for row in snapshot.player_weeks
        if snapshot.first_simulation_week
        <= row.scoring_week
        <= snapshot.final_simulation_week
        and row.scoring_week != observed_week
    )
    return ProjectedBaselineResult(
        championship_rounds=championship_rounds,
        consolation_rounds=consolation_rounds,
        standings_series=standings_series,
        snapshot_id=result.source_snapshot_id,
        canonical_sha256=canonical_sha256,
        status=result.status.value,
        teams=result.team_records,
        weeks=tuple(
            ProjectedSeasonWeek(
                scoring_week=week.scoring_week,
                phase=week.phase.value,
                lineups=week.frozen_team_weeks,
                matchups=week.regular_transition.matchup_results
                if week.regular_transition
                else (),
            )
            for week in result.weeks
        ),
        postseason=postseason.championship_matchups + postseason.consolation_matchups
        if postseason
        else (),
        champion_team_id=champion,
        transactions=result.final_evolving_state.ledger,
        observed_source_ids=current.evidence.source_ids if current else (),
        observed_scores=tuple(observations),
        projection_source_ids=tuple(sorted({row.source_id for row in projected_rows})),
        missing_projection_count=sum(
            row.raw_projection is None for row in projected_rows
        ),
        assumptions=(
            "canonical-projections-v1",
            f"ir_policy:{inputs.ir_policy.value}",
            f"waiver_boundary:{inputs.transaction_policy.waiver_boundary.value}",
            f"reject_incomplete_valuations:{inputs.transaction_policy.reject_incomplete_valuations}",
            *result.configuration_provenance,
        ),
        unresolved_capabilities=result.unresolved_capabilities,
    )
