from __future__ import annotations

from typing import Any

from .espn import as_float, as_int


LINEUP_SLOT_NAMES = {
    0: "QB",
    1: "TQB",
    2: "RB",
    3: "RB/WR",
    4: "WR",
    5: "WR/TE",
    6: "TE",
    7: "OP",
    16: "D/ST",
    17: "K",
    20: "BE",
    21: "IR",
    23: "FLEX",
}

NON_STARTER_SLOT_IDS = {20, 21}


def get_schedule_settings(
    settings_payload: dict[str, Any],
) -> dict[str, Any]:
    return settings_payload["settings"]["scheduleSettings"]


def get_roster_settings(
    settings_payload: dict[str, Any],
) -> dict[str, Any]:
    return settings_payload["settings"]["rosterSettings"]




def normalize_teams(
    team_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []

    for team in team_payload.get("teams", []):
        transaction_counter = team.get("transactionCounter")
        if not isinstance(transaction_counter, dict):
            transaction_counter = {}
        rows.append(
            {
                "team_id": as_int(team.get("id")),
                "team_name": team.get("name"),
                "abbrev": team.get("abbrev"),
                "waiver_rank": as_int(team.get("waiverRank")),
                "acquisitions": as_int(
                    transaction_counter.get("acquisitions"), 0
                ),
                "acquisition_budget_spent": as_float(
                    transaction_counter.get("acquisitionBudgetSpent")
                ),
                "transaction_locked": bool(
                    team.get("isTransactionLocked", False)
                ),
            }
        )

    rows.sort(key=lambda x: x["team_id"] or 0)
    return rows


def normalize_rosters(
    roster_payload: dict[str, Any],
    teams: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    names = {
        row["team_id"]: row["team_name"]
        for row in teams
    }

    rows = []

    for team in roster_payload.get("teams", []):
        team_id = as_int(team.get("id"))

        for entry in team.get("roster", {}).get("entries", []):
            pool_entry = entry.get("playerPoolEntry", {})
            player = pool_entry.get("player", {})

            player_id = as_int(player.get("id"))
            if player_id is None:
                continue

            eligible_slots = [
                int(slot)
                for slot in player.get("eligibleSlots", [])
                if as_int(slot) is not None
            ]

            rows.append(
                {
                    "team_id": team_id,
                    "team_name": names.get(team_id),
                    "player_id": player_id,
                    "player_name": player.get("fullName"),
                    "default_position_id": as_int(
                        player.get("defaultPositionId")
                    ),
                    "pro_team_id": as_int(player.get("proTeamId")),
                    "eligible_slots": eligible_slots,
                    "current_lineup_slot_id": as_int(
                        entry.get("lineupSlotId")
                    ),
                    "injury_status": player.get("injuryStatus"),
                    "acquisition_type": entry.get(
                        "acquisitionType"
                    ),
                    "player_status": pool_entry.get("status"),
                    "droppable": player.get("droppable", True),
                    "lineup_locked": bool(
                        pool_entry.get("lineupLocked", False)
                    ),
                    "roster_locked": bool(
                        pool_entry.get("rosterLocked", False)
                    ),
                }
            )

    rows.sort(
        key=lambda x: (
            x["team_id"] or 0,
            x["player_name"] or "",
        )
    )
    return rows


def build_starter_slots(
    settings_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    counts = get_roster_settings(settings_payload).get(
        "lineupSlotCounts",
        {},
    )

    slots = []

    for raw_slot_id, raw_count in counts.items():
        slot_id = as_int(raw_slot_id)
        count = as_int(raw_count, 0) or 0

        if (
            slot_id is None
            or count <= 0
            or slot_id in NON_STARTER_SLOT_IDS
        ):
            continue

        for instance in range(1, count + 1):
            slots.append(
                {
                    "slot_id": slot_id,
                    "slot_name": LINEUP_SLOT_NAMES.get(
                        slot_id,
                        f"SLOT_{slot_id}",
                    ),
                    "slot_instance": instance,
                }
            )

    if not slots:
        raise RuntimeError(
            "No starting lineup slots found in ESPN settings."
        )

    return slots


def normalize_schedule(
    matchup_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []

    for matchup in matchup_payload.get("schedule", []):
        period = as_int(matchup.get("matchupPeriodId"))

        if period is None:
            continue

        home = matchup.get("home") or {}
        away = matchup.get("away") or {}

        home_id = as_int(home.get("teamId"))
        away_id = as_int(away.get("teamId"))

        if home_id is None or away_id is None:
            continue

        rows.append(
            {
                "matchup_period": period,
                "home_team_id": home_id,
                "away_team_id": away_id,
                "winner": matchup.get(
                    "winner",
                    "UNDECIDED",
                ),
                "actual_home_points": (
                    as_float(home.get("totalPoints"))
                    if home.get("totalPoints") is not None
                    else None
                ),
                "actual_away_points": (
                    as_float(away.get("totalPoints"))
                    if away.get("totalPoints") is not None
                    else None
                ),
            }
        )

    rows.sort(
        key=lambda x: (
            x["matchup_period"],
            x["home_team_id"],
        )
    )
    return rows


def normalize_season_rules(settings_payload):
    """Translate supported ESPN settings once at the ingestion boundary."""
    from .season import SeasonRules, SeasonModelError
    settings = get_schedule_settings(settings_payload)
    regular = as_int(settings.get("matchupPeriodCount"))
    count = as_int(settings.get("playoffTeamCount"))
    if regular is None or count is None:
        raise SeasonModelError("ESPN schedule settings are missing season or playoff lengths.")
    if settings.get("divisionWinnerPlayoffSeed", 0) or settings.get("divisionCount", 0) > 1 or len(settings.get("divisions", [])) > 1:
        raise SeasonModelError("Division-based playoff seeding is not supported.")
    mapping = settings.get("matchupPeriods", {})
    period_weeks = {int(period): tuple(int(w) for w in weeks) for period, weeks in mapping.items()}
    round_lengths = settings.get("playoffMatchupPeriodLengthByRound", {})
    lengths = [int(round_lengths[k]) for k in sorted(round_lengths, key=int)] if count else []
    rounds = []
    for offset, length in enumerate(lengths, 1):
        weeks = period_weeks.get(regular + offset)
        if not weeks or len(weeks) != length:
            raise SeasonModelError("ESPN playoff week mapping does not match configured round lengths.")
        rounds.append(weeks)
    explicit_tiebreak = settings.get("playoffMatchupTieRule")
    if explicit_tiebreak not in (None, "HIGHER_SEED"):
        raise SeasonModelError(f"Unsupported ESPN playoff tiebreak: {explicit_tiebreak}.")
    return SeasonRules(regular_periods=regular, period_weeks=period_weeks,
                       playoff_team_count=count, playoff_rounds=tuple(rounds),
                       playoff_reseed=bool(settings.get("playoffReseed", False)),
                       consolation_ladder=not bool(settings.get("consolationLadderDisabled", False)),
                       seeding_tiebreak=settings.get("playoffSeedingRule", "UNSPECIFIED"))


def normalize_actual_weekly_points(matchup_payload, current_week):
    """Use only finished scoring weeks, never an in-progress week total."""
    from .season import SeasonModelError
    scores = {}
    for matchup in matchup_payload.get("schedule", []):
        for side in ("home", "away"):
            team = matchup.get(side) or {}
            team_id = as_int(team.get("teamId"))
            if team_id is None:
                continue
            for raw_week, points in team.get("pointsByScoringPeriod", {}).items():
                week = as_int(raw_week)
                completed = matchup.get("winner") in {"HOME", "AWAY", "TIE"}
                if week is None or week > current_week or (week == current_week and not completed) or points is None:
                    continue
                key = (team_id, week)
                value = float(points)
                if key in scores and scores[key] != value:
                    raise SeasonModelError("ESPN returned conflicting completed team-week scores.")
                scores[key] = value
    return [dict(team_id=team, week=week, points=points) for (team, week), points in sorted(scores.items())]
