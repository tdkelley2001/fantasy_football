from __future__ import annotations

from dataclasses import replace
import itertools

import pytest

from fantasy_football.canonical.model import SlotKind
from fantasy_football.evolving_state import IRPolicy, initialize_evolving_state, validate_evolving_state
from fantasy_football.scenario_evaluator import ProtectedPlayerPin, _state_with_roster
from fantasy_football.trade_candidates import TradeShape
from fantasy_football.trade_chains import (
    TradeChainError,
    TradeChainRejectionCode,
    TradeChainSearchConfiguration,
    VacancyEventOrigin,
    enumerate_multi_trade_chains,
    iter_multi_trade_chains,
)
from tests.test_scenario_evaluator import _scenario_snapshot_with_bench


def _snapshot():
    return _scenario_snapshot_with_bench()


def _state(snapshot=None):
    snapshot = _snapshot() if snapshot is None else snapshot
    return initialize_evolving_state(
        snapshot,
        scoring_week=snapshot.first_simulation_week,
        ir_policy=IRPolicy.PROJECTION_BASED,
    )


def _config(**changes):
    values = dict(
        requesting_team_id=1,
        counterparty_team_ids=(2, 3),
        player_universe_ids=(1, 2, 3, 10, 11, 12),
        trade_shapes=(TradeShape(1, 1),),
        minimum_chain_length=2,
        maximum_chain_length=2,
    )
    values.update(changes)
    return TradeChainSearchConfiguration(**values)


def _state_with_vacancies(snapshot, *player_ids):
    baseline = _state(snapshot)
    roster = tuple(
        item for item in baseline.roster_entries if item.player_id not in set(player_ids)
    )
    return _state_with_roster(
        baseline,
        snapshot,
        roster,
        released_player_ids=frozenset(player_ids),
        completion_pool=False,
    )


def _capacity_three_snapshot():
    snapshot = _snapshot()
    free_player = next(item for item in snapshot.players if item.player_id == -101)
    free_weeks = tuple(item for item in snapshot.player_weeks if item.player_id == -101)
    extra_ids = (-102, -103, -104, -105)
    return replace(
        snapshot,
        rules=replace(
            snapshot.rules,
            lineup_slots=tuple(
                replace(item, capacity=2) if item.kind is SlotKind.BENCH else item
                for item in snapshot.rules.lineup_slots
            ),
        ),
        players=tuple(
            sorted(
                (
                    *snapshot.players,
                    *(replace(free_player, player_id=player_id) for player_id in extra_ids),
                ),
                key=lambda item: item.player_id,
            )
        ),
        player_weeks=tuple(
            sorted(
                (
                    *snapshot.player_weeks,
                    *(
                        replace(week, player_id=player_id)
                        for player_id in extra_ids
                        for week in free_weeks
                    ),
                ),
                key=lambda item: (item.player_id, item.season, item.scoring_week),
            )
        ),
    )


def _signature(candidate):
    return tuple(
        (item.counterparty_team_id, item.outgoing_player_ids, item.incoming_player_ids)
        for item in candidate.trades
    )


def _independent_two_step_oracle(state, config):
    initial = {item.player_id: item.team_id for item in state.roster_entries}
    result = set()
    for first, second in itertools.permutations(config.counterparty_team_ids, 2):
        for sent in tuple(player for player in config.player_universe_ids if initial.get(player) == 1):
            for received in tuple(player for player in config.player_universe_ids if initial.get(player) == first):
                owners = dict(initial)
                owners[sent], owners[received] = first, 1
                for received2 in tuple(player for player in config.player_universe_ids if owners.get(player) == second):
                    # With a one-for-one shape the immediate dependency makes
                    # the just-acquired player the only legal second outgoing.
                    result.add(((first, (sent,), (received,)), (second, (received,), (received2,))))
    return result


def test_exact_two_step_count_matches_independent_oracle() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    config = _config()
    result = enumerate_multi_trade_chains(snapshot, state, config)
    expected = _independent_two_step_oracle(state, config)

    assert {_signature(item) for item in result.candidates} == expected
    assert len(result.candidates) == len(expected) == 16
    assert result.coverage.complete is True
    assert result.coverage.completed_feasible_chain_count == 16
    assert dict(result.coverage.rejection_code_counts)[
        TradeChainRejectionCode.IMMEDIATE_DEPENDENCY_MISSING
    ] > 0
    assert dict(result.coverage.rejection_code_counts)[
        TradeChainRejectionCode.CONSECUTIVE_COUNTERPARTY
    ] > 0
    assert all(item.trades[1].dependency_player_ids == item.trades[0].incoming_player_ids for item in result.candidates)


def test_three_step_dependency_is_immediate_and_partner_may_return() -> None:
    snapshot = _snapshot()
    result = enumerate_multi_trade_chains(
        snapshot,
        _state(snapshot),
        _config(minimum_chain_length=3, maximum_chain_length=3),
    )
    assert result.candidates
    for candidate in result.candidates:
        assert candidate.trades[0].counterparty_team_id == candidate.trades[2].counterparty_team_id
        assert candidate.trades[0].counterparty_team_id != candidate.trades[1].counterparty_team_id
        assert set(candidate.trades[2].outgoing_player_ids) & set(candidate.trades[1].incoming_player_ids)
        assert not (
            set(candidate.trades[2].dependency_player_ids)
            - set(candidate.trades[1].incoming_player_ids)
        )


def test_chronological_ownership_updates_both_sides_without_duplicates() -> None:
    snapshot = _snapshot()
    candidate = next(iter_multi_trade_chains(snapshot, _state(snapshot), _config()))
    owners = {item.player_id: item.team_id for item in candidate.completed_scenario.state.roster_entries}
    first, second = candidate.trades
    assert owners[first.outgoing_player_ids[0]] == first.counterparty_team_id
    assert owners[first.incoming_player_ids[0]] == second.counterparty_team_id
    assert owners[second.incoming_player_ids[0]] == 1
    assert len(owners) == len(set(owners))
    validate_evolving_state(candidate.completed_scenario.state, snapshot)


def test_asymmetric_chain_allows_intermediate_imbalance_and_completes_once() -> None:
    snapshot = _snapshot()
    config = _config(
        trade_shapes=(TradeShape(1, 2), TradeShape(2, 1)),
        maximum_completed_paths=40,
    )
    result = enumerate_multi_trade_chains(snapshot, _state(snapshot), config)
    assert result.candidates
    assert any(
        item.ordinary_player_count != item.configured_capacity
        for candidate in result.candidates
        for item in candidate.intermediate_capacity
    )
    for candidate in result.candidates:
        actions = (
            *candidate.completed_scenario.forced_drops,
            *candidate.completed_scenario.automatic_additions,
        )
        assert [item.action for item in actions] == sorted(
            (item.action for item in actions),
            key=lambda action: 0 if action == "automatic_capacity_drop" else 1,
        )
        validate_evolving_state(candidate.completed_scenario.state, snapshot)


def test_vacancy_priority_is_manager_first_not_round_robin() -> None:
    snapshot = replace(_snapshot(), rules=replace(_snapshot().rules, undroppable_list_enabled=False))
    # Two-for-one followed by one-for-two creates and then changes vacancies;
    # every final addition for the earlier outstanding manager is contiguous.
    result = enumerate_multi_trade_chains(
        snapshot,
        _state(snapshot),
        _config(trade_shapes=(TradeShape(2, 1), TradeShape(1, 2))),
    )
    assert result.candidates
    for candidate in result.candidates:
        teams = [item.team_id for item in candidate.completed_scenario.automatic_additions]
        assert teams == sorted(teams, key=lambda team: teams.index(team))
    example = result.candidates[0]
    # Team 2's first-trade vacancy is filled before team 3's second-trade
    # vacancy, and it may select a player dropped during final capacity repair.
    assert [item.team_id for item in example.completed_scenario.automatic_additions] == [2, 3]
    assert example.completed_scenario.automatic_additions[0].player_id in {
        item.player_id for item in example.completed_scenario.forced_drops
    }


def test_resolved_vacancy_loses_priority_and_later_event_gets_new_priority() -> None:
    snapshot = replace(_snapshot(), rules=replace(_snapshot().rules, undroppable_list_enabled=False))
    result = enumerate_multi_trade_chains(
        snapshot,
        _state(snapshot),
        _config(
            trade_shapes=(TradeShape(2, 1), TradeShape(1, 2)),
            minimum_chain_length=3,
            maximum_chain_length=3,
            maximum_completed_paths=200,
        ),
    )
    candidate = next(
        item
        for item in result.candidates
        if _signature(item)
        == (
            (2, (1, 10), (2,)),
            (3, (2,), (3, 12)),
            (2, (3, 12), (1,)),
        )
    )
    assert [(event.transaction_index, event.team_id, event.created_places, event.reduced_places) for event in candidate.vacancy_events] == [
        (1, 1, 1, 0),
        (2, 1, 0, 1),
        (2, 3, 1, 0),
        (3, 1, 1, 0),
    ]
    assert [item.team_id for item in candidate.completed_scenario.automatic_additions] == [3, 1]


def test_distinct_paths_remain_even_when_completed_state_identity_matches() -> None:
    snapshot = _snapshot()
    result = enumerate_multi_trade_chains(
        snapshot,
        _state(snapshot),
        _config(minimum_chain_length=3, maximum_chain_length=3),
    )
    groups = {}
    for candidate in result.candidates:
        groups.setdefault(candidate.completed_state_sha256, []).append(candidate.chain_id)
    assert len({item.chain_id for item in result.candidates}) == len(result.candidates)
    assert any(len(chain_ids) > 1 for chain_ids in groups.values())


def test_same_explicit_player_set_in_different_paths_can_complete_differently() -> None:
    snapshot = _snapshot()
    result = enumerate_multi_trade_chains(
        snapshot,
        _state(snapshot),
        _config(minimum_chain_length=3, maximum_chain_length=3),
    )
    grouped = {}
    for candidate in result.candidates:
        player_set = frozenset(
            player
            for trade in candidate.trades
            for player in (*trade.outgoing_player_ids, *trade.incoming_player_ids)
        )
        grouped.setdefault(player_set, []).append(candidate)
    assert any(
        len({item.completed_state_sha256 for item in candidates}) > 1
        for candidates in grouped.values()
    )


def test_reordered_configuration_is_deterministic() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    first = enumerate_multi_trade_chains(snapshot, state, _config())
    second = enumerate_multi_trade_chains(
        snapshot,
        state,
        _config(
            counterparty_team_ids=(3, 2),
            player_universe_ids=(12, 11, 10, 3, 2, 1),
        ),
    )
    assert first == second


def test_configured_limit_reports_incomplete_without_claiming_exhaustive() -> None:
    snapshot = _snapshot()
    result = enumerate_multi_trade_chains(
        snapshot, _state(snapshot), _config(maximum_completed_paths=3)
    )
    assert len(result.candidates) == 3
    assert result.coverage.complete is False
    assert result.coverage.truncation_stage == "completed_path_materialization"
    assert result.coverage.truncation_reason
    with pytest.raises(TradeChainError, match="incomplete coverage"):
        tuple(iter_multi_trade_chains(snapshot, _state(snapshot), _config(maximum_completed_paths=3)))


def test_zero_result_universe_and_invalid_configuration() -> None:
    snapshot = _snapshot()
    empty = enumerate_multi_trade_chains(
        snapshot,
        _state(snapshot),
        _config(allowed_outgoing_player_ids=()),
    )
    assert empty.candidates == ()
    assert empty.coverage.complete is True
    with pytest.raises(TradeChainError, match="at least two"):
        enumerate_multi_trade_chains(
            snapshot,
            _state(snapshot),
            _config(minimum_chain_length=1),
        )


def test_protected_pin_blocks_transfer_and_inputs_are_immutable() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    before = state
    result = enumerate_multi_trade_chains(
        snapshot,
        state,
        _config(protected_pins=(ProtectedPlayerPin(1, 1),)),
    )
    assert all(1 not in trade.outgoing_player_ids for item in result.candidates for trade in item.trades)
    assert state == before


def test_preexisting_vacancy_survives_equal_trades_and_is_completed() -> None:
    snapshot = _snapshot()
    state = _state_with_vacancies(snapshot, 10)
    result = enumerate_multi_trade_chains(
        snapshot,
        state,
        _config(player_universe_ids=(1, 2, 3, 11, 12)),
    )
    assert len(result.candidates) == 8
    for candidate in result.candidates:
        initial = candidate.vacancy_events[0]
        assert (initial.transaction_index, initial.team_id, initial.created_places) == (
            None,
            1,
            1,
        )
        assert initial.origin is VacancyEventOrigin.PRE_EXISTING
        assert candidate.completed_scenario.automatic_additions[0].team_id == 1
        assert "initial_vacancy_frozen_priority_completion_v1" in (
            candidate.completed_scenario.state.assumption_ids
        )
        validate_evolving_state(candidate.completed_scenario.state, snapshot)


def test_uninvolved_manager_preexisting_vacancy_is_not_omitted() -> None:
    snapshot = _snapshot()
    state = _state_with_vacancies(snapshot, 13)
    result = enumerate_multi_trade_chains(snapshot, state, _config())
    assert len(result.candidates) == 16
    assert all(
        any(
            event.origin is VacancyEventOrigin.PRE_EXISTING and event.team_id == 4
            for event in candidate.vacancy_events
        )
        for candidate in result.candidates
    )
    assert all(
        any(action.team_id == 4 for action in candidate.completed_scenario.automatic_additions)
        for candidate in result.candidates
    )


def test_preexisting_vacancy_precedes_later_trade_created_vacancy() -> None:
    snapshot = _snapshot()
    state = _state_with_vacancies(snapshot, 13)
    result = enumerate_multi_trade_chains(
        snapshot,
        state,
        _config(trade_shapes=(TradeShape(2, 1), TradeShape(1, 2))),
    )
    candidate = next(
        item
        for item in result.candidates
        if any(
            event.origin is VacancyEventOrigin.TRADE
            and event.team_id != 4
            and event.created_places
            for event in item.vacancy_events
        )
    )
    addition_teams = [item.team_id for item in candidate.completed_scenario.automatic_additions]
    assert addition_teams[0] == 4
    additions = candidate.completed_scenario.automatic_additions
    assert len({item.player_id for item in additions}) == len(additions)


def test_eliminated_initial_vacancy_does_not_keep_priority_when_recreated() -> None:
    snapshot = _snapshot()
    state = _state_with_vacancies(snapshot, 10)
    result = enumerate_multi_trade_chains(
        snapshot,
        state,
        _config(
            player_universe_ids=(1, 2, 3, 11, 12),
            trade_shapes=(TradeShape(1, 2), TradeShape(2, 1)),
        ),
    )
    candidate = next(
        item
        for item in result.candidates
        if _signature(item)
        == (
            (2, (1,), (2, 11)),
            (3, (2, 11), (3,)),
        )
    )
    requester_events = [event for event in candidate.vacancy_events if event.team_id == 1]
    assert [
        (item.transaction_index, item.created_places, item.reduced_places)
        for item in requester_events
    ] == [(None, 1, 0), (1, 0, 1), (2, 1, 0)]
    assert (
        requester_events[0].chronological_priority
        != requester_events[-1].chronological_priority
    )
    assert [item.team_id for item in candidate.completed_scenario.automatic_additions] == [
        2,
        1,
    ]


def test_partial_initial_vacancy_reduction_retains_original_priority() -> None:
    snapshot = _capacity_three_snapshot()
    state = _state_with_vacancies(snapshot, 10)
    result = enumerate_multi_trade_chains(
        snapshot,
        state,
        _config(
            player_universe_ids=(1, 2, 3, 11, 12),
            trade_shapes=(TradeShape(1, 2), TradeShape(1, 1)),
        ),
    )
    candidate = next(
        item
        for item in result.candidates
        if any(
            event.team_id == 1
            and event.reduced_places == 1
            and event.outstanding_places == 1
            for event in item.vacancy_events
        )
    )
    initial = next(event for event in candidate.vacancy_events if event.team_id == 1)
    reduction = next(
        event
        for event in candidate.vacancy_events
        if event.team_id == 1 and event.reduced_places
    )
    assert initial.origin is VacancyEventOrigin.PRE_EXISTING
    assert initial.created_places == 2
    assert reduction.outstanding_places == 1
    assert candidate.completed_scenario.automatic_additions[0].team_id == 1
