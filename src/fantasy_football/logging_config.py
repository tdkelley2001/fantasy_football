"""Central logging configuration for command-line processes."""

from __future__ import annotations

import logging
from typing import TextIO


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str, *, stream: TextIO | None = None) -> None:
    """Configure root logging with an already validated named level."""

    normalized = level.upper()
    numeric_level = logging.getLevelNamesMapping().get(normalized)
    if numeric_level is None or normalized == "NOTSET":
        raise ValueError(f"Unsupported logging level: {level}")
    logging.basicConfig(
        level=numeric_level,
        format=LOG_FORMAT,
        stream=stream,
        force=True,
    )
