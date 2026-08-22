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
from .waiver_analysis import WaiverComparison


def save_waiver_comparison_outputs(
    config: Config,
    result: WaiverComparison,
) -> Path:
    """Save complete projections and focused deltas for one add/drop."""
    out = timestamped_run_dir(config.output_dir, "waiver_comparison")

    save_outputs(
        replace(config, output_dir=out / "before"),
        result.before,
    )
    save_outputs(
        replace(config, output_dir=out / "after"),
        result.after,
    )
    write_json(out / "waiver_summary.json", result.waiver_summary)
    write_csv(out / "team_comparison.csv", result.team_comparison)
    write_csv(out / "weekly_comparison.csv", result.weekly_comparison)
    write_csv(out / "lineup_comparison.csv", result.lineup_comparison)
    write_csv(out / "league_comparison.csv", result.league_comparison)
    return out


def print_waiver_comparison(result: WaiverComparison) -> None:
    summary = result.waiver_summary
    row = result.team_comparison[0]

    print()
    print("=" * 72)
    print("PROPOSED WAIVER MOVE PROJECTION")
    print("=" * 72)
    print(
        f'{summary["my_team"]} adds {summary["add"]["player_name"]} '
        f'and drops {summary["drop"]["player_name"]}'
    )
    print()
    print(
        "Current-week starter projection: "
        f'{row["team_current_week_lineup_points_before"]:.2f} -> '
        f'{row["team_current_week_lineup_points_after"]:.2f} '
        f'({row["team_current_week_lineup_gain"]:+.2f})'
    )
    print(
        "Average weekly ROS starter projection: "
        f'{row["team_avg_remaining_season_lineup_points_before"]:.2f} -> '
        f'{row["team_avg_remaining_season_lineup_points_after"]:.2f} '
        f'({row["team_avg_remaining_season_lineup_gain"]:+.2f})'
    )
    print(
        "Regular-season lineup impact: "
        f'{row["team_regular_season_total_lineup_gain"]:+.2f}'
    )
    print(
        "Playoff-window lineup impact: "
        f'{row["team_playoff_window_total_lineup_gain"]:+.2f}'
    )
    print(
        "Projected record: "
        f'{row["team_projected_wins_before"]} wins -> '
        f'{row["team_projected_wins_after"]} wins'
    )
    print(
        "Regular-season seed: "
        f'{row["team_regular_seed_before"]} -> '
        f'{row["team_regular_seed_after"]}'
    )
    print(
        "Final place: "
        f'{row["team_final_place_before"]} -> '
        f'{row["team_final_place_after"]}'
    )
    print(
        "Projected game flips: "
        f'{row["team_projected_game_flips"]}'
    )
    print(
        "Playoff path: "
        f'{row["team_playoff_path_before"]} -> '
        f'{row["team_playoff_path_after"]}'
    )
    print(
        "Move tags: "
        + (" | ".join(summary["move_tags"]) or "NONE")
    )
