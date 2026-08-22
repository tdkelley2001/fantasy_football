from __future__ import annotations

import sys

import requests

from fantasy_projection.config import load_config
from fantasy_projection.pipeline import run_projection
from fantasy_projection.trade_analysis import (
    evaluate_trade,
    resolve_player_references,
)
from fantasy_projection.trade_analysis_outputs import (
    print_trade_comparison,
    save_trade_comparison_outputs,
)
from fantasy_projection.trade_config import load_my_team_id


def _split_references(value: str) -> list[str]:
    return [
        reference.strip()
        for reference in value.split(",")
        if reference.strip()
    ]


def _trade_inputs() -> tuple[list[str], list[str]]:
    print(
        "Enter exact player names or ESPN player IDs. "
        "Separate multiple players with commas."
    )
    give = _split_references(
        input("Players your team gives: ")
    )
    receive = _split_references(
        input("Players your team receives: ")
    )
    if not give or not receive:
        raise RuntimeError("At least one player is required on each side.")
    return give, receive


def main() -> int:
    try:
        give_references, receive_references = _trade_inputs()
        config = load_config()
        my_team_id = load_my_team_id()

        baseline = run_projection(config)
        give_ids = resolve_player_references(
            baseline.rosters, give_references
        )
        receive_ids = resolve_player_references(
            baseline.rosters, receive_references
        )
        result = evaluate_trade(
            baseline=baseline,
            config=config,
            my_team_id=my_team_id,
            give_player_ids=give_ids,
            receive_player_ids=receive_ids,
        )
        out = save_trade_comparison_outputs(config, result)
        print_trade_comparison(result)
        print()
        print(f"Saved trade comparison to: {out.resolve()}")
        return 0

    except (EOFError, KeyboardInterrupt):
        print("Trade evaluation cancelled.", file=sys.stderr)
        return 130
    except requests.HTTPError as exc:
        print(f"ESPN HTTP error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
