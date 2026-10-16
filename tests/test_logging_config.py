from __future__ import annotations

from io import StringIO
import logging

import pytest

from fantasy_football.logging_config import configure_logging


def test_configure_logging_uses_requested_level() -> None:
    stream = StringIO()
    configure_logging("WARNING", stream=stream)

    logger = logging.getLogger("smoke")
    logger.info("hidden")
    logger.warning("visible")

    output = stream.getvalue()
    assert "hidden" not in output
    assert "WARNING smoke visible" in output


def test_configure_logging_rejects_unknown_level() -> None:
    with pytest.raises(ValueError, match="Unsupported logging level"):
        configure_logging("verbose")
