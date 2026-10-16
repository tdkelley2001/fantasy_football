from copy import deepcopy
from dataclasses import replace
import math
import unittest
from unittest.mock import patch

from fantasy_projection.history import SAMPLE_VERSION, scoring_version
from fantasy_projection.monte_carlo import ResidualModel, player_draws, simulate_season
from fantasy_projection.pipeline import normalize_bye_weeks
from fantasy_projection.season import SeasonModelError, project_season
from test_season import league, matchup, finish_regular

RULES = [{"statId":3,"points":.04}]


def model(zero=False, size=1000):
    rows=[dict(season=2024,week=1,player_id=i,position="QB",projection_points=1+i/50,
               residual=7 if zero else (-10 if i%2 else 10),sample_version=SAMPLE_VERSION,
               initial_sample=True,sample_exclusions=[]) for i in range(size)]
    return ResidualModel(rows,scoring_version(RULES),"synthetic"),rows


def state(**kwargs):
    s=league(**kwargs)
    s.settings_payload["settings"]["scoringSettings"]={"scoringItems":RULES}
    return s


class MonteCarloTests(unittest.TestCase):
    def test_pool_matches_research_selection_and_has_zero_mean(self):
        from research.validate_residuals import Pools
        m,rows=model()
        research=Pools(rows)
        query=dict(season=2026,week=1,projection_points=7.5,position="QB")
        expected=research.forecast("D",query)
        pool=m.pool("QB",7.5,(2026,1))
        self.assertEqual(len(pool),500)
        self.assertAlmostEqual(math.fsum(pool),0,places=10)
        self.assertEqual(sorted(pool),[v-expected.mean for v in expected.x])

    def test_sparse_position_and_future_history_are_rejected(self):
        m,_=model(size=499)
        with self.assertRaises(SeasonModelError):m.pool("QB",10,(2026,1))
        m,_=model()
        with self.assertRaises(SeasonModelError):m.pool("TE",10,(2026,1))
        with self.assertRaises(SeasonModelError):m.pool("QB",10,(2024,1))

    def test_keyed_draws_are_reproducible_prefix_stable_and_unclipped(self):
        m,_=model()
        args=dict(season=2026,week=1,player_id=1,cutoff=(2026,1),seed=5)
        short=player_draws(m,"QB",1,simulations=20,**args)
        long=player_draws(m,"QB",1,simulations=100,**args)
        self.assertEqual(short,long[:20])
        self.assertLess(min(long),0)
        other=player_draws(m,"QB",1,simulations=20,**{**args,"player_id":2})
        self.assertNotEqual(short,other)

    def test_zero_variance_reproduces_deterministic_outcomes_without_mutation(self):
        s=state();before=deepcopy(s);m,_=model(zero=True)
        actual=simulate_season(s,m,simulations=8,seed=1)
        expected=project_season(s)
        for r in expected.team_outcomes:
            t=next(t for t in actual["teams"] if t["team_id"]==r["team_id"])
            self.assertEqual(t["expected_wins"],r["wins"])
            self.assertEqual(t["finish"]["p50"],r["final_place"])
            self.assertEqual(t["championship_probability"],float(r["final_place"]==1))
        self.assertEqual(s,before)

    def test_expected_lineup_selected_before_scores_are_drawn(self):
        s=state();m,_=model()
        s.rosters.append(dict(s.rosters[0],player_id=99,player_name="Bench"))
        s.player_projections.extend(dict(player_id=99,week=w,projected_points=89.) for w in range(1,s.final_week+1))
        def draw(*args,**kwargs):
            self.assertNotEqual(kwargs["player_id"],99)
            return [0.]*kwargs["simulations"]
        with patch('fantasy_projection.monte_carlo.player_draws',side_effect=draw):
            result=simulate_season(s,m,simulations=2)
        self.assertTrue(all(w["mean"]==0 for w in result["weekly"]))

    def test_confirmed_bye_zero_and_missing_projection_fail(self):
        s=state();m,_=model(zero=True)
        s=replace(s,player_bye_weeks={1:(1,)})
        result=simulate_season(s,m,simulations=3)
        w=next(w for w in result["weekly"] if w["team_id"]==1 and w["week"]==1)
        self.assertEqual(w["mean"],0)
        s=replace(s,player_bye_weeks={},player_projections=[p for p in s.player_projections if (p["player_id"],p["week"])!=(1,1)])
        with self.assertRaisesRegex(SeasonModelError,"Missing starter"):
            simulate_season(s,m,simulations=3)

    def test_actuals_and_partial_multiweek_results_are_preserved(self):
        s=state(current_week=2,multiweek=True);m,_=model()
        s.schedule_rows[:2]=[matchup(1,1,2,"AWAY",10,100),matchup(1,3,4,"HOME",30,20)]
        result=simulate_season(s,m,simulations=20)
        self.assertEqual(next(w for w in result["weekly"] if (w["team_id"],w["week"])==(2,1))["mean"],100)
        self.assertGreaterEqual(next(t for t in result["teams"] if t["team_id"]==2)["expected_wins"],1)

    def test_probability_conservation_and_reproducibility(self):
        s=state();m,_=model()
        for p in s.player_projections:p["projected_points"]=10.
        a=simulate_season(s,m,simulations=200,seed=9)
        b=simulate_season(s,m,simulations=200,seed=9)
        self.assertEqual(a,b)
        self.assertAlmostEqual(sum(t["championship_probability"] for t in a["teams"]),1)
        self.assertAlmostEqual(sum(t["playoff_probability"] for t in a["teams"]),4)
        for t in a["teams"]:
            self.assertAlmostEqual(sum(t["finish_distribution"].values()),1)

    def test_future_effective_rosters_and_shared_draws(self):
        s=state();m,_=model()
        roster=deepcopy(s.rosters)
        roster[0]["team_id"],roster[1]["team_id"]=2,1
        scenario=s.with_rosters(roster)
        a=simulate_season(s,m,simulations=30,seed=7)
        b=simulate_season(scenario,m,simulations=30,seed=7,effective_week=2)
        def weekly(result,tid,week):return next(w for w in result["weekly"] if (w["team_id"],w["week"])==(tid,week))
        self.assertEqual(weekly(a,1,1),weekly(b,1,1))
        self.assertEqual(weekly(a,1,2)["mean"],weekly(b,2,2)["mean"])
        self.assertEqual(weekly(a,3,2),weekly(b,3,2))

    def test_completed_season_no_playoffs_and_bad_scoring(self):
        s=state(team_count=2,playoff_count=0,current_week=3);m,_=model()
        s=replace(s,schedule_rows=[matchup(1,1,2,"HOME",20,10),matchup(2,1,2,"TIE",10,10)])
        r=simulate_season(s,m,simulations=2)
        self.assertIsNone(r["teams"][0]["championship_probability"])
        self.assertEqual(r["teams"][0]["expected_wins"],1)
        self.assertEqual(r["teams"][0]["expected_ties"],1)
        s=replace(s,settings_payload={})
        with self.assertRaisesRegex(SeasonModelError,"scoring"):
            simulate_season(s,m,simulations=2)

    def test_bye_normalization_requires_complete_schedule(self):
        s=state();s.rosters[0]["pro_team_id"]=1
        payload={"settings":{"proTeams":[{"id":t,"proGamesByScoringPeriod":{
            str(w):[{"id":w}] for w in range(1,19) if w!=9}} for t in range(1,33)]}}
        self.assertEqual(normalize_bye_weeks(s,payload)[1],(9,))
        payload["settings"]["proTeams"].pop()
        with self.assertRaises(SeasonModelError):normalize_bye_weeks(s,payload)

    def test_partial_playoff_round_and_completed_upset_survive_draws(self):
        m,_=model(zero=True)
        s=finish_regular(state(team_count=2,playoff_count=2,multiweek=True))
        s=replace(s,current_week=4,actual_weekly_points=[dict(team_id=1,week=3,points=1.),
                                                       dict(team_id=2,week=3,points=100.)])
        r=simulate_season(s,m,simulations=4)
        self.assertEqual(next(t for t in r["teams"] if t["team_id"]==2)["championship_probability"],1)
        s=replace(s,current_week=5,rosters=[],player_projections=[],postseason_results=[
            matchup(3,1,2,"HOME",200,180)])
        r=simulate_season(s,m,simulations=4)
        self.assertEqual(next(t for t in r["teams"] if t["team_id"]==1)["championship_probability"],1)
        self.assertTrue(all(t["expected_remaining_points"]==0 for t in r["teams"]))

    def test_probability_conservation_supported_brackets(self):
        m,_=model(zero=True)
        for teams,playoffs in ((4,2),(6,4),(10,6),(10,8)):
            s=state(team_count=teams,playoff_count=playoffs,multiweek=True)
            r=simulate_season(s,m,simulations=2)
            self.assertAlmostEqual(sum(t["playoff_probability"] for t in r["teams"]),playoffs)
            self.assertAlmostEqual(sum(t["championship_probability"] for t in r["teams"]),1)
            self.assertEqual(sorted(t["finish"]["p50"] for t in r["teams"]),list(range(1,teams+1)))
