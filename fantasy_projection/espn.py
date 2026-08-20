from __future__ import annotations

import json
import time
from typing import Any, Iterable

import requests
from tqdm import tqdm

from .config import Config


BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
TIMEOUT_SECONDS = 30
REQUEST_PAUSE_SECONDS = 0.10
PLAYER_LIMIT = 2000


def as_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class EspnClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 ESPN fantasy deterministic projection engine"
                ),
                "Accept": "application/json,text/plain,*/*",
            }
        )

        if config.espn_s2 and config.swid:
            self.session.cookies.update(
                {
                    "espn_s2": config.espn_s2,
                    "SWID": config.swid,
                }
            )

    @property
    def league_url(self) -> str:
        return (
            f"{BASE}/seasons/{self.config.season}/segments/0/"
            f"leagues/{self.config.league_id}"
        )

    def get_league(
        self,
        view: str,
        *,
        scoring_period_id: int | None = None,
        fantasy_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"view": view}
        if scoring_period_id is not None:
            params["scoringPeriodId"] = scoring_period_id

        headers = {}
        if fantasy_filter is not None:
            headers["X-Fantasy-Filter"] = json.dumps(fantasy_filter)

        response = self.session.get(
            self.league_url,
            params=params,
            headers=headers or None,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Unexpected ESPN response type for view={view}: "
                f"{type(payload).__name__}"
            )

        time.sleep(REQUEST_PAUSE_SECONDS)
        return payload


def find_player_nodes(obj: Any) -> Iterable[dict[str, Any]]:
    """Recursively find raw ESPN player dictionaries."""
    if isinstance(obj, dict):
        if (
            "id" in obj
            and ("fullName" in obj or "stats" in obj)
            and (
                "proTeamId" in obj
                or "eligibleSlots" in obj
                or "stats" in obj
            )
        ):
            yield obj

        for value in obj.values():
            yield from find_player_nodes(value)

    elif isinstance(obj, list):
        for value in obj:
            yield from find_player_nodes(value)


def pull_weekly_player_projections(
    client: EspnClient,
    *,
    first_week: int,
    final_week: int,
) -> list[dict[str, Any]]:
    """Pull one ESPN projected-fantasy-points record per player/week."""
    rows: list[dict[str, Any]] = []

    kona_filter = {
        "players": {
            "limit": PLAYER_LIMIT,
            "sortPercOwned": {
                "sortPriority": 1,
                "sortAsc": False,
            },
        }
    }

    weeks = range(first_week, final_week + 1)

    for week in tqdm(
        weeks,
        desc="Pulling ESPN projections",
        unit="week",
        dynamic_ncols=True,
    ):
        payload = client.get_league(
            "kona_player_info",
            scoring_period_id=week,
            fantasy_filter=kona_filter,
        )

        players_by_id: dict[int, dict[str, Any]] = {}
        for player in find_player_nodes(payload):
            player_id = as_int(player.get("id"))
            if player_id is None:
                continue

            old = players_by_id.get(player_id)
            if old is None or len(player.get("stats", [])) > len(
                old.get("stats", [])
            ):
                players_by_id[player_id] = player

        for player_id, player in players_by_id.items():
            candidates = []

            for stat in player.get("stats", []):
                if not isinstance(stat, dict):
                    continue
                if as_int(stat.get("seasonId")) != client.config.season:
                    continue
                if as_int(stat.get("scoringPeriodId")) != week:
                    continue

                source_id = as_int(stat.get("statSourceId"))
                if source_id in (None, 0):
                    continue

                split_id = as_int(stat.get("statSplitTypeId"))
                preference = (
                    0 if source_id == 1 and split_id == 1 else 1
                )
                candidates.append((preference, stat))

            if not candidates:
                continue

            candidates.sort(key=lambda x: x[0])
            stat = candidates[0][1]

            rows.append(
                {
                    "player_id": player_id,
                    "player_name": player.get("fullName"),
                    "week": week,
                    "projected_points": as_float(
                        stat.get("appliedTotal")
                    ),
                    "stat_source_id": as_int(
                        stat.get("statSourceId")
                    ),
                    "stat_split_type_id": as_int(
                        stat.get("statSplitTypeId")
                    ),
                    "pro_team_id": as_int(player.get("proTeamId")),
                    "default_position_id": as_int(
                        player.get("defaultPositionId")
                    ),
                    "injury_status": player.get("injuryStatus"),
                }
            )

    deduped: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        deduped[(row["player_id"], row["week"])] = row

    result = list(deduped.values())
    result.sort(
        key=lambda x: (
            x["week"],
            -x["projected_points"],
            x["player_name"] or "",
        )
    )
    return result
