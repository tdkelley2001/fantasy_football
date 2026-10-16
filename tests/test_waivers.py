from __future__ import annotations

import unittest

from fantasy_projection.espn import normalize_available_players
from fantasy_projection.waivers import (
    WaiverSearchOptions,
    _filter_waiver_candidates,
    _marginal_roster_values,
    _move_tags,
    _position_limit_allows,
)


class AvailablePlayerTests(unittest.TestCase):
    def test_generation_filters_adds_and_drops_before_evaluation(self) -> None:
        players = {
            1: {"player_id": 1, "default_position_id": 2},
            2: {"player_id": 2, "default_position_id": 3},
            3: {"player_id": 3, "default_position_id": 5},
            10: {"player_id": 10, "default_position_id": 2},
            11: {"player_id": 11, "default_position_id": 3},
        }
        options = WaiverSearchOptions(
            add_positions=(2,), target_add_player_ids=(1,),
            untouchable_drop_player_ids=(11,), include_special_teams=False,
        )
        adds, drops = _filter_waiver_candidates(
            [1, 2, 3], [players[10], players[11]], players, options
        )
        self.assertEqual([1], adds)
        self.assertEqual([10], [row["player_id"] for row in drops])

    def test_normalizes_only_free_agents_and_waivers(self) -> None:
        payload = {
            "players": [
                {
                    "status": "FREEAGENT",
                    "player": {
                        "id": 101,
                        "fullName": "Free Agent",
                        "defaultPositionId": 3,
                        "proTeamId": 8,
                        "eligibleSlots": [4, 23, 20],
                        "injuryStatus": "ACTIVE",
                        "ownership": {
                            "percentOwned": 15.5,
                            "percentStarted": 2.0,
                        },
                    },
                },
                {
                    "status": "WAIVERS",
                    "player": {
                        "id": 202,
                        "fullName": "Waiver Player",
                        "defaultPositionId": 2,
                        "eligibleSlots": [2, 23, 20],
                    },
                },
                {
                    "status": "ONTEAM",
                    "player": {
                        "id": 303,
                        "fullName": "Rostered Player",
                    },
                },
            ]
        }

        rows = normalize_available_players(payload)

        self.assertEqual([101, 202], [row["player_id"] for row in rows])
        self.assertEqual([4, 23, 20], rows[0]["eligible_slots"])
        self.assertEqual(15.5, rows[0]["percent_owned"])


class WaiverMetricTests(unittest.TestCase):
    def test_position_limit_rejects_an_extra_quarterback(self) -> None:
        players = {
            1: {"default_position_id": 1},
            2: {"default_position_id": 2},
            3: {"default_position_id": 1},
        }
        settings = {
            "settings": {
                "rosterSettings": {
                    "positionLimits": {"1": 1, "2": 3}
                }
            }
        }

        allowed = _position_limit_allows(
            frozenset({1, 3}),
            baseline_player_ids=frozenset({1, 2}),
            players=players,
            settings_payload=settings,
        )

        self.assertFalse(allowed)

    def test_move_tags_identify_stash_and_outcome_change(self) -> None:
        record = {
            "team_current_week_lineup_gain": 0.0,
            "team_total_remaining_season_lineup_gain": 4.0,
            "team_positive_weeks": 2,
            "team_median_weekly_lineup_gain": 0.0,
            "team_playoff_window_total_lineup_gain": 5.0,
            "team_regular_season_total_lineup_gain": -1.0,
            "team_projected_game_flips": 1,
            "team_projected_wins_change": 1,
            "team_regular_seed_improvement": 1,
            "team_final_place_improvement": 2,
        }

        tags = _move_tags(record)

        self.assertIn("BYE_OR_DEPTH_IMPROVEMENT", tags)
        self.assertIn("PLAYOFF_STASH", tags)
        self.assertIn("FLIPS_PROJECTED_GAME", tags)
        self.assertIn("IMPROVES_FINAL_POSITION", tags)

    def test_marginal_value_is_negative_when_replacement_improves_team(self) -> None:
        roster = [
            {
                "player_id": 10,
                "player_name": "Incumbent",
                "default_position_id": 3,
            }
        ]
        transactions = [
            {
                "evaluation_status": "VALID",
                "drop_player_id": 10,
                "add_player_id": 20,
                "add_player": "Replacement",
                "add_position": "WR",
                "same_position_swap": True,
                "team_current_week_lineup_gain": 1.0,
                "team_avg_remaining_season_lineup_gain": 2.0,
                "team_total_remaining_season_lineup_gain": 20.0,
                "team_regular_season_total_lineup_gain": 12.0,
                "team_playoff_window_total_lineup_gain": 8.0,
                "team_projected_wins_change": 1,
                "team_regular_seed_improvement": 1,
                "team_final_place_improvement": 1,
            }
        ]

        rows = _marginal_roster_values(transactions, roster)

        self.assertEqual(-2.0, rows[0]["marginal_avg_weekly_lineup_value"])
        self.assertEqual(-20.0, rows[0]["marginal_total_remaining_lineup_value"])
        self.assertEqual("Replacement", rows[0]["best_available_replacement"])

    def test_undroppable_player_remains_in_marginal_output(self) -> None:
        roster = [
            {
                "player_id": 10,
                "player_name": "Protected Player",
                "default_position_id": 2,
                "droppable": False,
            }
        ]

        rows = _marginal_roster_values([], roster)

        self.assertEqual(1, len(rows))
        self.assertEqual(
            "NO_EXECUTABLE_REPLACEMENT",
            rows[0]["marginal_value_status"],
        )



if __name__ == "__main__":
    unittest.main()
