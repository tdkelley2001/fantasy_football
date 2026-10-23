"""Bounded process execution for deterministic Monte Carlo path batches."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import multiprocessing
import pickle
import time

from fantasy_football.canonical.model import LeagueSnapshot
from fantasy_football.monte_carlo import (
    MonteCarloBatchResult,
    MonteCarloConfig,
    MonteCarloError,
    MonteCarloPathSummary,
    aggregate_monte_carlo_paths,
    run_monte_carlo_batch,
    run_monte_carlo_path,
    simulation_configuration_fingerprint,
)
from fantasy_football.player_outcomes import PlayerOutcomeModel


class ParallelExecutionError(MonteCarloError):
    """Raised when bounded process execution cannot preserve its contract."""


@dataclass(frozen=True, slots=True)
class ParallelExecutionConfiguration:
    worker_count: int
    paths_per_task: int
    start_method: str = "spawn"

    def __post_init__(self) -> None:
        for name in ("worker_count", "paths_per_task"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ParallelExecutionError(f"{name} must be a positive integer")
        if self.start_method not in multiprocessing.get_all_start_methods():
            raise ParallelExecutionError(
                f"unsupported multiprocessing start_method={self.start_method!r}"
            )


@dataclass(frozen=True, slots=True)
class ParallelExecutionDiagnostics:
    requested_workers: int
    workers_used: int
    paths_per_task: int
    task_count: int
    submitted_path_count: int
    elapsed_seconds: float
    start_method: str
    immutable_inputs_initialized_once_per_worker: bool


@dataclass(frozen=True, slots=True)
class ParallelMonteCarloResult:
    batch: MonteCarloBatchResult
    diagnostics: ParallelExecutionDiagnostics


_WORKER_SNAPSHOT: LeagueSnapshot | None = None
_WORKER_CONFIG: MonteCarloConfig | None = None
_WORKER_MODEL: PlayerOutcomeModel | None = None


def _initialize_worker(
    snapshot: LeagueSnapshot,
    config: MonteCarloConfig,
    model: PlayerOutcomeModel,
) -> None:
    global _WORKER_SNAPSHOT, _WORKER_CONFIG, _WORKER_MODEL
    _WORKER_SNAPSHOT = snapshot
    _WORKER_CONFIG = config
    _WORKER_MODEL = model


def _run_worker_chunk(path_indices: tuple[int, ...]) -> tuple[MonteCarloPathSummary, ...]:
    if _WORKER_SNAPSHOT is None or _WORKER_CONFIG is None or _WORKER_MODEL is None:
        raise ParallelExecutionError("Monte Carlo worker was not initialized")
    return tuple(
        run_monte_carlo_path(
            _WORKER_SNAPSHOT, _WORKER_CONFIG, _WORKER_MODEL, path_index
        )[0]
        for path_index in path_indices
    )


def _chunks(values: tuple[int, ...], size: int) -> tuple[tuple[int, ...], ...]:
    return tuple(values[index : index + size] for index in range(0, len(values), size))


def run_monte_carlo_batch_parallel(
    snapshot: LeagueSnapshot,
    config: MonteCarloConfig,
    model: PlayerOutcomeModel,
    execution: ParallelExecutionConfiguration,
) -> ParallelMonteCarloResult:
    """Execute exact path chunks in bounded processes and reconcile in path order."""

    with ParallelMonteCarloExecutor(snapshot, config, model, execution) as executor:
        return executor.run_batch(config)


class ParallelMonteCarloExecutor:
    """Reusable bounded worker pool initialized once with immutable run inputs."""

    def __init__(
        self,
        snapshot: LeagueSnapshot,
        config: MonteCarloConfig,
        model: PlayerOutcomeModel,
        execution: ParallelExecutionConfiguration,
    ) -> None:
        if not isinstance(execution, ParallelExecutionConfiguration):
            raise ParallelExecutionError(
                "execution must be ParallelExecutionConfiguration"
            )
        if not getattr(model, "model_id", None) or not hasattr(model, "generate_scenario"):
            raise ParallelExecutionError("model does not satisfy PlayerOutcomeModel")
        try:
            pickle.dumps((snapshot, config, model), protocol=pickle.HIGHEST_PROTOCOL)
        except (pickle.PickleError, TypeError, AttributeError) as exc:
            raise ParallelExecutionError(
                "snapshot, configuration, and outcome model must be process-serializable"
            ) from exc
        self._snapshot = snapshot
        self._config = config
        self._model = model
        self._execution = execution
        self._pool: ProcessPoolExecutor | None = None
        self._active = False

    def __enter__(self) -> ParallelMonteCarloExecutor:
        if self._active:
            raise ParallelExecutionError("parallel executor is already active")
        self._active = True
        path_chunks = _chunks(
            self._config.path_indices, self._execution.paths_per_task
        )
        workers = min(self._execution.worker_count, len(path_chunks))
        if workers > 1:
            self._pool = ProcessPoolExecutor(
                max_workers=workers,
                mp_context=multiprocessing.get_context(self._execution.start_method),
                initializer=_initialize_worker,
                initargs=(self._snapshot, self._config, self._model),
            )
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=exc is not None)
            self._pool = None
        self._active = False

    def run_batch(self, config: MonteCarloConfig) -> ParallelMonteCarloResult:
        if not self._active:
            raise ParallelExecutionError("parallel executor must be used as a context manager")
        if simulation_configuration_fingerprint(
            self._snapshot, config, self._model
        ) != simulation_configuration_fingerprint(
            self._snapshot, self._config, self._model
        ):
            raise ParallelExecutionError(
                "batch configuration does not match initialized simulation identity"
            )
        if not set(config.path_indices).issubset(self._config.path_indices):
            raise ParallelExecutionError(
                "batch path range is outside initialized executor range"
            )
        path_chunks = _chunks(config.path_indices, self._execution.paths_per_task)
        workers_used = min(self._execution.worker_count, len(path_chunks))
        started = time.perf_counter()
        if workers_used == 1:
            batch = run_monte_carlo_batch(self._snapshot, config, self._model)
        else:
            if self._pool is None:
                raise ParallelExecutionError("parallel executor is not active")
            completed: list[MonteCarloPathSummary] = []
            futures = tuple(
                self._pool.submit(_run_worker_chunk, path_chunk)
                for path_chunk in path_chunks
            )
            for future in as_completed(futures):
                completed.extend(future.result())
            batch = aggregate_monte_carlo_paths(
                self._snapshot, config, self._model, tuple(completed)
            )
        elapsed = time.perf_counter() - started
        return ParallelMonteCarloResult(
            batch,
            ParallelExecutionDiagnostics(
                self._execution.worker_count,
                workers_used,
                self._execution.paths_per_task,
                len(path_chunks),
                config.path_count,
                elapsed,
                self._execution.start_method,
                True,
            ),
        )
