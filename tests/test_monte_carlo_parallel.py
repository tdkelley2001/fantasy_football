from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from fantasy_football.monte_carlo import MonteCarloError, run_monte_carlo_batch
from fantasy_football.monte_carlo_parallel import (
    ParallelMonteCarloExecutor,
    ParallelExecutionConfiguration,
    ParallelExecutionError,
    run_monte_carlo_batch_parallel,
)
from fantasy_football.monte_carlo_precision import (
    PrecisionConfiguration,
    run_monte_carlo_to_precision,
)
from tests.test_monte_carlo import PrescribedModel, _config
from tests.test_season_simulator import _snapshot


def _execution(workers: int = 2, paths_per_task: int = 1):
    return ParallelExecutionConfiguration(workers, paths_per_task)


def test_parallel_batch_is_exactly_equal_to_sequential_reference() -> None:
    snapshot = _snapshot()
    config = _config(0, 6)
    model = PrescribedModel()
    expected = run_monte_carlo_batch(snapshot, config, model)
    actual = run_monte_carlo_batch_parallel(snapshot, config, model, _execution()).batch
    assert actual == expected


@pytest.mark.parametrize("workers,paths_per_task", ((1, 3), (2, 1), (3, 2)))
def test_worker_count_and_task_granularity_do_not_change_results(
    workers: int, paths_per_task: int,
) -> None:
    snapshot = _snapshot()
    config = _config(5, 6)
    model = PrescribedModel()
    expected = run_monte_carlo_batch(snapshot, config, model)
    result = run_monte_carlo_batch_parallel(
        snapshot, config, model, _execution(workers, paths_per_task)
    )
    assert result.batch == expected
    assert result.diagnostics.submitted_path_count == 6
    assert result.diagnostics.task_count == (6 + paths_per_task - 1) // paths_per_task
    assert result.diagnostics.workers_used == min(workers, result.diagnostics.task_count)


def test_repeated_parallel_execution_is_deterministic_except_measured_runtime() -> None:
    snapshot = _snapshot()
    config = _config(0, 4)
    model = PrescribedModel()
    first = run_monte_carlo_batch_parallel(snapshot, config, model, _execution(2, 2))
    second = run_monte_carlo_batch_parallel(snapshot, config, model, _execution(2, 2))
    assert first.batch == second.batch
    assert replace(first.diagnostics, elapsed_seconds=0.0) == replace(
        second.diagnostics, elapsed_seconds=0.0
    )


def test_parallel_common_random_paths_remain_isolated_by_seed() -> None:
    snapshot = _snapshot()
    model = PrescribedModel()
    base = run_monte_carlo_batch_parallel(
        snapshot, _config(0, 4), model, _execution(2, 1)
    ).batch
    changed = run_monte_carlo_batch_parallel(
        snapshot, replace(_config(0, 4), master_seed=9876), model, _execution(2, 1)
    ).batch
    assert base.path_indices == changed.path_indices
    assert base.run_identity_sha256 != changed.run_identity_sha256
    assert tuple(item.scenario_id for item in base.paths) != tuple(
        item.scenario_id for item in changed.paths
    )


def test_parallel_incomplete_capability_matches_sequential_fail_closed_behavior() -> None:
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        rules=replace(
            snapshot.rules,
            consolation=replace(snapshot.rules.consolation, enabled=False),
        ),
    )
    model = PrescribedModel()
    permissive = _config(0, 2, complete=False)
    assert run_monte_carlo_batch_parallel(
        snapshot, permissive, model, _execution(2, 1)
    ).batch == run_monte_carlo_batch(snapshot, permissive, model)
    with pytest.raises(MonteCarloError, match="capability-incomplete"):
        run_monte_carlo_batch_parallel(
            snapshot, _config(0, 2, complete=True), model, _execution(2, 1)
        )


def test_parallel_precision_checkpoints_match_sequential() -> None:
    snapshot = _snapshot()
    simulation = _config(0, 4)
    precision = PrecisionConfiguration(0.95, 0.01, 2, 4, 1)
    sequential = run_monte_carlo_to_precision(
        snapshot, simulation, PrescribedModel(), precision
    )
    parallel = run_monte_carlo_to_precision(
        snapshot,
        simulation,
        PrescribedModel(),
        precision,
        parallel_execution=_execution(2, 1),
    )
    assert parallel == sequential


@dataclass(frozen=True)
class _UnserializableModel(PrescribedModel):
    callback: object = lambda: None


def test_unserializable_inputs_fail_before_worker_execution() -> None:
    with pytest.raises(ParallelExecutionError, match="process-serializable"):
        run_monte_carlo_batch_parallel(
            _snapshot(), _config(0, 2), _UnserializableModel(), _execution(2, 1)
        )


@pytest.mark.parametrize(
    "workers,paths_per_task",
    ((0, 1), (1, 0), (True, 1)),
)
def test_invalid_parallel_resource_configuration_fails(
    workers: int, paths_per_task: int,
) -> None:
    with pytest.raises(ParallelExecutionError):
        _execution(workers, paths_per_task)


def test_reusable_executor_requires_explicit_bounded_lifecycle() -> None:
    executor = ParallelMonteCarloExecutor(
        _snapshot(), _config(0, 2), PrescribedModel(), _execution(2, 1)
    )
    with pytest.raises(ParallelExecutionError, match="context manager"):
        executor.run_batch(_config(0, 2))


def test_reusable_executor_rejects_batch_with_different_master_seed() -> None:
    snapshot = _snapshot()
    initialized = _config(0, 2)
    with ParallelMonteCarloExecutor(
        snapshot, initialized, PrescribedModel(), _execution(2, 1)
    ) as executor:
        with pytest.raises(ParallelExecutionError, match="run identity"):
            executor.run_batch(replace(initialized, master_seed=9876))
