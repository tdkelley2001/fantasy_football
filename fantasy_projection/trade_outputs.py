from __future__ import annotations

from pathlib import Path

from .config import Config
from .outputs import write_csv, write_json
from .trades import TradeSearchResult


def save_trade_outputs(
    config: Config,
    result: TradeSearchResult,
) -> Path:
    out = config.output_dir / "trades"
    out.mkdir(parents=True, exist_ok=True)

    # Primary diagnostic output: every attempted trade.
    write_csv(
        out / "all_trade_evaluations.csv",
        result.all_evaluations,
    )

    valid = [
        row for row in result.all_evaluations
        if row["evaluation_status"] == "VALID"
    ]
    both_positive = [
        row for row in valid
        if row.get("both_positive_gain") is True
    ]
    mutually_beneficial = [
        row for row in valid
        if row.get("both_above_threshold") is True
    ]

    write_csv(
        out / "both_positive_trades.csv",
        both_positive,
    )
    write_csv(
        out / "mutually_beneficial_trades.csv",
        mutually_beneficial,
    )
    write_csv(
        out / "top_trade_scenarios.csv",
        result.top_trades,
    )
    write_csv(
        out / "top_trade_weekly_impacts.csv",
        result.weekly_impacts,
    )
    write_json(
        out / "trade_search_summary.json",
        result.search_summary,
    )

    for trade_type, all_name, top_name in [
        (
            "1-for-1",
            "all_1_for_1_trade_evaluations.csv",
            "top_1_for_1_trades.csv",
        ),
        (
            "2-for-2",
            "all_2_for_2_trade_evaluations.csv",
            "top_2_for_2_trades.csv",
        ),
    ]:
        all_rows = [
            row for row in result.all_evaluations
            if row["trade_type"] == trade_type
        ]
        top_rows = [
            row for row in result.top_trades
            if row["trade_type"] == trade_type
        ]
        write_csv(out / all_name, all_rows)
        write_csv(out / top_name, top_rows)

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
            f"both > threshold {summary['both_above_threshold']:,}; "
            "both positive but below threshold "
            f"{summary['both_positive_below_threshold']:,}; "
            f"my side only {summary['my_team_only_positive']:,}; "
            f"partner only {summary['partner_only_positive']:,}; "
            f"neither {summary['neither_positive']:,}."
        )
        best = summary.get("best_mutual_avg_weekly_gain")
        if best is not None:
            print(
                "  best weaker-side average weekly gain: "
                f"{best:+.3f}."
            )

    print()
    print("Top trades by weaker-side average weekly gain:")
    shown = 0
    for row in sorted(
        result.top_trades,
        key=lambda x: (
            -x["mutual_avg_weekly_lineup_gain"],
            -x["combined_avg_weekly_lineup_gain"],
        ),
    ):
        print(
            f"- {row['trade_type']} with {row['partner_team']}: "
            f"give {row['my_give']} | receive {row['my_receive']} | "
            f"you {row['my_avg_weekly_lineup_gain']:+.2f}/wk, "
            f"partner {row['partner_avg_weekly_lineup_gain']:+.2f}/wk | "
            f"{row['trade_classification']}"
        )
        shown += 1
        if shown >= 10:
            break
