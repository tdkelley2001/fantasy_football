"""Technical references agree with source shape without network or databases."""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

from fantasy_football.app.contracts import (
    API_SCHEMA_VERSION,
    ActionSearchRequest,
    BaselineAnalysisRequest,
    ManualScenarioRequest,
    NormalOutcomeModelConfiguration,
    SnapshotRefreshRequest,
)
from fantasy_football.canonical.model import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS
from fantasy_football.monte_carlo import MonteCarloConfig
from fantasy_football.partial_week import PARTIAL_WEEK_ARTIFACT_VERSION
from fantasy_football.season_simulator import simulate_deterministic_season
from fantasy_football.snapshot_store import DATABASE_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8-sig")


def test_canonical_reference_versions_match_current_publication_and_reads() -> None:
    canonical = read("docs/CANONICAL_MODEL.md")
    storage = read("docs/SNAPSHOT_STORAGE.md")
    assert f"Schema Version {SCHEMA_VERSION}" in canonical
    versions = ", ".join(map(str, SUPPORTED_SCHEMA_VERSIONS))
    assert f"supported document reads are **{versions}**" in canonical
    assert f"New publication requires **{SCHEMA_VERSION}**" in canonical
    assert f"canonical schema **{SCHEMA_VERSION}**" in storage
    assert f"canonical schemas **{versions}**" in storage
    assert f"SQLite remains schema **{DATABASE_SCHEMA_VERSION}**" in storage
    assert f"artifact version **{PARTIAL_WEEK_ARTIFACT_VERSION}**" in canonical


def test_documented_api_inventory_matches_every_implemented_versioned_route() -> None:
    tree = ast.parse(read("src/fantasy_football/app/http.py"))
    actual = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "app"
                and decorator.func.attr in {"get", "post", "delete"}
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and str(decorator.args[0].value).startswith("/api/v1/")
            ):
                actual.add((decorator.func.attr.upper(), decorator.args[0].value))
    documented = re.findall(
        r"^\| (GET|POST|DELETE) \| `([^`]+)` \|",
        read("docs/APPLICATION_SERVICE.md"),
        re.MULTILINE,
    )
    assert actual
    assert len(documented) == len(set(documented))
    assert set(documented) == actual


def test_public_refresh_shape_and_engine_only_limits_are_documented() -> None:
    api = read("docs/APPLICATION_SERVICE.md")
    assert f"public schema version **{API_SCHEMA_VERSION}**" in api
    for name in SnapshotRefreshRequest.model_fields:
        assert f"`{name}`" in api
    assert SnapshotRefreshRequest.model_fields["first_simulation_week"].default is None
    for request in (
        BaselineAnalysisRequest,
        ManualScenarioRequest,
        ActionSearchRequest,
    ):
        assert "partial_week" not in request.model_fields
        assert (
            request.model_fields["outcome_model"].annotation
            is NormalOutcomeModelConfiguration
        )
        assert request.model_config["extra"] == "forbid"
    assert (
        "empirical selection and partial-week execution have no public request fields"
        in api
    )


def test_partial_contract_keeps_distinct_opt_in_engine_entry_points() -> None:
    assert (
        inspect.signature(simulate_deterministic_season)
        .parameters["partial_week"]
        .default
        is None
    )
    assert MonteCarloConfig.__dataclass_fields__["partial_week"].default is None
    document = read("docs/LW2_PARTIAL_WEEK_CONTRACT.md")
    current = document.split("## Current capability map", 1)[1].split(
        "## Original LW2.1", 1
    )[0]
    for name in (
        "DeterministicPartialWeekInput",
        "MonteCarloPartialWeekInput",
        "engine-only, Verified by tests",
        "every rostered current player must be unstarted",
        "Completed, in-progress, missing, nonparticipating or unresolved",
        "cutoff",
        "carry",
        "locked",
    ):
        assert name in current
