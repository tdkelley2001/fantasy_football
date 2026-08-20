from __future__ import annotations

from typing import Any

from .espn import as_int
from .league_data import (
    get_schedule_settings,
    matchup_period_scoring_weeks,
)


def playoff_round_scoring_weeks(
    settings_payload: dict[str, Any],
) -> list[list[int]]:
    """Return scoring weeks for each configured postseason round."""
    settings = get_schedule_settings(settings_payload)
    regular_count = as_int(
        settings.get("matchupPeriodCount"),
        0,
    ) or 0

    round_lengths = settings.get(
        "playoffMatchupPeriodLengthByRound",
        {},
    )

    round_numbers = sorted(
        as_int(key)
        for key in round_lengths
        if as_int(key) is not None
    )

    if not round_numbers:
        raise RuntimeError(
            "ESPN returned no playoff round-length settings."
        )

    return [
        matchup_period_scoring_weeks(
            settings_payload,
            regular_count + offset,
        )
        for offset, _ in enumerate(
            round_numbers,
            start=1,
        )
    ]


def team_score(
    team_id: int,
    scoring_weeks: list[int],
    weekly_lookup: dict[tuple[int, int], float],
) -> float:
    return sum(
        weekly_lookup.get((team_id, week), 0.0)
        for week in scoring_weeks
    )


def resolve_matchup(
    a: tuple[int, int],
    b: tuple[int, int],
    scoring_weeks: list[int],
    weekly_lookup: dict[tuple[int, int], float],
) -> dict[str, Any]:
    """
    Resolve one deterministic postseason matchup.

    a/b = (regular-season seed, team_id)
    """
    seed_a, team_a_id = a
    seed_b, team_b_id = b

    score_a = team_score(
        team_a_id,
        scoring_weeks,
        weekly_lookup,
    )
    score_b = team_score(
        team_b_id,
        scoring_weeks,
        weekly_lookup,
    )

    tiebreak_used = None

    if score_a > score_b:
        winner = a
        loser = b
    elif score_b > score_a:
        winner = b
        loser = a
    else:
        # ESPN reports no explicit playoff matchup tiebreak in the
        # current league. Higher regular-season seed is used only as
        # a deterministic fallback for an exact projected tie.
        winner = a if seed_a < seed_b else b
        loser = b if winner == a else a
        tiebreak_used = "HIGHER_SEED_FALLBACK"

    return {
        "seed_a": seed_a,
        "team_a_id": team_a_id,
        "score_a": score_a,
        "seed_b": seed_b,
        "team_b_id": team_b_id,
        "score_b": score_b,
        "winner_seed": winner[0],
        "winner_team_id": winner[1],
        "loser_seed": loser[0],
        "loser_team_id": loser[1],
        "tiebreak_used": tiebreak_used,
    }


def _bracket_row(
    *,
    bracket: str,
    round_number: int,
    round_name: str,
    matchup_number: int,
    scoring_weeks: list[int],
    result: dict[str, Any],
    names: dict[int, str],
    placement_high: int | None = None,
    placement_low: int | None = None,
) -> dict[str, Any]:
    return {
        "bracket": bracket,
        "round": round_number,
        "round_name": round_name,
        "matchup": matchup_number,
        "scoring_weeks": ",".join(map(str, scoring_weeks)),
        "seed_a": result["seed_a"],
        "team_a_id": result["team_a_id"],
        "team_a": names.get(result["team_a_id"]),
        "score_a": result["score_a"],
        "seed_b": result["seed_b"],
        "team_b_id": result["team_b_id"],
        "team_b": names.get(result["team_b_id"]),
        "score_b": result["score_b"],
        "winner_seed": result["winner_seed"],
        "winner_team_id": result["winner_team_id"],
        "winner_team": names.get(
            result["winner_team_id"]
        ),
        "loser_seed": result["loser_seed"],
        "loser_team_id": result["loser_team_id"],
        "loser_team": names.get(
            result["loser_team_id"]
        ),
        "winner_final_place": placement_high,
        "loser_final_place": placement_low,
        "tiebreak_used": result["tiebreak_used"],
    }


def project_six_team_championship_bracket(
    playoff_teams: list[tuple[int, int]],
    round_weeks: list[list[int]],
    weekly_lookup: dict[tuple[int, int], float],
    names: dict[int, str],
    playoff_reseed: bool,
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    """
    Produce full places 1-6.

    Round 1:
        3 v 6
        4 v 5
        1 and 2 bye

    Round 2:
        two semifinals
        first-round losers play for 5th/6th

    Round 3:
        semifinal winners play for 1st/2nd
        semifinal losers play for 3rd/4th
    """
    if len(round_weeks) < 3:
        raise RuntimeError(
            "Six-team playoffs require three configured rounds."
        )

    seed_to_team = dict(playoff_teams)
    rows = []
    placements: dict[int, int] = {}

    qf_36 = resolve_matchup(
        (3, seed_to_team[3]),
        (6, seed_to_team[6]),
        round_weeks[0],
        weekly_lookup,
    )
    qf_45 = resolve_matchup(
        (4, seed_to_team[4]),
        (5, seed_to_team[5]),
        round_weeks[0],
        weekly_lookup,
    )

    rows.append(
        _bracket_row(
            bracket="CHAMPIONSHIP",
            round_number=1,
            round_name="Quarterfinal",
            matchup_number=1,
            scoring_weeks=round_weeks[0],
            result=qf_36,
            names=names,
        )
    )
    rows.append(
        _bracket_row(
            bracket="CHAMPIONSHIP",
            round_number=1,
            round_name="Quarterfinal",
            matchup_number=2,
            scoring_weeks=round_weeks[0],
            result=qf_45,
            names=names,
        )
    )

    # 5th-place game occurs in Round 2 because both teams were
    # eliminated from title contention in Round 1.
    fifth_place = resolve_matchup(
        (
            qf_36["loser_seed"],
            qf_36["loser_team_id"],
        ),
        (
            qf_45["loser_seed"],
            qf_45["loser_team_id"],
        ),
        round_weeks[1],
        weekly_lookup,
    )
    placements[fifth_place["winner_team_id"]] = 5
    placements[fifth_place["loser_team_id"]] = 6

    if playoff_reseed:
        remaining = [
            (1, seed_to_team[1]),
            (2, seed_to_team[2]),
            (
                qf_36["winner_seed"],
                qf_36["winner_team_id"],
            ),
            (
                qf_45["winner_seed"],
                qf_45["winner_team_id"],
            ),
        ]
        remaining.sort(key=lambda x: x[0])
        semi_pairs = [
            (remaining[0], remaining[-1]),
            (remaining[1], remaining[-2]),
        ]
    else:
        semi_pairs = [
            (
                (1, seed_to_team[1]),
                (
                    qf_45["winner_seed"],
                    qf_45["winner_team_id"],
                ),
            ),
            (
                (2, seed_to_team[2]),
                (
                    qf_36["winner_seed"],
                    qf_36["winner_team_id"],
                ),
            ),
        ]

    semifinals = []
    for number, (a, b) in enumerate(
        semi_pairs,
        start=1,
    ):
        result = resolve_matchup(
            a,
            b,
            round_weeks[1],
            weekly_lookup,
        )
        semifinals.append(result)
        rows.append(
            _bracket_row(
                bracket="CHAMPIONSHIP",
                round_number=2,
                round_name="Semifinal",
                matchup_number=number,
                scoring_weeks=round_weeks[1],
                result=result,
                names=names,
            )
        )

    rows.append(
        _bracket_row(
            bracket="CHAMPIONSHIP",
            round_number=2,
            round_name="5th Place",
            matchup_number=3,
            scoring_weeks=round_weeks[1],
            result=fifth_place,
            names=names,
            placement_high=5,
            placement_low=6,
        )
    )

    championship = resolve_matchup(
        (
            semifinals[0]["winner_seed"],
            semifinals[0]["winner_team_id"],
        ),
        (
            semifinals[1]["winner_seed"],
            semifinals[1]["winner_team_id"],
        ),
        round_weeks[2],
        weekly_lookup,
    )
    placements[championship["winner_team_id"]] = 1
    placements[championship["loser_team_id"]] = 2

    third_place = resolve_matchup(
        (
            semifinals[0]["loser_seed"],
            semifinals[0]["loser_team_id"],
        ),
        (
            semifinals[1]["loser_seed"],
            semifinals[1]["loser_team_id"],
        ),
        round_weeks[2],
        weekly_lookup,
    )
    placements[third_place["winner_team_id"]] = 3
    placements[third_place["loser_team_id"]] = 4

    rows.append(
        _bracket_row(
            bracket="CHAMPIONSHIP",
            round_number=3,
            round_name="Championship",
            matchup_number=1,
            scoring_weeks=round_weeks[2],
            result=championship,
            names=names,
            placement_high=1,
            placement_low=2,
        )
    )
    rows.append(
        _bracket_row(
            bracket="CHAMPIONSHIP",
            round_number=3,
            round_name="3rd Place",
            matchup_number=2,
            scoring_weeks=round_weeks[2],
            result=third_place,
            names=names,
            placement_high=3,
            placement_low=4,
        )
    )

    return rows, placements


def next_consolation_ladder_games(
    results: list[dict[str, Any]],
) -> list[
    tuple[tuple[int, int], tuple[int, int]]
]:
    """
    ESPN-style consolation-ladder movement.

    Think of the consolation ladder as games stacked vertically:
      * winner of a game moves up one rung,
      * loser moves down one rung,
      * winner of the top game stays at the top,
      * loser of the bottom game stays at the bottom.

    With four games:
      next G1 = W(G1) vs W(G2)
      next G2 = L(G1) vs W(G3)
      next G3 = L(G2) vs W(G4)
      next G4 = L(G3) vs L(G4)
    """
    games = len(results)

    if games == 1:
        return [
            (
                (
                    results[0]["winner_seed"],
                    results[0]["winner_team_id"],
                ),
                (
                    results[0]["loser_seed"],
                    results[0]["loser_team_id"],
                ),
            )
        ]

    next_games = []

    for i in range(games):
        if i == 0:
            a = (
                results[0]["winner_seed"],
                results[0]["winner_team_id"],
            )
            b = (
                results[1]["winner_seed"],
                results[1]["winner_team_id"],
            )
        elif i == games - 1:
            a = (
                results[i - 1]["loser_seed"],
                results[i - 1]["loser_team_id"],
            )
            b = (
                results[i]["loser_seed"],
                results[i]["loser_team_id"],
            )
        else:
            a = (
                results[i - 1]["loser_seed"],
                results[i - 1]["loser_team_id"],
            )
            b = (
                results[i + 1]["winner_seed"],
                results[i + 1]["winner_team_id"],
            )

        next_games.append((a, b))

    return next_games


def project_consolation_ladder(
    consolation_teams: list[tuple[int, int]],
    round_weeks: list[list[int]],
    weekly_lookup: dict[tuple[int, int], float],
    names: dict[int, str],
    first_final_place: int,
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    """
    Project all non-playoff teams through an ESPN-style consolation ladder.

    The current league has 8 non-playoff teams and 3 postseason rounds,
    which naturally yields final places 7-14 after the last round.
    """
    if len(consolation_teams) % 2:
        raise NotImplementedError(
            "Odd-sized consolation ladders are not implemented yet."
        )

    # Start with adjacent regular-season seeds:
    # 7v8, 9v10, 11v12, 13v14 for this league.
    current_games = [
        (
            consolation_teams[i],
            consolation_teams[i + 1],
        )
        for i in range(0, len(consolation_teams), 2)
    ]

    rows = []
    final_results = None

    for round_index, weeks in enumerate(
        round_weeks,
        start=1,
    ):
        results = []

        for game_number, (a, b) in enumerate(
            current_games,
            start=1,
        ):
            result = resolve_matchup(
                a,
                b,
                weeks,
                weekly_lookup,
            )
            results.append(result)

            is_final_round = (
                round_index == len(round_weeks)
            )

            high_place = (
                first_final_place
                + 2 * (game_number - 1)
                if is_final_round
                else None
            )
            low_place = (
                high_place + 1
                if high_place is not None
                else None
            )

            rows.append(
                _bracket_row(
                    bracket="CONSOLATION_LADDER",
                    round_number=round_index,
                    round_name=(
                        "Final Placement"
                        if is_final_round
                        else f"Ladder Round {round_index}"
                    ),
                    matchup_number=game_number,
                    scoring_weeks=weeks,
                    result=result,
                    names=names,
                    placement_high=high_place,
                    placement_low=low_place,
                )
            )

        final_results = results

        if round_index < len(round_weeks):
            current_games = next_consolation_ladder_games(
                results
            )

    placements: dict[int, int] = {}

    for game_number, result in enumerate(
        final_results or [],
        start=1,
    ):
        high_place = (
            first_final_place
            + 2 * (game_number - 1)
        )
        placements[result["winner_team_id"]] = high_place
        placements[result["loser_team_id"]] = high_place + 1

    return rows, placements


def project_postseason(
    standings: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    weekly_team_projections: list[dict[str, Any]],
    settings_payload: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    """Project complete postseason and return final places 1 through N."""
    settings = get_schedule_settings(settings_payload)

    playoff_count = as_int(
        settings.get("playoffTeamCount"),
        0,
    ) or 0
    playoff_reseed = bool(
        settings.get("playoffReseed", False)
    )
    ladder_disabled = bool(
        settings.get("consolationLadderDisabled", False)
    )

    round_weeks = playoff_round_scoring_weeks(
        settings_payload
    )

    names = {
        team["team_id"]: team["team_name"]
        for team in teams
    }
    weekly_lookup = {
        (row["team_id"], row["week"]):
            row["projected_points"]
        for row in weekly_team_projections
    }

    seeded = [
        (row["seed"], row["team_id"])
        for row in standings
    ]
    playoff_teams = seeded[:playoff_count]
    consolation_teams = seeded[playoff_count:]

    if playoff_count != 6:
        raise NotImplementedError(
            "This MVP currently implements the current league's "
            f"6-team championship bracket; ESPN reports {playoff_count}."
        )

    championship_rows, championship_places = (
        project_six_team_championship_bracket(
            playoff_teams,
            round_weeks,
            weekly_lookup,
            names,
            playoff_reseed,
        )
    )

    if ladder_disabled:
        # If the league disables the consolation ladder, retain
        # regular-season order for non-playoff teams.
        consolation_rows = []
        consolation_places = {
            team_id: seed
            for seed, team_id in consolation_teams
        }
        consolation_model = (
            "REGULAR_SEASON_ORDER_LADDER_DISABLED"
        )
    else:
        consolation_rows, consolation_places = (
            project_consolation_ladder(
                consolation_teams,
                round_weeks,
                weekly_lookup,
                names,
                first_final_place=playoff_count + 1,
            )
        )
        consolation_model = "CONFIRMED_LEAGUE_LADDER"

    placements = {
        **championship_places,
        **consolation_places,
    }

    standings_lookup = {
        row["team_id"]: row
        for row in standings
    }

    final_standings = []

    for team_id, final_place in placements.items():
        regular = standings_lookup[team_id]
        final_standings.append(
            {
                "final_place": final_place,
                "team_id": team_id,
                "team_name": names.get(team_id),
                "regular_season_seed": regular["seed"],
                "regular_season_record": regular["record"],
                "regular_season_points_for": regular[
                    "points_for"
                ],
                "made_championship_playoffs": (
                    regular["seed"] <= playoff_count
                ),
            }
        )

    final_standings.sort(
        key=lambda x: x["final_place"]
    )

    champion = final_standings[0]

    summary = {
        "playoff_team_count": playoff_count,
        "playoff_reseed": playoff_reseed,
        "consolation_ladder_disabled": ladder_disabled,
        "consolation_projection_model": consolation_model,
        "round_scoring_weeks": round_weeks,
        "champion_team_id": champion["team_id"],
        "champion_team": champion["team_name"],
        "champion_seed": champion["regular_season_seed"],
    }

    return (
        championship_rows + consolation_rows,
        final_standings,
        summary,
    )
