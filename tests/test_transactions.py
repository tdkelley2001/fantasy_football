import unittest
from dataclasses import replace
from types import SimpleNamespace

from fantasy_projection.season import LeagueState, SeasonModelError, SeasonRules
from fantasy_projection.transactions import (FREE_AGENTS, Transaction, Transfer,
                                             apply_transaction, trade_transaction,
                                             waiver_transaction)
from fantasy_projection.trades import (TradeSearchOptions, _legal_trade_resolutions,
                                       select_trade_resolution)


def state(active_limit=2):
    return LeagueState(1, 2026, 1, 1, 2, SeasonRules(2, {1:(1,),2:(2,)}, 0, ()),
        [{"team_id":1,"team_name":"A"},{"team_id":2,"team_name":"B"}],
        [{"team_id":1,"team_name":"A","player_id":1,"player_name":"One","default_position_id":2,"eligible_slots":[2,20],"current_lineup_slot_id":20,"droppable":True},
         {"team_id":1,"team_name":"A","player_id":2,"player_name":"Two","default_position_id":3,"eligible_slots":[4,20],"current_lineup_slot_id":20,"droppable":True},
         {"team_id":2,"team_name":"B","player_id":3,"player_name":"Three","default_position_id":2,"eligible_slots":[2,20],"current_lineup_slot_id":20,"droppable":True}],
        [], [], [], [], settings_payload={"settings":{"rosterSettings":{"lineupSlotCounts":{"20":active_limit},"positionLimits":{"2":3,"3":3}}}},
        available_players=[{"player_id":4,"player_name":"Free","default_position_id":2,"eligible_slots":[2,20],"availability_status":"FREEAGENT"}])


class TransactionTests(unittest.TestCase):
    def test_free_agent_is_a_participant_and_open_slot_is_validated(self):
        with self.assertRaisesRegex(SeasonModelError, "drop.*required"):
            apply_transaction(state(), waiver_transaction(state(), team_id=1, add=4, drop=None, effective_week=1))
        result=apply_transaction(state(active_limit=3), waiver_transaction(state(active_limit=3), team_id=1, add=4, drop=None, effective_week=1))
        self.assertEqual(1, next(p for p in result.rosters if p["player_id"]==4)["team_id"])
        self.assertNotIn(4, {p["player_id"] for p in result.available_players})

    def test_atomic_trade_rejects_wrong_owner(self):
        tx=Transaction((Transfer(3,1,2),Transfer(1,2,1)),1)
        with self.assertRaisesRegex(SeasonModelError,"does not own"):
            apply_transaction(state(),tx)

    def test_transaction_does_not_change_lineup_scoring_rules(self):
        original=state(active_limit=3)
        result=apply_transaction(original,waiver_transaction(original,team_id=1,add=4,drop=None,effective_week=1))
        self.assertEqual(original.starter_slots,result.starter_slots)
        self.assertEqual(original.rules,result.rules)

    def test_drop_returns_player_to_free_agent_pool(self):
        result=apply_transaction(state(),waiver_transaction(state(),team_id=1,add=4,drop=1,effective_week=1))
        self.assertIn(1,{p["player_id"] for p in result.available_players})

    def test_uneven_trade_requires_and_applies_complete_roster_resolution(self):
        original=state()
        original=replace(original,rosters=original.rosters+[
            {"team_id":2,"team_name":"B","player_id":5,"player_name":"Five",
             "default_position_id":3,"eligible_slots":[4,20],"current_lineup_slot_id":20,"droppable":True}
        ])
        unresolved=trade_transaction(original,team_id=1,partner_id=2,give=[1],receive=[3,5],effective_week=1)
        with self.assertRaisesRegex(SeasonModelError,"drop.*required"):
            apply_transaction(original,unresolved)
        resolved=trade_transaction(original,team_id=1,partner_id=2,give=[1],receive=[3,5],
                                   team_drops=[2],effective_week=1)
        result=apply_transaction(original,resolved)
        self.assertEqual({3,5},{p["player_id"] for p in result.rosters if p["team_id"]==1})
        self.assertIn(2,{p["player_id"] for p in result.available_players})

    def test_uneven_trade_uses_real_open_slot_without_forcing_drop(self):
        original=state(active_limit=3)
        original=replace(original,rosters=original.rosters+[
            {"team_id":2,"team_name":"B","player_id":5,"player_name":"Five",
             "default_position_id":3,"eligible_slots":[4,20],"current_lineup_slot_id":20,"droppable":True}
        ])
        transaction=trade_transaction(original,team_id=1,partner_id=2,give=[1],receive=[3,5],effective_week=1)
        result=apply_transaction(original,transaction)
        self.assertEqual(3,len([p for p in result.rosters if p["team_id"]==1]))

    def test_search_generates_explicit_required_drop_resolution(self):
        original=state()
        original=replace(original,rosters=original.rosters+[
            {"team_id":2,"team_name":"B","player_id":5,"player_name":"Five",
             "default_position_id":3,"eligible_slots":[4,20],"current_lineup_slot_id":20,"droppable":True}
        ])
        resolutions=_legal_trade_resolutions(SimpleNamespace(state=original),1,2,(1,),(3,5),1,TradeSearchOptions())
        self.assertEqual([((2,),())],resolutions)

    def test_three_for_one_resolution_can_choose_two_required_drops(self):
        original=state(active_limit=3)
        original=replace(original,rosters=original.rosters+[
            {"team_id":1,"team_name":"A","player_id":6,"player_name":"Six","default_position_id":3,"eligible_slots":[4,20],"current_lineup_slot_id":20,"droppable":True},
            {"team_id":2,"team_name":"B","player_id":5,"player_name":"Five","default_position_id":3,"eligible_slots":[4,20],"current_lineup_slot_id":20,"droppable":True},
            {"team_id":2,"team_name":"B","player_id":7,"player_name":"Seven","default_position_id":3,"eligible_slots":[4,20],"current_lineup_slot_id":20,"droppable":True},
        ])
        resolutions=_legal_trade_resolutions(SimpleNamespace(state=original),1,2,(1,),(3,5,7),1,TradeSearchOptions())
        self.assertEqual([((2,6),())],resolutions)

    def test_automatic_drop_preserves_the_most_projected_lineup_points(self):
        original=state(active_limit=3)
        original=replace(original,
            rosters=original.rosters+[
                {"team_id":1,"team_name":"A","player_id":6,"player_name":"Six",
                 "default_position_id":2,"eligible_slots":[2,20],"current_lineup_slot_id":20,"droppable":True},
                {"team_id":2,"team_name":"B","player_id":5,"player_name":"Five",
                 "default_position_id":3,"eligible_slots":[4,20],"current_lineup_slot_id":20,"droppable":True}],
            starter_slots=[{"slot_id":2,"slot_name":"RB","slot_instance":1},
                           {"slot_id":4,"slot_name":"WR","slot_instance":1}],
            player_projections=[
                {"player_id":2,"week":week,"projected_points":5.0} for week in (1,2)
            ]+[
                {"player_id":3,"week":week,"projected_points":19.0} for week in (1,2)
            ]+[
                {"player_id":5,"week":week,"projected_points":0.0} for week in (1,2)
            ]+[
                {"player_id":6,"week":week,"projected_points":20.0} for week in (1,2)
            ])
        baseline=SimpleNamespace(state=original)
        self.assertEqual(
            ((6,),()),
            select_trade_resolution(baseline,1,2,(1,),(3,5),1),
        )
        self.assertEqual(
            ((2,),()),
            select_trade_resolution(
                baseline,1,2,(1,),(3,5),1,
                TradeSearchOptions(drop_strategy="lowest_projection")),
        )


if __name__ == '__main__': unittest.main()
