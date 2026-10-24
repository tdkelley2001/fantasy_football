"""Reproducible synthetic M3.6 checkpoint overhead and recovery benchmark."""

from __future__ import annotations

from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fantasy_football.monte_carlo_execution import (  # noqa: E402
    ExecutionProfileName,
    MonteCarloCheckpointStore,
    SimulationExecutionProfile,
    execute_monte_carlo_profile,
)
from fantasy_football.monte_carlo_precision import PrecisionConfiguration  # noqa: E402
from tests.test_monte_carlo import PrescribedModel, _config  # noqa: E402
from tests.test_season_simulator import _snapshot  # noqa: E402


def _timed(function):
    started = time.perf_counter()
    result = function()
    return result, time.perf_counter() - started


def main() -> None:
    profile = SimulationExecutionProfile(
        ExecutionProfileName.CUSTOM,
        PrecisionConfiguration(0.95, 0.001, 20, 100, 20),
        None,
    )
    snapshot = _snapshot()
    config = _config(0, 100)
    model = PrescribedModel()
    root = Path("outputs/m36-benchmark").resolve()
    store = MonteCarloCheckpointStore(root / "checkpoint.json", approved_root=root)
    try:
        _, baseline_seconds = _timed(
            lambda: execute_monte_carlo_profile(snapshot, config, model, profile)
        )
        checkpointed, checkpoint_seconds = _timed(
            lambda: execute_monte_carlo_profile(
                snapshot, config, model, profile, checkpoint_store=store
            )
        )
        resumed, recovery_seconds = _timed(
            lambda: execute_monte_carlo_profile(
                snapshot, config, model, profile,
                checkpoint_store=store, resume=True,
            )
        )
        print(f"paths={checkpointed.result.requested_paths}")
        print(f"checkpoints={len(checkpointed.result.checkpoints)}")
        print(f"baseline_seconds={baseline_seconds:.6f}")
        print(f"checkpointed_seconds={checkpoint_seconds:.6f}")
        print(f"checkpoint_overhead_seconds={checkpoint_seconds - baseline_seconds:.6f}")
        print(f"checkpoint_bytes={store.path.stat().st_size}")
        print(f"recovery_seconds={recovery_seconds:.6f}")
        print(f"recovered_paths={resumed.recovered_paths}")
        print(f"new_paths={resumed.newly_executed_paths}")
        print(f"identical={resumed.result == checkpointed.result}")
    finally:
        if store.path.exists():
            store.path.unlink()
        if root.exists():
            root.rmdir()


if __name__ == "__main__":
    main()
