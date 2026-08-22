from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .config import Config
from .pipeline import ProjectionResult, project_from_normalized_inputs


@dataclass(frozen=True)
class TradeSpec:
    my_team_id: int
    partner_team_id: int
    give_player_ids: tuple[int, ...]
    receive_player_ids: tuple[int, ...]


@dataclass
class TradeComparison:
    spec: TradeSpec
    trade_summary: dict[str, Any]
    team_comparison: list[dict[str, Any]]
    weekly_comparison: list[dict[str, Any]]
    lineup_comparison: list[dict[str, Any]]
    league_comparison: list[dict[str, Any]]
    before: ProjectionResult
    after: ProjectionResult


def resolve_player_references(
    rosters: list[dict[str, Any]],
    references: Iterable[str],
) -> tuple[int, ...]:
    """Resolve exact player names or ESPN player IDs on current rosters."""
    players_by_id = {row["player_id"]: row for row in rosters}
    players_by_name: dict[str, list[dict[str, Any]]] = {}
    for row in rosters:
        name_key = str(row["player_name"]).strip().casefold()
        players_by_name.setdefault(name_key, []).append(row)

    resolved: list[int] = []
    for reference in references:
        value = reference.strip()
        if not value:
            continue

        player = None
        try:
            player_id = int(value)
        except ValueError:
            matches = players_by_name.get(value.casefold(), [])
            if len(matches) > 1:
                details = ", ".join(
                    f'{row["player_name"]} ({row["player_id"]})'
                    for row in matches
                )
                raise RuntimeError(
                    f'Player name "{value}" is ambiguous: {details}. '
                    "Use the ESPN player ID instead."
                )
            if matches:
                player = matches[0]
        else:
            player = players_by_id.get(player_id)

        if player is None:
            suggestions = sorted(
                {
                    str(row["player_name"])
                    for row in rosters
                    if value.casefold()
                    in str(row["player_name"]).casefold()
                }
            )
            hint = (
                f" Possible matches: {', '.join(suggestions[:5])}."
                if suggestions
                else ""
            )
            raise RuntimeError(
                f'No rostered player matches "{value}".{hint}'
            )

        resolved.append(int(player["player_id"]))

    if not resolved:
        raise RuntimeError("At least one player is required on each side.")
    if len(resolved) != len(set(resolved)):
        raise RuntimeError("The same player was entered more than once.")
    return tuple(resolved)


def _validate_trade(
    baseline: ProjectionResult,
    *,
    my_team_id: int,
    give_player_ids: tuple[int, ...],
    receive_player_ids: tuple[int, ...],
) -> TradeSpec:
    teams = {row["team_id"]: row["team_name"] for row in baseline.teams}
    players = {row["player_id"]: row for row in baseline.rosters}

    if my_team_id not in teams:
        raise RuntimeError(
            f"Team ID {my_team_id} was not found in this league."
        )
    if not give_player_ids or not receive_player_ids:
        raise RuntimeError("At least one player is required on each side.")
    if len(give_player_ids) != len(set(give_player_ids)):
        raise RuntimeError("A player cannot be given more than once.")
    if len(receive_player_ids) != len(set(receive_player_ids)):
        raise RuntimeError("A player cannot be received more than once.")
    if set(give_player_ids) & set(receive_player_ids):
        raise RuntimeError("A player cannot be on both sides of a trade.")

    missing = [
        player_id
        for player_id in (*give_player_ids, *receive_player_ids)
        if player_id not in players
    ]
    if missing:
        raise RuntimeError(
            "These player IDs are not on a current roster: "
            + ", ".join(map(str, missing))
        )

    wrong_owner = [
        players[player_id]["player_name"]
        for player_id in give_player_ids
        if players[player_id]["team_id"] != my_team_id
    ]
    if wrong_owner:
        raise RuntimeError(
            f'{teams[my_team_id]} cannot give players it does not roster: '
            + ", ".join(wrong_owner)
        )

    partner_ids = {
        int(players[player_id]["team_id"])
        for player_id in receive_player_ids
    }
    if my_team_id in partner_ids:
        raise RuntimeError(
            "Received players must be rostered by another team."
        )
    if len(partner_ids) != 1:
        raise RuntimeError(
            "All received players must currently belong to the same team."
        )

    return TradeSpec(
        my_team_id=my_team_id,
        partner_team_id=partner_ids.pop(),
        give_player_ids=give_player_ids,
        receive_player_ids=receive_player_ids,
    )


def _trade_rosters(
    baseline: ProjectionResult,
    spec: TradeSpec,
) -> list[dict[str, Any]]:
    team_names = {
        row["team_id"]: row["team_name"] for row in baseline.teams
    }
    give_ids = set(spec.give_player_ids)
    receive_ids = set(spec.receive_player_ids)
    result = []

    for roster_row in baseline.rosters:
        row = dict(roster_row)
        if row["player_id"] in give_ids:
            row["team_id"] = spec.partner_team_id
            row["team_name"] = team_names[spec.partner_team_id]
        elif row["player_id"] in receive_ids:
            row["team_id"] = spec.my_team_id
            row["team_name"] = team_names[spec.my_team_id]
        result.append(row)

    return result


def _standings_lookup(
    result: ProjectionResult,
) -> dict[int, dict[str, Any]]:
    regular = {row["team_id"]: row for row in result.projected_standings}
    final = {row["team_id"]: row for row in result.final_standings}
    return {
        team_id: {
            "wins": row["wins"],
            "losses": row["losses"],
            "ties": row["ties"],
            "points_for": row["points_for"],
            "regular_seed": row["seed"],
            "final_place": final[team_id]["final_place"],
        }
        for team_id, row in regular.items()
    }


def _weekly_lookup(
    result: ProjectionResult,
) -> dict[tuple[int, int], float]:
    return {
        (row["team_id"], row["week"]): row["projected_points"]
        for row in result.weekly_team_projections
    }


def _team_comparison_rows(
    before: ProjectionResult,
    after: ProjectionResult,
    spec: TradeSpec,
    weeks: tuple[int, ...],
) -> list[dict[str, Any]]:
    names = {row["team_id"]: row["team_name"] for row in before.teams}
    before_standings = _standings_lookup(before)
    after_standings = _standings_lookup(after)
    before_weekly = _weekly_lookup(before)
    after_weekly = _weekly_lookup(after)
    rows = []

    for role, team_id in (
        ("MY_TEAM", spec.my_team_id),
        ("PARTNER", spec.partner_team_id),
    ):
        old = before_standings[team_id]
        new = after_standings[team_id]
        old_future = sum(before_weekly[(team_id, week)] for week in weeks)
        new_future = sum(after_weekly[(team_id, week)] for week in weeks)
        rows.append(
            {
                "team_role": role,
                "team_id": team_id,
                "team_name": names[team_id],
                "future_points_before": old_future,
                "future_points_after": new_future,
                "future_points_change": new_future - old_future,
                "avg_weekly_points_before": old_future / len(weeks),
                "avg_weekly_points_after": new_future / len(weeks),
                "avg_weekly_points_change": (
                    (new_future - old_future) / len(weeks)
                ),
                "wins_before": old["wins"],
                "wins_after": new["wins"],
                "wins_change": new["wins"] - old["wins"],
                "losses_before": old["losses"],
                "losses_after": new["losses"],
                "ties_before": old["ties"],
                "ties_after": new["ties"],
                "points_for_before": old["points_for"],
                "points_for_after": new["points_for"],
                "points_for_change": (
                    new["points_for"] - old["points_for"]
                ),
                "regular_seed_before": old["regular_seed"],
                "regular_seed_after": new["regular_seed"],
                "regular_seed_improvement": (
                    old["regular_seed"] - new["regular_seed"]
                ),
                "final_place_before": old["final_place"],
                "final_place_after": new["final_place"],
                "final_place_improvement": (
                    old["final_place"] - new["final_place"]
                ),
            }
        )
    return rows


def _weekly_comparison_rows(
    before: ProjectionResult,
    after: ProjectionResult,
    spec: TradeSpec,
    weeks: tuple[int, ...],
) -> list[dict[str, Any]]:
    names = {row["team_id"]: row["team_name"] for row in before.teams}
    old = _weekly_lookup(before)
    new = _weekly_lookup(after)
    rows = []
    for role, team_id in (
        ("MY_TEAM", spec.my_team_id),
        ("PARTNER", spec.partner_team_id),
    ):
        for week in weeks:
            before_points = old[(team_id, week)]
            after_points = new[(team_id, week)]
            rows.append(
                {
                    "team_role": role,
                    "team_id": team_id,
                    "team_name": names[team_id],
                    "week": week,
                    "projected_points_before": before_points,
                    "projected_points_after": after_points,
                    "projected_points_change": (
                        after_points - before_points
                    ),
                }
            )
    return rows


def _lineup_comparison_rows(
    before: ProjectionResult,
    after: ProjectionResult,
    spec: TradeSpec,
    weeks: tuple[int, ...],
) -> list[dict[str, Any]]:
    team_ids = {spec.my_team_id, spec.partner_team_id}

    def keyed(result: ProjectionResult) -> dict[tuple[int, int, int, int], dict[str, Any]]:
        return {
            (
                row["team_id"],
                row["week"],
                row["slot_id"],
                row["slot_instance"],
            ): row
            for row in result.optimal_lineups
            if row["team_id"] in team_ids and row["week"] in weeks
        }

    old = keyed(before)
    new = keyed(after)
    rows = []
    for key in sorted(old):
        old_row = old[key]
        new_row = new[key]
        rows.append(
            {
                "team_id": old_row["team_id"],
                "team_name": old_row["team_name"],
                "week": old_row["week"],
                "slot_id": old_row["slot_id"],
                "slot_name": old_row["slot_name"],
                "slot_instance": old_row["slot_instance"],
                "player_id_before": old_row["player_id"],
                "player_before": old_row["player_name"],
                "player_id_after": new_row["player_id"],
                "player_after": new_row["player_name"],
                "projected_points_before": old_row["projected_points"],
                "projected_points_after": new_row["projected_points"],
                "projected_points_change": (
                    new_row["projected_points"]
                    - old_row["projected_points"]
                ),
                "starter_changed": (
                    old_row["player_id"] != new_row["player_id"]
                ),
            }
        )
    return rows


def _league_comparison_rows(
    before: ProjectionResult,
    after: ProjectionResult,
    spec: TradeSpec,
) -> list[dict[str, Any]]:
    names = {row["team_id"]: row["team_name"] for row in before.teams}
    old = _standings_lookup(before)
    new = _standings_lookup(after)
    trade_teams = {spec.my_team_id, spec.partner_team_id}
    rows = []
    for team_id in sorted(names):
        rows.append(
            {
                "team_id": team_id,
                "team_name": names[team_id],
                "in_trade": team_id in trade_teams,
                "wins_before": old[team_id]["wins"],
                "wins_after": new[team_id]["wins"],
                "wins_change": new[team_id]["wins"] - old[team_id]["wins"],
                "regular_seed_before": old[team_id]["regular_seed"],
                "regular_seed_after": new[team_id]["regular_seed"],
                "regular_seed_improvement": (
                    old[team_id]["regular_seed"]
                    - new[team_id]["regular_seed"]
                ),
                "final_place_before": old[team_id]["final_place"],
                "final_place_after": new[team_id]["final_place"],
                "final_place_improvement": (
                    old[team_id]["final_place"]
                    - new[team_id]["final_place"]
                ),
            }
        )
    return rows


def evaluate_trade(
    *,
    baseline: ProjectionResult,
    config: Config,
    my_team_id: int,
    give_player_ids: Iterable[int],
    receive_player_ids: Iterable[int],
) -> TradeComparison:
    """Apply one proposed trade and compare full before/after projections."""
    spec = _validate_trade(
        baseline,
        my_team_id=my_team_id,
        give_player_ids=tuple(give_player_ids),
        receive_player_ids=tuple(receive_player_ids),
    )
    rosters_after = _trade_rosters(baseline, spec)

    after = project_from_normalized_inputs(
        config=config,
        teams=[dict(row) for row in baseline.teams],
        rosters=rosters_after,
        player_projections=baseline.player_projections,
        starter_slots=baseline.starter_slots,
        schedule_rows=baseline.schedule_rows,
        settings_payload=baseline.settings_payload,
        first_week=int(baseline.summary["first_scoring_period"]),
        final_week=int(baseline.summary["final_scoring_period"]),
        current_week=int(baseline.summary["current_scoring_period"]),
    )

    current_week = int(baseline.summary["current_scoring_period"])
    final_week = int(baseline.summary["final_scoring_period"])
    weeks = tuple(range(current_week, final_week + 1))
    if not weeks:
        raise RuntimeError("No scoring weeks remain to evaluate this trade.")

    players = {row["player_id"]: row for row in baseline.rosters}
    names = {row["team_id"]: row["team_name"] for row in baseline.teams}
    team_comparison = _team_comparison_rows(
        baseline, after, spec, weeks
    )
    trade_summary = {
        "my_team_id": spec.my_team_id,
        "my_team": names[spec.my_team_id],
        "partner_team_id": spec.partner_team_id,
        "partner_team": names[spec.partner_team_id],
        "give": [
            {
                "player_id": player_id,
                "player_name": players[player_id]["player_name"],
            }
            for player_id in spec.give_player_ids
        ],
        "receive": [
            {
                "player_id": player_id,
                "player_name": players[player_id]["player_name"],
            }
            for player_id in spec.receive_player_ids
        ],
        "comparison_weeks": list(weeks),
        "champion_before": baseline.summary["champion_team"],
        "champion_after": after.summary["champion_team"],
        "team_results": team_comparison,
    }

    return TradeComparison(
        spec=spec,
        trade_summary=trade_summary,
        team_comparison=team_comparison,
        weekly_comparison=_weekly_comparison_rows(
            baseline, after, spec, weeks
        ),
        lineup_comparison=_lineup_comparison_rows(
            baseline, after, spec, weeks
        ),
        league_comparison=_league_comparison_rows(
            baseline, after, spec
        ),
        before=baseline,
        after=after,
    )
