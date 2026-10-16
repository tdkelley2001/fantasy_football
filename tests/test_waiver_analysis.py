from __future__ import annotations

import unittest
from unittest.mock import patch

from fantasy_projection.season import LeagueState, SeasonModelError, SeasonRules, SeasonProjection
from fantasy_projection.waiver_analysis import (
    evaluate_waiver,
)


def _result(
    *,
    my_points: float,
    my_starter_id: int,
    my_starter_name: str,
    my_wins: int,
    my_seed: int,
    my_place: int,
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
            "player_name": "Current Player",
            "default_position_id": 3,
            "eligible_slots": [4],
            "droppable": True,
            "lineup_locked": False,
            "roster_locked": False,
        },
        {
            "team_id": 2,
            "team_name": "Beta",
            "player_id": 202,
            "player_name": "Opponent Player",
            "default_position_id": 3,
            "eligible_slots": [4],
            "droppable": True,
            "lineup_locked": False,
            "roster_locked": False,
        },
    ]
    standings = [
        {
            "team_id": 1,
            "team_name": "Alpha",
            "wins": my_wins,
            "losses": 10 - my_wins,
            "ties": 0,
            "points_for": 1000.0,
            "seed": my_seed,
        },
        {
            "team_id": 2,
            "team_name": "Beta",
            "wins": 7,
            "losses": 3,
            "ties": 0,
            "points_for": 950.0,
            "seed": 2 if my_seed == 1 else 1,
        },
    ]
    final = [
        {
            "team_id": 1,
            "team_name": "Alpha",
            "final_place": my_place,
        },
        {
            "team_id": 2,
            "team_name": "Beta",
            "final_place": 2 if my_place == 1 else 1,
        },
    ]
    weekly = [
        {
            "team_id": 1,
            "team_name": "Alpha",
            "week": 1,
            "projected_points": my_points,
        },
        {
            "team_id": 2,
            "team_name": "Beta",
            "week": 1,
            "projected_points": 90.0,
        },
    ]
    lineups = [
        {
            "team_id": 1,
            "team_name": "Alpha",
            "week": 1,
            "slot_id": 4,
            "slot_name": "WR",
            "slot_instance": 1,
            "player_id": my_starter_id,
            "player_name": my_starter_name,
            "projected_points": my_points,
        },
        {
            "team_id": 2,
            "team_name": "Beta",
            "week": 1,
            "slot_id": 4,
            "slot_name": "WR",
            "slot_instance": 1,
            "player_id": 202,
            "player_name": "Opponent Player",
            "projected_points": 90.0,
        },
    ]
    return SeasonProjection(
        state=LeagueState(league_id=1, season=2026, first_week=1, current_week=1, final_week=1,
                          rules=SeasonRules(1, {1: (1,)}, 0, ()),
        teams=teams,
        rosters=rosters,
        player_projections=[
            {
                "player_id": 101,
                "player_name": "Current Player",
                "week": 1,
                "projected_points": 10.0,
            },
            {
                "player_id": 303,
                "player_name": "Available Player",
                "week": 1,
                "projected_points": 15.0,
            },
        ],
        starter_slots=[
            {"slot_id": 4, "slot_name": "WR", "slot_instance": 1}
        ],
        schedule_rows=[],
        settings_payload={
            "settings": {"rosterSettings": {"positionLimits": {"3": 4}}}
        },
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
            "regular_season_matchup_periods": 1,
            "playoff_team_count": 1,
            "champion_team": "Alpha" if my_place == 1 else "Beta",
        },
    )


def _available() -> list[dict[str, object]]:
    return [
        {
            "team_id": None,
            "team_name": None,
            "player_id": 303,
            "player_name": "Available Player",
            "default_position_id": 3,
            "eligible_slots": [4],
            "availability_status": "FREEAGENT",
        }
    ]




class EvaluateWaiverTests(unittest.TestCase):
    def test_builds_before_after_comparison_and_replaces_player(self) -> None:
        before = _result(
            my_points=10.0,
            my_starter_id=101,
            my_starter_name="Current Player",
            my_wins=6,
            my_seed=2,
            my_place=2,
        )
        after = _result(
            my_points=15.0,
            my_starter_id=303,
            my_starter_name="Available Player",
            my_wins=7,
            my_seed=1,
            my_place=1,
        )

        with patch(
            "fantasy_projection.waiver_analysis."
            "project_season",
            return_value=after,
        ) as project:
            result = evaluate_waiver(
                baseline=before,
                my_team_id=1,
                available_players=_available(),
                add_player_id=303,
                drop_player_id=101,
            )

        projected_roster = project.call_args.args[0].rosters
        my_ids = {
            row["player_id"]
            for row in projected_roster
            if row["team_id"] == 1
        }
        self.assertEqual({303}, my_ids)
        self.assertEqual(
            5.0,
            result.team_comparison[0]["team_current_week_lineup_gain"],
        )
        self.assertEqual(
            1,
            result.team_comparison[0]["team_projected_wins_change"],
        )
        self.assertTrue(result.lineup_comparison[0]["starter_changed"])
        self.assertIn("IMMEDIATE_UPGRADE", result.waiver_summary["move_tags"])

    def test_rejects_undroppable_player(self) -> None:
        before = _result(
            my_points=10.0,
            my_starter_id=101,
            my_starter_name="Current Player",
            my_wins=6,
            my_seed=2,
            my_place=2,
        )
        before.state.rosters[0]["droppable"] = False

        with self.assertRaisesRegex(SeasonModelError, "undroppable"):
            evaluate_waiver(
                baseline=before,
                my_team_id=1,
                available_players=_available(),
                add_player_id=303,
                drop_player_id=101,
            )


if __name__ == "__main__":
    unittest.main()
