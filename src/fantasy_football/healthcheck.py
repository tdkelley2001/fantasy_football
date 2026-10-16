"""Local M0.1 setup health check; performs no ESPN or network access."""

from __future__ import annotations

import logging

from fantasy_football.config import SettingsError, load_settings
from fantasy_football.logging_config import configure_logging


def main() -> int:
    try:
        settings = load_settings()
    except SettingsError as exc:
        print(f"Configuration invalid: {exc}")
        return 2

    configure_logging(settings.log_level)
    logging.getLogger(__name__).info("M0.1 setup health check passed")
    return 0
