from __future__ import annotations

import unittest
from unittest.mock import patch

from fantasy_projection.season import LeagueState, SeasonModelError, SeasonRules, SeasonProjection
from fantasy_projection.trade_analysis import (
    evaluate_trade,
)


def _result(
    *,
    weekly_points: tuple[float, float],
    seeds: tuple[int, int],
    places: tuple[int, int],
    starters: tuple[int, int],
    champion: str,
) -> SeasonProjection:
    teams = [
        {"team_id": 1, "team_name": "Alpha"},
        {"team_id": 2, "team_name": "Beta"},
    ]
    rosters = [
        {
            "team_id": 1,
            "team_name": "Alpha",
            "player_id": 101,
            "player_name": "Alice Runner",
            "eligible_slots": [0],
        },
        {
            "team_id": 2,
            "team_name": "Beta",
            "player_id": 202,
            "player_name": "Bob Catcher",
            "eligible_slots": [0],
        },
    ]
    standings = [
        {
            "team_id": team_id,
            "team_name": name,
            "wins": 8 - index,
            "losses": 2 + index,
            "ties": 0,
            "points_for": 1000.0 - index * 10,
            "seed": seeds[index],
        }
        for index, (team_id, name) in enumerate(
            ((1, "Alpha"), (2, "Beta"))
        )
    ]
    final = [
        {
            "team_id": team_id,
            "team_name": name,
            "final_place": places[index],
        }
        for index, (team_id, name) in enumerate(
            ((1, "Alpha"), (2, "Beta"))
        )
    ]
    weekly = [
        {
            "team_id": team_id,
            "team_name": name,
            "week": 1,
            "projected_points": weekly_points[index],
        }
        for index, (team_id, name) in enumerate(
            ((1, "Alpha"), (2, "Beta"))
        )
    ]
    lineups = [
        {
            "team_id": team_id,
            "team_name": name,
            "week": 1,
            "slot_id": 0,
            "slot_name": "QB",
            "slot_instance": 1,
            "player_id": starters[index],
            "player_name": (
                "Alice Runner" if starters[index] == 101 else "Bob Catcher"
            ),
            "projected_points": weekly_points[index],
        }
        for index, (team_id, name) in enumerate(
            ((1, "Alpha"), (2, "Beta"))
        )
    ]
    return SeasonProjection(
        state=LeagueState(league_id=1, season=2026, first_week=1, current_week=1, final_week=1,
                          rules=SeasonRules(1, {1: (1,)}, 0, ()),
        teams=teams,
        rosters=rosters,
        player_projections=[],
        starter_slots=[],
        schedule_rows=[],
        settings_payload={},
        ),
        optimal_lineups=lineups,
        weekly_team_projections=weekly,
        regular_season_matchups=[],
        projected_standings=standings,
        postseason_matchups=[],
        final_standings=final,
        summary={
            "first_scoring_period": 1,
            "current_scoring_period": 1,
            "final_scoring_period": 1,
            "champion_team": champion,
        },
    )




class EvaluateTradeTests(unittest.TestCase):
    def test_builds_before_after_comparison_and_swaps_rosters(self) -> None:
        before = _result(
            weekly_points=(100.0, 90.0),
            seeds=(1, 2),
            places=(1, 2),
            starters=(101, 202),
            champion="Alpha",
        )
        after = _result(
            weekly_points=(105.0, 87.0),
            seeds=(1, 2),
            places=(1, 2),
            starters=(202, 101),
            champion="Alpha",
        )

        with patch(
            "fantasy_projection.trade_analysis."
            "project_season",
            return_value=after,
        ) as project:
            result = evaluate_trade(
                baseline=before,
                my_team_id=1,
                give_player_ids=[101],
                receive_player_ids=[202],
            )

        projected_rosters = project.call_args.args[0].rosters
        owners = {
            row["player_id"]: row["team_id"] for row in projected_rosters
        }
        self.assertEqual({101: 2, 202: 1}, owners)
        self.assertEqual(
            5.0, result.team_comparison[0]["future_points_change"]
        )
        self.assertEqual(
            -3.0, result.team_comparison[1]["future_points_change"]
        )
        self.assertTrue(result.lineup_comparison[0]["starter_changed"])
        self.assertEqual(
            "Bob Catcher",
            result.trade_summary["receive"][0]["player_name"],
        )

    def test_rejects_player_not_owned_by_my_team(self) -> None:
        before = _result(
            weekly_points=(100.0, 90.0),
            seeds=(1, 2),
            places=(1, 2),
            starters=(101, 202),
            champion="Alpha",
        )

        with self.assertRaisesRegex(SeasonModelError, "Received players"):
            evaluate_trade(
                baseline=before,
                my_team_id=1,
                give_player_ids=[202],
                receive_player_ids=[101],
            )


if __name__ == "__main__":
    unittest.main()
