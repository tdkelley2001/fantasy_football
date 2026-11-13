"""Repository-native planning integrity without changing engine contracts."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^]]*]\(([^)]+)\)")


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8-sig")


def _work_rows(section_title: str = "Work items") -> list[list[str]]:
    section = (
        _read("docs/BACKLOG.md")
        .split(f"## {section_title}\n", 1)[1]
        .split("\n## ", 1)[0]
    )
    return [
        [cell.strip() for cell in line.strip("|").split("|")]
        for line in section.splitlines()
        if re.match(r"^\| WR-\d{3} \|", line)
    ]


def test_backlog_ids_and_work_metadata_are_unambiguous() -> None:
    active = _work_rows()
    completed = _work_rows("Completed work")
    rows = active + completed
    assert rows
    identifiers = [row[0] for row in rows]
    assert len(set(identifiers)) == len(identifiers)
    assert [row[0] for row in active] == sorted(row[0] for row in active)
    assert [row[0] for row in completed] == sorted(row[0] for row in completed)
    assert all(row[3] != "Done" for row in active)
    assert all(row[3] == "Done" for row in completed)
    for row in rows:
        assert len(row) == 6, row
        kind, priority = row[2].split(" / ")
        assert kind in {
            "Bug",
            "Documentation",
            "Technical debt",
            "Enhancement",
            "Research",
        }
        assert priority in {"P0", "P1", "P2", "P3"}
        assert row[3] in {
            "Backlog",
            "Ready",
            "In Progress",
            "In Review",
            "Blocked",
            "Done",
        }
        assert row[1] and row[4] and row[5]


def test_every_r1_candidate_has_exactly_one_valid_disposition() -> None:
    audit = _read("docs/R1_REPOSITORY_AUDIT.md")
    catalog = audit.split("## 11. Proposed initial issue catalog", 1)[1].split(
        "## 12.", 1
    )[0]
    proposed = re.findall(r"\*\*(B\d{2}) —", catalog)
    assert proposed and len(proposed) == len(set(proposed))
    backlog = _read("docs/BACKLOG.md")
    mapping = backlog.split("## R1 candidate reconciliation", 1)[1].split(
        "## Completed work", 1
    )[0]
    mapped = [line for line in mapping.splitlines() if re.match(r"^\| B\d{2}", line)]
    assert Counter(re.findall(r"\bB\d{2}\b", "\n".join(mapped))) == Counter(proposed)
    valid = {row[0] for row in _work_rows() + _work_rows("Completed work")}
    for line in mapped:
        targets = re.findall(r"\bWR-\d{3}\b", line)
        assert len(targets) == 1 and targets[0] in valid, line


@pytest.mark.parametrize(
    "document",
    (
        "README.md",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "docs/BACKLOG.md",
        "docs/DATA.md",
        "docs/RESEARCH.md",
        "docs/INTERFACE.md",
        "docs/OPERATIONS.md",
        "docs/MISSING_PROJECTION_POLICY.md",
        "docs/PLAYER_OUTCOME_MODEL.md",
        "docs/MONTE_CARLO.md",
        "docs/SEASON_SIMULATOR.md",
        "docs/LW2_PARTIAL_WEEK_CONTRACT.md",
        "docs/APPLICATION_SERVICE.md",
        "docs/architecture/overview.md",
        "docs/R23_DOCUMENTATION_RECONCILIATION.md",
        "docs/PRE_M3_REPOSITORY_AUDIT.md",
        "docs/PRE_M4_INTEGRATION_AUDIT.md",
        "docs/archive/audits/PRE_M3_REPOSITORY_AUDIT.md",
        "docs/archive/audits/PRE_M4_INTEGRATION_AUDIT.md",
        "docs/R25_ARCHIVE_PILOT.md",
        "docs/R26_DOCUMENTATION_MIGRATION_PLAN.md",
        "docs/development/documentation-consolidation.md",
    ),
)
def test_contributor_links_and_fragments_resolve(document: str) -> None:
    path = ROOT / document
    for raw in LINK.findall(_read(document)):
        target = raw.strip().split(maxsplit=1)[0].strip("<>")
        if target.startswith(("https://", "http://", "mailto:")):
            continue
        name, _, fragment = unquote(target).partition("#")
        destination = (path.parent / name).resolve() if name else path
        assert destination.is_file(), (document, target)
        if fragment and destination.suffix == ".md":
            headings = re.findall(
                r"^#{1,6}\s+(.+)$",
                destination.read_text(encoding="utf-8-sig"),
                re.MULTILINE,
            )
            anchors = {
                re.sub(r"[^\w\- ]", "", title.casefold()).replace(" ", "-")
                for title in headings
            }
            assert fragment in anchors, (document, target)


@pytest.mark.parametrize("document", ("README.md", "AGENTS.md"))
def test_contributor_entry_points_link_the_four_distinct_authorities(
    document: str,
) -> None:
    targets = {target.split("#", 1)[0] for target in LINK.findall(_read(document))}
    assert {
        "CONTRIBUTING.md",
        "docs/BACKLOG.md",
        "docs/MASTER_SPEC.md",
        "docs/ROADMAP.md",
        "docs/INTERFACE.md",
    } <= targets


def test_fork_and_original_branch_sync_examples_are_both_present() -> None:
    guide = _read("CONTRIBUTING.md")
    assert "tdkelley2001/fantasy_football" in guide
    for remote in ("origin", "upstream"):
        assert f"git fetch {remote}" in guide
        assert f"git merge --ff-only {remote}/main" in guide
    assert "reviewed pull requests" in guide
    assert "fork only" in guide


def test_readme_covers_reader_needs_without_rewriting_r1_inventory() -> None:
    entry = _read("README.md")
    for heading in ("Current capabilities", "Start here", "Understand the system"):
        assert f"## {heading}\n" in entry
    assert "docs/INTERFACE.md" in entry
    audit = _read("docs/R1_REPOSITORY_AUDIT.md")
    section = audit.split("## 7. File-by-file documentation migration map", 1)[1].split(
        "## 8.", 1
    )[0]
    inventory = re.findall(r"^\| `([^`]+\.md)` \|", section, re.MULTILINE)
    assert len(inventory) == len(set(inventory)) == 56
    # The R1 map is dated evidence; current targets are checked recursively.
    assert "docs/ROADMAP.md" in entry


def test_accepted_r20_is_completed_but_broader_r2_work_remains_open() -> None:
    assert any(
        row[0] == "WR-001" and "3391552" in row[4]
        for row in _work_rows("Completed work")
    )
    assert any(row[0] == "WR-002" and row[3] != "Done" for row in _work_rows())


def test_current_setup_routes_replace_conflicting_user_guidance() -> None:
    for source in ("README.md", "AGENTS.md", "CONTRIBUTING.md", "docs/INTERFACE.md"):
        assert "OPERATIONS.md" in _read(source)
    assert "../CONTRIBUTING.md" in _read("docs/APPLICATION_SERVICE.md")
    assert 'pip install -e ".[app]"' not in _read("docs/APPLICATION_SERVICE.md")


def test_operations_launcher_defaults_match_supported_start_parameters() -> None:
    document = _read("docs/OPERATIONS.md")
    script = _read("scripts/start-local.ps1")
    rows = re.findall(
        r"^\| `(-\w+)` \| `(WAR_ROOM_\w+)` \| `([^`]+)` \|$",
        document,
        re.MULTILINE,
    )
    assert len(rows) == 5
    for parameter, variable, default in rows:
        value = re.escape(default)
        assert re.search(
            rf"\${parameter[1:]} = \$\(if \(\$env:{variable}\).*?else "
            rf'\{{ "?{value}"? \}}\)',
            script,
        ), (parameter, variable, default)


def test_operations_preserves_separate_configuration_authorities() -> None:
    document = _read("docs/OPERATIONS.md")
    for phrase in (
        "does not read `.env`",
        "Explicit parameters override process-environment variables",
        "process environment, including empty values",
        "not `SNAPSHOT_DB_PATH`",
        "**not the `.env` file's parent**",
        "**`--manual-config` explicitly**",
        "`--first-simulation-week` explicitly",
        "automatic safe-week detection",
        "WR-003 remains unresolved",
    ):
        assert phrase in document
    for name in (
        "ESPN_LEAGUE_ID",
        "ESPN_SEASON",
        "ESPN_S2",
        "ESPN_SWID",
        "SNAPSHOT_DB_PATH",
        "FANTASY_FOOTBALL_RULE_CONFIG_PATH",
    ):
        assert name in document and name in _read("src/fantasy_football/config.py")


def test_contributor_locked_setup_and_vite_commands_match_sources() -> None:
    document = _read("CONTRIBUTING.md")
    setup = _read("scripts/setup-local.ps1")
    for arguments in (
        "--disable-pip-version-check -r requirements.lock",
        "--disable-pip-version-check --no-deps -e .",
        "ci --no-audit --no-fund",
    ):
        assert arguments in document
        assert all(f'"{part}"' in setup for part in arguments.split())
    vite = _read("frontend/vite.config.ts")
    assert "VITE_API_TARGET" in document and "VITE_API_TARGET" in vite
    assert "changeOrigin: false" in vite and "without changing Origin" in document
    assert "not launcher-owned" in document


def test_release_signoffs_have_an_explicit_backlog_destination() -> None:
    section = (
        _read("docs/BACKLOG.md")
        .split("## WR-021 release acceptance\n", 1)[1]
        .split("\n## ", 1)[0]
    )
    for requirement in (
        "revision, working-tree state",
        "Clean Windows setup and production-local start",
        "Authenticated local identity/static boundary",
        "Refresh and snapshot evidence",
        "Ordinary analytical workflow",
        "Shutdown, restart and recovery",
        "No P0 or P1 finding remains open",
        "Repository privacy",
        "Independent release decision",
        "manual-rule configuration follow-ups",
        "V1 released",
    ):
        assert requirement in section
    assert "tier-4-release-verification" in section
    assert "tier-5-explicitly-authorized-integration" in section
