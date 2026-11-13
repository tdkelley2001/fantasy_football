"""Permanent requirements and evidence guards, not scientific/release acceptance.

These replace migration-inventory assertions; functional suites remain independent.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PERMANENT = {
    "AGENTS.md",
    "CONTRIBUTING.md",
    "README.md",
    "docs/APPLICATION_SERVICE.md",
    "docs/BACKLOG.md",
    "docs/DATA.md",
    "docs/INTERFACE.md",
    "docs/MANUAL_SCENARIOS.md",
    "docs/MONTE_CARLO.md",
    "docs/OPERATIONS.md",
    "docs/PARTIAL_WEEK.md",
    "docs/PLAYER_OUTCOME_MODEL.md",
    "docs/RESEARCH.md",
    "docs/SEASON_SIMULATOR.md",
    "docs/TRANSACTIONS.md",
    "docs/UNIFIED_ACTION_SEARCH.md",
    "docs/architecture/overview.md",
}
REQUIREMENTS = {
    "README.md": [
        "expected championship probability",
        "every manager",
        "ESPN is the sole initial projection source",
        "versioned official model",
        "not formally released",
        "M8.4 release disposition remains pending",
    ],
    "AGENTS.md": [
        "actual algorithm/formulas or pseudocode",
        "last validated implementation/model version",
        "minimal end-to-end smoke path",
        "only one participant",
        "counterexample",
        "resource-capped Monte Carlo",
        "Independently accepted decisions and requirements remain binding",
        "Only an explicitly approved successor",
        "BACKLOG preserves approved unimplemented",
        "README owns product scope/navigation",
        "reviewed pull requests",
        "Do not push changes directly to authoritative main",
    ],
    "CONTRIBUTING.md": [
        "sequential interval/stopping coverage",
        "aggregate-child",
        "feasible sequences, final states and path-indexed outcomes",
        "obsolete suite totals",
    ],
    "docs/RESEARCH.md": [
        (
            "uncertainty distributions, roster valuation, waiver behavior, candidate "
            "pruning and numerical methods"
        ),
        "incumbent approved version",
        "selection bias and runtime regression",
        "latest approved official combination",
    ],
    "docs/BACKLOG.md": [
        "peak parent and aggregate-child memory",
        "ordering and selected drops/additions",
        "named-player retention/drop probability and weeks held",
        "representative and analytically interesting",
        "Finalist validation",
        "run/scenario/team",
        "multi-sort",
        "all candidates receiving any Monte Carlo evaluation",
        "current filtered subset",
        "without resimulation",
        "does not perform the conversion",
        "sealed final-test protocol",
        "Ratios at zero are undefined",
        "exactly once in sampled outcomes",
        "minimum effective evidence",
        "No fabricated execution probability",
        "bye/seed",
        "consolation-round advancement",
        "final W/L/T",
        "code/build version",
        "abandoned-checkpoint expiration",
        "p95 below 100 ms",
        "one active/at most eight pending",
        "zero transient coordinator references",
        "no orphan analytical child",
        "No P0 or P1 finding remains open",
        "Independent release decision",
        "current simulation boundary",
        "latest validated refresh",
        "same current snapshot",
        "historical APIs",
        "separately gated proposal",
    ],
    "docs/APPLICATION_SERVICE.md": [
        "Binding run-provenance requirement",
        "source-completeness indicators",
        "code/build version",
        "not evidence that every artifact",
    ],
    "docs/MONTE_CARLO.md": [
        "95% family confidence",
        "0.5 probability-point",
        "h=0.005",
        "lack of a native profile wall-clock field",
        "without service-side scaling",
        "there is no conversion in that adapter",
        "Mathematical conversion to probability points",
        "seed-bearing **run identity**",
        "complete ordered parameters",
        "planned-look or across-state multiplier",
    ],
    "docs/architecture/overview.md": [
        "A — frontend",
        "J — aggregation/persistence/reporting",
        "Dependencies run frontend",
        "reference-equivalent",
    ],
}


def _validate(documents: dict[str, str]) -> None:
    assert documents.keys() == PERMANENT, "Missing/unexpected permanent authority"
    for path, fragments in REQUIREMENTS.items():
        for fragment in fragments:
            assert fragment in documents[path], (path, fragment)
    for path, text in documents.items():
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if target.startswith(("https://", "http://")):
                continue
            assert not re.search(
                r"(MASTER_SPEC|ROADMAP|R1_REPOSITORY_AUDIT|documentation-consolidation|d8-authority-transfer-crosswalk)\.md",
                target,
            ), (path, target)
    backlog = documents["docs/BACKLOG.md"]
    for number in (2, 3, 8, 17, 18, 19, 21, 23, 24, 25, 26):
        row = next(
            l for l in backlog.splitlines() if l.startswith(f"| WR-{number:03d} |")
        )
        assert "| Done |" not in row, row
    for path in PERMANENT:
        if path.startswith("docs/") and path != "docs/BACKLOG.md":
            assert "AGENTS.md#authority-and-precedence" in documents[path], path


def test_permanent_authority_and_acceptance_contracts() -> None:
    documents = {
        p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8")
        for p in [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md")]
    }
    _validate(documents)


@pytest.mark.parametrize(
    ("path", "requirement"),
    [
        ("AGENTS.md", "Only an explicitly approved successor"),
        ("CONTRIBUTING.md", "sequential interval/stopping coverage"),
        ("docs/BACKLOG.md", "abandoned-checkpoint expiration"),
        ("docs/BACKLOG.md", "No P0 or P1 finding remains open"),
        ("docs/BACKLOG.md", "all candidates receiving any Monte Carlo evaluation"),
        ("docs/BACKLOG.md", "sealed final-test protocol"),
        ("docs/MONTE_CARLO.md", "h=0.005"),
        ("docs/MONTE_CARLO.md", "seed-bearing **run identity**"),
    ],
)
def test_reject_lost_binding_obligation(path: str, requirement: str) -> None:
    documents = {p: (ROOT / p).read_text(encoding="utf-8") for p in PERMANENT}
    documents[path] = documents[path].replace(requirement, "")
    with pytest.raises(AssertionError):
        _validate(documents)


def test_reject_retired_master_as_current_authority() -> None:
    documents = {p: (ROOT / p).read_text(encoding="utf-8") for p in PERMANENT}
    documents["README.md"] += "\n[spec](docs/MASTER_SPEC.md)"
    with pytest.raises(AssertionError):
        _validate(documents)


def test_historical_numerical_artifacts_remain_byte_identical() -> None:
    # Pre-WR-022 evidence, not a current performance or numerical replay claim.
    hashes = {
        "lw23a_baseline_four.json": "3ca901d90dcef6636746454720b103426525a74637b204d6ea350753a8e29ab0",
        "lw23a_baseline_fourteen.json": "fcf15d9cb52296d7f53b5fb4e214231c5492ed51d88f98f8e13d9faec1c6690a",
        "lw23a_verify_four_team_reference.json": "80b2ce8cf8a774e000ee400e4d97c409985ad058501789e479f053cbae1d7f80",
        "lw23a_verify_four_team_retained.json": "21eb41eb794929a650f4107755dfc53b82da766324b505187c8b1c213f1a4458",
        "lw23a_verify_fourteen_team_reference.json": "05257296df2fb025700bc92d4e264d227b7945c1ae1dd6b9deef047b71a0a27f",
        "lw23a_verify_fourteen_team_retained.json": "9cc13af7b558d058f8bdd1172c9760fb11c24f4736cd04abb1ca1e7e030c2013",
    }
    for name, expected in hashes.items():
        assert (
            hashlib.sha256(
                (ROOT / "benchmarks/results" / name).read_bytes()
            ).hexdigest()
            == expected
        )
