from __future__ import annotations

from dataclasses import replace

import pytest

from fantasy_football.canonical.model import (
    ChampionshipRules,
    ConsolationRules,
    FantasyMatchup,
    FantasyTeam,
    MatchupEntryStatus,
    MatchupPeriod,
    MatchupPhase,
    PostseasonRound,
)
from fantasy_football.postseason import (
    ConsolationLadderConfiguration,
    LadderTransition,
    MatchupStatus,
    PostseasonError,
    WeeklyTeamScore,
    apply_postseason_team_scores,
    final_positions_complete,
    initialize_postseason,
    resolve_postseason_seeds,
)
from fantasy_football.weekly_engine import ModeledStanding
from tests.canonical_fixtures import canonical_snapshot


def _snapshot(*, team_count: int = 14, qualifier_count: int = 6):
    snapshot = canonical_snapshot()
    teams = tuple(
        FantasyTeam(
            team_id,
            f"Team {team_id}",
            0,
            0,
            0,
            0.0,
            0.0,
            team_count - team_id + 1,
            team_count - team_id + 1,
            team_id,
            None,
        )
        for team_id in range(1, team_count + 1)
    )
    periods = (
        MatchupPeriod(2, (15,), MatchupPhase.POSTSEASON),
        MatchupPeriod(3, (16,), MatchupPhase.POSTSEASON),
        MatchupPeriod(4, (17, 18), MatchupPhase.POSTSEASON),
    )
    rounds = tuple(PostseasonRound(index, index + 1) for index in range(1, 4))
    rules = replace(
        snapshot.rules,
        team_count=team_count,
        championship=ChampionshipRules(
            True, qualifier_count, False, rounds, "playoff_tie"
        ),
        consolation=ConsolationRules(
            True, team_count - qualifier_count, rounds, "consolation_structure"
        ),
    )
    return replace(
        snapshot,
        teams=teams,
        rules=rules,
        matchup_periods=periods,
        fantasy_matchups=(),
        player_weeks=snapshot.player_weeks
        + tuple(
            replace(record, scoring_week=18)
            for record in snapshot.player_weeks
            if record.scoring_week == 17
        ),
        nfl_games=snapshot.nfl_games
        + tuple(
            replace(game, game_id=f"{game.game_id}-w18", scoring_week=18)
            for game in snapshot.nfl_games
            if game.scoring_week == 17
        ),
        first_simulation_week=15,
        final_simulation_week=18,
    )


def _standings(snapshot):
    # Team 14 is seed 1, proving snapshot ranks do not control modeled seeding.
    return tuple(
        ModeledStanding(
            team.team_id,
            team.team_id,
            14 - team.team_id,
            0,
            float(team.team_id * 100),
            float((15 - team.team_id) * 100),
        )
        for team in snapshot.teams
    )


def _score_round(snapshot, state, round_number, winners):
    matchups = tuple(
        item
        for item in state.championship_matchups
        if item.round_number == round_number
        and item.status not in {MatchupStatus.BYE, MatchupStatus.COMPLETE}
    )
    for week in matchups[0].scoring_weeks:
        scores = []
        for matchup in matchups:
            winner = winners[matchup.purpose]
            for team_id in (matchup.home_team_id, matchup.away_team_id):
                scores.append(
                    WeeklyTeamScore(week, team_id, 100.0 if team_id == winner else 90.0)
                )
        # Consolation games share the week and therefore require totals too.
        for matchup in state.consolation_matchups:
            if week in matchup.scoring_weeks and matchup.status not in {
                MatchupStatus.BYE,
                MatchupStatus.COMPLETE,
            }:
                scores.extend(
                    (
                        WeeklyTeamScore(week, matchup.home_team_id, 80.0),
                        WeeklyTeamScore(week, matchup.away_team_id, 70.0),
                    )
                )
        state = apply_postseason_team_scores(snapshot, state, week, tuple(scores))
        matchups = tuple(
            item
            for item in state.championship_matchups
            if item.round_number == round_number
            and item.status not in {MatchupStatus.BYE, MatchupStatus.COMPLETE}
        )
    return state


def test_modeled_standings_create_six_seeds_and_fixed_championship_bracket() -> None:
    snapshot = _snapshot()
    seeds = resolve_postseason_seeds(snapshot, _standings(snapshot))
    assert tuple((item.original_seed, item.team_id) for item in seeds[:3]) == (
        (1, 14),
        (2, 13),
        (3, 12),
    )
    state = initialize_postseason(snapshot, _standings(snapshot))
    played = {
        tuple(sorted((item.home_team_id, item.away_team_id)))
        for item in state.championship_matchups
        if item.away_team_id is not None
    }
    byes = {
        next(
            seed.original_seed
            for seed in state.seeds
            if seed.team_id == item.home_team_id
        )
        for item in state.championship_matchups
        if item.status is MatchupStatus.BYE
    }
    assert played == {(9, 12), (10, 11)}
    assert byes == {1, 2}


def test_eight_team_consolation_uses_exact_adjacent_seed_pairings() -> None:
    state = initialize_postseason(_snapshot(), _standings(_snapshot()))
    seed_by_team = {item.team_id: item.original_seed for item in state.seeds}
    pairs = tuple(
        (seed_by_team[item.home_team_id], seed_by_team[item.away_team_id])
        for item in state.consolation_matchups
    )
    assert pairs == ((7, 8), (9, 10), (11, 12), (13, 14))
    assert state.unresolved_capabilities == (
        "consolation_later_round_transition_mapping",
    )
    assert all(item.active for item in state.consolation_positions)
    assert {item.original_seed for item in state.consolation_positions}.isdisjoint(
        {item.original_seed for item in state.seeds if item.championship_qualifier}
    )


def test_odd_consolation_field_gives_lowest_seed_bye() -> None:
    snapshot = _snapshot(team_count=13)
    state = initialize_postseason(snapshot, _standings(snapshot))
    bye = next(
        item for item in state.consolation_matchups if item.status is MatchupStatus.BYE
    )
    seed = next(
        item.original_seed for item in state.seeds if item.team_id == bye.home_team_id
    )
    assert seed == 13
    assert bye.winner_team_id == bye.home_team_id


def test_single_and_multiweek_progression_produces_places_one_through_six() -> None:
    snapshot = _snapshot()
    state = initialize_postseason(snapshot, _standings(snapshot))
    state = _score_round(snapshot, state, 1, {"three-six": 12, "four-five": 11})
    semifinals = {
        item.purpose: (item.home_team_id, item.away_team_id)
        for item in state.championship_matchups
        if item.round_number == 2
    }
    assert semifinals == {"semifinal-one": (14, 11), "semifinal-two": (13, 12)}
    state = _score_round(snapshot, state, 2, {"semifinal-one": 14, "semifinal-two": 12})
    state = _score_round(
        snapshot,
        state,
        3,
        {"championship-final": 14, "third-place": 13, "fifth-place": 10},
    )
    assert tuple((item.place, item.team_id) for item in state.placements) == (
        (1, 14),
        (2, 12),
        (3, 13),
        (4, 11),
        (5, 10),
        (6, 9),
    )
    assert final_positions_complete(state, 14) is False


def test_multiweek_matchup_does_not_advance_after_first_week() -> None:
    snapshot = _snapshot()
    state = initialize_postseason(snapshot, _standings(snapshot))
    state = _score_round(snapshot, state, 1, {"three-six": 12, "four-five": 11})
    state = _score_round(snapshot, state, 2, {"semifinal-one": 14, "semifinal-two": 12})
    final_matchups = tuple(
        item for item in state.championship_matchups if item.round_number == 3
    )
    scores = tuple(
        WeeklyTeamScore(17, team_id, float(100 - team_id))
        for matchup in final_matchups
        for team_id in (matchup.home_team_id, matchup.away_team_id)
    )
    state = apply_postseason_team_scores(snapshot, state, 17, scores)
    assert not state.placements
    assert all(
        item.status is MatchupStatus.IN_PROGRESS
        for item in state.championship_matchups
        if item.round_number == 3
    )


def test_exact_tie_uses_higher_original_seed_and_preserves_negative_scores() -> None:
    snapshot = _snapshot()
    state = initialize_postseason(snapshot, _standings(snapshot))
    active = tuple(
        item
        for item in state.championship_matchups + state.consolation_matchups
        if item.away_team_id is not None
    )
    scores = tuple(
        WeeklyTeamScore(15, team_id, -2.5)
        for matchup in active
        for team_id in (matchup.home_team_id, matchup.away_team_id)
    )
    state = apply_postseason_team_scores(snapshot, state, 15, scores)
    three_six = next(
        item for item in state.championship_matchups if item.purpose == "three-six"
    )
    assert three_six.home_total == -2.5
    assert three_six.winner_team_id == 12
    assert three_six.tiebreak_applied == "higher_original_seed"


def test_unresolved_deeper_seed_tie_fails_without_snapshot_order_fallback() -> None:
    snapshot = _snapshot()
    standings = list(_standings(snapshot))
    standings[0] = replace(
        standings[0],
        wins=standings[1].wins,
        losses=standings[1].losses,
        points_for=standings[1].points_for,
    )
    with pytest.raises(PostseasonError, match="seeding is unresolved"):
        initialize_postseason(snapshot, tuple(standings))


def test_reordered_inputs_are_deterministic_and_invalid_scores_fail() -> None:
    snapshot = _snapshot()
    first = initialize_postseason(snapshot, _standings(snapshot))
    second = initialize_postseason(snapshot, tuple(reversed(_standings(snapshot))))
    assert first == second
    with pytest.raises(PostseasonError, match="requires team scores"):
        apply_postseason_team_scores(snapshot, first, 15, ())
    with pytest.raises(PostseasonError, match="finite"):
        active_team = next(
            item.home_team_id
            for item in first.championship_matchups
            if item.away_team_id is not None
        )
        apply_postseason_team_scores(
            snapshot, first, 15, (WeeklyTeamScore(15, active_team, float("nan")),)
        )


def test_championship_and_consolation_never_cross() -> None:
    state = initialize_postseason(_snapshot(), _standings(_snapshot()))
    championship = {item.team_id for item in state.seeds if item.championship_qualifier}
    consolation = {item.team_id for item in state.consolation_positions}
    assert championship.isdisjoint(consolation)
    assert all(
        {item.home_team_id, item.away_team_id} <= consolation | {None}
        for item in state.consolation_matchups
    )


def test_explicit_full_ladder_configuration_produces_complete_positions() -> None:
    snapshot = _snapshot()
    transitions = tuple(
        LadderTransition(round_number, upper, upper + 1, upper, upper + 1)
        for round_number in (1, 2, 3)
        for upper in (7, 9, 11, 13)
    )
    config = ConsolationLadderConfiguration(
        transitions,
        tuple((position, position) for position in range(7, 15)),
    )
    state = initialize_postseason(
        snapshot, _standings(snapshot), consolation_configuration=config
    )
    state = _score_round(snapshot, state, 1, {"three-six": 12, "four-five": 11})
    assert {item.round_number for item in state.consolation_matchups} == {1, 2}
    assert all(item.active for item in state.consolation_positions)
    state = _score_round(snapshot, state, 2, {"semifinal-one": 14, "semifinal-two": 12})
    state = _score_round(
        snapshot,
        state,
        3,
        {"championship-final": 14, "third-place": 13, "fifth-place": 10},
    )
    assert final_positions_complete(state, 14)
    assert tuple(
        (item.place, item.team_id) for item in state.placements if item.place >= 7
    ) == tuple((position, 15 - position) for position in range(7, 15))
    assert all(item.active for item in state.consolation_positions)


def test_ladder_configuration_enforces_upper_and_lower_boundaries() -> None:
    snapshot = _snapshot()
    config = ConsolationLadderConfiguration(
        (
            LadderTransition(1, 7, 8, 6, 8),
            LadderTransition(1, 9, 10, 9, 10),
            LadderTransition(1, 11, 12, 11, 12),
            LadderTransition(1, 13, 14, 13, 14),
        ),
        tuple((position, position) for position in range(7, 15)),
    )
    state = initialize_postseason(
        snapshot, _standings(snapshot), consolation_configuration=config
    )
    active = tuple(
        item
        for item in state.championship_matchups + state.consolation_matchups
        if item.away_team_id is not None
    )
    scores = tuple(
        WeeklyTeamScore(15, team_id, 100.0 if team_id == matchup.home_team_id else 90.0)
        for matchup in active
        for team_id in (matchup.home_team_id, matchup.away_team_id)
    )
    with pytest.raises(PostseasonError, match="boundaries"):
        apply_postseason_team_scores(snapshot, state, 15, scores)


def test_postseason_requires_verified_higher_seed_tie_rule() -> None:
    snapshot = _snapshot()
    rules = replace(
        snapshot.rules,
        interpretations=tuple(
            replace(item, normalized_value="home_team")
            if item.rule_id == "playoff_tie"
            else item
            for item in snapshot.rules.interpretations
        ),
    )
    with pytest.raises(PostseasonError, match="understood higher_seed"):
        initialize_postseason(replace(snapshot, rules=rules), _standings(snapshot))


def test_canonical_first_round_schedule_must_reconcile() -> None:
    snapshot = _snapshot()
    conflicting = FantasyMatchup(
        901,
        2,
        14,
        13,
        "championship",
        MatchupEntryStatus.SCHEDULED,
    )
    with pytest.raises(PostseasonError, match="schedule.*conflicts"):
        initialize_postseason(
            replace(snapshot, fantasy_matchups=(conflicting,)), _standings(snapshot)
        )
