from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    league_id: int
    season: int
    espn_s2: str | None
    swid: str | None


def load_config() -> Config:
    """Load runtime configuration from .env. No CLI parser is used."""
    load_dotenv()

    league_id_raw = os.getenv("ESPN_LEAGUE_ID")
    season_raw = os.getenv("ESPN_SEASON", "2026")

    if not league_id_raw:
        raise RuntimeError("ESPN_LEAGUE_ID is missing from .env.")

    try:
        league_id = int(league_id_raw)
        season = int(season_raw)
    except ValueError as exc:
        raise RuntimeError(
            "ESPN_LEAGUE_ID and ESPN_SEASON must be integers."
        ) from exc

    return Config(
        league_id=league_id,
        season=season,
        espn_s2=os.getenv("ESPN_S2"),
        swid=os.getenv("ESPN_SWID"),
    )
