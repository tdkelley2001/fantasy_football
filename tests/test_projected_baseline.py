from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from fantasy_football.app.http import create_app
from fantasy_football.app.projected_baseline import _projected_rounds, _standings_series
from fantasy_football.app.service import ApplicationDependencies, ApplicationService
from fantasy_football.automatic_rosters import automatic_policy_from_loaded_snapshot
from fantasy_football.espn_adapter import translate_bundle
from fantasy_football.evolving_state import IRPolicy
from fantasy_football.live_scoring import NFLGameStatus
from fantasy_football.monte_carlo import MonteCarloConfig, run_monte_carlo_path
from fantasy_football.partial_week import (
    PartialPlayerState,
    PlayerScoreState,
    RemainingContributionStatus,
)
from fantasy_football.player_outcomes import (
    PreparedNormalOutcomes,
    ProvisionalNormalModel,
)
from fantasy_football.postseason import (
    ConsolationLadderConfiguration,
    LadderTransition,
    initialize_postseason,
)
from fantasy_football.score_resolution import projected_scores, resolve_observed_score
from fantasy_football.season_simulator import (
    DeterministicScoreScenario,
    simulate_deterministic_season,
)
from fantasy_football.weekly_engine import ModeledStanding, rank_standings
from fantasy_football.weekly_transactions import (
    WaiverBoundaryPolicy,
    WeeklyTransactionPolicy,
)
from tests.adapter_fixtures import source_bundle
from tests.test_app_service import FixtureStore
from tests.test_postseason import _snapshot as _postseason_snapshot
from tests.test_postseason import _standings as _postseason_standings
from tests.test_scenario_evaluator import _scenario_snapshot
from tests.test_weekly_engine import _supported_snapshot

ROUTE = "/api/v1/analyses/projected-baseline"


@pytest.mark.parametrize("qualifiers, explicit", [(6, False), (5, False), (6, True)])
def test_consolation_rounds_expose_only_the_authoritative_graph(qualifiers, explicit):
    snapshot = _postseason_snapshot(qualifier_count=qualifiers)
    config = (
        ConsolationLadderConfiguration(
            tuple(
                LadderTransition(round_number, upper, upper + 1, upper, upper + 1)
                for round_number in (1, 2, 3)
                for upper in (7, 9, 11, 13)
            ),
            tuple((position, position) for position in range(7, 15)),
        )
        if explicit
        else None
    )
    state = initialize_postseason(
        snapshot, _postseason_standings(snapshot), consolation_configuration=config
    )
    rounds = _projected_rounds(snapshot, state, consolation=True)

    assert [round_.scoring_weeks for round_ in rounds] == [(15,), (16,), (17, 18)]
    assert rounds[0].nodes
    assert state.consolation_graph is not None
    if explicit or qualifiers == 5:
        assert len(rounds[0].nodes) == (4 if explicit else 5)
        assert all(not round_.nodes for round_ in rounds[1:])
    else:
        assert tuple(node for round_ in rounds for node in round_.nodes) == (
            state.consolation_graph.nodes
        )
        assert {
            source.outcome for node in rounds[1].nodes for source in node.sources
        } == {
            "winner",
            "loser",
        }


@pytest.mark.parametrize(
    "game,status,actual,projection,points,basis",
    [
        (
            NFLGameStatus.COMPLETED,
            PlayerScoreState.COMPLETED_FIXED,
            -2,
            9,
            -2,
            "final_actual",
        ),
        (
            NFLGameStatus.IN_PROGRESS,
            PlayerScoreState.IN_PROGRESS,
            5,
            -3,
            -3,
            "projected_final",
        ),
        (NFLGameStatus.SCHEDULED, PlayerScoreState.UNSTARTED, None, 0, 0, "projection"),
        (
            NFLGameStatus.UNKNOWN,
            PlayerScoreState.MISSING,
            None,
            None,
            None,
            "unresolved",
        ),
        (
            NFLGameStatus.UNKNOWN,
            PlayerScoreState.NONPARTICIPATING,
            None,
            None,
            0,
            "verified_nonparticipation",
        ),
    ],
)
def test_resolve_with_source(game, status, actual, projection, points, basis):
    state = PartialPlayerState(
        1,
        game,
        status,
        actual,
        projection,
        RemainingContributionStatus.UNRESOLVED,
        "espn-page",
    )
    score = resolve_observed_score(state)
    assert (score.points, score.basis, score.observed_points, score.source_id) == (
        points,
        basis,
        actual,
        "espn-page",
    )
    with pytest.raises(ValueError, match="source identity"):
        resolve_observed_score(replace(state, source_id=""))


def test_contradictory_and_unsupported_score_observations():
    state = PartialPlayerState(
        1,
        NFLGameStatus.IN_PROGRESS,
        PlayerScoreState.IN_PROGRESS,
        5,
        None,
        RemainingContributionStatus.UNRESOLVED,
        "espn-page",
    )
    assert resolve_observed_score(state).points is None
    with pytest.raises(ValueError, match="requires a full-game projection"):
        resolve_observed_score(state, sampled_points=7)
    with pytest.raises(ValueError, match="projection and no actual"):
        resolve_observed_score(replace(state, score_state=PlayerScoreState.UNSTARTED))


def test_projected_baseline_http_matches_direct_and_identical_monte_carlo_scores(
    monkeypatch,
):
    snapshot = _scenario_snapshot()
    store = FixtureStore(snapshot)
    request = {
        "snapshot": {"snapshot_id": snapshot.snapshot_id},
        "canonical_sha256": store.loaded.metadata.canonical_sha256,
    }
    policy = WeeklyTransactionPolicy(
        WaiverBoundaryPolicy.MODELED_WEEKLY_V1,
        True,
        automatic_rosters=automatic_policy_from_loaded_snapshot(store.loaded, None),
    )
    scenario = DeterministicScoreScenario(
        "canonical-projections-v1", projected_scores(snapshot, observed_week=None)
    )
    direct = simulate_deterministic_season(
        snapshot,
        scenario,
        ir_policy=IRPolicy.PROJECTION_BASED,
        transaction_policy=policy,
    )

    def unexpected(*args, **kwargs):
        pytest.fail("Projected baseline called the stochastic outcome model")

    monkeypatch.setattr(ProvisionalNormalModel, "generate_scenario", unexpected)
    monkeypatch.setattr(PreparedNormalOutcomes, "__init__", unexpected)
    with TestClient(
        create_app(ApplicationService(ApplicationDependencies(store)))
    ) as client:
        response = client.post(ROUTE, json=request)
        assert response.status_code == 200, response.json()
        assert client.post(ROUTE, json={**request, "master_seed": 7}).status_code == 422
        assert (
            client.post(
                ROUTE, json={**request, "canonical_sha256": "wrong"}
            ).status_code
            == 422
        )
    payload = response.json()
    assert payload["champion_team_id"] == next(
        team.team_id for team in direct.team_records if team.final_placement == 1
    )
    assert payload["teams"] == TypeAdapter(type(direct.team_records)).dump_python(
        direct.team_records, mode="json"
    )
    postseason = direct.final_postseason_state
    assert postseason is not None
    bracket = postseason.championship_matchups + postseason.consolation_matchups
    assert payload["postseason"] == TypeAdapter(tuple).dump_python(bracket, mode="json")
    assert postseason.championship_graph is not None
    periods = {
        period.matchup_period_id: period.scoring_weeks
        for period in snapshot.matchup_periods
    }
    assert payload["championship_rounds"] == [
        {
            "round_number": round_.round_number,
            "matchup_period_id": round_.matchup_period_id,
            "scoring_weeks": list(periods[round_.matchup_period_id]),
            "nodes": TypeAdapter(tuple).dump_python(
                tuple(
                    node
                    for node in postseason.championship_graph.nodes
                    if node.round_number == round_.round_number
                ),
                mode="json",
            ),
        }
        for round_ in snapshot.rules.championship.rounds
    ]
    consolation_nodes = (
        postseason.consolation_graph.nodes if postseason.consolation_graph else ()
    )
    assert payload["consolation_rounds"] == [
        {
            "round_number": round_.round_number,
            "matchup_period_id": round_.matchup_period_id,
            "scoring_weeks": list(periods[round_.matchup_period_id]),
            "nodes": TypeAdapter(tuple).dump_python(
                tuple(
                    node
                    for node in consolation_nodes
                    if node.round_number == round_.round_number
                ),
                mode="json",
            ),
        }
        for round_ in snapshot.rules.consolation.rounds
        if snapshot.rules.consolation.enabled is True
    ]
    assert payload["transactions"] == TypeAdapter(tuple).dump_python(
        direct.final_evolving_state.ledger, mode="json"
    )
    assert payload["weeks"]
    for row, week in zip(payload["weeks"], direct.weeks, strict=True):
        assert row["lineups"] == TypeAdapter(tuple).dump_python(
            week.frozen_team_weeks, mode="json"
        )
        matchups = (
            week.regular_transition.matchup_results if week.regular_transition else ()
        )
        assert row["matchups"] == TypeAdapter(tuple).dump_python(matchups, mode="json")

    series = payload["standings_series"]
    start = series[0]
    assert (start["basis"], start["scoring_week"]) == (
        "snapshot_start",
        snapshot.first_simulation_week,
    )
    assert {row["team_id"]: row["rank"] for row in start["teams"]} == {
        team.team_id: team.standing for team in snapshot.teams
    }
    periods = {
        week: period.matchup_period_id
        for period in snapshot.matchup_periods
        for week in period.scoring_weeks
    }
    regular = [
        week.regular_transition for week in direct.weeks if week.regular_transition
    ]
    for point, transition in zip(series[1:], regular, strict=True):
        assert point["basis"] == "projected"
        assert point["scoring_week"] == transition.scoring_week
        assert point["matchup_period_id"] == periods[transition.scoring_week]
        assert point["teams"] == [
            {
                "team_id": row.team_id,
                "rank": row.rank,
                "unresolved_tie": not row.uniquely_ranked,
            }
            for row in transition.ranking.rows
        ]

    class PrescribedModel:
        model_id = "prescribed-projector"
        parameters = ()

        def generate_scenario(self, snapshot, *, master_seed, path_index):
            return scenario

    _, path = run_monte_carlo_path(
        snapshot,
        MonteCarloConfig(9, 1, 0, IRPolicy.PROJECTION_BASED, policy),
        PrescribedModel(),
        0,
        retain_result=True,
    )
    assert path == direct


@pytest.mark.parametrize("with_membership", [True, False])
def test_live_unplayed_baseline_requires_authoritative_period_membership(
    with_membership,
):
    snapshot = unplayed_live_snapshot()
    live = snapshot.live_scoring
    assert live is not None and not live.partial_week_simulation_required
    if not with_membership:
        snapshot = replace(
            snapshot,
            live_scoring=replace(live, current_matchup_period_scoring_weeks=()),
        )
    store = FixtureStore(snapshot)
    with TestClient(
        create_app(ApplicationService(ApplicationDependencies(store)))
    ) as client:
        response = client.post(
            ROUTE,
            json={
                "snapshot": {"snapshot_id": snapshot.snapshot_id},
                "canonical_sha256": store.loaded.metadata.canonical_sha256,
            },
        )
    if with_membership:
        assert response.status_code == 200, response.json()
        assert (
            response.json()["weeks"][0]["scoring_week"] == live.current_scoring_period
        )
        assert response.json()["observed_scores"] == []
    else:
        assert response.status_code == 422, response.json()
        assert "authoritative current matchup-period membership" in response.text


def unplayed_live_snapshot():
    snapshot = translate_bundle(source_bundle()).snapshot
    live = snapshot.live_scoring
    assert live is not None
    assert live.supported_simulation_week == snapshot.first_simulation_week == 2
    # Give each team one fillable starter slot for an otherwise unchanged live fixture.
    return replace(
        snapshot,
        snapshot_id="unplayed-live",
        rules=replace(
            snapshot.rules,
            lineup_slots=tuple(
                slot for slot in snapshot.rules.lineup_slots if slot.slot_id in (0, 21)
            ),
            position_limits=(),
            consolation=replace(
                snapshot.rules.consolation, rounds=snapshot.rules.championship.rounds
            ),
        ),
        players=tuple(
            replace(
                player, eligible_lineup_slot_ids=(0, *player.eligible_lineup_slot_ids)
            )
            if player.player_id == -101
            else replace(player, acquisition_status="UNKNOWN")
            if player.player_id == 5
            else player
            for player in snapshot.players
        ),
        roster_entries=tuple(
            replace(entry, lineup_slot_id=0) if entry.player_id == -101 else entry
            for entry in snapshot.roster_entries
        ),
    )


def test_standings_series_preserves_shared_ranks_and_marks_unexecuted_weeks():
    snapshot = _supported_snapshot(two_regular_weeks=True)
    direct = simulate_deterministic_season(
        snapshot,
        DeterministicScoreScenario(
            "journey", projected_scores(snapshot, observed_week=None)
        ),
        ir_policy=IRPolicy.PROJECTION_BASED,
        transaction_policy=WeeklyTransactionPolicy(
            WaiverBoundaryPolicy.MODELED_WEEKLY_V1, True
        ),
    )
    first = direct.weeks[0]
    assert first.regular_transition is not None
    standings = (
        ModeledStanding(1, 6, 4, 0, 110, 100),
        ModeledStanding(2, 6, 4, 0, 110, 99),
        ModeledStanding(3, 6, 4, 0, 100, 99),
        ModeledStanding(4, 5, 5, 0, 120, 99),
    )
    transition = replace(
        first.regular_transition,
        standings=standings,
        ranking=rank_standings(snapshot, standings),
    )
    incomplete = replace(direct, weeks=(replace(first, regular_transition=transition),))
    missing_start = replace(
        snapshot, teams=tuple(replace(team, standing=None) for team in snapshot.teams)
    )
    start, ranked, missing = _standings_series(missing_start, incomplete, None)
    assert start.status == "unavailable"
    assert ranked.status == "unresolved"
    assert {row.team_id: (row.rank, row.unresolved_tie) for row in ranked.teams} == {
        1: (1, True),
        2: (1, True),
        3: (3, False),
        4: (4, False),
    }
    assert (missing.scoring_week, missing.matchup_period_id, missing.status) == (
        16,
        3,
        "unavailable",
    )
    assert all(row.rank is None for row in missing.teams)
    _, resolved, _ = _standings_series(snapshot, incomplete, 17)
    assert [(row.team_id, row.rank) for row in resolved.teams] == [
        (row.team_id, row.rank)
        for row in rank_standings(snapshot, standings, fallback_seed=17).rows
    ]
    assert resolved.status == "complete"
