from __future__ import annotations

from dataclasses import replace

import pytest

from fantasy_football.canonical.model import (
    LineupSlotNamespace,
    LineupSlotRule,
    MatchupEntryStatus,
    Player,
    PlayerWeek,
    PositionLimit,
    ProjectionClass,
    ProjectionSource,
    RosterEntry,
    SlotKind,
)
from fantasy_football.canonical.validation import CanonicalValidationError
from fantasy_football.evolving_state import IRPolicy
from fantasy_football.season_simulator import (
    DeterministicScoreScenario,
    SeasonCompletionStatus,
    SeasonSimulationError,
    simulate_deterministic_season,
)
from fantasy_football.weekly_engine import RealizedPlayerScore
from fantasy_football.weekly_transactions import (
    WaiverBoundaryPolicy,
    WeeklyTransactionError,
    WeeklyTransactionPolicy,
)
from tests.test_postseason import _snapshot as _postseason_snapshot
from tests.test_weekly_engine import _supported_snapshot


def _snapshot():
    snapshot = _supported_snapshot(two_regular_weeks=True)
    rules = replace(
        snapshot.rules,
        consolation=replace(snapshot.rules.consolation, enabled=True),
    )
    return replace(snapshot, rules=rules)


def _scenario(snapshot, *, omit: tuple[int, int] | None = None):
    values = {
        15: {-101: 0.0, 1: 20.0, 2: 10.0, 3: 8.0, 4: 9.0},
        16: {-101: 0.0, 1: 5.0, 2: 15.0, 3: 20.0, 4: -1.0},
        17: {-101: 0.0, 1: 3.0, 2: 30.0, 3: 0.0, 4: -2.0},
    }
    return DeterministicScoreScenario(
        "hand-calculated-season-v1",
        tuple(
            RealizedPlayerScore(player_id, snapshot.season, week, points)
            for week, players in reversed(tuple(values.items()))
            for player_id, points in reversed(tuple(players.items()))
            if (player_id, week) != omit
        ),
    )


def _policy(*, authorized: bool = True):
    return WeeklyTransactionPolicy(
        waiver_boundary=(
            WaiverBoundaryPolicy.MODELED_WEEKLY_V1
            if authorized
            else WaiverBoundaryPolicy.UNRESOLVED
        )
    )


def _run(snapshot=None, scenario=None, *, policy=None):
    snapshot = _snapshot() if snapshot is None else snapshot
    scenario = _scenario(snapshot) if scenario is None else scenario
    return simulate_deterministic_season(
        snapshot,
        scenario,
        ir_policy=IRPolicy.PROJECTION_BASED,
        transaction_policy=_policy() if policy is None else policy,
    )


def _fourteen_team_postseason_snapshot():
    snapshot = _postseason_snapshot()
    source_id = snapshot.sources[0].source_id
    players = tuple(
        Player(
            100 + team.team_id,
            f"Player {team.team_id}",
            1,
            (0,),
            1,
            "ACTIVE",
            "ONTEAM",
            False,
            source_id,
        )
        for team in snapshot.teams
    )
    rosters = tuple(
        RosterEntry(100 + team.team_id, team.team_id, 0, team.team_id)
        for team in snapshot.teams
    )
    player_weeks = tuple(
        PlayerWeek(
            player.player_id,
            snapshot.season,
            week,
            10.0,
            ProjectionClass.PRESENT,
            10.0,
            ProjectionSource.ESPN,
            source_id,
        )
        for player in players
        for week in range(
            snapshot.first_simulation_week, snapshot.final_simulation_week + 1
        )
    )
    rules = replace(
        snapshot.rules,
        lineup_slots=(LineupSlotRule(0, 1, SlotKind.STARTER, "QB"),),
        position_limits=(PositionLimit(1, 1),),
    )
    return replace(
        snapshot,
        rules=rules,
        lineup_slot_namespace=LineupSlotNamespace((0,)),
        teams=tuple(
            replace(
                team,
                wins=team.team_id,
                losses=len(snapshot.teams) - team.team_id,
                points_for=float(team.team_id * 100),
                points_against=float((len(snapshot.teams) + 1 - team.team_id) * 100),
            )
            for team in snapshot.teams
        ),
        players=players,
        roster_entries=rosters,
        player_weeks=tuple(
            sorted(
                player_weeks,
                key=lambda item: (item.player_id, item.season, item.scoring_week),
            )
        ),
    )


def test_complete_hand_calculated_path_reconciles_every_stage() -> None:
    snapshot = _snapshot()
    result = _run(snapshot)

    assert result.status is SeasonCompletionStatus.COMPLETE
    assert tuple(item.scoring_week for item in result.weeks) == (15, 16, 17)
    assert tuple(
        (item.team_id, item.wins, item.losses, item.ties)
        for item in result.final_regular_standings
    ) == ((1, 9, 6, 0), (2, 8, 7, 0), (3, 7, 8, 0), (4, 6, 9, 0))
    assert tuple(
        (item.team_id, item.postseason_seed, item.final_placement)
        for item in result.team_records
    ) == ((1, 1, 2), (2, 2, 1), (3, 3, 3), (4, 4, 4))
    assert result.final_postseason_state is not None
    assert tuple(
        (item.place, item.team_id) for item in result.final_postseason_state.placements
    ) == ((1, 2), (2, 1), (3, 3), (4, 4))
    assert result.weeks[2].frozen_team_weeks[2].realized_points == 0.0
    assert result.weeks[2].frozen_team_weeks[3].realized_points == -2.0


def test_fourteen_team_six_qualifier_path_produces_exact_complete_placements() -> None:
    snapshot = _fourteen_team_postseason_snapshot()
    scenario = DeterministicScoreScenario(
        "fourteen-team-structural-regression",
        tuple(
            RealizedPlayerScore(
                player.player_id,
                snapshot.season,
                week,
                float(player.player_id),
            )
            for week in range(
                snapshot.first_simulation_week, snapshot.final_simulation_week + 1
            )
            for player in reversed(snapshot.players)
        ),
    )
    result = _run(snapshot, scenario)
    assert result.status is SeasonCompletionStatus.COMPLETE
    assert len(result.team_records) == 14
    assert tuple(sorted(item.final_placement for item in result.team_records)) == tuple(
        range(1, 15)
    )
    postseason = result.final_postseason_state
    assert postseason is not None
    placements = {item.team_id: item.place for item in postseason.placements}
    final_round = max(item.round_number for item in postseason.consolation_matchups)
    final_nodes = {
        item.node_id: item.position
        for item in postseason.consolation_graph.nodes
        if item.round_number == final_round
    }
    for matchup in postseason.consolation_matchups:
        if matchup.round_number != final_round:
            continue
        position = final_nodes[matchup.purpose]
        assert placements[matchup.winner_team_id] == 7 + position * 2
        assert placements[matchup.loser_team_id] == 8 + position * 2


def test_multiweek_championship_lead_can_reverse_without_early_champion() -> None:
    snapshot = _fourteen_team_postseason_snapshot()
    score_values = {
        (player.player_id, week): float(player.player_id)
        for player in snapshot.players
        for week in range(
            snapshot.first_simulation_week, snapshot.final_simulation_week + 1
        )
    }
    score_values[(114, 17)] = 100.0
    score_values[(113, 17)] = 0.0
    score_values[(114, 18)] = 0.0
    score_values[(113, 18)] = 200.0
    scenario = DeterministicScoreScenario(
        "multiweek-final-reversal",
        tuple(
            RealizedPlayerScore(player_id, snapshot.season, week, points)
            for (player_id, week), points in reversed(tuple(score_values.items()))
        ),
    )
    result = _run(snapshot, scenario)
    after_week_17 = next(item for item in result.weeks if item.scoring_week == 17)
    assert after_week_17.postseason_state is not None
    assert not any(
        item.place == 1 for item in after_week_17.postseason_state.placements
    )
    assert result.status is SeasonCompletionStatus.COMPLETE
    champion = next(item for item in result.team_records if item.final_placement == 1)
    assert champion.team_id == 13


def test_standings_totals_equal_initial_plus_modeled_regular_scores() -> None:
    result = _run()
    initial = {item.team_id: item for item in result.initial_standings}
    regular_scores = {team_id: [] for team_id in initial}
    for week in result.weeks:
        if week.regular_transition is None:
            continue
        for score in week.regular_transition.team_scores:
            regular_scores[score.team_id].append(score.total_realized_points)
    for final in result.final_regular_standings:
        assert final.points_for == pytest.approx(
            initial[final.team_id].points_for + sum(regular_scores[final.team_id])
        )


def test_essential_free_agent_acquisition_changes_frozen_lineup_and_matchup() -> None:
    snapshot = _snapshot()
    source_id = snapshot.sources[0].source_id
    defense = Player(
        30,
        "Essential defense",
        16,
        (16,),
        1,
        "ACTIVE",
        "FREEAGENT",
        False,
        source_id,
    )
    defense_weeks = tuple(
        PlayerWeek(
            30,
            snapshot.season,
            week,
            12.0,
            ProjectionClass.PRESENT,
            12.0,
            ProjectionSource.ESPN,
            source_id,
        )
        for week in range(
            snapshot.first_simulation_week, snapshot.final_simulation_week + 1
        )
    )
    snapshot = replace(
        snapshot,
        players=tuple(
            sorted(snapshot.players + (defense,), key=lambda item: item.player_id)
        ),
        player_weeks=tuple(
            sorted(
                snapshot.player_weeks + defense_weeks,
                key=lambda item: (item.player_id, item.season, item.scoring_week),
            )
        ),
        lineup_slot_namespace=replace(
            snapshot.lineup_slot_namespace,
            observed_slot_ids=tuple(
                sorted(set(snapshot.lineup_slot_namespace.observed_slot_ids) | {16})
            ),
        ),
    )
    base = _scenario(snapshot)
    scores = tuple(
        replace(item, points=1.0)
        if (item.player_id, item.scoring_week) == (4, 15)
        else item
        for item in base.scores
    ) + tuple(
        RealizedPlayerScore(30, snapshot.season, week, 50.0)
        for week in range(
            snapshot.first_simulation_week, snapshot.final_simulation_week + 1
        )
    )
    result = _run(snapshot, replace(base, scores=scores))
    first = result.weeks[0]
    acquisition = next(
        item
        for item in first.transaction_result.acquisitions
        if item.acquired_player_id == 30
    )
    assert acquisition.team_id == 4
    assert first.transaction_result.valuation_seconds == 0.0
    team_four = next(item for item in first.frozen_team_weeks if item.team_id == 4)
    assert {item.player_id for item in team_four.lineup.assignments} == {4, 30}
    assert team_four.realized_points == 51.0
    matchup = next(
        item
        for item in first.regular_transition.matchup_results
        if 4 in (item.home_team_id, item.away_team_id)
    )
    assert matchup.away_team_id == 4
    assert matchup.away_score == 51.0
    assert any(
        item.player_id == 30 and item.team_id == 4
        for item in result.final_evolving_state.roster_entries
    )


def test_replay_is_deterministic_and_inputs_are_immutable() -> None:
    snapshot = _snapshot()
    scenario = _scenario(snapshot)
    snapshot_before = snapshot
    scenario_before = scenario
    first = _run(snapshot, scenario)
    reordered = replace(scenario, scores=tuple(reversed(scenario.scores)))
    second = _run(snapshot, reordered)
    assert first == second
    assert snapshot == snapshot_before
    assert scenario == scenario_before


def test_complete_path_performs_no_espn_network_access(monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("deterministic season simulation must not access ESPN")

    monkeypatch.setattr("fantasy_football.espn_adapter.fetch_and_translate", forbidden)
    assert _run().status is SeasonCompletionStatus.COMPLETE


def test_only_materially_required_starter_scores_are_required() -> None:
    snapshot = _snapshot()
    extra_player = replace(
        next(item for item in snapshot.players if item.player_id == 3),
        player_id=30,
        display_name="Unused free agent",
        eligible_lineup_slot_ids=(25,),
        acquisition_status="FREEAGENT",
    )
    extra_weeks = tuple(
        replace(item, player_id=30)
        for item in snapshot.player_weeks
        if item.player_id == 3
    )
    snapshot_with_unused = replace(
        snapshot,
        players=tuple(
            sorted(snapshot.players + (extra_player,), key=lambda item: item.player_id)
        ),
        player_weeks=tuple(
            sorted(
                snapshot.player_weeks + extra_weeks,
                key=lambda item: (item.player_id, item.season, item.scoring_week),
            )
        ),
    )
    assert (
        _run(snapshot_with_unused, _scenario(snapshot_with_unused)).status
        is SeasonCompletionStatus.COMPLETE
    )
    required_missing = _scenario(snapshot, omit=(2, 17))
    with pytest.raises(SeasonSimulationError, match="lack realized scores"):
        _run(snapshot, required_missing)


def test_disabled_consolation_returns_explicit_partial_ranking() -> None:
    snapshot = _snapshot()
    rules = replace(
        snapshot.rules,
        consolation=replace(snapshot.rules.consolation, enabled=False),
    )
    snapshot = replace(snapshot, rules=rules)
    result = _run(snapshot, _scenario(snapshot))
    assert result.status is SeasonCompletionStatus.INCOMPLETE
    assert result.unresolved_capabilities == ("complete_league_placements_unavailable",)
    assert tuple(
        (item.team_id, item.final_placement) for item in result.team_records
    ) == ((1, 2), (2, 1), (3, None), (4, None))


def test_unresolved_essential_waiver_decision_returns_no_false_complete_path() -> None:
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        players=tuple(
            replace(item, acquisition_status="WAIVERS") if item.player_id == 4 else item
            for item in snapshot.players
        ),
        roster_entries=tuple(
            item for item in snapshot.roster_entries if item.player_id != 4
        ),
    )
    result = _run(snapshot, _scenario(snapshot), policy=_policy(authorized=False))
    assert result.status is SeasonCompletionStatus.INCOMPLETE
    assert result.weeks == ()
    assert "transaction_authorization_unresolved" in result.unresolved_capabilities[0]
    assert not any(
        item.player_id == 4 for item in result.final_evolving_state.roster_entries
    )


def test_preflight_rejects_partial_start_and_unsupported_acquisition_type() -> None:
    snapshot = _snapshot()
    partial = replace(
        snapshot,
        fantasy_matchups=tuple(
            replace(item, entry_status=MatchupEntryStatus.PARTIAL)
            if item.matchup_period_id == 1 and item.matchup_id == 1
            else item
            for item in snapshot.fantasy_matchups
        ),
    )
    with pytest.raises(CanonicalValidationError, match="regular-season matchup"):
        _run(partial, _scenario(partial))

    unsupported = replace(
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
    with pytest.raises(WeeklyTransactionError, match="WAIVERS_TRADITIONAL"):
        _run(unsupported, _scenario(unsupported))


def test_scenario_rejects_duplicate_unknown_and_nonfinite_scores() -> None:
    snapshot = _snapshot()
    scenario = _scenario(snapshot)
    duplicate = replace(scenario, scores=scenario.scores + (scenario.scores[0],))
    with pytest.raises(SeasonSimulationError, match="duplicate realized score"):
        _run(snapshot, duplicate)
    unknown = replace(
        scenario,
        scores=scenario.scores
        + (RealizedPlayerScore(99999, snapshot.season, 15, 1.0),),
    )
    with pytest.raises(SeasonSimulationError, match="unknown player"):
        _run(snapshot, unknown)
    nonfinite = replace(
        scenario,
        scores=(replace(scenario.scores[0], points=float("nan")),)
        + scenario.scores[1:],
    )
    with pytest.raises(SeasonSimulationError, match="must be finite"):
        _run(snapshot, nonfinite)
