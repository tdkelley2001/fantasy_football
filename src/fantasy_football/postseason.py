"""Deterministic M2.4 championship and consolation bracket mechanics."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum

from fantasy_football.canonical.model import (
    InterpretationStatus,
    LeagueSnapshot,
    MatchupEntryStatus,
    MatchupPhase,
    RosterEntry,
)
from fantasy_football.canonical.validation import validate_snapshot
from fantasy_football.lineup_optimizer import OptimizedLineup
from fantasy_football.weekly_engine import (
    ModeledStanding,
    RealizedPlayerScore,
    _score_index,
    _validate_lineups,
    rank_standings,
)


class PostseasonError(ValueError):
    """Raised when postseason inputs are invalid or required rules are unresolved."""


class BracketType(StrEnum):
    CHAMPIONSHIP = "championship"
    CONSOLATION = "consolation"
    PLACEMENT = "placement"


class MatchupStatus(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    BYE = "bye"


@dataclass(frozen=True, slots=True, order=True)
class PostseasonSeed:
    original_seed: int
    team_id: int
    championship_qualifier: bool


@dataclass(frozen=True, slots=True, order=True)
class WeeklyTeamScore:
    scoring_week: int
    team_id: int
    points: float


@dataclass(frozen=True, slots=True)
class PostseasonMatchup:
    matchup_id: str
    bracket_type: BracketType
    round_number: int
    matchup_period_id: int
    scoring_weeks: tuple[int, ...]
    home_team_id: int
    away_team_id: int | None
    purpose: str
    weekly_scores: tuple[WeeklyTeamScore, ...] = ()
    home_total: float | None = None
    away_total: float | None = None
    winner_team_id: int | None = None
    loser_team_id: int | None = None
    tiebreak_applied: str | None = None
    status: MatchupStatus = MatchupStatus.SCHEDULED


@dataclass(frozen=True, slots=True, order=True)
class ConsolationLadderPosition:
    team_id: int
    original_seed: int
    current_position: int
    active: bool = True


@dataclass(frozen=True, slots=True, order=True)
class FinalPlacement:
    place: int
    team_id: int
    bracket_type: BracketType


@dataclass(frozen=True, slots=True)
class LadderTransition:
    round_number: int
    upper_position: int
    lower_position: int
    winner_position: int
    loser_position: int


@dataclass(frozen=True, slots=True)
class ConsolationLadderConfiguration:
    """Explicit later-round ladder mapping; official first-round pairing is implicit."""

    transitions: tuple[LadderTransition, ...]
    final_positions_by_ladder_position: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class PostseasonState:
    source_snapshot_id: str | None
    season: int
    seeds: tuple[PostseasonSeed, ...]
    championship_matchups: tuple[PostseasonMatchup, ...]
    consolation_matchups: tuple[PostseasonMatchup, ...]
    consolation_positions: tuple[ConsolationLadderPosition, ...]
    placements: tuple[FinalPlacement, ...]
    unresolved_capabilities: tuple[str, ...]
    consolation_configuration: ConsolationLadderConfiguration | None = None


def resolve_postseason_seeds(
    snapshot: LeagueSnapshot, standings: tuple[ModeledStanding, ...]
) -> tuple[PostseasonSeed, ...]:
    """Resolve seeds from modeled final standings, never snapshot seed fields."""

    validate_snapshot(snapshot)
    table = rank_standings(snapshot, standings)
    if table.unresolved_groups:
        groups = tuple(group.team_ids for group in table.unresolved_groups)
        raise PostseasonError(
            f"unique postseason seeding is unresolved for teams {groups}"
        )
    qualifier_count = snapshot.rules.championship.qualifier_count
    if not 0 < qualifier_count <= len(snapshot.teams):
        raise PostseasonError(f"invalid championship qualifier count {qualifier_count}")
    ordered = tuple(sorted(table.rows, key=lambda item: item.rank))
    return tuple(
        PostseasonSeed(index, item.team_id, index <= qualifier_count)
        for index, item in enumerate(ordered, start=1)
    )


def _periods(
    snapshot: LeagueSnapshot, rounds
) -> dict[int, tuple[int, tuple[int, ...]]]:
    periods = {item.matchup_period_id: item for item in snapshot.matchup_periods}
    result = {}
    previous_weeks: tuple[int, ...] = ()
    for item in sorted(rounds, key=lambda value: value.round_number):
        period = periods.get(item.matchup_period_id)
        if period is None or period.phase is not MatchupPhase.POSTSEASON:
            raise PostseasonError(
                f"postseason round {item.round_number} references invalid period {item.matchup_period_id}"
            )
        if not period.scoring_weeks:
            raise PostseasonError(
                f"postseason period {period.matchup_period_id} has no scoring weeks"
            )
        if previous_weeks and min(period.scoring_weeks) <= max(previous_weeks):
            raise PostseasonError(
                "postseason round scoring weeks must be strictly ordered"
            )
        result[item.round_number] = (period.matchup_period_id, period.scoring_weeks)
        previous_weeks = period.scoring_weeks
    return result


def _matchup(
    bracket: BracketType,
    round_number: int,
    period_id: int,
    weeks: tuple[int, ...],
    home: int,
    away: int | None,
    purpose: str,
) -> PostseasonMatchup:
    participants = f"{home}-{away}" if away is not None else f"{home}-bye"
    return PostseasonMatchup(
        f"{bracket.value}-r{round_number}-{purpose}-{participants}",
        bracket,
        round_number,
        period_id,
        weeks,
        home,
        away,
        purpose,
        status=MatchupStatus.BYE if away is None else MatchupStatus.SCHEDULED,
        winner_team_id=home if away is None else None,
    )


def _reconcile_first_round_schedule(
    snapshot: LeagueSnapshot,
    generated: tuple[PostseasonMatchup, ...],
    bracket: BracketType,
) -> None:
    """Reject a populated canonical first round that contradicts generated rules."""

    period_id = generated[0].matchup_period_id if generated else None
    observed = tuple(
        item
        for item in snapshot.fantasy_matchups
        if item.matchup_period_id == period_id
        and item.bracket_type == bracket.value
        and item.entry_status in (MatchupEntryStatus.SCHEDULED, MatchupEntryStatus.BYE)
    )
    if not observed:
        return

    def participants(home: int | None, away: int | None) -> tuple[int, ...]:
        return tuple(sorted(team_id for team_id in (home, away) if team_id is not None))

    expected = tuple(
        sorted(participants(item.home_team_id, item.away_team_id) for item in generated)
    )
    actual = tuple(
        sorted(participants(item.home_team_id, item.away_team_id) for item in observed)
    )
    if actual != expected:
        raise PostseasonError(
            f"canonical {bracket.value} first-round schedule {actual} conflicts with expected {expected}"
        )


def initialize_postseason(
    snapshot: LeagueSnapshot,
    standings: tuple[ModeledStanding, ...],
    *,
    consolation_configuration: ConsolationLadderConfiguration | None = None,
) -> PostseasonState:
    """Initialize the verified six-team championship and ESPN consolation first round."""

    seeds = resolve_postseason_seeds(snapshot, standings)
    championship = snapshot.rules.championship
    tie_rule = next(
        (
            item
            for item in snapshot.rules.interpretations
            if item.rule_id == championship.matchup_tie_rule_id
        ),
        None,
    )
    if (
        tie_rule is None
        or tie_rule.status is not InterpretationStatus.UNDERSTOOD
        or tie_rule.normalized_value != "higher_seed"
    ):
        raise PostseasonError(
            "postseason resolution requires an understood higher_seed matchup tie rule"
        )
    if championship.qualifier_count != 6 or championship.reseed is not False:
        raise PostseasonError(
            "supported championship structure requires six qualifiers and playoffReseed=false"
        )
    championship_periods = _periods(snapshot, championship.rounds)
    if tuple(championship_periods) != (1, 2, 3):
        raise PostseasonError(
            "supported six-team championship requires rounds 1, 2, and 3"
        )
    team_by_seed = {item.original_seed: item.team_id for item in seeds}
    period_id, weeks = championship_periods[1]
    championship_matchups = (
        _matchup(
            BracketType.CHAMPIONSHIP,
            1,
            period_id,
            weeks,
            team_by_seed[1],
            None,
            "seed-1-bye",
        ),
        _matchup(
            BracketType.CHAMPIONSHIP,
            1,
            period_id,
            weeks,
            team_by_seed[2],
            None,
            "seed-2-bye",
        ),
        _matchup(
            BracketType.CHAMPIONSHIP,
            1,
            period_id,
            weeks,
            team_by_seed[3],
            team_by_seed[6],
            "three-six",
        ),
        _matchup(
            BracketType.CHAMPIONSHIP,
            1,
            period_id,
            weeks,
            team_by_seed[4],
            team_by_seed[5],
            "four-five",
        ),
    )

    consolation_seeds = tuple(item for item in seeds if not item.championship_qualifier)
    consolation_rules = snapshot.rules.consolation
    if consolation_rules.enabled is False:
        consolation_matchups: tuple[PostseasonMatchup, ...] = ()
        positions: tuple[ConsolationLadderPosition, ...] = ()
        unresolved = ()
    else:
        if consolation_rules.participant_count not in (None, len(consolation_seeds)):
            raise PostseasonError(
                "configured consolation participant count conflicts with non-qualifiers"
            )
        consolation_periods = _periods(snapshot, consolation_rules.rounds)
        if 1 not in consolation_periods:
            raise PostseasonError(
                "consolation ladder requires a configured first-round period"
            )
        consolation_matchups_list = []
        period_id, weeks = consolation_periods[1]
        index = 0
        while index + 1 < len(consolation_seeds):
            upper, lower = consolation_seeds[index : index + 2]
            consolation_matchups_list.append(
                _matchup(
                    BracketType.CONSOLATION,
                    1,
                    period_id,
                    weeks,
                    upper.team_id,
                    lower.team_id,
                    f"positions-{upper.original_seed}-{lower.original_seed}",
                )
            )
            index += 2
        if index < len(consolation_seeds):
            bye = consolation_seeds[index]
            consolation_matchups_list.append(
                _matchup(
                    BracketType.CONSOLATION,
                    1,
                    period_id,
                    weeks,
                    bye.team_id,
                    None,
                    f"lowest-seed-{bye.original_seed}-bye",
                )
            )
        consolation_matchups = tuple(consolation_matchups_list)
        positions = tuple(
            ConsolationLadderPosition(
                item.team_id, item.original_seed, item.original_seed
            )
            for item in consolation_seeds
        )
        unresolved = (
            ()
            if consolation_configuration is not None
            else ("consolation_later_round_transition_mapping",)
        )
    _reconcile_first_round_schedule(
        snapshot, championship_matchups, BracketType.CHAMPIONSHIP
    )
    _reconcile_first_round_schedule(
        snapshot, consolation_matchups, BracketType.CONSOLATION
    )
    return PostseasonState(
        snapshot.snapshot_id,
        snapshot.season,
        seeds,
        championship_matchups,
        consolation_matchups,
        positions,
        (),
        unresolved,
        consolation_configuration,
    )


def _seed_map(state: PostseasonState) -> dict[int, int]:
    return {item.team_id: item.original_seed for item in state.seeds}


def _finish_matchup(
    state: PostseasonState, matchup: PostseasonMatchup
) -> PostseasonMatchup:
    if matchup.away_team_id is None:
        return matchup
    home_scores = tuple(
        item.points
        for item in matchup.weekly_scores
        if item.team_id == matchup.home_team_id
    )
    away_scores = tuple(
        item.points
        for item in matchup.weekly_scores
        if item.team_id == matchup.away_team_id
    )
    if len(home_scores) != len(matchup.scoring_weeks) or len(away_scores) != len(
        matchup.scoring_weeks
    ):
        return replace(matchup, status=MatchupStatus.IN_PROGRESS)
    home_total = math.fsum(home_scores)
    away_total = math.fsum(away_scores)
    tiebreak = None
    if home_total > away_total:
        winner, loser = matchup.home_team_id, matchup.away_team_id
    elif away_total > home_total:
        winner, loser = matchup.away_team_id, matchup.home_team_id
    else:
        seeds = _seed_map(state)
        winner = min(
            (matchup.home_team_id, matchup.away_team_id), key=seeds.__getitem__
        )
        loser = (
            matchup.away_team_id
            if winner == matchup.home_team_id
            else matchup.home_team_id
        )
        tiebreak = "higher_original_seed"
    return replace(
        matchup,
        home_total=home_total,
        away_total=away_total,
        winner_team_id=winner,
        loser_team_id=loser,
        tiebreak_applied=tiebreak,
        status=MatchupStatus.COMPLETE,
    )


def _advance_championship(
    snapshot: LeagueSnapshot, state: PostseasonState
) -> PostseasonState:
    matchups = list(state.championship_matchups)
    periods = _periods(snapshot, snapshot.rules.championship.rounds)
    by_round = {
        number: tuple(item for item in matchups if item.round_number == number)
        for number in (1, 2, 3)
    }
    if not by_round[2] and all(
        item.status in {MatchupStatus.COMPLETE, MatchupStatus.BYE}
        for item in by_round[1]
    ):
        three_six = next(item for item in by_round[1] if item.purpose == "three-six")
        four_five = next(item for item in by_round[1] if item.purpose == "four-five")
        seed_one = next(item.team_id for item in state.seeds if item.original_seed == 1)
        seed_two = next(item.team_id for item in state.seeds if item.original_seed == 2)
        period_id, weeks = periods[2]
        matchups.extend(
            (
                _matchup(
                    BracketType.CHAMPIONSHIP,
                    2,
                    period_id,
                    weeks,
                    seed_one,
                    four_five.winner_team_id,
                    "semifinal-one",
                ),
                _matchup(
                    BracketType.CHAMPIONSHIP,
                    2,
                    period_id,
                    weeks,
                    seed_two,
                    three_six.winner_team_id,
                    "semifinal-two",
                ),
            )
        )
    by_round_two = tuple(item for item in matchups if item.round_number == 2)
    if (
        by_round_two
        and not any(item.round_number == 3 for item in matchups)
        and all(item.status is MatchupStatus.COMPLETE for item in by_round_two)
    ):
        semifinal_one = next(
            item for item in by_round_two if item.purpose == "semifinal-one"
        )
        semifinal_two = next(
            item for item in by_round_two if item.purpose == "semifinal-two"
        )
        three_six = next(item for item in matchups if item.purpose == "three-six")
        four_five = next(item for item in matchups if item.purpose == "four-five")
        period_id, weeks = periods[3]
        matchups.extend(
            (
                _matchup(
                    BracketType.CHAMPIONSHIP,
                    3,
                    period_id,
                    weeks,
                    semifinal_one.winner_team_id,
                    semifinal_two.winner_team_id,
                    "championship-final",
                ),
                _matchup(
                    BracketType.PLACEMENT,
                    3,
                    period_id,
                    weeks,
                    semifinal_one.loser_team_id,
                    semifinal_two.loser_team_id,
                    "third-place",
                ),
                _matchup(
                    BracketType.PLACEMENT,
                    3,
                    period_id,
                    weeks,
                    three_six.loser_team_id,
                    four_five.loser_team_id,
                    "fifth-place",
                ),
            )
        )
    final_round = tuple(item for item in matchups if item.round_number == 3)
    placements = list(state.placements)
    if (
        final_round
        and all(item.status is MatchupStatus.COMPLETE for item in final_round)
        and not placements
    ):
        purpose_places = {
            "championship-final": (1, 2),
            "third-place": (3, 4),
            "fifth-place": (5, 6),
        }
        for item in final_round:
            winner_place, loser_place = purpose_places[item.purpose]
            placements.extend(
                (
                    FinalPlacement(
                        winner_place, item.winner_team_id, BracketType.CHAMPIONSHIP
                    ),
                    FinalPlacement(
                        loser_place, item.loser_team_id, BracketType.CHAMPIONSHIP
                    ),
                )
            )
    return replace(
        state,
        championship_matchups=tuple(sorted(matchups, key=lambda item: item.matchup_id)),
        placements=tuple(sorted(placements)),
    )


def _advance_consolation(
    snapshot: LeagueSnapshot, state: PostseasonState
) -> PostseasonState:
    """Apply only an explicit validated ladder transition configuration."""

    config = state.consolation_configuration
    if config is None or not state.consolation_matchups:
        return state
    if any(item.bracket_type is BracketType.CONSOLATION for item in state.placements):
        return state
    matchups = list(state.consolation_matchups)
    positions = {item.team_id: item for item in state.consolation_positions}
    configured_rounds = {item.round_number for item in config.transitions}
    completed_rounds = tuple(
        round_number
        for round_number in sorted({item.round_number for item in matchups})
        if all(
            item.status in {MatchupStatus.COMPLETE, MatchupStatus.BYE}
            for item in matchups
            if item.round_number == round_number
        )
    )
    for round_number in completed_rounds:
        if any(item.round_number == round_number + 1 for item in matchups):
            continue
        round_matchups = tuple(
            item for item in matchups if item.round_number == round_number
        )
        transitions = {
            (item.upper_position, item.lower_position): item
            for item in config.transitions
            if item.round_number == round_number
        }
        if round_number not in configured_rounds:
            continue
        for matchup in round_matchups:
            if matchup.away_team_id is None:
                continue
            home_position = positions[matchup.home_team_id].current_position
            away_position = positions[matchup.away_team_id].current_position
            key = tuple(sorted((home_position, away_position)))
            transition = transitions.get(key)
            if transition is None:
                raise PostseasonError(
                    f"consolation round {round_number} lacks transition for positions {key}"
                )
            upper, lower = key
            min_position = min(
                item.original_seed for item in state.consolation_positions
            )
            max_position = max(
                item.original_seed for item in state.consolation_positions
            )
            if not (
                min_position <= transition.winner_position <= upper
                and lower <= transition.loser_position <= max_position
            ):
                raise PostseasonError(
                    f"consolation transition {transition} violates upward/downward boundaries"
                )
            positions[matchup.winner_team_id] = replace(
                positions[matchup.winner_team_id],
                current_position=transition.winner_position,
            )
            positions[matchup.loser_team_id] = replace(
                positions[matchup.loser_team_id],
                current_position=transition.loser_position,
            )
        current_values = tuple(item.current_position for item in positions.values())
        if len(current_values) != len(set(current_values)):
            raise PostseasonError(
                f"consolation round {round_number} transitions produce duplicate ladder positions"
            )
        next_round = round_number + 1
        if not any(item.round_number == next_round for item in matchups):
            rounds = _periods(snapshot, snapshot.rules.consolation.rounds)
            if next_round in rounds:
                period_id, weeks = rounds[next_round]
                ordered = tuple(
                    sorted(positions.values(), key=lambda item: item.current_position)
                )
                for index in range(0, len(ordered) - 1, 2):
                    upper_entry, lower_entry = ordered[index : index + 2]
                    matchups.append(
                        _matchup(
                            BracketType.CONSOLATION,
                            next_round,
                            period_id,
                            weeks,
                            upper_entry.team_id,
                            lower_entry.team_id,
                            f"positions-{upper_entry.current_position}-{lower_entry.current_position}",
                        )
                    )
                if len(ordered) % 2:
                    bye = ordered[-1]
                    matchups.append(
                        _matchup(
                            BracketType.CONSOLATION,
                            next_round,
                            period_id,
                            weeks,
                            bye.team_id,
                            None,
                            f"lowest-position-{bye.current_position}-bye",
                        )
                    )

    last_round = max(item.round_number for item in matchups)
    last_complete = all(
        item.status in {MatchupStatus.COMPLETE, MatchupStatus.BYE}
        for item in matchups
        if item.round_number == last_round
    )
    placements = list(state.placements)
    if last_complete and last_round == len(snapshot.rules.consolation.rounds):
        place_by_position = dict(config.final_positions_by_ladder_position)
        expected_positions = {item.current_position for item in positions.values()}
        if set(place_by_position) != expected_positions:
            raise PostseasonError(
                "consolation final placement map must cover every final ladder position"
            )
        placements.extend(
            FinalPlacement(
                place_by_position[item.current_position],
                item.team_id,
                BracketType.CONSOLATION,
            )
            for item in positions.values()
        )
    return replace(
        state,
        consolation_matchups=tuple(sorted(matchups, key=lambda item: item.matchup_id)),
        consolation_positions=tuple(sorted(positions.values())),
        placements=tuple(sorted(placements)),
        unresolved_capabilities=(),
    )


def apply_postseason_team_scores(
    snapshot: LeagueSnapshot,
    state: PostseasonState,
    scoring_week: int,
    team_scores: tuple[WeeklyTeamScore, ...],
) -> PostseasonState:
    """Record one week's audited team totals and advance only complete periods."""

    validate_snapshot(snapshot)
    if not isinstance(team_scores, tuple):
        raise PostseasonError("postseason team scores must be an immutable tuple")
    score_map = {}
    for score in team_scores:
        if score.scoring_week != scoring_week:
            raise PostseasonError("postseason team score week mismatch")
        if score.team_id in score_map:
            raise PostseasonError(
                f"duplicate postseason team score for team {score.team_id}"
            )
        if (
            isinstance(score.points, bool)
            or not isinstance(score.points, (int, float))
            or not math.isfinite(score.points)
        ):
            raise PostseasonError(
                f"team {score.team_id} postseason score must be finite"
            )
        score_map[score.team_id] = float(score.points)
    active = tuple(
        item
        for item in state.championship_matchups + state.consolation_matchups
        if scoring_week in item.scoring_weeks
        and item.status not in {MatchupStatus.COMPLETE, MatchupStatus.BYE}
    )
    required = {
        team
        for item in active
        for team in (item.home_team_id, item.away_team_id)
        if team is not None
    }
    if set(score_map) != required:
        raise PostseasonError(
            f"postseason week {scoring_week} requires team scores {sorted(required)}, observed {sorted(score_map)}"
        )

    def update(matchup: PostseasonMatchup) -> PostseasonMatchup:
        if matchup not in active:
            return matchup
        additions = tuple(
            WeeklyTeamScore(scoring_week, team_id, score_map[team_id])
            for team_id in (matchup.home_team_id, matchup.away_team_id)
            if team_id is not None
        )
        if any(item.scoring_week == scoring_week for item in matchup.weekly_scores):
            raise PostseasonError(
                f"matchup {matchup.matchup_id} already has week {scoring_week}"
            )
        return _finish_matchup(
            state, replace(matchup, weekly_scores=matchup.weekly_scores + additions)
        )

    updated = replace(
        state,
        championship_matchups=tuple(
            update(item) for item in state.championship_matchups
        ),
        consolation_matchups=tuple(update(item) for item in state.consolation_matchups),
    )
    return _advance_consolation(snapshot, _advance_championship(snapshot, updated))


def score_frozen_postseason_week(
    snapshot: LeagueSnapshot,
    state: PostseasonState,
    scoring_week: int,
    lineups: tuple[OptimizedLineup, ...],
    realized_scores: tuple[RealizedPlayerScore, ...],
    *,
    roster_entries: tuple[RosterEntry, ...] | None = None,
) -> PostseasonState:
    """Score legal frozen lineups, then apply their totals to the active bracket."""

    active = tuple(
        item
        for item in state.championship_matchups + state.consolation_matchups
        if scoring_week in item.scoring_weeks
        and item.status not in {MatchupStatus.COMPLETE, MatchupStatus.BYE}
    )
    teams = {
        team
        for item in active
        for team in (item.home_team_id, item.away_team_id)
        if team is not None
    }
    modeled_roster = (
        snapshot.roster_entries if roster_entries is None else roster_entries
    )
    frozen = _validate_lineups(snapshot, scoring_week, lineups, teams, modeled_roster)
    scores = _score_index(snapshot, scoring_week, realized_scores)
    totals = []
    for team_id in sorted(teams):
        assignments = frozen[team_id].assignments
        missing = tuple(
            item.player_id for item in assignments if item.player_id not in scores
        )
        if missing:
            raise PostseasonError(
                f"team {team_id} missing realized scores for starters {missing}"
            )
        totals.append(
            WeeklyTeamScore(
                scoring_week,
                team_id,
                math.fsum(scores[item.player_id] for item in assignments),
            )
        )
    return apply_postseason_team_scores(snapshot, state, scoring_week, tuple(totals))


def final_positions_complete(state: PostseasonState, team_count: int) -> bool:
    """Return true only when every league team has one explicit final placement."""

    return (
        not state.unresolved_capabilities
        and len(state.placements) == team_count
        and {item.place for item in state.placements} == set(range(1, team_count + 1))
        and len({item.team_id for item in state.placements}) == team_count
    )
