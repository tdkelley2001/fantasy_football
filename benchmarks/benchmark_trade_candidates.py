"""Reproducible synthetic M5.1 exhaustive-generation benchmark."""

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
from tests.test_trade_candidates import _snapshot, _state  # noqa: E402


def main() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    configuration = SingleTradeSearchConfiguration(
        requesting_team_id=1,
        counterparty_team_ids=(2, 3, 4),
        player_universe_ids=(1, 2, 3, 4, 10, 11, 12, 13),
        trade_shapes=(
            TradeShape(1, 1),
            TradeShape(1, 2),
            TradeShape(2, 1),
            TradeShape(2, 2),
        ),
    )
    started = time.perf_counter()
    result = enumerate_single_trade_candidates(snapshot, state, configuration)
    elapsed = time.perf_counter() - started
    tracemalloc.start()
    enumerate_single_trade_candidates(snapshot, state, configuration)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"teams={len(snapshot.teams)}")
    print(f"declared_players={result.coverage.declared_player_count}")
    print(f"combinations={result.coverage.combination_count}")
    print(f"feasible={result.coverage.structurally_feasible_count}")
    print(f"infeasible={result.coverage.structurally_infeasible_count}")
    print(f"seconds={elapsed:.6f}")
    print(f"combinations_per_second={result.coverage.combination_count / elapsed:.3f}")
    print(f"traced_peak_mib={peak / 1024 / 1024:.3f}")


if __name__ == "__main__":
    main()
