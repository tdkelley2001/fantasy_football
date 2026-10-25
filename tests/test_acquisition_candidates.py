from __future__ import annotations

from dataclasses import replace

import pytest

from fantasy_football.acquisition_candidates import (
    AcquisitionCandidateError,
    AcquisitionDisposition,
    ImmediateAcquisitionSearchConfiguration,
    enumerate_immediate_acquisition_candidates,
    iter_immediate_acquisition_candidates,
)
from fantasy_football.evolving_state import (
    AcquisitionAvailability,
    IRPolicy,
    PlayerAvailability,
    TransactionErrorCode,
    TransactionStateError,
    drop_player,
    initialize_evolving_state,
    state_to_json,
)
from fantasy_football.weekly_transactions import WaiverBoundaryPolicy
from fantasy_football.lineup_optimizer import optimize_starting_lineup
from tests.canonical_fixtures import canonical_snapshot


def _state(snapshot=None):
    snapshot = canonical_snapshot() if snapshot is None else snapshot
    return initialize_evolving_state(
        snapshot, scoring_week=15, ir_policy=IRPolicy.PROJECTION_BASED
    )


def _configuration(**changes):
    return replace(
        ImmediateAcquisitionSearchConfiguration(
            requesting_team_id=1,
            acquisition_player_ids=(3,),
        ),
        **changes,
    )


def _availability(state, player_id, status):
    return replace(
        state,
        availability=tuple(
            PlayerAvailability(
                item.player_id,
                status,
                item.clearance_at_utc,
                item.hold_until_cycle,
                item.prohibited_cycle_id,
                item.source_id,
            )
            if item.player_id == player_id
            else item
            for item in state.availability
        ),
    )


def test_small_free_agent_universe_reconciles_exact_independent_oracle() -> None:
    snapshot = canonical_snapshot()
    state = _state(snapshot)
    result = enumerate_immediate_acquisition_candidates(
        snapshot, state, _configuration()
    )
    # Independent leaf universe: two eligible destinations multiplied by one
    # add-only action plus one action for each of the two owned drop players.
    oracle = {
        (3, drop_id, slot_id)
        for drop_id in (None, -101, 1)
        for slot_id in (0, 20)
    }
    observed = {
        (item.acquired_player_id, item.dropped_player_id, item.destination_slot_id)
        for item in result.candidates
    }
    assert observed == oracle
    assert tuple(
        iter_immediate_acquisition_candidates(snapshot, state, _configuration())
    ) == result.candidates
    assert result.coverage.raw_combination_count == 6
    assert result.coverage.authorized_immediate_count == 2
    assert result.coverage.prohibited_count == 2
    assert result.coverage.structurally_infeasible_count == 4
    assert sum(count for _, count in result.coverage.disposition_counts) == 6


def test_add_only_open_capacity_and_full_slot_are_distinct_candidates() -> None:
    snapshot = canonical_snapshot()
    snapshot = replace(
        snapshot,
        player_weeks=tuple(
            replace(item, raw_projection=1.0, effective_projection=1.0)
            if item.player_id == -101 and item.scoring_week == 15
            else item
            for item in snapshot.player_weeks
        ),
    )
    state = _state(snapshot)
    assert optimize_starting_lineup(
        snapshot, 1, 15, roster_entries=state.roster_entries
    ).vacancy_count == 0
    result = enumerate_immediate_acquisition_candidates(
        snapshot,
        state,
        _configuration(eligible_drop_player_ids=(), include_drop_and_add=False),
    )
    by_slot = {item.destination_slot_id: item for item in result.candidates}
    assert by_slot[20].disposition is AcquisitionDisposition.AUTHORIZED_IMMEDIATE
    assert by_slot[20].resulting_state is not None
    assert by_slot[0].disposition is AcquisitionDisposition.STRUCTURALLY_INFEASIBLE
    assert by_slot[0].resulting_state is None


def test_drop_add_preserves_selected_drop_and_protection() -> None:
    result = enumerate_immediate_acquisition_candidates(
        canonical_snapshot(),
        _state(),
        _configuration(include_add_only=False),
    )
    legal = next(
        item
        for item in result.candidates
        if item.dropped_player_id == -101 and item.destination_slot_id == 20
    )
    assert legal.disposition is AcquisitionDisposition.AUTHORIZED_IMMEDIATE
    assert legal.resulting_state is not None
    assert {item.player_id for item in legal.resulting_state.roster_entries}.issuperset({1, 3})
    assert -101 not in {item.player_id for item in legal.resulting_state.roster_entries}
    availability = {
        item.player_id: item.status for item in legal.resulting_state.availability
    }
    assert availability[-101] is AcquisitionAvailability.HOLD
    assert availability[3] is AcquisitionAvailability.ROSTERED
    protected = [item for item in result.candidates if item.dropped_player_id == 1]
    assert protected
    assert all(item.disposition is AcquisitionDisposition.PROHIBITED for item in protected)


def test_waiver_claim_requires_controlled_boundary_and_remains_conditional() -> None:
    snapshot = canonical_snapshot()
    state = _state(snapshot)
    unresolved = enumerate_immediate_acquisition_candidates(
        snapshot,
        state,
        _configuration(
            acquisition_player_ids=(4,),
            eligible_drop_player_ids=(),
            include_drop_and_add=False,
        ),
    )
    open_slot = next(item for item in unresolved.candidates if item.destination_slot_id == 20)
    assert open_slot.disposition is AcquisitionDisposition.UNRESOLVED
    assert open_slot.resulting_state is None
    assert open_slot.structurally_feasible

    conditional = enumerate_immediate_acquisition_candidates(
        snapshot,
        state,
        _configuration(
            acquisition_player_ids=(4,),
            eligible_drop_player_ids=(),
            include_drop_and_add=False,
            waiver_boundary=WaiverBoundaryPolicy.MODELED_WEEKLY_V1,
        ),
    )
    claim = next(item for item in conditional.candidates if item.destination_slot_id == 20)
    assert claim.disposition is AcquisitionDisposition.CONDITIONAL_WAIVER
    assert claim.resulting_state is not None
    assert claim.required_assumptions == ("modeled_weekly_waiver_boundary_v1",)
    assert "not_guaranteed" in " ".join(claim.execution_caveats)
    assert claim.resulting_state.current_waiver_priority == (2, 3, 4, 1)
    assert sum(
        item.player_id == 4 for item in claim.resulting_state.roster_entries
    ) == 1


@pytest.mark.parametrize(
    "status",
    (AcquisitionAvailability.HOLD, AcquisitionAvailability.UNRESOLVED),
)
def test_held_and_unresolved_players_never_become_authorized(status) -> None:
    snapshot = canonical_snapshot()
    state = _availability(_state(snapshot), 3, status)
    result = enumerate_immediate_acquisition_candidates(
        snapshot,
        state,
        _configuration(eligible_drop_player_ids=(), include_drop_and_add=False),
    )
    assert all(item.disposition is AcquisitionDisposition.UNRESOLVED for item in result.candidates)
    assert all(item.resulting_state is None for item in result.candidates)


def test_rostered_player_is_prohibited_not_silently_transferred() -> None:
    result = enumerate_immediate_acquisition_candidates(
        canonical_snapshot(),
        _state(),
        _configuration(
            acquisition_player_ids=(2,),
            eligible_drop_player_ids=(),
            include_drop_and_add=False,
        ),
    )
    assert all(item.disposition is AcquisitionDisposition.PROHIBITED for item in result.candidates)
    assert all(item.resulting_state is None for item in result.candidates)


def test_priority_diagnostics_preserve_unknown_competing_claim_behavior() -> None:
    result = enumerate_immediate_acquisition_candidates(
        canonical_snapshot(),
        _state(),
        _configuration(
            requesting_team_id=2,
            eligible_drop_player_ids=(),
            include_drop_and_add=False,
        ),
    )
    candidate = next(item for item in result.candidates if item.destination_slot_id == 20)
    assert candidate.waiver_priority.requesting_team_position == 2
    assert candidate.waiver_priority.higher_priority_team_ids == (1,)
    assert not candidate.waiver_priority.competitive_claim_behavior_resolved


def test_modeled_waiver_boundary_rejects_unsupported_faab_rules() -> None:
    snapshot = canonical_snapshot()
    snapshot = replace(
        snapshot,
        rules=replace(
            snapshot.rules,
            acquisition=replace(
                snapshot.rules.acquisition,
                acquisition_type="WAIVERS_FAAB",
                uses_budget=True,
            ),
        ),
    )
    with pytest.raises(ValueError, match="WAIVERS_TRADITIONAL"):
        enumerate_immediate_acquisition_candidates(
            snapshot,
            _state(snapshot),
            _configuration(
                acquisition_player_ids=(4,),
                waiver_boundary=WaiverBoundaryPolicy.MODELED_WEEKLY_V1,
            ),
        )
    free_agent_only = enumerate_immediate_acquisition_candidates(
        snapshot,
        _state(snapshot),
        _configuration(
            acquisition_player_ids=(3,),
            eligible_drop_player_ids=(),
            include_drop_and_add=False,
            waiver_boundary=WaiverBoundaryPolicy.MODELED_WEEKLY_V1,
        ),
    )
    assert free_agent_only.coverage.authorized_immediate_count == 1


def test_omitted_and_empty_filters_remain_distinct() -> None:
    snapshot = canonical_snapshot()
    state = _state(snapshot)
    omitted = enumerate_immediate_acquisition_candidates(
        snapshot, state, _configuration(include_add_only=False)
    )
    empty_drops = enumerate_immediate_acquisition_candidates(
        snapshot,
        state,
        _configuration(
            eligible_drop_player_ids=(),
            include_add_only=True,
            include_drop_and_add=True,
        ),
    )
    empty_status = enumerate_immediate_acquisition_candidates(
        snapshot,
        state,
        _configuration(acquisition_status_filter=()),
    )
    assert omitted.coverage.declared_drop_player_count == 2
    assert empty_drops.coverage.declared_drop_player_count == 0
    assert empty_status.coverage.raw_combination_count == 0
    assert empty_status.coverage.complete


def test_reordered_inputs_have_stable_identity_and_results() -> None:
    snapshot = canonical_snapshot()
    state = _state(snapshot)
    first = enumerate_immediate_acquisition_candidates(
        snapshot,
        state,
        _configuration(acquisition_player_ids=(4, 3), eligible_drop_player_ids=(1, -101)),
    )
    second = enumerate_immediate_acquisition_candidates(
        snapshot,
        state,
        _configuration(acquisition_player_ids=(3, 4), eligible_drop_player_ids=(-101, 1)),
    )
    assert first.search_configuration_sha256 == second.search_configuration_sha256
    assert first.candidates == second.candidates
    assert first.coverage == second.coverage


def test_mixed_universe_excludes_player_without_ordinary_destination() -> None:
    snapshot = canonical_snapshot()
    snapshot = replace(
        snapshot,
        players=tuple(
            replace(item, eligible_lineup_slot_ids=(21,))
            if item.player_id == 4
            else item
            for item in snapshot.players
        ),
    )
    state = _state(snapshot)
    first = enumerate_immediate_acquisition_candidates(
        snapshot,
        state,
        _configuration(acquisition_player_ids=(4, 3)),
    )
    second = enumerate_immediate_acquisition_candidates(
        snapshot,
        state,
        _configuration(acquisition_player_ids=(3, 4)),
    )
    assert first == second
    assert first.coverage.declared_acquisition_player_count == 2
    assert first.coverage.eligible_acquisition_player_count == 2
    assert first.coverage.excluded_player_count == 1
    assert first.coverage.player_exclusions[0].player_id == 4
    assert (
        first.coverage.player_exclusions[0].rejection_code
        == "no_supported_ordinary_destination"
    )
    assert {item.acquired_player_id for item in first.candidates} == {3}
    assert first.coverage.raw_combination_count == len(first.candidates) == 6
    assert sum(count for _, count in first.coverage.disposition_counts) == 6


def test_stable_rejection_codes_cover_transaction_failure_classes() -> None:
    snapshot = canonical_snapshot()
    state = _state(snapshot)
    basic = enumerate_immediate_acquisition_candidates(
        snapshot, state, _configuration()
    )
    by_plan = {
        (item.dropped_player_id, item.destination_slot_id): item
        for item in basic.candidates
    }
    assert by_plan[(None, 0)].rejection_code == "slot_capacity"
    assert by_plan[(1, 20)].rejection_code == "undroppable_protected"

    reentry_state = replace(
        state,
        availability=tuple(
            replace(item, prohibited_cycle_id=state.cycle_id)
            if item.player_id == 3
            else item
            for item in state.availability
        ),
    )
    reentry = enumerate_immediate_acquisition_candidates(
        snapshot,
        reentry_state,
        _configuration(eligible_drop_player_ids=(), include_drop_and_add=False),
    )
    assert next(
        item for item in reentry.candidates if item.destination_slot_id == 20
    ).rejection_code == "prohibited_reentry"

    limited_snapshot = replace(
        snapshot,
        rules=replace(
            snapshot.rules,
            acquisition=replace(snapshot.rules.acquisition, season_limit=0),
        ),
    )
    counts = {team.team_id: 0 for team in snapshot.teams}
    limited_state = initialize_evolving_state(
        limited_snapshot,
        scoring_week=15,
        ir_policy=IRPolicy.PROJECTION_BASED,
        season_acquisition_counts=counts,
    )
    limited = enumerate_immediate_acquisition_candidates(
        limited_snapshot,
        limited_state,
        _configuration(eligible_drop_player_ids=(), include_drop_and_add=False),
    )
    assert next(
        item for item in limited.candidates if item.destination_slot_id == 20
    ).rejection_code == "acquisition_limit"


def test_position_and_ir_evidence_failures_have_stable_codes() -> None:
    snapshot = canonical_snapshot()
    position_snapshot = replace(
        snapshot,
        rules=replace(
            snapshot.rules,
            position_limits=tuple(
                replace(item, maximum=1) if item.position_id == 1 else item
                for item in snapshot.rules.position_limits
            ),
        ),
    )
    position_result = enumerate_immediate_acquisition_candidates(
        position_snapshot,
        _state(position_snapshot),
        _configuration(eligible_drop_player_ids=(), include_drop_and_add=False),
    )
    assert next(
        item for item in position_result.candidates if item.destination_slot_id == 20
    ).rejection_code == "position_limit"

    strict = initialize_evolving_state(
        snapshot, scoring_week=15, ir_policy=IRPolicy.STRICT
    )
    strict = replace(
        strict,
        roster_entries=tuple(
            replace(item, lineup_slot_id=21) if item.player_id == 1 else item
            for item in strict.roster_entries
        ),
    )
    ir_result = enumerate_immediate_acquisition_candidates(
        snapshot,
        strict,
        _configuration(eligible_drop_player_ids=(), include_drop_and_add=False),
    )
    assert next(
        item for item in ir_result.candidates if item.destination_slot_id == 20
    ).rejection_code == "ir_evidence_unresolved"


def test_transaction_error_codes_do_not_depend_on_human_message(monkeypatch) -> None:
    def changed_message(*_args, **_kwargs):
        raise TransactionStateError(
            "this wording is intentionally unrelated",
            TransactionErrorCode.SLOT_CAPACITY,
        )

    monkeypatch.setattr(
        "fantasy_football.acquisition_candidates.add_player", changed_message
    )
    result = enumerate_immediate_acquisition_candidates(
        canonical_snapshot(),
        _state(),
        _configuration(eligible_drop_player_ids=(), include_drop_and_add=False),
    )
    assert all(
        item.disposition is AcquisitionDisposition.STRUCTURALLY_INFEASIBLE
        for item in result.candidates
    )
    assert {item.rejection_code for item in result.candidates} == {"slot_capacity"}


def test_transaction_boundary_ownership_code_is_explicit() -> None:
    snapshot = canonical_snapshot()
    state = _state(snapshot)
    with pytest.raises(TransactionStateError) as captured:
        drop_player(state, snapshot, team_id=1, player_id=2)
    assert captured.value.code is TransactionErrorCode.OWNERSHIP


def test_inputs_remain_immutable_and_execution_is_offline(monkeypatch) -> None:
    snapshot = canonical_snapshot()
    state = _state(snapshot)
    before = state_to_json(state, snapshot)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    result = enumerate_immediate_acquisition_candidates(snapshot, state, _configuration())
    assert result.candidates
    assert state_to_json(state, snapshot) == before
    assert state.ledger == ()


@pytest.mark.parametrize(
    "configuration,match",
    (
        (_configuration(requesting_team_id=999), "unknown"),
        (_configuration(acquisition_player_ids=(999,)), "unknown players"),
        (_configuration(eligible_drop_player_ids=(2,)), "not owned"),
        (_configuration(acquisition_player_ids=(3, 3)), "duplicate"),
        (_configuration(include_add_only=False, include_drop_and_add=False), "at least one"),
        (_configuration(waiver_boundary="anything"), "unsupported waiver boundary"),
    ),
)
def test_invalid_configuration_fails_safely(configuration, match) -> None:
    with pytest.raises(AcquisitionCandidateError, match=match):
        enumerate_immediate_acquisition_candidates(
            canonical_snapshot(), _state(), configuration
        )

