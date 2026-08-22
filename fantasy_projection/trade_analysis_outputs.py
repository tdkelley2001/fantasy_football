from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .config import Config
from .outputs import (
    save_outputs,
    timestamped_run_dir,
    write_csv,
    write_json,
)
from .trade_analysis import TradeComparison


def save_trade_comparison_outputs(
    config: Config,
    result: TradeComparison,
) -> Path:
    """Save complete projections and focused deltas for one trade."""
    out = timestamped_run_dir(config.output_dir, "trade_comparison")

    save_outputs(
        replace(config, output_dir=out / "before"),
        result.before,
    )
    save_outputs(
        replace(config, output_dir=out / "after"),
        result.after,
    )
    write_json(out / "trade_summary.json", result.trade_summary)
    write_csv(out / "team_comparison.csv", result.team_comparison)
    write_csv(out / "weekly_comparison.csv", result.weekly_comparison)
    write_csv(out / "lineup_comparison.csv", result.lineup_comparison)
    write_csv(out / "league_comparison.csv", result.league_comparison)
    return out


def print_trade_comparison(result: TradeComparison) -> None:
    summary = result.trade_summary
    give = " + ".join(row["player_name"] for row in summary["give"])
    receive = " + ".join(
        row["player_name"] for row in summary["receive"]
    )

    print()
    print("=" * 72)
    print("PROPOSED TRADE PROJECTION")
    print("=" * 72)
    print(
        f'{summary["my_team"]} gives {give} to '
        f'{summary["partner_team"]}'
    )
    print(f'{summary["my_team"]} receives {receive}')
    print()

    for row in result.team_comparison:
        print(row["team_name"])
        print(
            "  Average weekly starter projection: "
            f'{row["avg_weekly_points_before"]:.2f} -> '
            f'{row["avg_weekly_points_after"]:.2f} '
            f'({row["avg_weekly_points_change"]:+.2f})'
        )
        print(
            "  Projected record: "
            f'{row["wins_before"]}-{row["losses_before"]} -> '
            f'{row["wins_after"]}-{row["losses_after"]}'
        )
        print(
            "  Regular-season seed: "
            f'{row["regular_seed_before"]} -> '
            f'{row["regular_seed_after"]}'
        )
        print(
            "  Final place: "
            f'{row["final_place_before"]} -> '
            f'{row["final_place_after"]}'
        )
        print()

    print(
        "Projected champion: "
        f'{summary["champion_before"]} -> {summary["champion_after"]}'
    )
