from copy import deepcopy
from dataclasses import replace
from itertools import permutations
import unittest
from unittest.mock import patch

from fantasy_projection.season import LeagueState, SeasonRules, SeasonModelError, project_season
from fantasy_projection.lineup import optimize_lineup, optimize_lineup_weeks
from fantasy_projection.regular_season import build_projected_standings
from fantasy_projection.league_data import normalize_season_rules, normalize_schedule, normalize_actual_weekly_points
from fantasy_projection.trades import _scenario_metrics, _team_metrics, _preserve_actual_scores
from fantasy_projection.trade_analysis import evaluate_trade
from fantasy_projection.waiver_analysis import evaluate_waiver


def matchup(period, home, away, winner="UNDECIDED", home_points=None, away_points=None):
    return dict(matchup_period=period, home_team_id=home, away_team_id=away,
                winner=winner, actual_home_points=home_points, actual_away_points=away_points)


def league(team_count=4, playoff_count=4, current_week=1, multiweek=False):
    rounds = {0: 0, 2: 1, 4: 2, 6: 3, 8: 3}[playoff_count]
    mapping = {1: (1,), 2: (2,)}
    mapping.update({3 + r: (3 + r,) for r in range(rounds)})
    if multiweek and rounds:
        mapping[2 + rounds] = (2 + rounds, 3 + rounds)
    final = max(w for weeks in mapping.values() for w in weeks)
    return LeagueState(
        league_id=1, season=2026, first_week=1, current_week=current_week, final_week=final,
        rules=SeasonRules(2, mapping, playoff_count, tuple(mapping[p] for p in range(3, 3 + rounds))),
        teams=[dict(team_id=t, team_name=f"Team {t}") for t in range(1, team_count + 1)],
        rosters=[dict(team_id=t, team_name=f"Team {t}", player_id=t, player_name=f"Player {t}",
                      eligible_slots=[0], default_position_id=1) for t in range(1, team_count + 1)],
        player_projections=[dict(player_id=t, week=w, projected_points=float(100 - 10*t))
                            for t in range(1, team_count + 1) for w in range(1, final + 1)],
        starter_slots=[dict(slot_id=0, slot_name="QB", slot_instance=1)],
        schedule_rows=[matchup(w, t, t+1) for w in (1, 2) for t in range(1, team_count, 2)],
        settings_payload={"settings": {"rosterSettings": {}}},
    )


def finish_regular(state):
    result = project_season(state)
    return replace(state, current_week=3, schedule_rows=[
        matchup(r["matchup_period"], r["home_team_id"], r["away_team_id"],
                "TIE" if r["winner_team_id"] is None else "HOME" if r["winner_team_id"] == r["home_team_id"] else "AWAY",
                r["home_points"], r["away_points"])
        for r in result.regular_season_matchups])


class SeasonTests(unittest.TestCase):
    def test_reproducible_and_input_and_output_are_isolated(self):
        state = league()
        original = deepcopy(state)
        first = project_season(state)
        self.assertEqual(first, project_season(state))
        self.assertEqual(original, state)
        first.state.rosters[0]["player_name"] = "Changed"
        self.assertEqual(original, state)
        self.assertEqual({1, 2, 3, 4}, {r["final_place"] for r in first.team_outcomes})

    def test_effective_week_uses_original_roster_before_boundary(self):
        state = league()
        rosters = deepcopy(state.rosters)
        rosters[0]["team_id"], rosters[1]["team_id"] = 2, 1
        scenario = state.with_rosters(rosters)
        original = deepcopy(scenario)
        after = project_season(scenario, effective_week=2)
        scores = {(r["team_id"], r["week"]): r["projected_points"] for r in after.weekly_team_projections}
        self.assertEqual(90, scores[1, 1])
        self.assertEqual(80, scores[1, 2])
        self.assertEqual(90, scores[2, 2])
        self.assertEqual(original, scenario)
        baseline = project_season(state)
        no_effect = project_season(scenario, state.final_week + 1)
        self.assertEqual(baseline.team_outcomes, no_effect.team_outcomes)

    def test_completed_results_survive_roster_changes(self):
        state = league(current_week=2)
        state.schedule_rows[0].update(winner="AWAY", actual_home_points=5.0, actual_away_points=7.0)
        state.schedule_rows[1].update(winner="HOME", actual_home_points=9.0, actual_away_points=8.0)
        before = project_season(state)
        rosters = deepcopy(state.rosters)
        rosters[0]["team_id"], rosters[1]["team_id"] = 2, 1
        after = project_season(state.with_rosters(rosters))
        self.assertEqual(before.regular_season_matchups[:2], after.regular_season_matchups[:2])
        self.assertEqual(2, after.regular_season_matchups[0]["winner_team_id"])
        self.assertFalse(any(r["week"] == 1 for r in after.optimal_lineups))

    def test_missing_zero_and_negative_projections_are_distinct(self):
        state = league()
        state.player_projections[0]["projected_points"] = None
        state.player_projections[1]["projected_points"] = 0.0
        state.player_projections[2]["projected_points"] = -4.0
        result = project_season(state)
        self.assertEqual(1, result.summary["missing_projection_count"])
        self.assertEqual(1, result.summary["missing_starter_projection_count"])
        self.assertEqual(1, result.diagnostics[0]["week"])
        week3 = next(r for r in result.optimal_lineups if r["week"] == 3 and r["team_id"] == 1)
        self.assertEqual(-4.0, week3["projected_points"])
        self.assertFalse(week3["projection_missing"])

    def test_all_supported_brackets_assign_every_place_once(self):
        for teams, count in ((4, 0), (4, 2), (4, 4), (6, 6), (8, 8), (14, 6)):
            with self.subTest(teams=teams, playoffs=count):
                result = project_season(league(teams, count, multiweek=True))
                self.assertEqual(set(range(1, teams+1)), {r["final_place"] for r in result.final_standings})
                self.assertEqual(teams, len(result.final_standings))
                self.assertEqual(1, result.summary["champion_team_id"])
                self.assertEqual(count, sum(r["made_playoffs"] for r in result.team_outcomes))

    def test_six_team_reseeding_changes_semifinal_pairings_after_upset(self):
        state = league(6,6)
        for row in state.player_projections:
            if row["player_id"] == 6 and row["week"] == 3:
                row["projected_points"] = 200.0
        fixed = project_season(state)
        reseeded = project_season(replace(state, rules=replace(state.rules, playoff_reseed=True)))
        def opponent(result):
            game = next(r for r in result.postseason_matchups if r["round_name"] == "Semifinal" and r["team_a_id"] == 1)
            return game["team_b_id"]
        self.assertEqual(2, opponent(fixed))
        self.assertEqual(6, opponent(reseeded))

    def test_current_period_final_is_not_counted_as_remaining_points(self):
        state = league(2,2)
        state.schedule_rows[0].update(winner="AWAY",actual_home_points=10.0,actual_away_points=20.0)
        result = project_season(state)
        self.assertEqual(180.0, result.team_outcomes[0]["remaining_points"])
        self.assertEqual((10.0,99.0),_preserve_actual_scores(result,1,(1,2),(999.0,99.0)))

    def test_multiweek_final_sums_both_weeks(self):
        state = league(2, 2, multiweek=True)
        for row in state.player_projections:
            if row["player_id"] == 2 and row["week"] == 4:
                row["projected_points"] = 200.0
        result = project_season(state)
        final = result.postseason_matchups[0]
        self.assertEqual("3,4", final["scoring_weeks"])
        self.assertEqual(2, final["winner_team_id"])
        self.assertEqual(280, final["score_b"])

    def test_partially_completed_multiweek_round_uses_week_actuals(self):
        state = finish_regular(league(2, 2, multiweek=True))
        state = replace(state, current_week=4, actual_weekly_points=[
            dict(team_id=1, week=3, points=1.0), dict(team_id=2, week=3, points=100.0)])
        result = project_season(state)
        self.assertEqual(91, result.postseason_matchups[0]["score_a"])
        self.assertEqual(180, result.postseason_matchups[0]["score_b"])
        self.assertEqual(2, result.summary["champion_team_id"])

    def test_missing_completed_week_is_not_reprojected(self):
        state = finish_regular(league(2, 2, multiweek=True))
        with self.assertRaisesRegex(SeasonModelError, "Missing completed playoff"):
            project_season(replace(state, current_week=4))

    def test_completed_playoff_upset_changes_future_participants(self):
        state = finish_regular(league())
        state = replace(state, current_week=4, postseason_results=[
            matchup(3, 1, 4, "AWAY", 10, 20), matchup(3, 3, 2, "HOME", 30, 20)])
        result = project_season(state)
        title = next(r for r in result.postseason_matchups if r["round_name"] == "Championship")
        self.assertEqual({3, 4}, {title["team_a_id"], title["team_b_id"]})
        self.assertEqual(2, sum(r["result_type"] == "ACTUAL" for r in result.postseason_matchups))

    def test_completed_season_requires_no_roster_optimization(self):
        state = finish_regular(league(2, 2, multiweek=True))
        state = replace(state, current_week=5, rosters=[], player_projections=[], postseason_results=[
            matchup(3, 1, 2, "AWAY", 10, 20)])
        result = project_season(state)
        self.assertEqual(2, result.summary["champion_team_id"])
        self.assertEqual([], result.optimal_lineups)
        self.assertTrue(all(r["remaining_points"] == 0 for r in result.team_outcomes))

    def test_unrecorded_finished_round_is_an_error(self):
        state = finish_regular(league(2, 2))
        with self.assertRaises(SeasonModelError):
            project_season(replace(state, current_week=4))

    def test_projected_playoff_ties_use_explicit_seed_policy(self):
        state = league(2, 2)
        for row in state.player_projections:
            row["projected_points"] = 10.0
        result = project_season(state)
        self.assertEqual(2, result.projected_standings[0]["ties"])
        self.assertEqual("HIGHER_SEED", result.postseason_matchups[0]["tiebreak_used"])
        self.assertEqual(1, result.summary["champion_team_id"])

    def test_actual_tied_score_uses_recorded_advancing_team(self):
        state = finish_regular(league(2, 2))
        state = replace(state, current_week=4, postseason_results=[matchup(3, 1, 2, "AWAY", 20, 20)])
        result = project_season(state)
        self.assertEqual(2, result.summary["champion_team_id"])
        self.assertEqual("RECORDED_WINNER", result.postseason_matchups[0]["tiebreak_used"])

    def test_cached_search_scoring_matches_full_state_projection(self):
        state = league()
        baseline = project_season(state)
        after = evaluate_trade(baseline=baseline, my_team_id=1, give_player_ids=[1], receive_player_ids=[2]).after
        scores = {(r["team_id"], r["week"]): r["projected_points"] for r in after.weekly_team_projections}
        metrics, _, games, playoffs = _scenario_metrics(baseline, scores)
        self.assertEqual(_team_metrics(after), metrics)
        self.assertEqual(after.regular_season_matchups, games)
        self.assertEqual(after.postseason_matchups, playoffs)

    def test_waiver_runs_through_state_engine(self):
        state = league()
        available = [dict(player_id=100, player_name="Free agent", eligible_slots=[0], default_position_id=1,
                          team_id=None, availability_status="FREEAGENT")]
        state.player_projections.extend(dict(player_id=100, week=w, projected_points=120.0)
                                        for w in range(1, state.final_week+1))
        comparison = evaluate_waiver(baseline=project_season(state), my_team_id=1, available_players=available,
                                     add_player_id=100, drop_player_id=1)
        self.assertEqual(120, next(r for r in comparison.after.weekly_team_projections if r["team_id"] == 1)["projected_points"])
        self.assertEqual(1, state.rosters[0]["player_id"])

    def test_invalid_state_and_rules_fail_explicitly(self):
        state = league()
        cases = [replace(state, rules=replace(state.rules, seeding_tiebreak="HEAD_TO_HEAD")),
                 replace(state, rules=replace(state.rules, playoff_team_count=3)),
                 replace(state, rules=replace(state.rules, playoff_tiebreak="BENCH_POINTS")),
                 replace(state, schedule_rows=state.schedule_rows[:-2]),
                 replace(state, rosters=state.rosters + state.rosters[:1]),
                 replace(state, player_projections=state.player_projections + state.player_projections[:1]),
                 replace(state, player_projections=[dict(player_id=1, week=1, projected_points=float("nan"))]),
                 replace(state, starter_slots=state.starter_slots*2)]
        for case in cases:
            with self.subTest(case=case.rules), self.assertRaises(SeasonModelError):
                project_season(case)
        for week in (0, -1, 6, 1.5, True):
            with self.subTest(week=week), self.assertRaises(SeasonModelError):
                project_season(state, week)

    def test_impossible_lineup_reports_team_and_week(self):
        state = league()
        state.rosters[0]["eligible_slots"] = [2]
        with self.assertRaisesRegex(SeasonModelError, "Team 1, week 1"):
            project_season(state)

    def test_seeding_uses_half_win_ties_before_points(self):
        teams = [dict(team_id=t, team_name=str(t)) for t in (1,2,3,4)]
        games = [dict(home_team_id=1, away_team_id=2, home_points=100, away_points=0, winner_team_id=1, result_type="ACTUAL"),
                 dict(home_team_id=1, away_team_id=2, home_points=0, away_points=100, winner_team_id=2, result_type="ACTUAL"),
                 dict(home_team_id=3, away_team_id=4, home_points=1, away_points=1, winner_team_id=None, result_type="ACTUAL"),
                 dict(home_team_id=3, away_team_id=4, home_points=1, away_points=1, winner_team_id=None, result_type="ACTUAL"),
                 dict(home_team_id=3, away_team_id=4, home_points=2, away_points=1, winner_team_id=3, result_type="ACTUAL")]
        self.assertEqual(3, build_projected_standings(teams, games, league().rules)[0]["team_id"])


class LineupTests(unittest.TestCase):
    def test_optimizer_matches_exhaustive_assignment_with_overlapping_slots(self):
        roster = [dict(player_id=i, player_name=str(i), eligible_slots=slots)
                  for i, slots in [(1,[0,7]), (2,[2,7,23]), (3,[2,23]), (4,[4,7,23]), (5,[6,23])]]
        slots = [dict(slot_id=s, slot_name=str(s), slot_instance=1) for s in (0,7,23)]
        points = {(i,w): float((i*13+w*7)%23-5) for i in range(1,6) for w in range(1,5)}
        expected = []
        for week in range(1,5):
            best = max(sum(points[p["player_id"],week] for p in assignment)
                       for assignment in permutations(roster, len(slots))
                       if all(s["slot_id"] in p["eligible_slots"] for s,p in zip(slots,assignment)))
            score, lineup = optimize_lineup(roster,slots,points,week)
            self.assertEqual(best, score)
            self.assertEqual(len(lineup),len({r["player_id"] for r in lineup}))
            expected.append(best)
        self.assertEqual(tuple(expected), optimize_lineup_weeks(roster,slots,points,(1,2,3,4)))


class EspnAdapterTests(unittest.TestCase):
    def test_ingestion_advances_finished_period_and_does_not_fetch_history(self):
        from fantasy_projection.config import Config
        from fantasy_projection.pipeline import load_league_state
        settings = {"settings": {"scheduleSettings": dict(matchupPeriodCount=2, playoffTeamCount=2,
            matchupPeriods={"1":[1],"2":[2],"3":[3,4]}, playoffMatchupPeriodLengthByRound={"1":2},
            playoffSeedingRule="TOTAL_POINTS_SCORED", consolationLadderDisabled=True),
            "rosterSettings":{"lineupSlotCounts":{"0":1}}}}
        payloads = {"mTeam":{"teams":[dict(id=1,name="One"),dict(id=2,name="Two")]},
                    "mRoster":{"status":dict(firstScoringPeriod=1,currentScoringPeriod=1,finalScoringPeriod=4)},
                    "mSettings":settings,"mMatchupScore":{"schedule":[dict(matchupPeriodId=1,winner="HOME",
                    home=dict(teamId=1,totalPoints=20),away=dict(teamId=2,totalPoints=10))]}}
        with patch('fantasy_projection.pipeline.EspnClient') as client, patch('fantasy_projection.pipeline.pull_weekly_player_projections',return_value=[]) as projections:
            client.return_value.get_league.side_effect=lambda view:payloads[view]
            state = load_league_state(Config(1,2026,None,None))
        self.assertEqual(2,state.current_week)
        self.assertEqual(2,projections.call_args.kwargs['first_week'])
        self.assertEqual(4,projections.call_args.kwargs['final_week'])
        self.assertNotIn('espn_s2',state.settings_payload)

    def test_normalizes_multiweek_rules_and_preserves_postseason_actuals(self):
        payload = {"settings": {"scheduleSettings": dict(matchupPeriodCount=2, playoffTeamCount=2,
            matchupPeriods={"1":[1],"2":[2],"3":[3,4]}, playoffMatchupPeriodLengthByRound={"1":2},
            playoffSeedingRule="TOTAL_POINTS_SCORED", consolationLadderDisabled=True)}}
        rules = normalize_season_rules(payload)
        self.assertEqual(((3,4),),rules.playoff_rounds)
        schedule = {"schedule": [dict(matchupPeriodId=3, winner="AWAY",
            home=dict(teamId=1,totalPoints=13,pointsByScoringPeriod={"3":3,"4":10}),
            away=dict(teamId=2,totalPoints=20,pointsByScoringPeriod={"3":5,"4":15}))]}
        self.assertEqual("AWAY", normalize_schedule(schedule)[0]["winner"])
        self.assertEqual(4,len(normalize_actual_weekly_points(schedule,5)))
        payload["settings"]["scheduleSettings"]["divisions"] = [{},{}]
        with self.assertRaisesRegex(SeasonModelError, "Division"):
            normalize_season_rules(payload)

    def test_in_progress_week_points_are_not_added_to_full_week_projection(self):
        schedule = {"schedule": [dict(matchupPeriodId=1, winner="UNDECIDED",
                    home=dict(teamId=1,pointsByScoringPeriod={"1":4,"2":9}), away=dict(teamId=2))]}
        self.assertEqual([dict(team_id=1,week=1,points=4)],normalize_actual_weekly_points(schedule,2))
