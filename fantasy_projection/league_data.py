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
        rows.append(
            {
                "team_id": as_int(team.get("id")),
                "team_name": team.get("name"),
                "abbrev": team.get("abbrev"),
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


def normalize_regular_season_schedule(
    matchup_payload: dict[str, Any],
    settings_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    regular_period_count = as_int(
        get_schedule_settings(settings_payload).get(
            "matchupPeriodCount"
        ),
        0,
    ) or 0

    rows = []

    for matchup in matchup_payload.get("schedule", []):
        period = as_int(matchup.get("matchupPeriodId"))

        if period is None or period > regular_period_count:
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
                "espn_winner": matchup.get(
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


def matchup_period_scoring_weeks(
    settings_payload: dict[str, Any],
    matchup_period: int,
) -> list[int]:
    mapping = get_schedule_settings(settings_payload).get(
        "matchupPeriods",
        {},
    )

    raw = mapping.get(str(matchup_period))
    if raw is None:
        raw = mapping.get(matchup_period)

    if isinstance(raw, list):
        weeks = [as_int(x) for x in raw]
        return [x for x in weeks if x is not None]

    return [matchup_period]
