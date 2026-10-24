from __future__ import annotations

from dataclasses import replace
import itertools

import pytest

from fantasy_football.canonical.model import PositionLimit
from fantasy_football.evolving_state import (
    IRPolicy,
    initialize_evolving_state,
    validate_evolving_state,
)
from fantasy_football.scenario_evaluator import (
    ExplicitRosterChange,
    ManualScenario,
    ProtectedPlayerPin,
    ScenarioEvaluationError,
    complete_manual_scenario,
)
from fantasy_football.trade_candidates import (
    SingleTradeSearchConfiguration,
    TradeCandidateError,
    TradeExecutionStatus,
    TradeShape,
    enumerate_single_trade_candidates,
    iter_single_trade_candidates,
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


def _config(
    *,
    counterparties=(2,),
    universe=(1, 2, 10, 11),
    shapes=(TradeShape(1, 1),),
    outgoing=None,
    incoming=None,
    pins=(),
):
    return SingleTradeSearchConfiguration(
        1, counterparties, universe, shapes, outgoing, incoming, pins
    )


def _signature(candidate):
    return (
        candidate.counterparty_team_id,
        candidate.shape.outgoing_count,
        candidate.shape.incoming_count,
        candidate.outgoing_player_ids,
        candidate.incoming_player_ids,
    )


def _independent_oracle(snapshot, state, config):
    owners = {item.player_id: item.team_id for item in state.roster_entries}
    outgoing = (
        tuple(player for player in config.player_universe_ids if owners.get(player) == 1)
        if config.allowed_outgoing_player_ids is None
        else config.allowed_outgoing_player_ids
    )
    incoming_filter = (
        set(config.player_universe_ids)
        if config.allowed_incoming_player_ids is None
        else set(config.allowed_incoming_player_ids)
    )
    feasible = set()
    attempted = 0
    for partner in config.counterparty_team_ids:
        incoming = tuple(
            player
            for player in config.player_universe_ids
            if owners.get(player) == partner and player in incoming_filter
        )
        for shape in config.trade_shapes:
            for sent in itertools.combinations(outgoing, shape.outgoing_count):
                for received in itertools.combinations(incoming, shape.incoming_count):
                    attempted += 1
                    changes = tuple(
                        ExplicitRosterChange(player, 1, partner) for player in sent
                    ) + tuple(
                        ExplicitRosterChange(player, partner, 1) for player in received
                    )
                    try:
                        complete_manual_scenario(
                            snapshot,
                            state,
                            ManualScenario("independent-oracle", changes, config.protected_pins),
                        )
                    except ScenarioEvaluationError:
                        continue
                    feasible.add(
                        (partner, shape.outgoing_count, shape.incoming_count, sent, received)
                    )
    return attempted, feasible


def test_one_for_one_exact_count_identity_and_contract() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    result = enumerate_single_trade_candidates(snapshot, state, _config())

    assert result.coverage.combination_count == result.coverage.structurally_feasible_count == 4
    assert result.coverage.structurally_infeasible_count == 0
    assert result.coverage.complete is True
    assert len({item.candidate_id for item in result.candidates}) == 4
    assert {
        (item.outgoing_player_ids, item.incoming_player_ids) for item in result.candidates
    } == {((1,), (2,)), ((1,), (11,)), ((10,), (2,)), ((10,), (11,))}
    assert all(item.structural_feasible for item in result.candidates)
    assert all(
        item.execution_status is TradeExecutionStatus.STRUCTURAL_HYPOTHETICAL_ONLY
        for item in result.candidates
    )
    assert all("counterparty_acceptance_not_modeled" in item.execution_caveats for item in result.candidates)
    for candidate in result.candidates:
        validate_evolving_state(candidate.completed_scenario.state, snapshot)
    assert state == _state(snapshot)


def test_multiple_counterparties_and_reordered_input_are_deterministic() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    first = enumerate_single_trade_candidates(
        snapshot,
        state,
        _config(counterparties=(3, 2), universe=(12, 2, 10, 3, 1, 11)),
    )
    second = enumerate_single_trade_candidates(
        snapshot,
        state,
        _config(counterparties=(2, 3), universe=(1, 2, 3, 10, 11, 12)),
    )
    assert first == second
    assert first.coverage.combination_count == 8
    assert {item.counterparty_team_id for item in first.candidates} == {2, 3}


def test_all_requested_trade_shapes_match_independent_exhaustive_oracle() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    config = _config(
        shapes=(TradeShape(2, 2), TradeShape(1, 2), TradeShape(2, 1), TradeShape(1, 1))
    )
    attempted, expected = _independent_oracle(snapshot, state, config)
    result = enumerate_single_trade_candidates(snapshot, state, config)
    assert attempted == result.coverage.combination_count == 9
    assert {_signature(item) for item in result.candidates} == expected
    assert len(result.candidates) == len(expected)
    assert any(item.completed_scenario.forced_drops for item in result.candidates)
    assert any(item.completed_scenario.automatic_additions for item in result.candidates)


def test_filters_distinguish_omitted_from_explicitly_empty() -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    omitted = enumerate_single_trade_candidates(snapshot, state, _config())
    restricted = enumerate_single_trade_candidates(
        snapshot, state, _config(outgoing=(10,), incoming=(11,))
    )
    empty_out = enumerate_single_trade_candidates(snapshot, state, _config(outgoing=()))
    empty_in = enumerate_single_trade_candidates(snapshot, state, _config(incoming=()))
    assert len(omitted.candidates) == 4
    assert [_signature(item) for item in restricted.candidates] == [
        (2, 1, 1, (10,), (11,))
    ]
    assert empty_out.coverage.combination_count == len(empty_out.candidates) == 0
    assert empty_in.coverage.combination_count == len(empty_in.candidates) == 0
    assert omitted.search_configuration_sha256 != empty_out.search_configuration_sha256
    shared = next(
        item for item in omitted.candidates
        if item.outgoing_player_ids == (10,) and item.incoming_player_ids == (11,)
    )
    assert shared.candidate_id == restricted.candidates[0].candidate_id
    assert tuple(iter_single_trade_candidates(snapshot, state, _config())) == omitted.candidates


@pytest.mark.parametrize(
    "config,match",
    (
        (_config(counterparties=(1,)), "cannot also be a counterparty"),
        (_config(counterparties=(2, 2)), "duplicate"),
        (_config(counterparties=(999,)), "unknown teams"),
        (_config(universe=(1, 2, 999)), "unknown players"),
        (_config(universe=(1, 2, -101)), "must be owned"),
        (_config(outgoing=(2,)), "not owned by requesting team"),
        (_config(incoming=(1,)), "not owned by an allowed counterparty"),
        (_config(shapes=(TradeShape(0, 1),)), "positive integer"),
        (_config(shapes=(TradeShape(1, 1), TradeShape(1, 1))), "duplicates"),
    ),
)
def test_invalid_search_configuration_fails_with_context(config, match) -> None:
    snapshot = _snapshot()
    with pytest.raises(TradeCandidateError, match=match):
        enumerate_single_trade_candidates(snapshot, _state(snapshot), config)


def test_disabled_closed_or_zero_limit_trade_rules_fail_closed() -> None:
    snapshot = _snapshot()
    disabled = replace(snapshot, rules=replace(snapshot.rules, trades=replace(snapshot.rules.trades, enabled=False)))
    with pytest.raises(TradeCandidateError, match="disable trades"):
        enumerate_single_trade_candidates(disabled, _state(disabled), _config())
    zero = replace(snapshot, rules=replace(snapshot.rules, trades=replace(snapshot.rules.trades, trade_limit=0)))
    with pytest.raises(TradeCandidateError, match="prohibits trades"):
        enumerate_single_trade_candidates(zero, _state(zero), _config())
    closed = replace(
        snapshot,
        rules=replace(
            snapshot.rules,
            trades=replace(snapshot.rules.trades, deadline_utc=snapshot.retrieval_started_at_utc),
        ),
    )
    with pytest.raises(TradeCandidateError, match="after the configured trade deadline"):
        enumerate_single_trade_candidates(closed, _state(closed), _config())


def test_undroppable_and_pin_constraints_are_applied_by_m4_completion() -> None:
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        players=tuple(
            replace(item, is_undroppable=True)
            if item.player_id in {1, 2, 10, 11}
            else item
            for item in snapshot.players
        ),
    )
    result = enumerate_single_trade_candidates(
        snapshot,
        _state(snapshot),
        _config(shapes=(TradeShape(2, 1),)),
    )
    assert result.coverage.combination_count == 2
    assert result.coverage.structurally_feasible_count == 0
    assert result.coverage.structurally_infeasible_count == 2
    assert result.coverage.infeasible_reason_counts

    ordinary = _snapshot()
    pinned = enumerate_single_trade_candidates(
        ordinary,
        _state(ordinary),
        _config(
            shapes=(TradeShape(1, 2),),
            outgoing=(1,),
            pins=(ProtectedPlayerPin(1, 10),),
        ),
    )
    assert pinned.coverage.combination_count == 1
    assert pinned.coverage.structurally_feasible_count == 1
    assert pinned.candidates[0].completed_scenario.forced_drops
    assert all(
        item.player_id != 10 for item in pinned.candidates[0].completed_scenario.forced_drops
    )


def test_position_limit_and_capacity_edges_are_structurally_reconciled() -> None:
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        players=tuple(
            replace(item, default_position_id=2)
            if item.player_id in {2, 10}
            else item
            for item in snapshot.players
        ),
        rules=replace(
            snapshot.rules,
            position_limits=(PositionLimit(1, 2), PositionLimit(2, 1)),
        ),
    )
    result = enumerate_single_trade_candidates(snapshot, _state(snapshot), _config())
    assert result.coverage.combination_count == 4
    assert result.coverage.structurally_feasible_count == 2
    assert result.coverage.structurally_infeasible_count == 2
    assert {_signature(item) for item in result.candidates} == {
        (2, 1, 1, (1,), (11,)),
        (2, 1, 1, (10,), (2,)),
    }


def test_enumeration_is_offline_and_preserves_inputs(monkeypatch) -> None:
    snapshot = _snapshot()
    state = _state(snapshot)
    original_snapshot = snapshot
    original_state = state

    def no_network(*_args, **_kwargs):
        raise AssertionError("single-trade enumeration attempted network access")

    monkeypatch.setattr("socket.create_connection", no_network)
    result = enumerate_single_trade_candidates(snapshot, state, _config())
    assert result.coverage.complete
    assert snapshot == original_snapshot
    assert state == original_state
