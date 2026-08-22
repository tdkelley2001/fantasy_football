from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .outputs import timestamped_run_dir, write_csv, write_json
from .waivers import WaiverAnalysisResult


def save_waiver_outputs(
    config: Config,
    result: WaiverAnalysisResult,
) -> Path:
    out = timestamped_run_dir(config.output_dir, "waiver_analysis")
    out.mkdir(parents=True, exist_ok=True)

    available_rows = []
    for source in result.available_players:
        row = dict(source)
        row["eligible_slots"] = json.dumps(row["eligible_slots"])
        available_rows.append(row)

    write_csv(out / "all_available_players.csv", available_rows)
    write_csv(out / "all_add_drop_results.csv", result.transactions)
    write_csv(
        out / "marginal_roster_values.csv",
        result.marginal_roster_values,
    )
    write_json(out / "waiver_analysis_summary.json", result.summary)
    return out


def print_waiver_summary(result: WaiverAnalysisResult) -> None:
    summary = result.summary
    print()
    print("=" * 72)
    print("COMPLETE WAIVER ANALYSIS")
    print("=" * 72)
    print(
        f'{summary["available_players_pulled"]:,} available players pulled; '
        f'{summary["available_players_evaluated"]:,} had usable remaining '
        "projections and lineup eligibility."
    )
    print(
        f'{summary["valid_transactions"]:,} valid add/drop transactions; '
        f'{summary["invalid_lineup_transactions"]:,} invalid lineups; '
        f'{summary["illegal_position_limit_pairs_skipped"]:,} illegal '
        "position-limit combinations skipped."
    )

    immediate = [
        row for row in result.transactions
        if row.get("immediate_upgrade") is True
    ]
    print()
    print("Best immediate upgrades:")
    for row in sorted(
        immediate,
        key=lambda item: -item["team_current_week_lineup_gain"],
    )[:10]:
        print(
            f'- add {row["add_player"]}, drop {row["drop_player"]}: '
            f'{row["team_current_week_lineup_gain"]:+.2f} this week, '
            f'{row["team_avg_remaining_season_lineup_gain"]:+.2f}/week ROS'
        )
