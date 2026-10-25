"""Synthetic M5.5 exhaustive immediate-acquisition benchmark."""

from __future__ import annotations

from pathlib import Path
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fantasy_football.acquisition_candidates import (  # noqa: E402
    ImmediateAcquisitionSearchConfiguration,
    enumerate_immediate_acquisition_candidates,
)
from fantasy_football.evolving_state import IRPolicy, initialize_evolving_state  # noqa: E402
from fantasy_football.weekly_transactions import WaiverBoundaryPolicy  # noqa: E402
from tests.canonical_fixtures import canonical_snapshot  # noqa: E402


def main() -> None:
    snapshot = canonical_snapshot()
    state = initialize_evolving_state(
        snapshot, scoring_week=15, ir_policy=IRPolicy.PROJECTION_BASED
    )
    configuration = ImmediateAcquisitionSearchConfiguration(
        1,
        (2, 3, 4),
        (-101, 1),
        waiver_boundary=WaiverBoundaryPolicy.MODELED_WEEKLY_V1,
    )
    tracemalloc.start()
    started = time.perf_counter()
    result = enumerate_immediate_acquisition_candidates(
        snapshot, state, configuration
    )
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"raw_combinations={result.coverage.raw_combination_count}")
    print(f"structurally_feasible={result.coverage.structurally_feasible_count}")
    print(f"authorized_immediate={result.coverage.authorized_immediate_count}")
    print(f"conditional_waiver={result.coverage.conditional_waiver_count}")
    print(f"unresolved={result.coverage.unresolved_count}")
    print(f"prohibited={result.coverage.prohibited_count}")
    print(f"seconds={elapsed:.6f}")
    print(f"traced_peak_mib={peak / 1024 / 1024:.3f}")


if __name__ == "__main__":
    main()
