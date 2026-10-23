"""Reproducible synthetic M3.5 sequential/parallel benchmark.

Run from the repository root with:
    python benchmarks/benchmark_monte_carlo_execution.py
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import argparse
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fantasy_football.monte_carlo import run_monte_carlo_batch  # noqa: E402
from fantasy_football.monte_carlo_parallel import (  # noqa: E402
    ParallelExecutionConfiguration,
    run_monte_carlo_batch_parallel,
)
from tests.test_monte_carlo import (  # noqa: E402
    EffectiveProjectionModel,
    PrescribedModel,
    _config,
)
from tests.test_season_simulator import (  # noqa: E402
    _fourteen_team_postseason_snapshot,
    _postseason_shared_player_fixture,
    _snapshot,
)


@dataclass(frozen=True)
class FixedScenarioModel:
    scenario: object
    model_id: str = "m35-fixed-transaction-benchmark-v1"
    parameters: tuple[tuple[str, str], ...] = (("evidence", "synthetic"),)

    def generate_scenario(self, snapshot, *, master_seed, path_index):
        return replace(
            self.scenario,
            scenario_id=f"m35-transaction:{master_seed}:{path_index}",
        )


def _measure(label, snapshot, config, model, workers, paths_per_task, trace_parent):
    if trace_parent:
        tracemalloc.start()
    started = time.perf_counter()
    if workers == 1:
        batch = run_monte_carlo_batch(snapshot, config, model)
    else:
        batch = run_monte_carlo_batch_parallel(
            snapshot,
            config,
            model,
            ParallelExecutionConfiguration(workers, paths_per_task),
        ).batch
    elapsed = time.perf_counter() - started
    if trace_parent:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory = f", parent_only_traced_peak_mib={peak / 1024 / 1024:.3f}"
    else:
        memory = ""
    print(
        f"{label}, workers={workers}, chunk={paths_per_task}, "
        f"paths={config.path_count}, seconds={elapsed:.6f}, "
        f"paths_per_second={config.path_count / elapsed:.3f}"
        f"{memory}, "
        f"run={batch.run_identity_sha256[:12]}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--trace-parent-memory",
        action="store_true",
        help="enable tracemalloc in the parent only; timings are then not comparable",
    )
    parser.add_argument("--path-multiplier", type=int, default=1)
    parser.add_argument("--workload", action="append")
    parser.add_argument("--workers", type=int, action="append")
    parser.add_argument("--chunk", type=int, action="append")
    args = parser.parse_args()
    if args.path_multiplier < 1:
        parser.error("--path-multiplier must be positive")
    transaction_snapshot, transaction_scenario = _postseason_shared_player_fixture(
        consolation_enabled=True
    )
    workloads = (
        ("four_team", _snapshot(), _config(0, 40), PrescribedModel(), 5),
        (
            "four_team_transaction",
            transaction_snapshot,
            _config(0, 20),
            FixedScenarioModel(transaction_scenario),
            5,
        ),
        (
            "fourteen_team_postseason",
            _fourteen_team_postseason_snapshot(),
            _config(0, 20),
            EffectiveProjectionModel(),
            5,
        ),
    )
    for label, snapshot, config, model, paths_per_task in workloads:
        if args.workload and label not in args.workload:
            continue
        config = replace(config, path_count=config.path_count * args.path_multiplier)
        for chunk in args.chunk or (paths_per_task,):
            if chunk < 1:
                parser.error("--chunk must be positive")
            for workers in args.workers or (1, 2, 4):
                _measure(
                    label,
                    snapshot,
                    config,
                    model,
                    workers,
                    chunk,
                    args.trace_parent_memory,
                )


if __name__ == "__main__":
    main()
