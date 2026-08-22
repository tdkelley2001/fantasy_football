from __future__ import annotations

import sys

import requests

from fantasy_projection.config import load_config
from fantasy_projection.espn import EspnClient, pull_available_players
from fantasy_projection.pipeline import run_projection
from fantasy_projection.trade_config import load_my_team_id
from fantasy_projection.waiver_outputs import (
    print_waiver_summary,
    save_waiver_outputs,
)
from fantasy_projection.waivers import analyze_waivers


def main() -> int:
    try:
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
        print(
            f"Found {len(available_players):,} players currently marked "
            "as free agents or waivers."
        )

        result = analyze_waivers(
            baseline=baseline,
            my_team_id=my_team_id,
            available_players=available_players,
        )
        out = save_waiver_outputs(config, result)
        print_waiver_summary(result)
        print()
        print(f"Saved waiver analysis to: {out.resolve()}")
        return 0

    except requests.HTTPError as exc:
        print(f"ESPN HTTP error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
