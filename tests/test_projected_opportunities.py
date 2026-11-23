from fastapi.testclient import TestClient

from fantasy_football.app.contracts import ProjectedBaselineRequest, SnapshotSelector
from fantasy_football.app.http import create_app
from fantasy_football.app.projected_baseline import prepare_projection_request
from fantasy_football.app.service import ApplicationDependencies, ApplicationService
from fantasy_football.effective_trades import (
    TradeTransfer,
    inspect_trade_timing,
    prepare_trade_timeline,
)
from fantasy_football.evolving_state import initialize_evolving_state
from fantasy_football.monte_carlo import MonteCarloConfig
from fantasy_football.monte_carlo_precision import PrecisionConfiguration
from fantasy_football.projected_opportunities import (
    discover_projected_intents,
    evaluate_projected_opportunities,
    prepare_discovered_trade,
)
from fantasy_football.projected_season import (
    ProjectedSeasonInputs,
    compare_projected_scenario,
)
from fantasy_football.scenario_evaluator import evaluate_manual_scenario
from fantasy_football.snapshot_store import SnapshotStore
from fantasy_football.trade_candidates import TradeShape
from fantasy_football.unified_actions import (
    ActionFamily,
    ActionOrdering,
    UnifiedActionSearchConfiguration,
    enumerate_unified_action_candidates,
    evaluate_unified_action_states,
)
from fantasy_football.weekly_transactions import WaiverBoundaryPolicy
from tests.test_app_service import FixtureStore
from tests.test_current_week import _bundle, _publish
from tests.test_monte_carlo import PrescribedModel
from tests.test_scenario_evaluator import _scenario_snapshot

ROUTE = "/api/v1/analyses/projected-opportunities"


def _request(loaded):
    return ProjectedBaselineRequest(
        snapshot=SnapshotSelector(snapshot_id=loaded.metadata.snapshot_id),
        canonical_sha256=loaded.metadata.canonical_sha256,
    )


def _config(team, rival, player_ids):
    return UnifiedActionSearchConfiguration(
        team,
        (ActionFamily.TRADE,),
        (ActionOrdering.STANDALONE_TRADE,),
        counterparty_team_ids=(rival,),
        tradeable_player_ids=player_ids,
        trade_shapes=(TradeShape(1, 1),),
        maximum_completed_paths=6,
        waiver_boundary=WaiverBoundaryPolicy.MODELED_WEEKLY_V1,
    )


def test_discovered_structural_comparison_exactly_matches_manual_and_sampled_paths(
    monkeypatch,
):
    snapshot = _scenario_snapshot()
    loaded = FixtureStore(snapshot).loaded
    inputs = prepare_projection_request(loaded, _request(loaded))
    config = _config(1, 2, (1, 2))
    execute = ProjectedSeasonInputs.execute
    calls = []

    def count(self, **kwargs):
        calls.append(kwargs)
        return execute(self, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(ProjectedSeasonInputs, "execute", count)
        search = evaluate_projected_opportunities(
            inputs, (), config, should_stop=lambda: False
        )
    assert len(calls) == 2
    assert search.evaluation_complete
    (row,) = search.candidates
    assert row.evaluation_index == 0 and not row.timeline
    baseline, hypothetical, completed = compare_projected_scenario(
        inputs, row.candidate.scenario
    )
    assert search.baseline == baseline
    assert search.evaluations[0] == hypothetical
    assert completed == row.candidate.completed

    state = initialize_evolving_state(
        snapshot,
        scoring_week=snapshot.first_simulation_week,
        ir_policy=inputs.ir_policy,
    )
    enumeration = enumerate_unified_action_candidates(snapshot, state, config)
    mc = MonteCarloConfig(41, 2, 0, inputs.ir_policy, inputs.transaction_policy)
    precision = PrecisionConfiguration(0.95, 0.9, 1, 2, 1)
    model = PrescribedModel()
    discovered = evaluate_unified_action_states(
        snapshot, state, enumeration, mc, model, precision
    )
    manual = evaluate_manual_scenario(
        snapshot, state, row.candidate.scenario, mc, model, precision
    )
    assert discovered.evaluations[0].comparison == manual


def test_live_discovery_uses_manual_timeline_and_preserves_original_scoring(tmp_path):
    bundle = _bundle()
    for source in (bundle.league_initial, bundle.league_reconciliation):
        source.payload["settings"]["tradeSettings"]["deadlineDate"] = 1798000000000
        source.payload["settings"]["scheduleSettings"]["consolationLadderDisabled"] = (
            True
        )
    snapshot, responses = _publish(tmp_path, bundle)
    loaded = SnapshotStore(tmp_path / "snapshots.sqlite3").load(snapshot.snapshot_id)
    inputs = prepare_projection_request(loaded, _request(loaded))
    search = evaluate_projected_opportunities(
        inputs, responses, _config(2, 4, (2, 4)), should_stop=lambda: False
    )
    (row,) = search.candidates
    assert row.limitation is None
    manual_timeline = prepare_trade_timeline(
        snapshot, responses, ((None, (TradeTransfer(2, 2, 4), TradeTransfer(4, 4, 2))),)
    )
    assert row.timeline == manual_timeline and row.timeline[0].scoring_week == 3
    before, after, _ = compare_projected_scenario(
        inputs, row.candidate.scenario, trades=manual_timeline
    )
    assert search.baseline == before
    assert search.evaluations[row.evaluation_index] == after
    assert after[0].initial_standings == before[0].initial_standings
    assert after[0].weeks[0] == before[0].weeks[0]
    assert (
        next(score for player_id, score in after[1] if player_id == 2).points == 13.25
    )

    state = initialize_evolving_state(
        snapshot,
        scoring_week=snapshot.first_simulation_week,
        ir_policy=inputs.ir_policy,
    )
    config = _config(1, 4, (-101, 4))
    _, _, _, (eligible,) = discover_projected_intents(
        inputs, state, config, should_stop=lambda: False
    )
    timing = inspect_trade_timing(snapshot, responses)
    immediate = prepare_discovered_trade(
        snapshot, state, eligible, inputs.current.evidence, timing
    )
    delayed = prepare_discovered_trade(
        snapshot, state, eligible, inputs.current.evidence, timing, selected_week=3
    )
    assert immediate != delayed
    assert immediate[0].scoring_week == 2 and delayed[0].scoring_week == 3
    _, immediate_result, _ = compare_projected_scenario(
        inputs, eligible.scenario, trades=immediate
    )
    _, delayed_result, _ = compare_projected_scenario(
        inputs, eligible.scenario, trades=delayed
    )
    assert immediate_result[0].weeks[0] != delayed_result[0].weeks[0]

    absent = evaluate_projected_opportunities(
        inputs, (), config, should_stop=lambda: False
    )
    assert absent.baseline is None and not absent.evaluation_complete
    assert absent.candidates[0].limitation


def test_projected_search_endpoint_matches_standalone_baseline_and_reports_limits():
    store = FixtureStore(_scenario_snapshot())
    request = _request(store.loaded).model_dump(mode="json")
    with TestClient(
        create_app(ApplicationService(ApplicationDependencies(store)))
    ) as client:
        standalone = client.post("/api/v1/analyses/projected-baseline", json=request)
        result = client.post(
            ROUTE, json={**request, "requesting_team_id": 1, "counterparty_team_id": 2}
        )
        invalid = client.post(
            ROUTE, json={**request, "requesting_team_id": 1, "counterparty_team_id": 1}
        )
    assert result.status_code == 200, result.json()
    assert invalid.status_code == 422
    body = result.json()
    assert body["baseline"]["season"] == standalone.json()
    assert body["candidate_coverage_complete"] and body["evaluation_coverage_complete"]
    assert "ranking_resolved" not in body
    assert "precision" not in body


def test_cancelled_projection_search_never_runs_a_season(monkeypatch):
    snapshot = _scenario_snapshot()
    loaded = FixtureStore(snapshot).loaded
    inputs = prepare_projection_request(loaded, _request(loaded))

    def unexpected(*args, **kwargs):
        raise AssertionError("cancelled search evaluated a season")

    monkeypatch.setattr(ProjectedSeasonInputs, "execute", unexpected)
    result = evaluate_projected_opportunities(
        inputs, (), _config(1, 2, (1, 2)), should_stop=lambda: True
    )
    assert not result.coverage_complete
    assert not result.evaluations


def test_structural_chains_share_evaluations_without_losing_their_ordered_paths():
    from tests.test_scenario_evaluator import _scenario_snapshot_with_bench
    from tests.test_unified_actions import _trade_config

    snapshot = _scenario_snapshot_with_bench()
    loaded = FixtureStore(snapshot).loaded
    inputs = prepare_projection_request(loaded, _request(loaded))
    config = _trade_config(
        action_families=(ActionFamily.TRADE_CHAIN,),
        action_orderings=(ActionOrdering.STANDALONE_CHAIN,),
        counterparty_team_ids=(2, 3),
        tradeable_player_ids=(1, 2, 3, 10, 11, 12),
        minimum_trade_chain_length=3,
        maximum_trade_chain_length=3,
        maximum_total_action_count=3,
        maximum_completed_paths=100,
        waiver_boundary=WaiverBoundaryPolicy.MODELED_WEEKLY_V1,
    )
    result = evaluate_projected_opportunities(
        inputs, (), config, should_stop=lambda: False
    )
    groups = {}
    for row in result.candidates:
        assert row.limitation is None
        groups.setdefault(row.evaluation_index, []).append(row)
    duplicated = next(rows for rows in groups.values() if len(rows) > 1)
    assert len({row.candidate.candidate_id for row in duplicated}) == len(duplicated)
    assert len({row.candidate.actions for row in duplicated}) > 1
    assert len({row.candidate.completed_state_sha256 for row in duplicated}) == 1
    assert len(result.evaluations) == len(groups) < len(result.candidates)
