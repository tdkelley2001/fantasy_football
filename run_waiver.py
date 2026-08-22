from __future__ import annotations

import sys

import requests

from fantasy_projection.config import load_config
from fantasy_projection.espn import EspnClient, pull_available_players
from fantasy_projection.pipeline import run_projection
from fantasy_projection.trade_config import load_my_team_id
from fantasy_projection.waiver_analysis import (
    evaluate_waiver,
    resolve_player_reference,
)
from fantasy_projection.waiver_analysis_outputs import (
    print_waiver_comparison,
    save_waiver_comparison_outputs,
)


def _waiver_inputs() -> tuple[str, str]:
    print("Enter exact player names or ESPN player IDs.")
    add = input("Available player to add: ").strip()
    drop = input("Player from your roster to drop: ").strip()
    if not add or not drop:
        raise RuntimeError("Both an add and a drop are required.")
    return add, drop


def main() -> int:
    try:
        add_reference, drop_reference = _waiver_inputs()
        config = load_config()
        my_team_id = load_my_team_id()
        baseline = run_projection(config)

        current_week = int(
            baseline.summary["current_scoring_period"]
        )
        print("Pulling currently available ESPN players...")
        available_players = pull_available_players(
            EspnClient(config),
            scoring_period_id=current_week,
        )
        my_roster = [
            row
            for row in baseline.rosters
            if int(row["team_id"]) == my_team_id
        ]
        add_player_id = resolve_player_reference(
            available_players,
            add_reference,
            pool_description="currently available player",
        )
        drop_player_id = resolve_player_reference(
            my_roster,
            drop_reference,
            pool_description="player on your roster",
        )

        result = evaluate_waiver(
            baseline=baseline,
            config=config,
            my_team_id=my_team_id,
            available_players=available_players,
            add_player_id=add_player_id,
            drop_player_id=drop_player_id,
        )
        out = save_waiver_comparison_outputs(config, result)
        print_waiver_comparison(result)
        print()
        print(f"Saved waiver comparison to: {out.resolve()}")
        return 0

    except (EOFError, KeyboardInterrupt):
        print("Waiver evaluation cancelled.", file=sys.stderr)
        return 130
    except requests.HTTPError as exc:
        print(f"ESPN HTTP error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
