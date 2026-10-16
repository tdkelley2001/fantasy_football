from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable

from .season import SeasonModelError, SeasonProjection, project_season
from .transactions import apply_transaction, trade_transaction
from .roster_fill import fill_open_roster_slots


@dataclass(frozen=True)
class TradeSpec:
    my_team_id: int
    partner_team_id: int
    give_player_ids: tuple[int, ...]
    receive_player_ids: tuple[int, ...]
    my_drop_player_ids: tuple[int, ...]
    partner_drop_player_ids: tuple[int, ...]
    effective_week: int


@dataclass
class TradeComparison:
    spec: TradeSpec
    trade_summary: dict[str, Any]
    team_comparison: list[dict[str, Any]]
    weekly_comparison: list[dict[str, Any]]
    lineup_comparison: list[dict[str, Any]]
    league_comparison: list[dict[str, Any]]
    before: SeasonProjection
    after: SeasonProjection




def _validate_trade(
    baseline: SeasonProjection,
    *,
    my_team_id: int,
    give_player_ids: tuple[int, ...],
    receive_player_ids: tuple[int, ...],
    my_drop_player_ids: tuple[int, ...],
    partner_drop_player_ids: tuple[int, ...],
    effective_week: int,
) -> TradeSpec:
    teams = {row["team_id"]: row["team_name"] for row in baseline.state.teams}
    players = {row["player_id"]: row for row in baseline.state.rosters}

    if my_team_id not in teams:
        raise SeasonModelError(f"Team ID {my_team_id} was not found in this league.")
    if not give_player_ids or not receive_player_ids:
        raise SeasonModelError("At least one player is required on each side.")

    missing = [
        player_id
        for player_id in (*give_player_ids, *receive_player_ids,
                          *my_drop_player_ids, *partner_drop_player_ids)
        if player_id not in players
    ]
    if missing:
        raise SeasonModelError(
            "These player IDs are not on a current roster: "
            + ", ".join(map(str, missing))
        )

    partner_ids = {
        int(players[player_id]["team_id"])
        for player_id in receive_player_ids
    }
    if my_team_id in partner_ids:
        raise SeasonModelError(
            "Received players must be rostered by another team."
        )
    if len(partner_ids) != 1:
        raise SeasonModelError(
            "All received players must currently belong to the same team."
        )

    return TradeSpec(
        my_team_id=my_team_id,
        partner_team_id=partner_ids.pop(),
        give_player_ids=give_player_ids,
        receive_player_ids=receive_player_ids,
        my_drop_player_ids=my_drop_player_ids,
        partner_drop_player_ids=partner_drop_player_ids,
        effective_week=effective_week,
    )


def _standings_lookup(
    result: SeasonProjection,
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
    result: SeasonProjection,
) -> dict[tuple[int, int], float]:
    return {
        (row["team_id"], row["week"]): row["projected_points"]
        for row in result.weekly_team_projections
    }


def _team_comparison_rows(
    before: SeasonProjection,
    after: SeasonProjection,
    spec: TradeSpec,
    weeks: tuple[int, ...],
) -> list[dict[str, Any]]:
    names = {row["team_id"]: row["team_name"] for row in before.state.teams}
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
    before: SeasonProjection,
    after: SeasonProjection,
    spec: TradeSpec,
    weeks: tuple[int, ...],
) -> list[dict[str, Any]]:
    names = {row["team_id"]: row["team_name"] for row in before.state.teams}
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
    before: SeasonProjection,
    after: SeasonProjection,
    spec: TradeSpec,
    weeks: tuple[int, ...],
) -> list[dict[str, Any]]:
    team_ids = {spec.my_team_id, spec.partner_team_id}

    def keyed(result: SeasonProjection) -> dict[tuple[int, int, int, int], dict[str, Any]]:
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
    before: SeasonProjection,
    after: SeasonProjection,
    spec: TradeSpec,
) -> list[dict[str, Any]]:
    names = {row["team_id"]: row["team_name"] for row in before.state.teams}
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
    baseline: SeasonProjection,
    my_team_id: int,
    give_player_ids: Iterable[int],
    receive_player_ids: Iterable[int],
    my_drop_player_ids: Iterable[int] = (),
    partner_drop_player_ids: Iterable[int] = (),
    effective_week: int | None = None,
    available_players: list[dict[str, Any]] | None = None,
    fill_open_slots: bool = False,
    roster_target: int = 17,
) -> TradeComparison:
    """Apply one proposed trade and compare full before/after projections."""
    effective_week = baseline.state.current_week if effective_week is None else effective_week
    spec = _validate_trade(
        baseline,
        my_team_id=my_team_id,
        give_player_ids=tuple(give_player_ids),
        receive_player_ids=tuple(receive_player_ids),
        my_drop_player_ids=tuple(my_drop_player_ids),
        partner_drop_player_ids=tuple(partner_drop_player_ids),
        effective_week=effective_week,
    )
    transaction = trade_transaction(
        baseline.state, team_id=spec.my_team_id, partner_id=spec.partner_team_id,
        give=spec.give_player_ids, receive=spec.receive_player_ids,
        effective_week=effective_week, team_drops=spec.my_drop_player_ids,
        partner_drops=spec.partner_drop_player_ids,
    )
    source = replace(baseline.state, available_players=available_players or baseline.state.available_players)
    transaction = trade_transaction(
        source, team_id=spec.my_team_id, partner_id=spec.partner_team_id,
        give=spec.give_player_ids, receive=spec.receive_player_ids,
        effective_week=effective_week, team_drops=spec.my_drop_player_ids,
        partner_drops=spec.partner_drop_player_ids,
    )
    after_state = apply_transaction(source, transaction)
    waiver_fills = []
    if fill_open_slots:
        after_state, waiver_fills = fill_open_roster_slots(
            after_state, (spec.my_team_id, spec.partner_team_id),
            effective_week=effective_week, target_size=roster_target)
    after = project_season(after_state, effective_week)

    current_week = effective_week
    final_week = int(baseline.summary["final_scoring_period"])
    weeks = tuple(range(current_week, final_week + 1))
    if not weeks:
        raise SeasonModelError("No scoring weeks remain to evaluate this trade.")

    players = {row["player_id"]: row for row in baseline.state.rosters}
    names = {row["team_id"]: row["team_name"] for row in baseline.state.teams}
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
        "my_required_drops": [
            {"player_id": player_id, "player_name": players[player_id]["player_name"]}
            for player_id in spec.my_drop_player_ids
        ],
        "partner_required_drops": [
            {"player_id": player_id, "player_name": players[player_id]["player_name"]}
            for player_id in spec.partner_drop_player_ids
        ],
        "comparison_weeks": list(weeks),
        "effective_week": effective_week,
        "champion_before": baseline.summary["champion_team"],
        "champion_after": after.summary["champion_team"],
        "team_results": team_comparison,
        "waiver_fill_enabled": fill_open_slots,
        "waiver_fills": waiver_fills,
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
