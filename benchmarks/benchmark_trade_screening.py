"""Reproducible synthetic M5.2 exhaustive-screening benchmark."""

from __future__ import annotations

from pathlib import Path
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fantasy_football.trade_candidates import (  # noqa: E402
    SingleTradeSearchConfiguration,
    TradeShape,
    enumerate_single_trade_candidates,
)
from fantasy_football.trade_screening import (  # noqa: E402
    TradeScreeningConfiguration,
    screen_trade_candidates,
)
from tests.test_trade_candidates import _snapshot, _state  # noqa: E402


def main() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    enumeration = enumerate_single_trade_candidates(
        snapshot,
        state,
        SingleTradeSearchConfiguration(
            1,
            (2, 3, 4),
            (1, 2, 3, 4, 10, 11, 12, 13),
            (
                TradeShape(1, 1),
                TradeShape(1, 2),
                TradeShape(2, 1),
                TradeShape(2, 2),
            ),
        ),
    )
    configuration = TradeScreeningConfiguration(
        True, minimum_counterparty_delta=0.0
    )
    started = time.perf_counter()
    result = screen_trade_candidates(snapshot, state, enumeration, configuration)
    elapsed = time.perf_counter() - started
    tracemalloc.start()
    screen_trade_candidates(snapshot, state, enumeration, configuration)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"candidates={result.coverage.assessed_candidate_count}")
    print(f"retained={result.coverage.retained_candidate_count}")
    print(f"excluded={result.coverage.excluded_candidate_count}")
    print(f"seconds={elapsed:.6f}")
    print(f"candidates_per_second={result.coverage.assessed_candidate_count / elapsed:.3f}")
    print(f"traced_peak_mib={peak / 1024 / 1024:.3f}")


if __name__ == "__main__":
    main()
