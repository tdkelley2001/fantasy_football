from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from fantasy_football.evolving_state import IRPolicy
from fantasy_football.monte_carlo import (
    MonteCarloConfig,
    MonteCarloError,
    combine_monte_carlo_batches,
    run_monte_carlo_batch,
    run_monte_carlo_path,
)
from fantasy_football.player_outcomes import ProvisionalNormalModel
from fantasy_football.season_simulator import DeterministicScoreScenario
from fantasy_football.weekly_engine import RealizedPlayerScore
from fantasy_football.weekly_transactions import (
    WaiverBoundaryPolicy,
    WeeklyTransactionPolicy,
)
from tests.test_season_simulator import (
    _fourteen_team_postseason_snapshot,
    _postseason_shared_player_fixture,
    _scenario,
    _snapshot,
)


def _config(first: int = 0, count: int = 2, *, complete: bool = True):
    return MonteCarloConfig(
        master_seed=12345,
        path_count=count,
        first_path_index=first,
        ir_policy=IRPolicy.PROJECTION_BASED,
        transaction_policy=WeeklyTransactionPolicy(
            waiver_boundary=WaiverBoundaryPolicy.MODELED_WEEKLY_V1
        ),
        require_complete=complete,
    )


@dataclass(frozen=True)
class PrescribedModel:
    @property
    def model_id(self):
        return "prescribed-test-v1"

    @property
    def parameters(self):
        return (("evidence", "verified_by_tests"),)

    def generate_scenario(self, snapshot, *, master_seed, path_index):
        base = _scenario(snapshot)
        scores = tuple(
            replace(item, points=40.0)
            if (item.player_id, item.scoring_week) == ((1 if path_index % 2 else 2), 17)
            else replace(item, points=1.0)
            if item.scoring_week == 17
            else item
            for item in base.scores
        )
        return DeterministicScoreScenario(f"prescribed:{master_seed}:{path_index}", scores)


@dataclass(frozen=True)
class EffectiveProjectionModel:
    model_id: str = "effective-projection-test-v1"
    parameters: tuple[tuple[str, str], ...] = (("evidence", "verified_by_tests"),)

    def generate_scenario(self, snapshot, *, master_seed, path_index):
        return DeterministicScoreScenario(
            f"effective:{master_seed}:{path_index}",
            tuple(
                RealizedPlayerScore(
                    item.player_id,
                    item.season,
                    item.scoring_week,
                    item.effective_projection,
                )
                for item in snapshot.player_weeks
            ),
        )


def test_path_alone_matches_same_path_in_batch_and_replay() -> None:
    snapshot = _snapshot()
    model = ProvisionalNormalModel(2.0, 0.2)
    config = _config(10, 3)
    alone, detailed = run_monte_carlo_path(
        snapshot, config, model, 10, retain_result=True
    )
    batch = run_monte_carlo_batch(snapshot, config, model)
    assert alone == batch.paths[0]
    assert detailed is not None
    assert batch == run_monte_carlo_batch(snapshot, config, model)


def test_prescribed_paths_produce_hand_checkable_counts_and_reconcile() -> None:
    snapshot = _snapshot()
    result = run_monte_carlo_batch(snapshot, _config(0, 4), PrescribedModel())
    assert result.completed_paths == 4
    assert result.incomplete_paths == result.invalid_paths == 0
    assert result.reconciliation_complete
    assert sum(item.championship_wins for item in result.teams) == 4
    assert sum(item.playoff_qualifications for item in result.teams) == 8
    assert all(sum(count for _, count in item.placement_counts) == 4 for item in result.teams)
    assert all(item.championship_frequency is not None for item in result.teams)
    by_team = {item.team_id: item for item in result.teams}
    assert by_team[1].championship_wins == by_team[2].championship_wins == 2
    assert by_team[1].championship_frequency == by_team[2].championship_frequency == 0.5


def test_batch_partition_and_merge_are_exactly_equivalent() -> None:
    snapshot = _snapshot()
    model = PrescribedModel()
    whole_config = _config(0, 6)
    whole = run_monte_carlo_batch(snapshot, whole_config, model)
    left = run_monte_carlo_batch(snapshot, _config(0, 3), model)
    right = run_monte_carlo_batch(snapshot, _config(3, 3), model)
    merged = combine_monte_carlo_batches(
        snapshot, whole_config, model, (right, left)
    )
    assert merged == whole


def test_capability_incomplete_paths_do_not_publish_probabilities() -> None:
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        rules=replace(
            snapshot.rules,
            consolation=replace(snapshot.rules.consolation, enabled=False),
        ),
    )
    result = run_monte_carlo_batch(snapshot, _config(0, 2, complete=False), PrescribedModel())
    assert result.incomplete_paths == 2
    assert result.completed_paths == 0
    assert not result.reconciliation_complete
    assert all(item.championship_frequency is None for item in result.teams)
    with pytest.raises(MonteCarloError, match="capability-incomplete"):
        run_monte_carlo_batch(snapshot, _config(0, 1, complete=True), PrescribedModel())


def test_full_player_week_universe_covers_dynamic_acquisition_candidate() -> None:
    snapshot = _snapshot()
    extra = replace(
        snapshot.players[-1],
        player_id=99,
        display_name="Acquirable player",
        acquisition_status="FREEAGENT",
    )
    weeks = tuple(
        replace(item, player_id=99)
        for item in snapshot.player_weeks
        if item.player_id == snapshot.players[-1].player_id
    )
    expanded = replace(
        snapshot,
        players=snapshot.players + (extra,),
        player_weeks=snapshot.player_weeks + weeks,
    )
    scenario = ProvisionalNormalModel(1.0, 0.1).generate_scenario(
        expanded, master_seed=1, path_index=0
    )
    assert {(item.player_id, item.scoring_week) for item in scenario.scores if item.player_id == 99} == {
        (99, week)
        for week in range(expanded.first_simulation_week, expanded.final_simulation_week + 1)
    }


def test_dynamic_acquisition_uses_pre_generated_scores() -> None:
    snapshot, scenario = _postseason_shared_player_fixture(consolation_enabled=True)

    @dataclass(frozen=True)
    class ScenarioModel:
        model_id: str = "dynamic-acquisition-test-v1"
        parameters: tuple[tuple[str, str], ...] = (("evidence", "verified_by_tests"),)

        def generate_scenario(self, snapshot, *, master_seed, path_index):
            return replace(scenario, scenario_id=f"dynamic:{master_seed}:{path_index}")

    _, detailed = run_monte_carlo_path(
        snapshot, _config(0, 1), ScenarioModel(), 0, retain_result=True
    )
    assert detailed is not None
    assert any(item.player_id == 30 for item in detailed.final_evolving_state.roster_entries)
    assert any(
        assignment.player_id == 30
        for week in detailed.weeks
        for team in week.frozen_team_weeks
        for assignment in team.lineup.assignments
    )


def test_same_runner_supports_fourteen_team_configuration() -> None:
    snapshot = _fourteen_team_postseason_snapshot()
    result = run_monte_carlo_batch(snapshot, _config(0, 1), EffectiveProjectionModel())
    assert len(result.teams) == 14
    assert result.completed_paths == 1
    assert sum(item.championship_wins for item in result.teams) == 1
    assert all(sum(count for _, count in item.placement_counts) == 1 for item in result.teams)


@pytest.mark.parametrize(
    "kwargs",
    (
        {"master_seed": True},
        {"path_count": 0},
        {"first_path_index": -1},
        {"require_complete": 1},
    ),
)
def test_invalid_configuration_rejected(kwargs) -> None:
    values = {
        "master_seed": 1,
        "path_count": 1,
        "first_path_index": 0,
        "ir_policy": IRPolicy.PROJECTION_BASED,
        "transaction_policy": WeeklyTransactionPolicy(
            waiver_boundary=WaiverBoundaryPolicy.MODELED_WEEKLY_V1
        ),
        "require_complete": True,
    }
    values.update(kwargs)
    with pytest.raises(MonteCarloError):
        MonteCarloConfig(**values)


def test_invalid_model_failure_identifies_path() -> None:
    class BadModel(PrescribedModel):
        def generate_scenario(self, snapshot, *, master_seed, path_index):
            return DeterministicScoreScenario(
                "bad",
                (RealizedPlayerScore(999999, snapshot.season, 15, 1.0),),
            )

    with pytest.raises(MonteCarloError, match="invalid path 0"):
        run_monte_carlo_batch(_snapshot(), _config(0, 1), BadModel())


def test_runner_does_not_access_network_or_mutate_input(monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Monte Carlo execution must not access ESPN")

    monkeypatch.setattr("fantasy_football.espn_adapter.fetch_and_translate", forbidden)
    snapshot = _snapshot()
    before = snapshot
    run_monte_carlo_batch(snapshot, _config(0, 2), PrescribedModel())
    assert snapshot == before
