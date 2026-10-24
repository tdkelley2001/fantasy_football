"""Synthetic M5.3 equivalent-state Monte Carlo reuse benchmark."""

from __future__ import annotations

from pathlib import Path
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fantasy_football.monte_carlo_precision import PrecisionConfiguration  # noqa: E402
from fantasy_football.trade_candidates import (  # noqa: E402
    TradeShape,
    enumerate_single_trade_candidates,
)
from fantasy_football.trade_evaluation import (  # noqa: E402
    build_candidate_state_registry,
    evaluate_trade_candidate_states,
)
from fantasy_football.trade_screening import screen_trade_candidates  # noqa: E402
from tests.test_monte_carlo import PrescribedModel  # noqa: E402
from tests.test_scenario_evaluator import _config as simulation_config  # noqa: E402
from tests.test_trade_candidates import _config, _snapshot, _state  # noqa: E402


def main() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    screening = screen_trade_candidates(
        snapshot,
        state,
        enumerate_single_trade_candidates(
            snapshot,
            state,
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
        ),
    )
    registry = build_candidate_state_registry(snapshot, screening)
    simulation = simulation_config(1)
    precision = PrecisionConfiguration(0.95, 0.9, 1, 1, 1)
    model = PrescribedModel()

    started = time.perf_counter()
    result = evaluate_trade_candidate_states(
        snapshot, state, registry, simulation, model, precision
    )
    elapsed = time.perf_counter() - started
    tracemalloc.start()
    evaluate_trade_candidate_states(
        snapshot, state, registry, simulation, model, precision
    )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"candidate_paths={result.coverage.candidate_path_count}")
    print(f"unique_states={result.coverage.unique_completed_state_count}")
    print(f"paired_evaluations={result.coverage.actual_paired_evaluation_count}")
    print(f"evaluations_avoided={result.coverage.paired_evaluations_avoided}")
    print(f"seconds={elapsed:.6f}")
    print(f"traced_peak_mib={peak / 1024 / 1024:.3f}")


if __name__ == "__main__":
    main()
