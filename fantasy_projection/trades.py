from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from statistics import median
from typing import Any, Iterable

from .progress import Progress as tqdm

from .lineup import optimize_lineup_weeks
from .season import SeasonModelError, SeasonProjection, season_results
from .trade_config import TradeConfig
from .transactions import apply_transaction, trade_transaction
from .search_runtime import SearchRuntime, prune_ranked, runtime_profile

EPSILON = 1e-9


@dataclass
class TradeSearchResult:
    all_evaluations: list[dict[str, Any]]
    search_summary: list[dict[str, Any]]


@dataclass(frozen=True)
class TradeSearchOptions:
    partner_ids: tuple[int, ...] = ()
    package_shapes: tuple[tuple[int, int], ...] = ((1, 1), (1, 2), (2, 1), (2, 2))
    include_player_ids: tuple[int, ...] = ()
    exclude_player_ids: tuple[int, ...] = ()
    untouchable_player_ids: tuple[int, ...] = ()
    target_player_ids: tuple[int, ...] = ()
    include_positions: tuple[int, ...] = ()
    exclude_positions: tuple[int, ...] = ()
    include_special_teams: bool = True
    drop_strategy: str = "least_lineup_benefit"
    effective_week: int | None = None
    balance_filter: bool = False
    minimum_value_ratio: float = 0.5
    runtime: SearchRuntime = runtime_profile()


def _candidate_packages(player_ids, size, players, *, required=(), excluded=(),
                        include_positions=(), exclude_positions=(), include_special=True):
    """Generate packages only; scoring and season evaluation happen later."""
    excluded, required = set(excluded), set(required)
    allowed = [pid for pid in player_ids if pid not in excluded
               and (include_special or players[pid].get("default_position_id") not in (5, 16))
               and players[pid].get("default_position_id") not in set(exclude_positions)]
    packages = _packages(allowed, size)
    return [package for package in packages if required.issubset(package)
            and (not include_positions or any(players[pid].get("default_position_id") in include_positions for pid in package))]


def _team_name_map(
    teams: list[dict[str, Any]],
) -> dict[int, str]:
    return {
        row["team_id"]: row["team_name"]
        for row in teams
    }


def _roster_ids_by_team(
    rosters: list[dict[str, Any]],
) -> dict[int, set[int]]:
    result: dict[int, set[int]] = {}
    for row in rosters:
        result.setdefault(row["team_id"], set()).add(
            row["player_id"]
        )
    return result


def _player_map(
    rosters: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    return {
        row["player_id"]: row
        for row in rosters
    }


def _tradable_player_ids(
    team_id: int,
    roster_ids: dict[int, set[int]],
) -> list[int]:
    """Return every rostered player, including kickers and D/ST."""
    return sorted(roster_ids.get(team_id, set()))


def _packages(
    player_ids: list[int],
    size: int,
) -> list[tuple[int, ...]]:
    if size == 1:
        return [(x,) for x in player_ids]
    return list(combinations(player_ids, size))


def _projection_lookup(
    player_projections: list[dict[str, Any]],
) -> dict[tuple[int, int], float]:
    return {
        (row["player_id"], row["week"]): row[
            "projected_points"
        ]
        for row in player_projections
        if row.get("projected_points") is not None
    }


def _materialize_roster(
    player_ids: Iterable[int],
    players: dict[int, dict[str, Any]],
    *,
    team_id: int,
    team_name: str,
) -> list[dict[str, Any]]:
    rows = []
    for player_id in player_ids:
        row = dict(players[player_id])
        row["team_id"] = team_id
        row["team_name"] = team_name
        rows.append(row)
    return rows


def _score_roster_weeks(
    player_ids: frozenset[int],
    *,
    team_id: int,
    team_name: str,
    weeks: tuple[int, ...],
    players: dict[int, dict[str, Any]],
    starter_slots: list[dict[str, Any]],
    projection_lookup: dict[tuple[int, int], float],
    cache: dict[
        tuple[frozenset[int], tuple[int, ...]],
        tuple[float, ...],
    ],
) -> tuple[float, ...]:
    key = (player_ids, weeks)
    cached = cache.get(key)
    if cached is not None:
        return cached

    roster = _materialize_roster(
        player_ids,
        players,
        team_id=team_id,
        team_name=team_name,
    )

    result = optimize_lineup_weeks(
        roster,
        starter_slots,
        projection_lookup,
        weeks,
    )
    cache[key] = result
    return result


def _sum_scores(scores: Iterable[float]) -> float:
    return float(sum(scores))


def _player_label(
    package: tuple[int, ...],
    players: dict[int, dict[str, Any]],
) -> str:
    return " + ".join(
        players[player_id]["player_name"]
        for player_id in package
    )


def _baseline_team_scores(
    baseline: SeasonProjection,
) -> dict[tuple[int, int], float]:
    return {
        (row["team_id"], row["week"]): row[
            "projected_points"
        ]
        for row in baseline.weekly_team_projections
    }


def _preserve_actual_scores(baseline, team_id, weeks, scores):
    """Cached roster scores must not overwrite a finalized current-week score."""
    actuals = {r["week"]: r["projected_points"] for r in baseline.weekly_team_projections
               if r["team_id"] == team_id and r.get("result_type") == "ACTUAL"}
    return tuple(actuals.get(week, score) for week, score in zip(weeks, scores, strict=True))


def _team_metrics(
    baseline: SeasonProjection,
) -> dict[int, dict[str, Any]]:
    reg = {
        row["team_id"]: row
        for row in baseline.projected_standings
    }
    final = {
        row["team_id"]: row
        for row in baseline.final_standings
    }

    metrics = {}
    for team_id, reg_row in reg.items():
        final_row = final[team_id]
        metrics[team_id] = {
            "regular_seed": reg_row["seed"],
            "wins": reg_row["wins"],
            "losses": reg_row["losses"],
            "ties": reg_row["ties"],
            "points_for": reg_row["points_for"],
            "final_place": final_row["final_place"],
        }
    return metrics


def _scenario_metrics(
    baseline: SeasonProjection,
    replacement_weekly_scores: dict[tuple[int, int], float],
) -> tuple[
    dict[int, dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Reproject standings/postseason using already-computed lineup scores."""
    weekly = []
    for row in baseline.weekly_team_projections:
        key = (row["team_id"], row["week"])
        copy = dict(row)
        if key in replacement_weekly_scores and row["week"] >= baseline.state.current_week and row.get("result_type") != "ACTUAL":
            copy["projected_points"] = replacement_weekly_scores[key]
        weekly.append(copy)

    regular_matchups, standings, postseason_matchups, final_standings, postseason_summary = season_results(baseline.state, weekly)

    reg_lookup = {row["team_id"]: row for row in standings}
    final_lookup = {
        row["team_id"]: row
        for row in final_standings
    }

    metrics = {}
    for team_id, row in reg_lookup.items():
        metrics[team_id] = {
            "regular_seed": row["seed"],
            "wins": row["wins"],
            "losses": row["losses"],
            "ties": row["ties"],
            "points_for": row["points_for"],
            "final_place": final_lookup[team_id]["final_place"],
        }

    return (
        metrics,
        postseason_summary,
        regular_matchups,
        postseason_matchups,
    )


def _classify_trade(
    my_gain: float,
    partner_gain: float,
) -> str:
    my_positive = my_gain > EPSILON
    partner_positive = partner_gain > EPSILON

    if my_positive and partner_positive:
        return "BOTH_POSITIVE"
    if my_positive and not partner_positive:
        return "MY_TEAM_ONLY"
    if partner_positive and not my_positive:
        return "PARTNER_ONLY"
    return "NEITHER_POSITIVE"


def _weekly_lineup_metrics(
    prefix: str,
    before: tuple[float, ...],
    after: tuple[float, ...],
    weeks: tuple[int, ...],
) -> dict[str, Any]:
    deltas = tuple(
        0.0 if abs(new - old) <= EPSILON else new - old
        for old, new in zip(before, after, strict=True)
    )
    best_index = max(range(len(deltas)), key=deltas.__getitem__)
    worst_index = min(range(len(deltas)), key=deltas.__getitem__)
    before_total = _sum_scores(before)
    after_total = _sum_scores(after)
    total_gain = after_total - before_total
    if abs(total_gain) <= EPSILON:
        total_gain = 0.0
    # A transaction's single best week is often a bye or short-term injury
    # replacement. Excluding that one spike measures repeatable roster value.
    sustained_gain = (
        (total_gain - max(0.0, max(deltas))) / (len(deltas) - 1)
        if len(deltas) > 1
        else total_gain
    )
    if abs(sustained_gain) <= EPSILON:
        sustained_gain = 0.0

    return {
        f"{prefix}_current_week_lineup_points_before": before[0],
        f"{prefix}_current_week_lineup_points_after": after[0],
        f"{prefix}_current_week_lineup_gain": deltas[0],
        f"{prefix}_avg_remaining_season_lineup_points_before": (
            before_total / len(before)
        ),
        f"{prefix}_avg_remaining_season_lineup_points_after": (
            after_total / len(after)
        ),
        f"{prefix}_avg_remaining_season_lineup_gain": (
            total_gain / len(deltas)
        ),
        f"{prefix}_total_remaining_season_lineup_points_before": (
            before_total
        ),
        f"{prefix}_total_remaining_season_lineup_points_after": after_total,
        f"{prefix}_total_remaining_season_lineup_gain": total_gain,
        f"{prefix}_median_weekly_lineup_gain": float(median(deltas)),
        f"{prefix}_sustained_weekly_lineup_gain": sustained_gain,
        f"{prefix}_positive_weeks": sum(x > EPSILON for x in deltas),
        f"{prefix}_negative_weeks": sum(x < -EPSILON for x in deltas),
        f"{prefix}_neutral_weeks": sum(abs(x) <= EPSILON for x in deltas),
        f"{prefix}_best_week": weeks[best_index],
        f"{prefix}_best_week_gain": deltas[best_index],
        f"{prefix}_worst_week": weeks[worst_index],
        f"{prefix}_worst_week_gain": deltas[worst_index],
        f"{prefix}_weekly_weeks": list(weeks),
        f"{prefix}_weekly_lineup_gains": list(deltas),
    }


def _phase_lineup_metrics(
    prefix: str,
    phase: str,
    before: tuple[float, ...],
    after: tuple[float, ...],
    all_weeks: tuple[int, ...],
    phase_weeks: tuple[int, ...],
) -> dict[str, float]:
    before_values = tuple(
        before[all_weeks.index(week)] for week in phase_weeks
    )
    after_values = tuple(
        after[all_weeks.index(week)] for week in phase_weeks
    )
    before_total = _sum_scores(before_values)
    after_total = _sum_scores(after_values)
    total_gain = after_total - before_total
    if abs(total_gain) <= EPSILON:
        total_gain = 0.0
    count = len(phase_weeks)
    return {
        f"{prefix}_{phase}_avg_weekly_lineup_points_before": (
            before_total / count if count else 0.0
        ),
        f"{prefix}_{phase}_avg_weekly_lineup_points_after": (
            after_total / count if count else 0.0
        ),
        f"{prefix}_{phase}_avg_weekly_lineup_gain": (
            total_gain / count if count else 0.0
        ),
        f"{prefix}_{phase}_total_lineup_points_before": before_total,
        f"{prefix}_{phase}_total_lineup_points_after": after_total,
        f"{prefix}_{phase}_total_lineup_gain": total_gain,
    }


def _playoff_path(
    team_id: int,
    matchups: list[dict[str, Any]],
) -> str:
    games = []
    for row in matchups:
        if team_id not in {row["team_a_id"], row["team_b_id"]}:
            continue
        if row["team_a_id"] == team_id:
            opponent = row["team_b"]
        else:
            opponent = row["team_a"]
        outcome = (
            "WIN" if row["winner_team_id"] == team_id else "LOSS"
        )
        games.append(
            (
                int(row["round"]),
                int(row["matchup"]),
                f'{row["bracket"]} R{row["round"]} '
                f'{row["round_name"]} vs {opponent} ({outcome})',
            )
        )

    games.sort()
    return " | ".join(game[2] for game in games) or "NO_PLAYOFF_GAME"


def _projected_game_flip_metrics(
    prefix: str,
    team_id: int,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> dict[str, Any]:
    def result(row: dict[str, Any]) -> str:
        winner = row["winner_team_id"]
        if winner is None:
            return "TIE"
        return "WIN" if winner == team_id else "LOSS"

    after_by_period = {
        row["matchup_period"]: row
        for row in after
        if row["result_type"] == "PROJECTED"
        and team_id in {row["home_team_id"], row["away_team_id"]}
    }
    flips = []
    for row in before:
        if row["result_type"] != "PROJECTED":
            continue
        if team_id not in {row["home_team_id"], row["away_team_id"]}:
            continue
        old_result = result(row)
        new_result = result(after_by_period[row["matchup_period"]])
        if old_result != new_result:
            flips.append(
                (row["matchup_period"], old_result, new_result)
            )

    return {
        f"{prefix}_projected_game_flips": len(flips),
        f"{prefix}_projected_wins_gained_from_flips": sum(
            old != "WIN" and new == "WIN" for _, old, new in flips
        ),
        f"{prefix}_projected_wins_lost_from_flips": sum(
            old == "WIN" and new != "WIN" for _, old, new in flips
        ),
        f"{prefix}_projected_game_flip_details": " | ".join(
            f"Period {period}: {old}_TO_{new}"
            for period, old, new in flips
        ),
    }


def _base_export_record(
    *,
    trade_id: str,
    trade_type: str,
    partner_id: int,
    partner_name: str,
    my_out: tuple[int, ...],
    partner_out: tuple[int, ...],
    my_drops: tuple[int, ...],
    partner_drops: tuple[int, ...],
    players: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "trade_id": trade_id,
        "trade_type": trade_type,
        "partner_team_id": partner_id,
        "partner_team": partner_name,
        "my_give_player_ids": ",".join(map(str, my_out)),
        "my_give": _player_label(my_out, players),
        "my_receive_player_ids": ",".join(map(str, partner_out)),
        "my_receive": _player_label(partner_out, players),
        "my_drop_player_ids": ",".join(map(str, my_drops)),
        "my_required_drops": _player_label(my_drops, players) if my_drops else "",
        "partner_drop_player_ids": ",".join(map(str, partner_drops)),
        "partner_required_drops": _player_label(partner_drops, players) if partner_drops else "",
    }


def _legal_trade_resolutions(baseline, my_team_id, partner_id, my_out, partner_out,
                             effective_week, options):
    """Return explicit required-drop resolutions, preferring real open slots."""
    def valid(my_drops=(), partner_drops=()):
        apply_transaction(baseline.state, trade_transaction(
            baseline.state, team_id=my_team_id, partner_id=partner_id,
            give=my_out, receive=partner_out, effective_week=effective_week,
            team_drops=my_drops, partner_drops=partner_drops))
    try:
        valid()
        return [((), ())]
    except SeasonModelError:
        pass
    if len(partner_out) > len(my_out):
        rows = [row for row in baseline.state.rosters
                if row["team_id"] == my_team_id and row["player_id"] not in my_out
                and row["player_id"] not in options.untouchable_player_ids
                and row["player_id"] not in options.exclude_player_ids
                and (options.include_special_teams or row.get("default_position_id") not in (5, 16))
                and row.get("droppable", True) and not row.get("lineup_locked") and not row.get("roster_locked")]
        max_drops = len(partner_out) - len(my_out)
        candidates = [(tuple(combo), ()) for size in range(1, max_drops + 1)
                      for combo in combinations((int(row["player_id"]) for row in rows), size)]
    elif len(my_out) > len(partner_out):
        rows = [row for row in baseline.state.rosters
                if row["team_id"] == partner_id and row["player_id"] not in partner_out
                and row["player_id"] not in options.exclude_player_ids
                and (options.include_special_teams or row.get("default_position_id") not in (5, 16))
                and row.get("droppable", True) and not row.get("lineup_locked") and not row.get("roster_locked")]
        max_drops = len(my_out) - len(partner_out)
        candidates = [((), tuple(combo)) for size in range(1, max_drops + 1)
                      for combo in combinations((int(row["player_id"]) for row in rows), size)]
    else:
        return []
    result = []
    for my_drops, partner_drops in candidates:
        try:
            valid(my_drops, partner_drops)
            result.append((my_drops, partner_drops))
        except SeasonModelError:
            continue
    return result


def select_trade_resolution(
    baseline: SeasonProjection,
    my_team_id: int,
    partner_id: int,
    my_out: tuple[int, ...],
    partner_out: tuple[int, ...],
    effective_week: int,
    options: TradeSearchOptions | None = None,
    *,
    roster_ids: dict[int, set[int]] | None = None,
    players: dict[int, dict[str, Any]] | None = None,
    projection_lookup: dict[tuple[int, int], float] | None = None,
    score_cache: dict | None = None,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Choose the legal required drops under the requested projection strategy."""
    options = options or TradeSearchOptions(effective_week=effective_week)
    resolutions = _legal_trade_resolutions(
        baseline, my_team_id, partner_id, my_out, partner_out, effective_week, options)
    if not resolutions:
        raise SeasonModelError("This trade has no legal required-drop resolution.")
    if len(resolutions) == 1:
        return resolutions[0]
    roster_ids = roster_ids or _roster_ids_by_team(baseline.state.rosters)
    players = players or _player_map(baseline.state.rosters)
    projection_lookup = projection_lookup or _projection_lookup(baseline.state.player_projections)
    score_cache = score_cache if score_cache is not None else {}
    weeks = tuple(range(effective_week, baseline.state.final_week + 1))
    names = _team_name_map(baseline.state.teams)

    def package_value(package):
        return sum(projection_lookup.get((pid, week), 0.0)
                   for pid in package for week in weeks)

    def rank(resolution):
        my_drops, partner_drops = resolution
        raw_drop_value = package_value(my_drops) + package_value(partner_drops)
        if options.drop_strategy == "lowest_projection":
            return (-raw_drop_value,)
        if options.drop_strategy != "least_lineup_benefit":
            raise SeasonModelError(f"Unsupported trade drop strategy: {options.drop_strategy}.")
        if my_drops:
            team_id, outgoing, incoming, drops = my_team_id, my_out, partner_out, my_drops
        else:
            team_id, outgoing, incoming, drops = partner_id, partner_out, my_out, partner_drops
        final_ids = (roster_ids[team_id] - set(outgoing) - set(drops)) | set(incoming)
        scores = _score_roster_weeks(
            frozenset(final_ids), team_id=team_id, team_name=names[team_id],
            weeks=weeks, players=players, starter_slots=baseline.state.starter_slots,
            projection_lookup=projection_lookup, cache=score_cache)
        return (_sum_scores(scores), -raw_drop_value)

    return max(resolutions, key=rank)


def _evaluate_all_trades_for_type(
    *,
    give_size: int,
    receive_size: int,
    baseline: SeasonProjection,
    trade_config: TradeConfig,
    progress_callback=None,
    roster_ids: dict[int, set[int]],
    players: dict[int, dict[str, Any]],
    projection_lookup: dict[tuple[int, int], float],
    score_cache: dict[
        tuple[frozenset[int], tuple[int, ...]],
        tuple[float, ...],
    ],
    future_weeks: tuple[int, ...],
    regular_weeks: tuple[int, ...],
    postseason_weeks: tuple[int, ...],
    options: TradeSearchOptions,
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
]:
    """Evaluate every legal package combination for one trade size.

    Candidate constraints and an optional raw-value balance screen are
    applied before full lineup evaluation. Trades that make a legal starting
    lineup impossible are retained with evaluation_status=INVALID_LINEUP.
    """
    names = _team_name_map(baseline.state.teams)
    my_team_id = trade_config.my_team_id
    trade_type = f"{give_size}-for-{receive_size}"
    baseline_weekly = _baseline_team_scores(baseline)
    baseline_metrics = _team_metrics(baseline)

    my_tradable = _tradable_player_ids(
        my_team_id,
        roster_ids,
    )
    my_packages = _candidate_packages(my_tradable, give_size, players,
        required=options.include_player_ids,
        excluded=(*options.exclude_player_ids, *options.untouchable_player_ids),
        include_positions=options.include_positions, exclude_positions=options.exclude_positions,
        include_special=options.include_special_teams)

    partner_info = []
    total_combinations = 0
    for team in baseline.state.teams:
        partner_id = team["team_id"]
        if partner_id == my_team_id:
            continue
        if options.partner_ids and partner_id not in options.partner_ids:
            continue

        partner_tradable = _tradable_player_ids(
            partner_id,
            roster_ids,
        )
        partner_packages = _candidate_packages(partner_tradable, receive_size, players,
            required=options.target_player_ids, excluded=options.exclude_player_ids,
            include_positions=options.include_positions, exclude_positions=options.exclude_positions,
            include_special=options.include_special_teams)
        partner_info.append((partner_id, partner_packages))
        total_combinations += len(my_packages) * len(partner_packages)

    def package_value(package):
        return sum(projection_lookup.get((pid, week), 0.0)
                   for pid in package for week in future_weeks)

    raw_candidates = [(partner_id, my_out, partner_out)
                      for partner_id, partner_packages in partner_info
                      for my_out in my_packages for partner_out in partner_packages]
    balance_pruned = 0
    if getattr(options, "balance_filter", False):
        minimum_value_ratio = getattr(options, "minimum_value_ratio", 0.5)
        if not 0 <= minimum_value_ratio <= 1:
            raise SeasonModelError("Minimum package value ratio must be from 0 to 1.")
        balanced = []
        for candidate in raw_candidates:
            my_value, partner_value = package_value(candidate[1]), package_value(candidate[2])
            high = max(my_value, partner_value)
            ratio = min(my_value, partner_value) / high if high > 0 else 1.0
            if ratio >= minimum_value_ratio:
                balanced.append(candidate)
        balance_pruned = len(raw_candidates) - len(balanced)
        raw_candidates = balanced
    candidates_to_resolve, pruning = prune_ranked(
        raw_candidates, options.runtime.candidate_limit,
        key=lambda row: (abs(package_value(row[1]) - package_value(row[2])), row),
    )
    if progress_callback and pruning["pruned"]:
        progress_callback("Applying approximate value filter", pruning["evaluated"],
                          pruning["generated"], "candidates")
    resolved = {}
    if progress_callback:
        progress_callback(f"Resolving required drops for {trade_type} trades",
                          0, len(candidates_to_resolve), "trades")
    for index, (partner_id, my_out, partner_out) in enumerate(candidates_to_resolve, start=1):
        try:
            resolution = select_trade_resolution(
                baseline, my_team_id, partner_id, my_out, partner_out,
                options.effective_week or baseline.state.current_week, options,
                roster_ids=roster_ids, players=players,
                projection_lookup=projection_lookup, score_cache=score_cache)
            resolved[(partner_id, my_out, partner_out)] = resolution
        except (RuntimeError, SeasonModelError):
            # Some required-drop choices satisfy transaction constraints but
            # cannot fill every required lineup slot.  They are invalid trade
            # candidates, not a fatal error for the rest of the search.
            pass
        if progress_callback and (index % 100 == 0 or index == len(candidates_to_resolve)):
            progress_callback(f"Resolving required drops for {trade_type} trades",
                              index, len(candidates_to_resolve), "trades")
    constrained = [(*key, *resolution) for key, resolution in resolved.items()]
    candidates = []
    if progress_callback:
        progress_callback("Validating legal trade candidates", 0, len(constrained), "trades")
    for index, (partner_id, my_out, partner_out, my_drops, partner_drops) in enumerate(constrained, start=1):
        try:
            apply_transaction(baseline.state, trade_transaction(
                baseline.state, team_id=my_team_id, partner_id=partner_id,
                give=my_out, receive=partner_out,
                effective_week=options.effective_week or baseline.state.current_week,
                team_drops=my_drops, partner_drops=partner_drops,
            ))
            candidates.append((partner_id, my_out, partner_out, my_drops, partner_drops))
        except SeasonModelError:
            pass
        if progress_callback and (index % 100 == 0 or index == len(constrained)):
            progress_callback("Validating legal trade candidates", index, len(constrained), "trades")
    lossless_filtered = ((len(candidates_to_resolve) - len(resolved))
                         + (len(constrained) - len(candidates)))

    my_baseline_future = tuple(
        baseline_weekly[(my_team_id, week)]
        for week in future_weeks
    )

    evaluations: list[dict[str, Any]] = []
    valid_internal: list[dict[str, Any]] = []
    invalid_count = 0
    counter = 0

    progress = tqdm(
        total=len(candidates),
        desc=f"Evaluating all {trade_type} trades",
        unit="trade",
        dynamic_ncols=True,
        callback=progress_callback,
        leave=True,
    )

    candidate_map = {(partner_id, my_out, partner_out):(my_drops, partner_drops)
                     for partner_id, my_out, partner_out, my_drops, partner_drops in candidates}
    for partner_id, partner_packages in partner_info:
        partner_base = frozenset(roster_ids[partner_id])
        partner_baseline_future = tuple(
            baseline_weekly[(partner_id, week)]
            for week in future_weeks
        )
        for my_out in my_packages:
            my_remaining = roster_ids[my_team_id] - set(my_out)
            for partner_out in partner_packages:
                resolution = candidate_map.get((partner_id, my_out, partner_out))
                if resolution is None:
                    continue
                my_drops, partner_drops = resolution
                counter += 1
                trade_id = (
                    f"{trade_type.replace('-', '')}_"
                    f"{partner_id}_{counter:06d}"
                )

                base_record = _base_export_record(
                    trade_id=trade_id,
                    trade_type=trade_type,
                    partner_id=partner_id,
                    partner_name=names[partner_id],
                    my_out=my_out,
                    partner_out=partner_out,
                    my_drops=my_drops,
                    partner_drops=partner_drops,
                    players=players,
                )

                my_new_ids = frozenset(
                    (my_remaining | set(partner_out)) - set(my_drops)
                )
                partner_new_ids = frozenset(
                    (roster_ids[partner_id] - set(partner_out))
                    | set(my_out)
                ) - set(partner_drops)

                try:
                    my_scores = _score_roster_weeks(
                        my_new_ids,
                        team_id=my_team_id,
                        team_name=names[my_team_id],
                        weeks=future_weeks,
                        players=players,
                        starter_slots=baseline.state.starter_slots,
                        projection_lookup=projection_lookup,
                        cache=score_cache,
                    )
                    partner_scores = _score_roster_weeks(
                        partner_new_ids,
                        team_id=partner_id,
                        team_name=names[partner_id],
                        weeks=future_weeks,
                        players=players,
                        starter_slots=baseline.state.starter_slots,
                        projection_lookup=projection_lookup,
                        cache=score_cache,
                    )
                except (RuntimeError, SeasonModelError) as exc:
                    invalid_count += 1
                    evaluations.append(
                        {
                            **base_record,
                            "evaluation_status": "INVALID_LINEUP",
                            "trade_classification": "INVALID_LINEUP",
                            "invalid_reason": str(exc),
                        }
                    )
                    progress.update(1)
                    continue

                my_scores = _preserve_actual_scores(baseline, my_team_id, future_weeks, my_scores)
                partner_scores = _preserve_actual_scores(baseline, partner_id, future_weeks, partner_scores)
                my_weekly_metrics = _weekly_lineup_metrics(
                    "my", my_baseline_future, my_scores, future_weeks
                )
                partner_weekly_metrics = _weekly_lineup_metrics(
                    "partner",
                    partner_baseline_future,
                    partner_scores,
                    future_weeks,
                )
                my_avg_gain = my_weekly_metrics[
                    "my_avg_remaining_season_lineup_gain"
                ]
                partner_avg_gain = partner_weekly_metrics[
                    "partner_avg_remaining_season_lineup_gain"
                ]
                mutual_avg_gain = min(my_avg_gain, partner_avg_gain)
                combined_avg_gain = my_avg_gain + partner_avg_gain
                my_sustained_gain = my_weekly_metrics[
                    "my_sustained_weekly_lineup_gain"
                ]
                partner_sustained_gain = partner_weekly_metrics[
                    "partner_sustained_weekly_lineup_gain"
                ]
                classification = _classify_trade(
                    my_sustained_gain,
                    partner_sustained_gain,
                )

                export_record = {
                    **base_record,
                    "evaluation_status": "VALID",
                    "trade_classification": classification,
                    "invalid_reason": "",
                    "current_scoring_week": future_weeks[0],
                    "remaining_scoring_weeks": len(future_weeks),
                    "remaining_regular_season_weeks": len(regular_weeks),
                    "playoff_window_weeks": len(postseason_weeks),
                    **my_weekly_metrics,
                    **partner_weekly_metrics,
                    **_phase_lineup_metrics(
                        "my",
                        "regular_season",
                        my_baseline_future,
                        my_scores,
                        future_weeks,
                        regular_weeks,
                    ),
                    **_phase_lineup_metrics(
                        "partner",
                        "regular_season",
                        partner_baseline_future,
                        partner_scores,
                        future_weeks,
                        regular_weeks,
                    ),
                    **_phase_lineup_metrics(
                        "my",
                        "playoff_window",
                        my_baseline_future,
                        my_scores,
                        future_weeks,
                        postseason_weeks,
                    ),
                    **_phase_lineup_metrics(
                        "partner",
                        "playoff_window",
                        partner_baseline_future,
                        partner_scores,
                        future_weeks,
                        postseason_weeks,
                    ),
                    "mutual_avg_remaining_season_lineup_gain": (
                        mutual_avg_gain
                    ),
                    "combined_avg_remaining_season_lineup_gain": (
                        combined_avg_gain
                    ),
                    "mutual_sustained_weekly_lineup_gain": min(
                        my_sustained_gain, partner_sustained_gain
                    ),
                    "combined_sustained_weekly_lineup_gain": (
                        my_sustained_gain + partner_sustained_gain
                    ),
                    "my_positive_gain": my_sustained_gain > EPSILON,
                    "partner_positive_gain": partner_sustained_gain > EPSILON,
                    "both_positive_gain": (
                        my_sustained_gain > EPSILON
                        and partner_sustained_gain > EPSILON
                    ),
                }

                evaluations.append(export_record)
                valid_internal.append(
                    {
                        "export": export_record,
                        "my_scores": my_scores,
                        "partner_scores": partner_scores,
                    }
                )
                progress.update(1)

    progress.close()

    # Rank by the weaker side's sustained gain first. Removing each side's
    # single best week prevents a bye/injury fill-in from leading the search.
    # is informational only; no trade is removed from the output.
    valid_internal.sort(
        key=lambda x: (
            -x["export"]["mutual_sustained_weekly_lineup_gain"],
            -x["export"]["combined_sustained_weekly_lineup_gain"],
            -x["export"]["my_sustained_weekly_lineup_gain"],
            -x["export"]["mutual_avg_remaining_season_lineup_gain"],
            x["export"]["partner_team_id"],
            x["export"]["trade_id"],
        )
    )

    for rank, item in enumerate(valid_internal, start=1):
        item["export"]["rank_by_mutual_gain_within_type"] = rank

    for item in tqdm(
        valid_internal,
        desc=f"Reprojecting all valid {trade_type} trades",
        unit="trade",
        dynamic_ncols=True,
        callback=progress_callback,
        leave=True,
    ):
        record = item["export"]
        partner_id = record["partner_team_id"]
        my_scores = item["my_scores"]
        partner_scores = item["partner_scores"]

        replacements: dict[tuple[int, int], float] = {}
        for week, my_score, partner_score in zip(
            future_weeks,
            my_scores,
            partner_scores,
            strict=True,
        ):
            replacements[(my_team_id, week)] = my_score
            replacements[(partner_id, week)] = partner_score

        (
            scenario_metrics,
            postseason_summary,
            scenario_regular_matchups,
            scenario_postseason_matchups,
        ) = _scenario_metrics(baseline, replacements)

        my_before = baseline_metrics[my_team_id]
        my_after = scenario_metrics[my_team_id]
        partner_before = baseline_metrics[partner_id]
        partner_after = scenario_metrics[partner_id]

        record.update(
            {
                "my_projected_wins_before": my_before["wins"],
                "my_projected_wins_after": my_after["wins"],
                "my_projected_wins_change": (
                    my_after["wins"] - my_before["wins"]
                ),
                "partner_projected_wins_before": partner_before["wins"],
                "partner_projected_wins_after": partner_after["wins"],
                "partner_projected_wins_change": (
                    partner_after["wins"] - partner_before["wins"]
                ),
                **_projected_game_flip_metrics(
                    "my",
                    my_team_id,
                    baseline.regular_season_matchups,
                    scenario_regular_matchups,
                ),
                **_projected_game_flip_metrics(
                    "partner",
                    partner_id,
                    baseline.regular_season_matchups,
                    scenario_regular_matchups,
                ),
                "my_regular_seed_before": my_before["regular_seed"],
                "my_regular_seed_after": my_after["regular_seed"],
                "my_regular_seed_improvement": (
                    my_before["regular_seed"] - my_after["regular_seed"]
                ),
                "partner_regular_seed_before": partner_before["regular_seed"],
                "partner_regular_seed_after": partner_after["regular_seed"],
                "partner_regular_seed_improvement": (
                    partner_before["regular_seed"]
                    - partner_after["regular_seed"]
                ),
                "my_final_place_before": my_before["final_place"],
                "my_final_place_after": my_after["final_place"],
                "my_final_place_improvement": (
                    my_before["final_place"] - my_after["final_place"]
                ),
                "partner_final_place_before": partner_before["final_place"],
                "partner_final_place_after": partner_after["final_place"],
                "partner_final_place_improvement": (
                    partner_before["final_place"]
                    - partner_after["final_place"]
                ),
                "my_playoff_path_before": _playoff_path(
                    my_team_id, baseline.postseason_matchups
                ),
                "my_playoff_path_after": _playoff_path(
                    my_team_id, scenario_postseason_matchups
                ),
                "partner_playoff_path_before": _playoff_path(
                    partner_id, baseline.postseason_matchups
                ),
                "partner_playoff_path_after": _playoff_path(
                    partner_id, scenario_postseason_matchups
                ),
                "both_final_places_nonworse": (
                    my_after["final_place"] <= my_before["final_place"]
                    and partner_after["final_place"] <= partner_before["final_place"]
                ),
                "projected_champion_before_trade": baseline.summary[
                    "champion_team"
                ],
                "projected_champion_after_trade": postseason_summary[
                    "champion_team"
                ],
            }
        )

    valid_exports = [item["export"] for item in valid_internal]

    # Put valid trades first in rank order, then invalid lineup combinations.
    invalid_exports = [
        row for row in evaluations
        if row["evaluation_status"] == "INVALID_LINEUP"
    ]
    all_sorted = valid_exports + invalid_exports

    class_counts: dict[str, int] = {}
    for row in valid_exports:
        cls = row["trade_classification"]
        class_counts[cls] = class_counts.get(cls, 0) + 1

    summary = {
        "trade_type": trade_type,
        "total_combinations": total_combinations,
        "balance_filter_enabled": getattr(options, "balance_filter", False),
        "balance_filtered": balance_pruned,
        "minimum_value_ratio": getattr(options, "minimum_value_ratio", None) if getattr(options, "balance_filter", False) else None,
        "search_mode": options.runtime.mode,
        "candidate_limit": options.runtime.candidate_limit,
        "legal_candidates": len(candidates) + pruning["pruned"],
        "lossless_filtered": lossless_filtered,
        **pruning,
        "valid_trades_evaluated": len(valid_exports),
        "invalid_lineup_trades": invalid_count,
        "both_positive": class_counts.get("BOTH_POSITIVE", 0),
        "my_team_only_positive": class_counts.get("MY_TEAM_ONLY", 0),
        "partner_only_positive": class_counts.get("PARTNER_ONLY", 0),
        "neither_positive": class_counts.get("NEITHER_POSITIVE", 0),
        "fully_reprojected_trades": len(valid_exports),
        "best_mutual_avg_remaining_season_lineup_gain": (
            valid_exports[0][
                "mutual_avg_remaining_season_lineup_gain"
            ]
            if valid_exports else None
        ),
    }

    return all_sorted, summary


def evaluate_all_trades(
    *,
    baseline: SeasonProjection,
    trade_config: TradeConfig,
    progress_callback=None,
    options: TradeSearchOptions | None = None,
) -> TradeSearchResult:
    """Evaluate configured one-, two-, and three-player trade packages.

    Every rostered player is eligible, including bench players, kickers, and
    D/ST. Every valid trade is fully reprojected through the regular season
    and postseason; no ranking threshold or top-N filter is applied.
    """
    options = options or TradeSearchOptions()
    names = _team_name_map(baseline.state.teams)
    if trade_config.my_team_id not in names:
        raise RuntimeError(
            f"MY_TEAM_ID={trade_config.my_team_id} was not found in the "
            "league. Check teams.csv."
        )

    regular_end = int(
        max(baseline.state.rules.period_weeks[baseline.state.rules.regular_periods])
    )
    current_week = options.effective_week or int(baseline.summary["current_scoring_period"])
    if not baseline.state.current_week <= current_week <= baseline.state.final_week:
        raise RuntimeError("Trade search effective week must be within the remaining season.")
    final_week = int(baseline.summary["final_scoring_period"])

    future_weeks = tuple(range(current_week, final_week + 1))
    if not future_weeks:
        raise RuntimeError("No scoring weeks remain to evaluate trades.")
    regular_weeks = tuple(
        week for week in future_weeks if week <= regular_end
    )
    postseason_weeks = tuple(
        week for week in future_weeks if week > regular_end
    )

    roster_ids = _roster_ids_by_team(baseline.state.rosters)
    players = _player_map(baseline.state.rosters)
    projection_lookup = _projection_lookup(
        baseline.state.player_projections
    )
    score_cache: dict[
        tuple[frozenset[int], tuple[int, ...]],
        tuple[float, ...],
    ] = {}

    all_evaluations: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    print(
        f"Searching trades for {names[trade_config.my_team_id]} "
        f"(team_id={trade_config.my_team_id})."
    )
    print(
        f"Trade evaluation horizon: Weeks {current_week}-{final_week}."
    )
    print(
        "All rostered positions are included. Every retained valid trade "
        "will receive a full standings/playoff projection."
    )

    for give_size, receive_size in options.package_shapes:
        if give_size not in (1, 2, 3) or receive_size not in (1, 2, 3):
            raise RuntimeError("Trade search supports one-, two-, and three-player sides.")
        evaluations, summary = _evaluate_all_trades_for_type(
            give_size=give_size,
            receive_size=receive_size,
            progress_callback=progress_callback,
            baseline=baseline,
            trade_config=trade_config,
            roster_ids=roster_ids,
            players=players,
            projection_lookup=projection_lookup,
            score_cache=score_cache,
            future_weeks=future_weeks,
            regular_weeks=regular_weeks,
            postseason_weeks=postseason_weeks,
            options=options,
        )

        all_evaluations.extend(evaluations)
        summaries.append(summary)

    return TradeSearchResult(
        all_evaluations=all_evaluations,
        search_summary=summaries,
    )
