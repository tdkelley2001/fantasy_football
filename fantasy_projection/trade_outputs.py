from __future__ import annotations

from pathlib import Path

from .config import Config
from .outputs import timestamped_run_dir, write_csv, write_json
from .trades import TradeSearchResult


def save_trade_outputs(
    config: Config,
    result: TradeSearchResult,
) -> Path:
    out = timestamped_run_dir(config.output_dir, "trade_search")
    out.mkdir(parents=True, exist_ok=True)

    write_csv(
        out / "all_trade_results.csv",
        result.all_evaluations,
    )
    write_json(
        out / "trade_search_summary.json",
        result.search_summary,
    )

    return out


def print_trade_summary(
    result: TradeSearchResult,
) -> None:
    print()
    print("=" * 72)
    print("COMPLETE TRADE SEARCH")
    print("=" * 72)

    for summary in result.search_summary:
        print(
            f"{summary['trade_type']}: "
            f"{summary['total_combinations']:,} combinations, "
            f"{summary['valid_trades_evaluated']:,} valid, "
            f"{summary['invalid_lineup_trades']:,} invalid lineup."
        )
        print(
            "  classifications: "
            f"both positive {summary['both_positive']:,}; "
            f"my side only {summary['my_team_only_positive']:,}; "
            f"partner only {summary['partner_only_positive']:,}; "
            f"neither {summary['neither_positive']:,}."
        )
        best = summary.get(
            "best_mutual_avg_remaining_season_lineup_gain"
        )
        if best is not None:
            print(
                "  best weaker-side average weekly gain: "
                f"{best:+.3f}."
            )

    print()
    print("Every trade and metric is available in all_trade_results.csv.")
