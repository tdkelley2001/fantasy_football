from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class TradeConfig:
    my_team_id: int
    top_n_per_type: int
    min_avg_weekly_gain: float
    reproject_all: bool


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False

    raise RuntimeError(
        f"{name} must be true/false, yes/no, 1/0, or on/off."
    )


def load_trade_config() -> TradeConfig:
    """Load trade-search settings from the same project .env file."""
    load_dotenv()

    my_team_id_raw = os.getenv("MY_TEAM_ID")
    if not my_team_id_raw:
        raise RuntimeError(
            "MY_TEAM_ID is missing from .env. Use teams.csv to identify "
            "your ESPN team_id and add MY_TEAM_ID=<id>."
        )

    try:
        my_team_id = int(my_team_id_raw)
        top_n_per_type = int(
            os.getenv("TRADE_TOP_N_PER_TYPE", "100")
        )

        if os.getenv("TRADE_MIN_FUTURE_GAIN") is not None:
            raise RuntimeError(
                "TRADE_MIN_FUTURE_GAIN is deprecated. Replace it with "
                "TRADE_MIN_AVG_WEEKLY_GAIN in .env."
            )

        min_avg_weekly_gain = float(
            os.getenv("TRADE_MIN_AVG_WEEKLY_GAIN", "0.50")
        )
    except ValueError as exc:
        raise RuntimeError(
            "MY_TEAM_ID and TRADE_TOP_N_PER_TYPE must be integers; "
            "TRADE_MIN_AVG_WEEKLY_GAIN must be numeric."
        ) from exc

    if top_n_per_type <= 0:
        raise RuntimeError("TRADE_TOP_N_PER_TYPE must be positive.")

    if min_avg_weekly_gain < 0:
        raise RuntimeError(
            "TRADE_MIN_AVG_WEEKLY_GAIN cannot be negative."
        )

    return TradeConfig(
        my_team_id=my_team_id,
        top_n_per_type=top_n_per_type,
        min_avg_weekly_gain=min_avg_weekly_gain,
        reproject_all=_env_bool("TRADE_REPROJECT_ALL", True),
    )
