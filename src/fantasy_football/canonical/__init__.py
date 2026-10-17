"""Canonical snapshot contracts and deterministic schema-v2 serialization."""

from fantasy_football.canonical.model import *  # noqa: F403
from fantasy_football.canonical.serialization import snapshot_from_json, snapshot_to_json
from fantasy_football.canonical.validation import (
    CanonicalValidationError,
    require_understood_rules,
    validate_snapshot,
)

__all__ = [
    "CanonicalValidationError",
    "require_understood_rules",
    "snapshot_from_json",
    "snapshot_to_json",
    "validate_snapshot",
]
