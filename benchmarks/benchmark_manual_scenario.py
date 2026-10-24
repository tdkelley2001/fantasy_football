"""Reproducible synthetic M4 completion and paired-evaluation benchmark."""

from __future__ import annotations

from pathlib import Path
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fantasy_football.monte_carlo_precision import PrecisionConfiguration  # noqa: E402
from fantasy_football.scenario_evaluator import (  # noqa: E402
    ExplicitRosterChange,
    ManualScenario,
    complete_manual_scenario,
    evaluate_manual_scenario,
)
from tests.test_monte_carlo import PrescribedModel  # noqa: E402
from tests.test_scenario_evaluator import _config, _scenario_snapshot, _state  # noqa: E402


def main() -> None:
    snapshot = _scenario_snapshot()
    baseline = _state(snapshot)
    scenario = ManualScenario(
        "m4-benchmark-swap",
        (ExplicitRosterChange(1, 1, 2), ExplicitRosterChange(2, 2, 1)),
    )
    tracemalloc.start()
    started = time.perf_counter()
    completed = complete_manual_scenario(snapshot, baseline, scenario)
    completion_seconds = time.perf_counter() - started
    _, completion_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    started = time.perf_counter()
    comparison = evaluate_manual_scenario(
        snapshot,
        baseline,
        scenario,
        _config(100),
        PrescribedModel(),
        PrecisionConfiguration(0.95, 0.01, 100, 100, 100),
    )
    paired_seconds = time.perf_counter() - started
    print(f"teams={len(snapshot.teams)}")
    print(f"paths={comparison.matched_path_count}")
    print(f"forced_drops={len(completed.forced_drops)}")
    print(f"automatic_additions={len(completed.automatic_additions)}")
    print(f"completion_seconds={completion_seconds:.6f}")
    print(f"paired_seconds={paired_seconds:.6f}")
    print(f"paired_paths_per_second={comparison.matched_path_count / paired_seconds:.3f}")
    print(f"completion_only_traced_peak_mib={completion_peak / 1024 / 1024:.3f}")


if __name__ == "__main__":
    main()
