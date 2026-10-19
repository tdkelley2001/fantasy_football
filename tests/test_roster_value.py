from __future__ import annotations

from dataclasses import replace
import random
import time

import pytest

from fantasy_football.canonical.model import (
    Player,
    PlayerWeek,
    ProjectionClass,
    ProjectionSource,
    RosterEntry,
)
from fantasy_football.evolving_state import (
    AcquisitionAvailability,
    IRPolicy,
    add_player,
    initialize_evolving_state,
)
from fantasy_football.roster_value import (
    ReplacementAccessContext,
    RosterValuationError,
    compare_roster_values,
    value_hypothetical_roster,
    value_roster,
)
from tests.canonical_fixtures import canonical_snapshot


def _valuation_snapshot(*, competing_teams: int = 0, pool_values=(8.0, 6.0)):
    snapshot = canonical_snapshot()
    source_id = snapshot.sources[0].source_id
    base_players = tuple(
        replace(item, acquisition_status="UNKNOWN") if item.player_id in {-101, 2, 3, 4} else item
        for item in snapshot.players
    )
    owned = (
        Player(20, "Team 2 QB", 1, (0, 20), 2, "ACTIVE", "ONTEAM", False, source_id),
        Player(30, "Team 3 QB", 1, (0, 20), 3, "ACTIVE", "ONTEAM", False, source_id),
        Player(40, "Team 4 QB", 1, (0, 20), 4, "ACTIVE", "ONTEAM", False, source_id),
        Player(-202, "Team 2 DST", 16, (16, 20), 2, None, "ONTEAM", False, source_id),
        Player(-203, "Team 3 DST", 16, (16, 20), 3, None, "ONTEAM", False, source_id),
        Player(-204, "Team 4 DST", 16, (16, 20), 4, None, "ONTEAM", False, source_id),
    )
    pool = tuple(
        Player(-300 - index, f"Pool DST {index}", 16, (16, 20), 3, None, "FREEAGENT", False, source_id)
        for index, _ in enumerate(pool_values)
    )
    players = base_players + owned + pool
    rosters = [RosterEntry(1, 1, 0, 1)]
    for team_id, qb_id, dst_id in ((2, 20, -202), (3, 30, -203), (4, 40, -204)):
        rosters.append(RosterEntry(qb_id, team_id, 0, team_id))
        if team_id - 1 > competing_teams:
            rosters.append(RosterEntry(dst_id, team_id, 16, team_id))
        else:
            players = tuple(
                replace(item, acquisition_status="UNKNOWN") if item.player_id == dst_id else item
                for item in players
            )
    extra_weeks = []
    for week in (15, 16, 17):
        for player_id in (20, 30, 40):
            extra_weeks.append(PlayerWeek(
                player_id, 2026, week, 9.0, ProjectionClass.PRESENT, 9.0,
                ProjectionSource.ESPN, source_id,
            ))
        for player_id in (-202, -203, -204):
            extra_weeks.append(PlayerWeek(
                player_id, 2026, week, 7.0, ProjectionClass.PRESENT, 7.0,
                ProjectionSource.ESPN, source_id,
            ))
        for index, projection in enumerate(pool_values):
            extra_weeks.append(PlayerWeek(
                -300 - index, 2026, week, projection,
                ProjectionClass.EXPLICIT_ZERO if projection == 0 else ProjectionClass.PRESENT,
                projection, ProjectionSource.ESPN, source_id,
            ))
    return replace(
        snapshot,
        players=tuple(sorted(players, key=lambda item: item.player_id)),
        roster_entries=tuple(sorted(rosters, key=lambda item: (item.team_id, item.player_id))),
        player_weeks=tuple(sorted(snapshot.player_weeks + tuple(extra_weeks), key=lambda item: (item.player_id, item.season, item.scoring_week))),
    )


def _state(snapshot):
    return initialize_evolving_state(snapshot, scoring_week=15, ir_policy=IRPolicy.PROJECTION_BASED)


def test_equal_weight_multiweek_value_and_replacement_diagnostics() -> None:
    snapshot = _valuation_snapshot()
    state = _state(snapshot)
    result = value_roster(snapshot, state, 1)
    assert result.total_value == pytest.approx(57.0)
    assert tuple(item.projected_lineup_points for item in result.weeks) == (18.0, 19.0, 20.0)
    assert tuple(item.owned_projected_points for item in result.weeks) == (10.0, 11.0, 12.0)
    assert all(item.mandatory_vacancy_count == 1 for item in result.weeks)
    assert all(item.remaining_vacancy_count == 0 for item in result.weeks)
    assert all(item.replacement_assignments[0].player_id == -300 for item in result.weeks)
    assert state.ledger == ()


def test_nonpositive_pool_leaves_explicit_vacancies() -> None:
    snapshot = _valuation_snapshot(pool_values=(0.0, -1.0))
    result = value_roster(snapshot, _state(snapshot), 1)
    assert result.total_value == pytest.approx(33.0)
    assert all(item.remaining_vacancy_count == 1 for item in result.weeks)
    assert all(not item.replacement_assignments for item in result.weeks)


def test_conservative_shared_pool_allocation_is_opponent_first_without_double_counting() -> None:
    snapshot = _valuation_snapshot(competing_teams=1)
    result = value_roster(snapshot, _state(snapshot), 1)
    for week in result.weeks:
        assert week.opponent_replacement_assignments[0].player_id == -300
        assert week.replacement_assignments[0].player_id == -301
        assigned = {
            item.player_id for item in week.opponent_replacement_assignments + week.replacement_assignments
        }
        assert len(assigned) == 2
        assert week.replacement_assignments[0].access_rank == 2
    assert result.total_value == pytest.approx(51.0)


def test_insufficient_shared_pool_fills_opponents_before_target() -> None:
    snapshot = _valuation_snapshot(competing_teams=2)
    result = value_roster(snapshot, _state(snapshot), 1)
    assert all(item.remaining_vacancy_count == 1 for item in result.weeks)
    assert all(len(item.opponent_replacement_assignments) == 2 for item in result.weeks)
    assert result.total_value == pytest.approx(33.0)


def test_held_and_unresolved_players_are_not_assumed_accessible() -> None:
    snapshot = _valuation_snapshot()
    state = _state(snapshot)
    availability = tuple(
        replace(item, status=AcquisitionAvailability.HOLD, prohibited_cycle_id=state.cycle_id)
        if item.player_id == -300 else
        replace(item, status=AcquisitionAvailability.UNRESOLVED)
        if item.player_id == -301 else item
        for item in state.availability
    )
    state = replace(state, availability=availability)
    result = value_roster(snapshot, state, 1)
    assert result.total_value == pytest.approx(33.0)
    assert result.is_complete is False
    assert result.unresolved_inputs == ("hold", "unresolved")


def test_actual_add_and_compound_result_use_same_unified_value_without_mutation() -> None:
    snapshot = _valuation_snapshot(competing_teams=1)
    state = _state(snapshot)
    baseline = value_roster(snapshot, state, 1)
    added = add_player(state, snapshot, team_id=1, player_id=-300, lineup_slot_id=16)
    scenario = value_roster(snapshot, added, 1)
    comparison = compare_roster_values(baseline, scenario)
    assert comparison.delta == pytest.approx(6.0)
    assert comparison.current_week_vacancy_improvement == 1
    assert state.ledger == ()
    assert len(added.ledger) == 1


def test_reordered_canonical_inputs_produce_equivalent_value() -> None:
    snapshot = _valuation_snapshot(competing_teams=1)
    state = _state(snapshot)
    expected = value_roster(snapshot, state, 1)
    reordered = replace(
        snapshot,
        players=tuple(reversed(snapshot.players)),
        player_weeks=tuple(reversed(snapshot.player_weeks)),
        teams=tuple(reversed(snapshot.teams)),
    )
    reordered_state = replace(
        state,
        roster_entries=tuple(reversed(state.roster_entries)),
        availability=tuple(reversed(state.availability)),
    )
    assert value_roster(reordered, reordered_state, 1) == expected


def test_invalid_identity_and_horizon_fail_explicitly() -> None:
    snapshot = _valuation_snapshot()
    state = _state(snapshot)
    with pytest.raises(RosterValuationError, match="unknown fantasy team"):
        value_roster(snapshot, state, 99)
    with pytest.raises(RosterValuationError, match="valuation first week"):
        value_roster(snapshot, state, 1, first_scoring_week=14)


def test_structural_hypothetical_is_explicit_and_does_not_mutate_or_authorize_transactions() -> None:
    snapshot = _valuation_snapshot(competing_teams=1)
    state = _state(snapshot)
    entries = state.roster_entries + (RosterEntry(-300, 1, 16, 1),)
    availability = tuple(
        replace(item, status=AcquisitionAvailability.ROSTERED)
        if item.player_id == -300 else item for item in state.availability
    )
    result = value_hypothetical_roster(
        snapshot, state, 1, roster_entries=entries, availability=availability
    )
    assert result.weeks[0].mandatory_vacancy_count == 0
    assert state.ledger == ()
    assert all(item.player_id != -300 for item in state.roster_entries)


def test_seeded_distinct_dst_pools_match_hand_exhaustive_ordering() -> None:
    rng = random.Random(2303)
    for competing_teams in range(3):
        for _ in range(8):
            values = tuple(sorted((rng.uniform(1, 20) for _ in range(3)), reverse=True))
            snapshot = _valuation_snapshot(competing_teams=competing_teams, pool_values=values)
            result = value_roster(snapshot, _state(snapshot), 1)
            expected = values[competing_teams]
            assert result.weeks[0].replacement_assignments[0].effective_projection == pytest.approx(expected)
            assigned = result.weeks[0].opponent_replacement_assignments + result.weeks[0].replacement_assignments
            assert len({item.player_id for item in assigned}) == len(assigned)


def test_representative_pool_benchmark_and_no_network(monkeypatch) -> None:
    values = tuple(float(200 - index) / 10 for index in range(120))
    snapshot = _valuation_snapshot(competing_teams=2, pool_values=values)
    state = _state(snapshot)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("V(R) must not access ESPN")

    monkeypatch.setattr("fantasy_football.espn_adapter.fetch_and_translate", forbidden)
    started = time.perf_counter()
    first = value_roster(snapshot, state, 1)
    elapsed = time.perf_counter() - started
    second = value_roster(snapshot, state, 1)
    assert second == first
    assert elapsed < 5.0


def test_waiver_players_require_explicit_current_waiver_context() -> None:
    snapshot = _valuation_snapshot(pool_values=())
    player = next(item for item in snapshot.players if item.player_id == 4)
    snapshot = replace(
        snapshot,
        players=tuple(
            replace(item, default_position_id=16, eligible_lineup_slot_ids=(16, 20), acquisition_status="WAIVERS")
            if item.player_id == player.player_id else item for item in snapshot.players
        ),
        player_weeks=tuple(
            replace(item, raw_projection=5.5, projection_class=ProjectionClass.PRESENT,
                    effective_projection=5.5, effective_source=ProjectionSource.ESPN)
            if item.player_id == 4 else item for item in snapshot.player_weeks
        ),
    )
    state = _state(snapshot)
    future = value_roster(snapshot, state, 1)
    imminent = value_roster(
        snapshot, state, 1, access_context=ReplacementAccessContext.CURRENT_WAIVER
    )
    assert future.weeks[0].remaining_vacancy_count == 1
    assert imminent.weeks[0].remaining_vacancy_count == 0
    assert imminent.weeks[1].remaining_vacancy_count == 1
