from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fantasy_projection.config import Config
from fantasy_projection.pipeline import ProjectionResult
from fantasy_projection.trade_analysis import (
    evaluate_trade,
    resolve_player_references,
)


def _result(
    *,
    weekly_points: tuple[float, float],
    seeds: tuple[int, int],
    places: tuple[int, int],
    starters: tuple[int, int],
    champion: str,
) -> ProjectionResult:
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
    return ProjectionResult(
        teams=teams,
        rosters=rosters,
        player_projections=[],
        starter_slots=[],
        schedule_rows=[],
        settings_payload={},
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


class ResolvePlayerReferencesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rosters = _result(
            weekly_points=(100.0, 90.0),
            seeds=(1, 2),
            places=(1, 2),
            starters=(101, 202),
            champion="Alpha",
        ).rosters

    def test_resolves_case_insensitive_name_and_id(self) -> None:
        actual = resolve_player_references(
            self.rosters, ["alice runner", "202"]
        )
        self.assertEqual((101, 202), actual)

    def test_unknown_player_includes_partial_match(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Alice Runner"):
            resolve_player_references(self.rosters, ["Alice"])


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
        config = Config(1, 2026, Path("outputs"), None, None)

        with patch(
            "fantasy_projection.trade_analysis."
            "project_from_normalized_inputs",
            return_value=after,
        ) as project:
            result = evaluate_trade(
                baseline=before,
                config=config,
                my_team_id=1,
                give_player_ids=[101],
                receive_player_ids=[202],
            )

        projected_rosters = project.call_args.kwargs["rosters"]
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
        config = Config(1, 2026, Path("outputs"), None, None)

        with self.assertRaisesRegex(RuntimeError, "does not roster"):
            evaluate_trade(
                baseline=before,
                config=config,
                my_team_id=1,
                give_player_ids=[202],
                receive_player_ids=[101],
            )


if __name__ == "__main__":
    unittest.main()
