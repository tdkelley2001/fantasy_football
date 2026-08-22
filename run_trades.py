from __future__ import annotations

import sys

import requests

from fantasy_projection.config import load_config
from fantasy_projection.pipeline import run_projection
from fantasy_projection.trade_config import load_trade_config
from fantasy_projection.trade_outputs import (
    print_trade_summary,
    save_trade_outputs,
)
from fantasy_projection.trades import evaluate_all_trades


def main() -> int:
    try:
        config = load_config()
        trade_config = load_trade_config()

        baseline = run_projection(config)

        result = evaluate_all_trades(
            baseline=baseline,
            trade_config=trade_config,
        )
        trade_out = save_trade_outputs(config, result)
        print_trade_summary(result)

        print()
        print(f"Saved trade outputs to: {trade_out.resolve()}")
        return 0

    except requests.HTTPError as exc:
        print(f"ESPN HTTP error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
