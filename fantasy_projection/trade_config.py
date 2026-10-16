from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class TradeConfig:
    my_team_id: int


def load_my_team_id() -> int:
    """Load the user's ESPN team ID from the project environment."""
    load_dotenv()

    raw = os.getenv("MY_TEAM_ID")
    if not raw:
        raise RuntimeError(
            "MY_TEAM_ID is missing from .env. Add the teamId from your "
            "ESPN team's URL as MY_TEAM_ID=<id>."
        )

    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError("MY_TEAM_ID must be an integer.") from exc
