from __future__ import annotations

import unittest
from unittest.mock import patch

from fantasy_projection.lineup import optimize_lineup, optimize_lineup_weeks
from fantasy_projection.trades import (
    _candidate_packages,
    _packages,
    _evaluate_all_trades_for_type,
    _playoff_path,
    _projected_game_flip_metrics,
    _tradable_player_ids,
    _weekly_lineup_metrics,
)


class TradeMetricTests(unittest.TestCase):
    def test_three_player_packages_are_generated(self) -> None:
        self.assertEqual([(1, 2, 3), (1, 2, 4), (1, 3, 4), (2, 3, 4)], _packages([1, 2, 3, 4], 3))

    def test_lineup_failure_in_asymmetric_resolution_skips_candidate(self) -> None:
        from types import SimpleNamespace

        baseline = SimpleNamespace(
            state=SimpleNamespace(
                teams=[{"team_id": 1, "team_name": "Mine"},
                       {"team_id": 2, "team_name": "Theirs"}],
                rosters=[], starter_slots=[], current_week=1,
            ),
            weekly_team_projections=[
                {"team_id": 1, "week": 1, "projected_points": 10.0},
                {"team_id": 2, "week": 1, "projected_points": 10.0},
            ], projected_standings=[],
            final_standings=[],
        )
        options = SimpleNamespace(
            partner_ids=(),
            include_player_ids=(), exclude_player_ids=(),
            untouchable_player_ids=(), target_player_ids=(),
            include_positions=(), exclude_positions=(),
            include_special_teams=True, effective_week=1,
            runtime=SimpleNamespace(candidate_limit=1, mode="quick"),
        )

        with patch("fantasy_projection.trades.select_trade_resolution",
                   side_effect=RuntimeError("Cannot fill required lineup slots")):
            rows, summary = _evaluate_all_trades_for_type(
                give_size=1, receive_size=2, baseline=baseline,
                trade_config=SimpleNamespace(my_team_id=1),
                roster_ids={1: {101}, 2: {201, 202, 203}},
                players={101: {"player_name": "A", "default_position_id": 2},
                         201: {"player_name": "B", "default_position_id": 2},
                         202: {"player_name": "C", "default_position_id": 4},
                         203: {"player_name": "D", "default_position_id": 6}},
                projection_lookup={}, score_cache={}, future_weeks=(1,),
                regular_weeks=(1,), postseason_weeks=(), options=options,
            )

        self.assertEqual([], rows)
        self.assertEqual(1, summary["lossless_filtered"])
        self.assertEqual(3, summary["generated"])
        self.assertEqual(1, summary["evaluated"])

    def test_candidate_generation_applies_assets_positions_and_special_teams(self) -> None:
        players = {
            1: {"default_position_id": 2},
            2: {"default_position_id": 3},
            3: {"default_position_id": 5},
            4: {"default_position_id": 2},
        }
        packages = _candidate_packages(
            [1, 2, 3, 4], 2, players, required=(1,), excluded=(4,),
            include_positions=(3,), exclude_positions=(), include_special=False,
        )
        self.assertEqual([(1, 2)], packages)

    def test_multiweek_optimizer_matches_independent_weekly_results(self) -> None:
        roster = [
            {
                "player_id": 1,
                "player_name": "RB One",
                "eligible_slots": [2, 23],
            },
            {
                "player_id": 2,
                "player_name": "RB Two",
                "eligible_slots": [2, 23],
            },
            {
                "player_id": 3,
                "player_name": "WR One",
                "eligible_slots": [4, 23],
            },
        ]
        slots = [
            {"slot_id": 2, "slot_name": "RB", "slot_instance": 1},
            {"slot_id": 23, "slot_name": "FLEX", "slot_instance": 1},
        ]
        projections = {
            (1, 1): 10.0,
            (2, 1): 8.0,
            (3, 1): 9.0,
            (1, 2): 2.0,
            (2, 2): 12.0,
            (3, 2): 11.0,
        }

        expected = tuple(
            optimize_lineup(roster, slots, projections, week)[0]
            for week in (1, 2)
        )

        self.assertEqual(
            expected,
            optimize_lineup_weeks(
                roster, slots, projections, (1, 2)
            ),
        )

    def test_standard_fast_path_matches_independent_lineups(self) -> None:
        slots = [
            {"slot_id": 0, "slot_name": "QB", "slot_instance": 1},
            {"slot_id": 2, "slot_name": "RB", "slot_instance": 1},
            {"slot_id": 2, "slot_name": "RB", "slot_instance": 2},
            {"slot_id": 4, "slot_name": "WR", "slot_instance": 1},
            {"slot_id": 4, "slot_name": "WR", "slot_instance": 2},
            {"slot_id": 6, "slot_name": "TE", "slot_instance": 1},
            {"slot_id": 16, "slot_name": "D/ST", "slot_instance": 1},
            {"slot_id": 17, "slot_name": "K", "slot_instance": 1},
            {"slot_id": 23, "slot_name": "FLEX", "slot_instance": 1},
        ]
        definitions = [
            (1, [0]),
            (2, [2, 23]),
            (3, [2, 23]),
            (4, [2, 23]),
            (5, [4, 23]),
            (6, [4, 23]),
            (7, [4, 23]),
            (8, [6, 23]),
            (9, [6, 23]),
            (10, [16]),
            (11, [17]),
        ]
        roster = [
            {
                "player_id": player_id,
                "player_name": f"Player {player_id}",
                "eligible_slots": eligible,
            }
            for player_id, eligible in definitions
        ]
        projections = {
            (player_id, week): float((player_id * 7 + week * 3) % 17)
            for player_id, _ in definitions
            for week in (1, 2, 3)
        }
        expected = tuple(
            optimize_lineup(roster, slots, projections, week)[0]
            for week in (1, 2, 3)
        )

        self.assertEqual(
            expected,
            optimize_lineup_weeks(
                roster, slots, projections, (1, 2, 3)
            ),
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
        self.assertAlmostEqual(1 / 3, metrics["my_sustained_weekly_lineup_gain"])
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



if __name__ == "__main__":
    unittest.main()
