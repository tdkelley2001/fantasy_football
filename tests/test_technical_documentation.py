"""Technical references agree with source shape without network or databases."""

from __future__ import annotations

import ast
import inspect
import json
import re
from dataclasses import fields
from pathlib import Path
from typing import get_args

from fantasy_football.app.background import BackgroundRunPolicy
from fantasy_football.app.contracts import (
    API_SCHEMA_VERSION,
    ActionSearchRequest,
    BaselineAnalysisRequest,
    ErrorDetail,
    ManualScenarioRequest,
    NormalOutcomeModelConfiguration,
    RunStatus,
    SnapshotRefreshRequest,
)
from fantasy_football.app.service import SynchronousSearchSafetyPolicy
from fantasy_football.canonical.model import SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS
from fantasy_football.monte_carlo import MonteCarloConfig
from fantasy_football.partial_week import PARTIAL_WEEK_ARTIFACT_VERSION
from fantasy_football.season_simulator import simulate_deterministic_season
from fantasy_football.snapshot_store import DATABASE_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8-sig")


def test_verification_guide_covers_current_release_steps_and_actual_test_modules() -> (
    None
):
    guide = read("CONTRIBUTING.md")
    script = read("scripts/verify-release.ps1")
    default_steps = script.split("if ($IncludeWindowsProcessTests)", 1)[0]
    names = re.findall(r'Invoke-ReleaseStep "([^"]+)"', default_steps)
    assert names
    assert all(name in guide for name in names)
    modules = set(re.findall(r"tests/[a-z0-9_]+\.py", guide))
    assert modules
    assert all((ROOT / name).is_file() for name in modules)
    assert '"-m", "pytest", "-m", "not windows_process"' in script
    assert '-m "not windows_process"' in guide
    assert '"--omit=dev", "--audit-level=high"' in script
    assert "audit --omit=dev --audit-level=high" in guide


def test_verification_frontend_commands_and_navigation_match_current_sources() -> None:
    guide = read("CONTRIBUTING.md")
    scripts = json.loads(read("frontend/package.json"))["scripts"]
    commands = re.findall(r"npm\.cmd --prefix frontend run ([a-z-]+)", guide)
    assert commands
    assert all(command in scripts for command in commands)
    assert scripts["test"] == "vitest run"
    assert scripts["typecheck"] in guide
    assert scripts["build"] in guide
    for path in ("README.md", "AGENTS.md", "docs/INTERFACE.md", "docs/OPERATIONS.md"):
        assert "CONTRIBUTING.md" in read(path)


def test_canonical_reference_versions_match_current_publication_and_reads() -> None:
    data = read("docs/DATA.md")
    versions = ", ".join(map(str, SUPPORTED_SCHEMA_VERSIONS))
    assert f"canonical schema **{SCHEMA_VERSION}**" in data
    assert f"supported document reads **{versions}**" in data
    assert f"new publication requires **{SCHEMA_VERSION}**" in data
    assert f"SQLite snapshot schema **{DATABASE_SCHEMA_VERSION}**" in data
    assert f"companion artifact **{PARTIAL_WEEK_ARTIFACT_VERSION}**" in data


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


def test_application_admission_defaults_are_documented_from_current_policies() -> None:
    rows = dict(
        re.findall(
            r"^\| ((?:SynchronousSearchSafetyPolicy|BackgroundRunPolicy)\.\w+) \| ([0-9.]+) \|$",
            read("docs/APPLICATION_SERVICE.md"),
            re.MULTILINE,
        )
    )
    expected = {
        f"{policy.__name__}.{field.name}": float(field.default)
        for policy in (SynchronousSearchSafetyPolicy, BackgroundRunPolicy)
        for field in fields(policy)
    }
    assert {key: float(value) for key, value in rows.items()} == expected


def test_application_reference_covers_public_lifecycle_and_error_categories() -> None:
    document = read("docs/APPLICATION_SERVICE.md")
    categories = get_args(ErrorDetail.model_fields["category"].annotation)
    for value in (*get_args(RunStatus), *categories):
        assert re.search(rf"\b{re.escape(value)}\b", document), value
    for source in (
        "README.md",
        "docs/INTERFACE.md",
        "docs/architecture/overview.md",
        "CONTRIBUTING.md",
        "docs/BACKLOG.md",
    ):
        assert re.search(r"\]\([^)]*APPLICATION_SERVICE\.md(?:#[^)]*)?\)", read(source))


def test_product_workspace_availability_matches_shell_navigation() -> None:
    navigation = re.findall(
        r'\["\w+", "([^"]+)", \w+, (true|false)\]',
        read("frontend/src/App.tsx"),
    )
    assert len(navigation) == 5
    product = read("README.md")
    interface = read("docs/INTERFACE.md")
    for name, deferred in navigation:
        assert name in product and name in interface
        if deferred == "false":
            assert f"## {name}\n" in interface
        else:
            assert (
                name
                in product.split("| Unsupported / deferred |", 1)[1].split("\n", 1)[0]
            )
    for boundary in (
        "Accepted engine interfaces, not exposed in the browser/API",
        "fully unstarted",
        "Provisional / evidence-limited",
        "M8.4 release disposition remains pending",
        "safe whole-week boundary",
    ):
        assert boundary in product


def test_interface_display_bounds_are_backed_by_current_frontend() -> None:
    interface = read("docs/INTERFACE.md")
    explorer = read("frontend/src/OpportunityExplorer.tsx")
    api = read("frontend/src/lib/api.ts")
    simulation = read("frontend/src/SimulationCenter.tsx")
    page = re.search(r"const PAGE_SIZE=(\d+)", explorer)
    comparison = re.search(r"current.length<(\d+)", explorer)
    history = re.search(r"/api/v1/runs\?limit=(\d+)", api)
    assert page and comparison and history
    assert f"**{page[1]}-row server pages**" in interface
    assert int(comparison[1]) == 4 and "**four** paths" in interface
    assert f"newest {history[1]} records" in interface
    presets = re.findall(r"(?:quick|balanced|detailed):\{paths:(\d+)", simulation)
    assert len(presets) == 3
    assert "**" + " / ".join(presets) + "**" in interface
    assert "not complete lifetime history" in interface


def test_interface_preserves_request_and_accessibility_boundaries() -> None:
    interface = read("docs/INTERFACE.md")
    shell = read("frontend/src/App.tsx")
    manual = read("frontend/src/TradeLab.tsx")
    for name in ("war-room-theme", "war-room-snapshot"):
        assert name in shell and f"`{name}`" in interface
    assert "item.inert=true" in shell and "inert analytical background" in interface
    assert "retainedRequest" in manual and "monotonic token" in interface
    assert (
        "AbortController" in interface
        and "does not cancel an accepted backend job" in interface
    )
    assert "refresh declares dialog semantics" in interface
    assert "lacks equivalent tested focus containment" in interface
    for phrase in (
        "Interval unavailable",
        "no invented zero-width marker",
        "no extra multiplication by 100",
        "no inferred percentage or ETA",
    ):
        assert phrase.casefold() in interface.casefold()
    followup = (
        read("docs/BACKLOG.md")
        .split("## Interface follow-up disposition", 1)[1]
        .split("\n## ", 1)[0]
    )
    for term in (
        "glossary",
        "denominator",
        "runtime",
        "WR-017",
        "Superseded",
        "approval",
    ):
        assert term in followup


def test_mechanics_interfaces_have_distinct_documented_owners() -> None:
    owners = {
        "docs/SEASON_SIMULATOR.md": {
            "season_simulator": ("simulate_deterministic_season",),
            "lineup_optimizer": (
                "optimize_starting_lineup",
                "optimize_candidate_lineup",
            ),
            "weekly_engine": ("resolve_regular_season_week", "rank_standings"),
            "postseason": (
                "generate_championship_graph",
                "generate_consolation_graph",
                "resolve_postseason_seeds",
                "apply_postseason_team_scores",
                "score_frozen_postseason_week",
            ),
        },
        "docs/TRANSACTIONS.md": {
            "evolving_state": (
                "initialize_evolving_state",
                "validate_evolving_state",
                "validate_eligibility_evidence_artifact",
            ),
            "weekly_transactions": ("execute_weekly_essential_transactions",),
            "roster_value": (
                "value_roster",
                "value_hypothetical_roster",
                "compare_roster_values",
                "exhaustive_allocation_oracle",
            ),
            "transaction_cycle": (
                "enumerate_feasible_cycles",
                "execute_sequential_policy_reference",
                "validate_operational_policy_equivalence",
                "compare_sequential_to_feasible",
            ),
        },
    }
    for document, modules in owners.items():
        text = read(document)
        for module, names in modules.items():
            tree = ast.parse(read(f"src/fantasy_football/{module}.py"))
            actual = {
                node.name for node in tree.body if isinstance(node, ast.FunctionDef)
            }
            for name in names:
                assert name in actual and f"{name}(" in text, (document, name)
    oracle = "_exhaustive_small_correction_oracle"
    assert f"`{oracle}()" in read("docs/TRANSACTIONS.md")
    assert f"def {oracle}(" in read("tests/test_weekly_transactions.py")


def test_mechanics_authority_and_reference_coverage_remain_discoverable() -> None:
    canonical = read("docs/DATA.md")
    assert "TRANSACTIONS.md" in canonical
    assert "### Eligibility evidence trust boundary" not in canonical
    transactions = read("docs/TRANSACTIONS.md")
    for constraint in (
        "### Eligibility evidence trust boundary",
        "validated_fixture",
        "maximize vacancies filled",
        "minimize the target's best residual attainable lineup",
        "CURRENT_WAIVER",
        "reverse frozen opening priority",
        "legal_enumeration_complete",
        "determination_complete=False",
        "not jointly attainable",
        "independently disableable",
        "None, never substituted",
    ):
        assert constraint in transactions
    for path in (
        "README.md",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "docs/architecture/overview.md",
    ):
        assert "TRANSACTIONS.md" in read(path)
        assert "SEASON_SIMULATOR.md" in read(path)
    for path in ("docs/MANUAL_SCENARIOS.md", "docs/UNIFIED_ACTION_SEARCH.md"):
        assert "TRANSACTIONS.md#resulting-roster-valuation" in read(path)


def test_mechanics_limits_and_unimplemented_obligations_are_not_waived() -> None:
    season = read("docs/SEASON_SIMULATOR.md")
    for term in (
        "higher original postseason seed",
        "final_positions_by_ladder_position",
        "championship_complete_placement_mapping",
        "consolation_bye_reentry_mapping",
        "all_teams_continue_essential_acquisitions_v1",
        "independent round lists",
        "negative projections",
        "Decimal.from_float",
        "math.fsum",
    ):
        assert term.casefold() in season.casefold()
    detail = (
        read("docs/BACKLOG.md")
        .split("## Mechanics review obligations", 1)[1]
        .split("\n## ", 1)[0]
    )
    for term in (
        "WR-023",
        "precision 28",
        "Fraction",
        "WR-014",
        "guard",
        "calibration",
        "discount",
        "independent",
        "approval",
    ):
        assert term in detail


def test_data_reference_preserves_source_semantics_and_publication_boundary() -> None:
    from fantasy_football.canonical.model import (
        InterpretationStatus,
        ProjectionClass,
        ProjectionSource,
        SourceReference,
    )
    from fantasy_football.snapshot_store import SnapshotStore

    data = read("docs/DATA.md")
    for enum in (ProjectionClass, ProjectionSource, InterpretationStatus):
        for member in enum:
            assert member.value in data
    for field in fields(SourceReference):
        assert field.name in data
    for method in ("publish", "load", "verify", "check_database_integrity"):
        assert callable(getattr(SnapshotStore, method))
        assert f"{method}(" in data
    for contract in (
        "Present exactly zero",
        "Present finite negative",
        "effective_projection > 0",
        "Structural validity is not execution permission",
        "original canonical_json",
        "post-commit failure",
        "undroppable_player_mapping stays unverified",
        "false alone -> unknown",
        "matchup_period_configuration",
    ):
        assert contract in data


def test_research_reference_preserves_trust_and_scientific_promotion_gates() -> None:
    from fantasy_football.historical_dataset import (
        DATASET_SCHEMA_VERSION,
        ProjectionTemporalProvenance,
        ProjectionValueKind,
        validate_pregame_capture_manifest,
    )
    from fantasy_football.outcome_distribution_research import (
        EvidencePolicy,
        TemporalSplit,
    )

    research = read("docs/RESEARCH.md")
    assert f"HistoricalResearchDataset schema **{DATASET_SCHEMA_VERSION}**" in research
    for enum in (ProjectionTemporalProvenance, ProjectionValueKind):
        for member in enum:
            assert member.value in research
    assert EvidencePolicy.AUTHENTICATED_ONLY.value == "authenticated_only"
    assert "EvidencePolicy.AUTHENTICATED_ONLY" in research
    for field in fields(TemporalSplit):
        assert field.name in research
    assert (
        "independently_trusted_manifest_sha256"
        in inspect.signature(validate_pregame_capture_manifest).parameters
    )
    for gate in (
        "independently_trusted_manifest_sha256",
        "exact captured payload bytes",
        "player ID, season, week, raw projection, default position and NFL team",
        "not independent real-world authentication",
        "not a third sealed final-test set",
        "research recommendation pending independent review",
        "zero authenticated-pregame pairs",
        "sparse_partially_pooled_rows",
    ):
        assert gate in research


def test_data_research_authority_and_m0_role_checks_remain_discoverable() -> None:
    from fantasy_football.m0_verification import EVIDENCE_DOCUMENTS, build_report

    for path in (
        "README.md",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "docs/architecture/overview.md",
    ):
        text = read(path)
        assert "DATA.md" in text and "RESEARCH.md" in text
    report = build_report(ROOT)
    assert report.evidence_documents == EVIDENCE_DOCUMENTS
    assert len(report.evidence_roles) == 7
    assert all(not row["historical_content_verified"] for row in report.evidence_roles)
    assert "docs/MISSING_PROJECTION_POLICY.md" in report.evidence_documents
    backlog = read("docs/BACKLOG.md")
    assert "bounded M0 migration" in backlog
    assert "In Review" in backlog
