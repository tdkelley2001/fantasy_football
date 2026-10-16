import unittest

from research.espn_history_probe import player_nodes, score_stat, weekly_records


class HistoricalExtractionTests(unittest.TestCase):
    def stat(self, **overrides):
        return dict(seasonId=2025, scoringPeriodId=1, statSourceId=0,
                    statSplitTypeId=1, stats={"3": 100}, **overrides)

    def test_stat_objects_are_not_players(self):
        payload = {"players": [{"player": {"id": 12, "fullName": "Example",
                    "proTeamId": 1, "stats": [dict(self.stat(), id="stat-id", proTeamId=1)]}}]}
        self.assertEqual(list(player_nodes(payload)), [12])

    def test_only_target_season_weekly_raw_records_survive(self):
        valid = self.stat()
        invalid = [dict(valid, seasonId=2024), dict(valid, scoringPeriodId=0),
                   dict(valid, scoringPeriodId=-1), dict(valid, statSplitTypeId=0),
                   dict(valid, statSourceId=2), dict(valid, stats=None)]
        records, _ = weekly_records({12: {"stats": invalid + [valid]}}, 2025)
        self.assertEqual(records, {(12, 1, 0): valid})
        self.assertNotIn((12, 1, 1), records)  # Missing projection is not zero.

    def test_conflicting_duplicates_are_quarantined_regardless_of_order(self):
        first = self.stat()
        other = dict(first, stats={"3": 0})
        for rows in ([first, other, first], [other, first, other]):
            records, duplicates = weekly_records({12: {"stats": rows}}, 2025)
            self.assertEqual(records, {})
            self.assertEqual(duplicates, 2)
        records, duplicates = weekly_records({12: {"stats": [first, first]}}, 2025)
        self.assertEqual(len(records), 1)
        self.assertEqual(duplicates, 1)

    def test_position_override_and_fractional_bucket_are_preserved(self):
        items = [{"statId": 89, "points": 0, "pointsOverrides": {"16": 10}}]
        self.assertEqual(score_stat({"stats": {"89": .125}}, 16, items), 1.25)
        self.assertEqual(score_stat({"stats": {"89": .125}}, 1, items), 0)
        self.assertEqual(score_stat({"stats": {}}, 16, items), 0)
