import copy
import unittest

from fantasy_projection.history import (
    canonical_rows, diagnose, index_games, resolve_records, scoring_version,
)

RULES = [{"statId": 3, "points": .04}, {"statId": 20, "points": -2},
         {"statId": 89, "points": 0, "pointsOverrides": {"16": 10}}]


def schedule():
    return [dict(id=f"{week}-{team}", season={"year":2018,"type":2},week={"number":week},
                 status={"type":{"name":"STATUS_FINAL","completed":True}},
                 competitions=[{"competitors":[{"team":{"id":str(team)}}, {"team":{"id":str(team+1)}}]}])
            for week in range(1,18) for team in range(1,33,2)
            if week != (9 if team <= 16 else 8)]


def stat(source, week=1, stats=None, **changes):
    return dict(dict(seasonId=2018,scoringPeriodId=week,statSourceId=source,
                     statSplitTypeId=1,proTeamId=1,stats={"210":1,"3":100} if stats is None else stats),**changes)


def rows(records, games=None, position=1):
    return list(canonical_rows([dict(id=1,fullName="Test",defaultPositionId=position,
                                   proTeamId=1,eligibleSlots=[0],stats=records)],
                              schedule() if games is None else games,2018,RULES,{}))


class CanonicalHistoryTests(unittest.TestCase):
    def test_universe_and_missing_are_preserved(self):
        result=rows([stat(0),stat(1)])
        self.assertEqual(len(result),17)
        self.assertTrue(result[0]["initial_sample"])
        self.assertEqual(result[1]["actual_status"],"missing")
        self.assertIsNone(result[1]["actual_points"])
        self.assertIsNone(result[1]["zero_actual"])
        self.assertEqual(result[1]["participation_status"],"unknown")

    def test_zero_actual_played_is_included_but_zero_projection_is_not(self):
        r=rows([stat(0,stats={"210":1}),stat(1)])[0]
        self.assertTrue(r["zero_actual"])
        self.assertTrue(r["initial_sample"])
        r=rows([stat(0),stat(1,stats={})])[0]
        self.assertIn("nonpositive_projection",r["sample_exclusions"])

    def test_negative_actual_is_retained(self):
        r=rows([stat(0,stats={"210":1,"20":2}),stat(1)])[0]
        self.assertEqual(r["actual_points"],-4)
        self.assertEqual(r["residual"],-8)
        self.assertTrue(r["initial_sample"])

    def test_dnp_does_not_prove_inactive(self):
        r=rows([stat(0,stats={"210":0}),stat(1)])[0]
        self.assertEqual(r["participation_status"],"did_not_play")
        self.assertEqual(r["inactive_status"],"unknown")
        self.assertFalse(r["initial_sample"])

    def test_activity_proves_appearance_when_gp_is_absent(self):
        r=rows([stat(0,stats={"58":1}),stat(1)])[0]
        self.assertEqual(r["actual_points"],0)
        self.assertEqual(r["participation_evidence"],"actual_recorded_activity")
        self.assertTrue(r["initial_sample"])
        r=rows([stat(0,stats={}),stat(1)])[0]
        self.assertEqual(r["participation_status"],"unknown")
        self.assertFalse(r["initial_sample"])
        r=rows([stat(0,stats={"210":0,"58":1}),stat(1)])[0]
        self.assertTrue(r["participation_conflict"])
        self.assertFalse(r["initial_sample"])

    def test_cancellation_overrides_stat_pair_presence(self):
        events=schedule()
        events[0]["status"]["type"]={"name":"STATUS_CANCELED","completed":False}
        r=rows([stat(0),stat(1)],events)[0]
        self.assertEqual(r["game_status"],"cancelled")
        self.assertTrue(r["participation_conflict"])
        self.assertFalse(r["initial_sample"])

    def test_bye_and_inferred_bye_have_separate_evidence(self):
        result=rows([stat(0,8),stat(0,10)])
        self.assertEqual(result[8]["game_status"],"inferred_bye")
        r=rows([stat(0,9,stats={"210":0})])[8]
        self.assertEqual(r["game_status"],"bye")
        self.assertFalse(r["initial_sample"])

    def test_conflict_keeps_both_raw_records_and_no_arbitrary_score(self):
        a=stat(0); b=stat(0,stats={"3":50,"210":1})
        for records in ([a,b,stat(1)],[b,a,stat(1)]):
            r=rows(records)[0]
            self.assertEqual(r["actual_status"],"conflicting")
            self.assertIsNone(r["actual_points"])
            self.assertEqual(len(r["raw_actual_records"]),2)
            self.assertFalse(r["initial_sample"])

    def test_exact_duplicates_and_nonfinite_values(self):
        a=stat(0)
        self.assertEqual(resolve_records([a,copy.deepcopy(a)],1,RULES)[0],"valid")
        self.assertEqual(resolve_records([stat(0,stats={"3":float("nan")})],1,RULES)[0],"invalid")

    def test_team_disagreement_excludes_sample(self):
        r=rows([stat(0),stat(1,proTeamId=3)])[0]
        self.assertTrue(r["team_conflict"])
        self.assertIn("team_conflict",r["sample_exclusions"])

    def test_scoring_version_and_fractional_defensive_bucket(self):
        r=rows([stat(0,stats={"89":1}),stat(1,stats={"89":.125})],position=16)[0]
        self.assertEqual(r["projection_points"],1.25)
        self.assertEqual(r["actual_points"],10)
        self.assertEqual(scoring_version(RULES),scoring_version(list(reversed(RULES))))
        with self.assertRaises(ValueError):
            scoring_version([dict(statId=3,points=1,isReverseItem=True)])

    def test_incomplete_schedule_is_rejected(self):
        with self.assertRaises(ValueError):
            rows([],schedule()[1:])

    def test_diagnostics_use_only_selected_rows_and_known_residuals(self):
        result=rows([stat(0,stats={"210":1,"3":200}),stat(1),
                     stat(0,2,stats={"210":1}),stat(1,2),
                     stat(0,3,stats={"210":0}),stat(1,3)])
        report=diagnose(result)
        self.assertEqual(report["canonical_rows"],17)
        self.assertEqual(report["overall"]["n"],2)
        self.assertEqual(report["overall"]["mean_error"],0)
        self.assertEqual(report["overall"]["mae"],4)
        self.assertEqual(report["overall"]["zero_actual_rate"],.5)


if __name__ == "__main__":
    unittest.main()
