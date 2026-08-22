from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fantasy_projection.config import Config
from fantasy_projection.outputs import timestamped_run_dir
from fantasy_projection.trade_outputs import save_trade_outputs
from fantasy_projection.trades import (
    TradeSearchResult,
    _playoff_path,
    _projected_game_flip_metrics,
    _tradable_player_ids,
    _weekly_lineup_metrics,
)


class TradeMetricTests(unittest.TestCase):
    def test_timestamped_run_directory_uses_compact_local_time(self) -> None:
        now = datetime(2026, 8, 21, 14, 35, 9, 123456)

        actual = timestamped_run_dir(
            Path("outputs"), "trade_search", now=now
        )

        self.assertEqual(
            Path("outputs/trade_search_260821_143509"),
            actual,
        )

    def test_all_rostered_positions_are_tradable(self) -> None:
        roster_ids = {1: {101, 102, 103}}

        self.assertEqual(
            [101, 102, 103],
            _tradable_player_ids(1, roster_ids),
        )

    def test_weekly_metrics_cover_requested_distribution(self) -> None:
        metrics = _weekly_lineup_metrics(
            "my",
            (100.0, 100.0, 100.0, 100.0),
            (103.0, 98.0, 100.0, 105.0),
            (10, 11, 12, 13),
        )

        self.assertEqual(
            100.0, metrics["my_current_week_lineup_points_before"]
        )
        self.assertEqual(
            103.0, metrics["my_current_week_lineup_points_after"]
        )
        self.assertEqual(3.0, metrics["my_current_week_lineup_gain"])
        self.assertEqual(
            1.5, metrics["my_avg_remaining_season_lineup_gain"]
        )
        self.assertEqual(
            6.0, metrics["my_total_remaining_season_lineup_gain"]
        )
        self.assertEqual(1.5, metrics["my_median_weekly_lineup_gain"])
        self.assertEqual(2, metrics["my_positive_weeks"])
        self.assertEqual(1, metrics["my_negative_weeks"])
        self.assertEqual(1, metrics["my_neutral_weeks"])
        self.assertEqual(13, metrics["my_best_week"])
        self.assertEqual(11, metrics["my_worst_week"])

    def test_projected_game_flips_are_counted(self) -> None:
        before = [
            {
                "matchup_period": 8,
                "home_team_id": 1,
                "away_team_id": 2,
                "winner_team_id": 2,
                "result_type": "PROJECTED",
            }
        ]
        after = [
            {
                "matchup_period": 8,
                "home_team_id": 1,
                "away_team_id": 2,
                "winner_team_id": 1,
                "result_type": "PROJECTED",
            }
        ]

        metrics = _projected_game_flip_metrics(
            "my", 1, before, after
        )

        self.assertEqual(1, metrics["my_projected_game_flips"])
        self.assertEqual(
            1, metrics["my_projected_wins_gained_from_flips"]
        )
        self.assertEqual(
            "Period 8: LOSS_TO_WIN",
            metrics["my_projected_game_flip_details"],
        )

    def test_playoff_path_lists_opponent_and_result(self) -> None:
        matchups = [
            {
                "bracket": "CHAMPIONSHIP",
                "round": 2,
                "round_name": "Semifinal",
                "matchup": 1,
                "team_a_id": 1,
                "team_a": "Alpha",
                "team_b_id": 2,
                "team_b": "Beta",
                "winner_team_id": 1,
            }
        ]

        self.assertEqual(
            "CHAMPIONSHIP R2 Semifinal vs Beta (WIN)",
            _playoff_path(1, matchups),
        )

    def test_trade_search_writes_only_results_and_summary(self) -> None:
        result = TradeSearchResult(
            all_evaluations=[{"trade_id": "trade_1"}],
            search_summary=[{"valid_trades_evaluated": 1}],
        )
        config = Config(
            league_id=1,
            season=2026,
            output_dir=Path("output-root"),
            espn_s2=None,
            swid=None,
        )
        out_path = Path("output-root/trade_search_timestamp")

        with (
            patch("pathlib.Path.mkdir"),
            patch(
                "fantasy_projection.trade_outputs.timestamped_run_dir",
                return_value=out_path,
            ),
            patch(
                "fantasy_projection.trade_outputs.write_csv"
            ) as write_csv,
            patch(
                "fantasy_projection.trade_outputs.write_json"
            ) as write_json,
        ):
            out = save_trade_outputs(config, result)

        self.assertEqual(out_path, out)
        write_csv.assert_called_once_with(
            out / "all_trade_results.csv",
            result.all_evaluations,
        )
        write_json.assert_called_once_with(
            out / "trade_search_summary.json",
            result.search_summary,
        )


if __name__ == "__main__":
    unittest.main()
