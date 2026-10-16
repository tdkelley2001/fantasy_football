from __future__ import annotations

from fantasy_football.config import load_settings
from fantasy_football.logging_config import configure_logging


def test_repository_smoke() -> None:
    settings = load_settings(
        env_file=None,
        environ={
            "ESPN_LEAGUE_ID": "123456",
            "ESPN_SEASON": "2026",
            "LOG_LEVEL": "INFO",
        },
    )
    configure_logging(settings.log_level)

    assert settings.credentials is None
