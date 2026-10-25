"""Synthetic M5.4 progressive trade-search benchmark."""

from __future__ import annotations

from pathlib import Path
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fantasy_football.trade_candidates import TradeShape  # noqa: E402
from fantasy_football.trade_screening import TradeScreeningConfiguration  # noqa: E402
from fantasy_football.trade_search import (  # noqa: E402
    ProgressiveSamplingConfiguration,
    ProgressiveTradeSearchConfiguration,
    run_progressive_trade_search,
)
from tests.test_monte_carlo import PrescribedModel  # noqa: E402
from tests.test_scenario_evaluator import _config as simulation_config  # noqa: E402
from tests.test_trade_candidates import _config, _snapshot, _state  # noqa: E402


def main() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    configuration = ProgressiveTradeSearchConfiguration(
        _config(
            counterparties=(2, 3, 4),
            universe=(1, 2, 3, 4, 10, 11, 12, 13),
            shapes=(
                TradeShape(1, 1),
                TradeShape(1, 2),
                TradeShape(2, 1),
                TradeShape(2, 2),
            ),
        ),
        TradeScreeningConfiguration(),
        ProgressiveSamplingConfiguration(0.95, 0.01, 1, 1, 2, 2),
    )
    tracemalloc.start()
    started = time.perf_counter()
    result = run_progressive_trade_search(
        snapshot, state, configuration, simulation_config(2), PrescribedModel()
    )
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    coverage = result.coverage
    print(f"raw_combinations={coverage.raw_candidate_combinations}")
    print(f"structurally_feasible={coverage.structurally_feasible_candidates}")
    print(f"screen_retained={coverage.screen_retained_candidates}")
    print(f"unique_states={coverage.eligible_unique_states}")
    print(f"initially_evaluated={coverage.initially_evaluated_states}")
    print(f"refined_states={coverage.refined_states}")
    print(f"baseline_paths_computed={coverage.monte_carlo_baseline_paths_computed}")
    print(f"scenario_paths_computed={coverage.monte_carlo_scenario_paths_computed}")
    print(f"evaluations_avoided={coverage.candidate_evaluations_avoided_by_state_deduplication}")
    print(f"unevaluated_states={coverage.unevaluated_states}")
    print(f"stop_reason={result.stop_reason.value}")
    print(f"seconds={elapsed:.6f}")
    print(f"traced_peak_mib={peak / 1024 / 1024:.3f}")


if __name__ == "__main__":
    main()
