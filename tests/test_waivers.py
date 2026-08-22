from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import call, patch

from fantasy_projection.config import Config
from fantasy_projection.espn import normalize_available_players
from fantasy_projection.waiver_outputs import save_waiver_outputs
from fantasy_projection.waivers import (
    WaiverAnalysisResult,
    _marginal_roster_values,
    _move_tags,
    _position_limit_allows,
)


class AvailablePlayerTests(unittest.TestCase):
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

    def test_waiver_output_contract_uses_one_timestamped_folder(self) -> None:
        result = WaiverAnalysisResult(
            available_players=[{"player_id": 1, "eligible_slots": [2]}],
            transactions=[{"add_player_id": 1, "drop_player_id": 2}],
            marginal_roster_values=[{"rostered_player_id": 2}],
            summary={"valid_transactions": 1},
        )
        config = Config(1, 2026, Path("outputs"), None, None)
        out = Path("outputs/waiver_analysis_timestamp")

        with (
            patch("pathlib.Path.mkdir"),
            patch(
                "fantasy_projection.waiver_outputs.timestamped_run_dir",
                return_value=out,
            ),
            patch(
                "fantasy_projection.waiver_outputs.write_csv"
            ) as write_csv,
            patch(
                "fantasy_projection.waiver_outputs.write_json"
            ) as write_json,
        ):
            actual = save_waiver_outputs(config, result)

        self.assertEqual(out, actual)
        self.assertEqual(3, write_csv.call_count)
        self.assertEqual(
            call(out / "waiver_analysis_summary.json", result.summary),
            write_json.call_args,
        )


if __name__ == "__main__":
    unittest.main()
