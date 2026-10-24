from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

import fantasy_football.trade_evaluation as evaluation_module
from fantasy_football.evolving_state import AcquisitionAvailability
from fantasy_football.monte_carlo_precision import PrecisionConfiguration
from fantasy_football.player_outcomes import ProvisionalNormalModel
from fantasy_football.trade_candidates import TradeShape, enumerate_single_trade_candidates
from fantasy_football.trade_evaluation import (
    TradeEvaluationError,
    build_candidate_state_registry,
    completed_state_fingerprint,
    evaluate_trade_candidate_states,
    evaluation_fingerprint,
    validate_candidate_state_registry,
)
from fantasy_football.trade_screening import screen_trade_candidates
from tests.test_monte_carlo import PrescribedModel
from tests.test_scenario_evaluator import _config as _simulation_config
from tests.test_trade_candidates import _config, _snapshot, _state


def _screening():
    snapshot = _snapshot()
    state = _state(snapshot)
    candidates = enumerate_single_trade_candidates(snapshot, state, _config())
    return snapshot, state, screen_trade_candidates(snapshot, state, candidates)


def _equivalent_paths_screening(snapshot, state):
    screening = screen_trade_candidates(
        snapshot,
        state,
        enumerate_single_trade_candidates(
            snapshot,
            state,
            _config(
                counterparties=(2, 3, 4),
                universe=(1, 2, 3, 4, 10, 11, 12, 13),
                shapes=(
                    TradeShape(1, 1),
                    TradeShape(1, 2),
                    TradeShape(2, 1),
                    TradeShape(2, 2),
                ),
            ),
        ),
    )
    groups = {}
    for outcome in screening.outcomes:
        state_id = completed_state_fingerprint(
            snapshot, outcome.candidate.completed_scenario.state
        )
        groups.setdefault(state_id, []).append(outcome)
    selected = tuple(next(values for values in groups.values() if len(values) == 2))
    candidate_enumeration = replace(
        screening.candidate_enumeration,
        candidates=tuple(item.candidate for item in selected),
        coverage=replace(
            screening.candidate_enumeration.coverage,
            combination_count=2,
            structurally_feasible_count=2,
            structurally_infeasible_count=0,
        ),
    )
    return replace(
        screening,
        candidate_enumeration=candidate_enumeration,
        outcomes=selected,
        retained_candidate_ids=tuple(item.candidate.candidate_id for item in selected),
        coverage=replace(
            screening.coverage,
            raw_combination_count=2,
            structurally_feasible_count=2,
            structurally_infeasible_count=0,
            assessed_candidate_count=2,
            retained_candidate_count=2,
            excluded_candidate_count=0,
        ),
    )


def test_distinct_candidates_share_one_canonical_completed_state() -> None:
    snapshot, state, _ = _screening()
    registry = build_candidate_state_registry(
        snapshot, _equivalent_paths_screening(snapshot, state)
    )

    assert len(registry.paths) == 2
    assert len(registry.states) == 1
    assert len({item.candidate_id for item in registry.paths}) == 2
    assert registry.states[0].candidate_ids == tuple(
        sorted(item.candidate_id for item in registry.paths)
    )
    assert registry.paths[0].screening_outcome.candidate.explicit_changes != (
        registry.paths[1].screening_outcome.candidate.explicit_changes
    )


def test_shared_evaluation_executes_once_and_reuses_byte_identical_result(monkeypatch) -> None:
    snapshot, state, _ = _screening()
    registry = build_candidate_state_registry(
        snapshot, _equivalent_paths_screening(snapshot, state)
    )
    calls = 0
    real = evaluation_module.evaluate_completed_manual_scenario

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(evaluation_module, "evaluate_completed_manual_scenario", counted)
    result = evaluate_trade_candidate_states(
        snapshot,
        state,
        registry,
        _simulation_config(1),
        PrescribedModel(),
        PrecisionConfiguration(0.95, 0.9, 1, 1, 1),
    )

    assert calls == 1
    assert result.coverage.candidate_path_count == 2
    assert result.coverage.unique_completed_state_count == 1
    assert result.coverage.actual_paired_evaluation_count == 1
    assert result.coverage.paired_evaluations_avoided == 1
    assert len({item.evaluation_sha256 for item in result.candidate_links}) == 1
    shared = result.evaluations[0].comparison
    assert all(
        next(
            value.comparison
            for value in result.evaluations
            if value.evaluation_sha256 == link.evaluation_sha256
        )
        is shared
        for link in result.candidate_links
    )
    assert shared.baseline.batch.path_indices == shared.hypothetical.batch.path_indices
    assert shared.matched_path_count == 1


def test_state_identity_covers_all_teams_priority_availability_and_exact_numbers() -> None:
    snapshot, state, screening = _screening()
    completed = screening.outcomes[0].candidate.completed_scenario.state
    base = completed_state_fingerprint(snapshot, completed)
    priority = replace(
        completed,
        current_waiver_priority=tuple(reversed(completed.current_waiver_priority)),
    )
    availability = tuple(
        replace(item, status=AcquisitionAvailability.UNRESOLVED)
        if item.status is AcquisitionAvailability.FREE_AGENT
        else item
        for item in completed.availability
    )
    changed_availability = replace(completed, availability=availability)

    assert completed_state_fingerprint(snapshot, priority) != base
    assert completed_state_fingerprint(snapshot, changed_availability) != base
    assert completed_state_fingerprint(snapshot, state) != base


def test_different_completed_league_states_are_not_merged() -> None:
    snapshot, _, screening = _screening()
    registry = build_candidate_state_registry(snapshot, screening)
    assert len(registry.paths) == 4
    assert len(registry.states) > 1
    by_requester_roster = {}
    for group in registry.states:
        requester = tuple(
            sorted(item.player_id for item in group.state.roster_entries if item.team_id == 1)
        )
        by_requester_roster.setdefault(requester, set()).add(group.completed_state_sha256)
    assert all(len(values) >= 1 for values in by_requester_roster.values())


def test_same_requester_roster_with_different_opponent_ownership_has_distinct_identity() -> None:
    snapshot, _, screening = _screening()
    state = screening.outcomes[0].candidate.completed_scenario.state
    requester_before = tuple(
        item for item in state.roster_entries if item.team_id == 1
    )
    team_two_entry = next(item for item in state.roster_entries if item.team_id == 2)
    team_three_entry = next(
        item
        for item in state.roster_entries
        if item.team_id == 3 and item.lineup_slot_id == team_two_entry.lineup_slot_id
    )
    team_two_player = team_two_entry.player_id
    team_three_player = team_three_entry.player_id
    swapped = replace(
        state,
        roster_entries=tuple(
            sorted(
                (
                    replace(item, team_id=3, raw_owner_team_id=3)
                    if item.player_id == team_two_player
                    else replace(item, team_id=2, raw_owner_team_id=2)
                    if item.player_id == team_three_player
                    else item
                    for item in state.roster_entries
                ),
                key=lambda item: (item.team_id, item.player_id),
            )
        ),
    )
    assert tuple(item for item in swapped.roster_entries if item.team_id == 1) == requester_before
    assert completed_state_fingerprint(snapshot, swapped) != completed_state_fingerprint(
        snapshot, state
    )


def test_evaluation_identity_separates_seed_range_precision_model_and_snapshot() -> None:
    snapshot, state, screening = _screening()
    completed = screening.outcomes[0].candidate.completed_scenario.state
    precision = PrecisionConfiguration(0.95, 0.9, 1, 1, 1)
    config = _simulation_config(1)
    base = evaluation_fingerprint(
        snapshot, state, completed, config, PrescribedModel(), precision
    )
    assert evaluation_fingerprint(
        snapshot, state, completed, replace(config, master_seed=999), PrescribedModel(), precision
    ) != base
    assert evaluation_fingerprint(
        snapshot, state, completed, replace(config, first_path_index=1), PrescribedModel(), precision
    ) != base
    assert evaluation_fingerprint(
        snapshot,
        state,
        completed,
        config,
        PrescribedModel(),
        PrecisionConfiguration(0.9, 0.9, 1, 1, 1),
    ) != base
    assert evaluation_fingerprint(
        snapshot, state, completed, config, ProvisionalNormalModel(1.0, 0.1), precision
    ) != base
    changed_snapshot = replace(
        snapshot,
        retrieval_finished_at_utc=snapshot.retrieval_finished_at_utc + timedelta(seconds=1),
    )
    assert completed_state_fingerprint(changed_snapshot, replace(
        completed, source_snapshot_id=changed_snapshot.snapshot_id or ""
    )) != completed_state_fingerprint(snapshot, completed)


def test_candidate_order_does_not_change_registry() -> None:
    snapshot, _, screening = _screening()
    first = build_candidate_state_registry(snapshot, screening)
    reordered = replace(screening, outcomes=tuple(reversed(screening.outcomes)))
    assert build_candidate_state_registry(snapshot, reordered) == first


def test_excluded_candidates_are_omitted_by_default_but_can_remain_inspectable() -> None:
    snapshot, _, screening = _screening()
    retained_ids = screening.retained_candidate_ids[:2]
    narrowed = replace(
        screening,
        retained_candidate_ids=retained_ids,
        outcomes=tuple(
            replace(item, passes_screen=item.candidate.candidate_id in retained_ids)
            for item in screening.outcomes
        ),
        coverage=replace(
            screening.coverage,
            retained_candidate_count=2,
            excluded_candidate_count=2,
        ),
    )
    assert len(build_candidate_state_registry(snapshot, narrowed).paths) == 2
    assert len(build_candidate_state_registry(snapshot, narrowed, retained_only=False).paths) == 4


def test_malformed_registry_and_conflicting_identity_fail_closed() -> None:
    snapshot, _, screening = _screening()
    registry = build_candidate_state_registry(snapshot, screening)
    group = registry.states[0]
    malformed = replace(
        registry,
        states=(replace(group, completed_state_sha256="0" * 64), *registry.states[1:]),
    )
    with pytest.raises(TradeEvaluationError, match="content conflicts|do not reconcile"):
        validate_candidate_state_registry(snapshot, malformed)
    duplicate_path = replace(registry, paths=(registry.paths[0], registry.paths[0]))
    with pytest.raises(TradeEvaluationError, match="unique canonical ordering"):
        validate_candidate_state_registry(snapshot, duplicate_path)


def test_candidate_paths_cannot_exchange_completed_states_even_if_groups_reconcile() -> None:
    snapshot, _, screening = _screening()
    registry = build_candidate_state_registry(snapshot, screening)
    paths = list(registry.paths)
    left = paths[0]
    right_index = next(
        index
        for index, item in enumerate(paths[1:], start=1)
        if item.completed_state_sha256 != left.completed_state_sha256
    )
    right = paths[right_index]
    paths[0] = replace(left, completed_state_sha256=right.completed_state_sha256)
    paths[right_index] = replace(right, completed_state_sha256=left.completed_state_sha256)
    memberships = {}
    for path in paths:
        memberships.setdefault(path.completed_state_sha256, []).append(path.candidate_id)
    states = tuple(
        replace(group, candidate_ids=tuple(sorted(memberships[group.completed_state_sha256])))
        for group in registry.states
    )
    forged = replace(registry, paths=tuple(paths), states=states)

    with pytest.raises(TradeEvaluationError, match="path completed state conflicts"):
        validate_candidate_state_registry(snapshot, forged)


def test_wrong_valid_baseline_is_rejected_before_paired_evaluation(monkeypatch) -> None:
    snapshot, state, screening = _screening()
    registry = build_candidate_state_registry(snapshot, screening)
    wrong_baseline = replace(
        state,
        current_waiver_priority=tuple(reversed(state.current_waiver_priority)),
    )
    calls = 0

    def forbidden(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("paired evaluator must not be called")

    monkeypatch.setattr(evaluation_module, "evaluate_completed_manual_scenario", forbidden)
    with pytest.raises(TradeEvaluationError, match="baseline state identity differs"):
        evaluate_trade_candidate_states(
            snapshot,
            wrong_baseline,
            registry,
            _simulation_config(1),
            PrescribedModel(),
            PrecisionConfiguration(0.95, 0.9, 1, 1, 1),
        )
    assert calls == 0


def test_registry_construction_rejects_screening_baseline_provenance_mismatch() -> None:
    snapshot, _, screening = _screening()
    forged = replace(screening, baseline_state_sha256="0" * 64)
    with pytest.raises(TradeEvaluationError, match="enumeration baseline identities differ"):
        build_candidate_state_registry(snapshot, forged)


def test_registry_and_evaluation_do_not_mutate_inputs_or_call_network(monkeypatch) -> None:
    snapshot, state, screening = _screening()
    before = (snapshot, state, screening)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    registry = build_candidate_state_registry(snapshot, screening)
    evaluate_trade_candidate_states(
        snapshot,
        state,
        registry,
        _simulation_config(1),
        PrescribedModel(),
        PrecisionConfiguration(0.95, 0.9, 1, 1, 1),
    )
    assert (snapshot, state, screening) == before
