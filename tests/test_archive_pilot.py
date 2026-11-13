"""R2.5 evidence/anchor preservation against the independently accepted R2.4 tree."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "05165a8fbf4084fc9c2d56780335581c65006657"
NAMES = ("PRE_M3_REPOSITORY_AUDIT.md", "PRE_M4_INTEGRATION_AUDIT.md")
LINK = re.compile(r"!?\[[^]]*]\(([^)]+)\)")


def _baseline(path: str) -> str:
    # Read-only; absence of the approved object is an error, never a silent skip.
    result = subprocess.run(
        ["git", "show", f"{BASELINE}:{path}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, (
        f"Historical-integrity tests require accepted R2.4 object {BASELINE}: {result.stderr}"
    )
    return result.stdout


def _headings(text: str) -> list[tuple[str, str]]:
    # The original audits have plain ATX headings and no fenced code blocks.
    return re.findall(r"^(#{1,6}) (.+)$", text, re.MULTILINE)


def _anchors(text: str) -> list[str]:
    """GitHub section-link rules for these plain headings, including collisions."""
    used: set[str] = set()
    anchors = []
    for _, title in _headings(text):
        base = re.sub(r"[^\w -]", "", title.strip().lower()).replace(" ", "-")
        candidate, suffix = base, 0
        while candidate in used:
            suffix += 1
            candidate = f"{base}-{suffix}"
        used.add(candidate)
        anchors.append(candidate)
    return anchors


def _notice(name: str) -> str:
    return (
        f"> Archived historical evidence, relocated in R2.5 from `docs/{name}`. "
        "Original findings, measurements and acceptance gates remain in force at their "
        "stated baseline; relocation does not supersede them. For current behavior use "
        "the [architecture overview](../../architecture/overview.md) and "
        "[verification guide](../../../CONTRIBUTING.md#tier-1-fast-local-checks).\n\n"
    )


@pytest.mark.parametrize("name", NAMES)
def test_complete_archived_evidence_matches_accepted_r24_with_only_reviewed_changes(
    name,
):
    original = _baseline(f"docs/{name}")
    actual = (ROOT / "docs/archive/audits" / name).read_text(encoding="utf-8")
    expected = original
    if name == NAMES[0]:
        assert original.count("(LEAGUE_CONFIGURATION_AUDIT.md)") == 1
        expected = original.replace(
            "(LEAGUE_CONFIGURATION_AUDIT.md)",
            "(../../DATA.md#rules-and-manual-authority)",
        )
    # Full text comparison: no summaries, filtered prose or broad normalization.
    assert actual == _notice(name) + expected


@pytest.mark.parametrize("name, count", ((NAMES[0], 13), (NAMES[1], 11)))
def test_every_original_heading_and_anchor_survives_at_old_and_new_locations(
    name, count
):
    original = _baseline(f"docs/{name}")
    stub = (ROOT / "docs" / name).read_text(encoding="utf-8")
    archive = (ROOT / "docs/archive/audits" / name).read_text(encoding="utf-8")
    assert "```" not in original
    assert all(title.isascii() for _, title in _headings(original))
    assert len(_headings(original)) == count
    assert _headings(stub) == _headings(original) == _headings(archive)
    assert _anchors(stub) == _anchors(original) == _anchors(archive)
    assert len(set(_anchors(original))) == count
    for anchor in _anchors(original):
        assert f"archive/audits/{name}#{anchor}" in stub
    assert "Archived historical evidence" in stub
    assert "not current implementation instructions" in stub
    assert (
        "architecture/overview.md" in stub
        and "../CONTRIBUTING.md#tier-1-fast-local-checks" in stub
    )


def test_duplicate_heading_suffixes_preserve_distinct_automatic_ids():
    # Exercises repeated headings and a heading already containing a suffix.
    assert _anchors(
        "# Sample Section\n## SAMPLE SECTION!\n## sample section-1\n## Sample Section\n"
    ) == [
        "sample-section",
        "sample-section-1",
        "sample-section-1-1",
        "sample-section-2",
    ]


def test_all_markdown_inbound_fragments_to_pilot_documents_resolve():
    targets = {
        (ROOT / folder / name).resolve()
        for folder in ("docs", "docs/archive/audits")
        for name in NAMES
    }
    observed = 0
    for path in (*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md")):
        for raw in LINK.findall(path.read_text(encoding="utf-8-sig")):
            target = raw.strip().split(maxsplit=1)[0].strip("<>")
            if target.startswith(("https://", "http://", "mailto:")):
                continue
            name, _, fragment = unquote(target).partition("#")
            destination = (path.parent / name).resolve() if name else path.resolve()
            if destination not in targets:
                continue
            observed += 1
            assert destination.is_file(), (path, target)
            if fragment:
                assert fragment in _anchors(destination.read_text(encoding="utf-8")), (
                    path,
                    target,
                )
    assert observed >= 24


@pytest.mark.parametrize("name", NAMES)
def test_archived_outbound_relative_links_resolve(name):
    path = ROOT / "docs/archive/audits" / name
    for target in LINK.findall(path.read_text(encoding="utf-8")):
        name, _, fragment = unquote(target).partition("#")
        destination = (path.parent / name).resolve()
        assert destination.is_file(), target
        if fragment:
            assert fragment in _anchors(destination.read_text(encoding="utf-8")), target


def test_original_pilot_inventory_record_is_unchanged():
    # Current governing references may update citations after an authorized
    # consolidation. The pilot does not freeze every later specification edit.
    path = "docs/R1_REPOSITORY_AUDIT.md"
    actual = (ROOT / path).read_text(encoding="utf-8")
    # D3 retargets the supersession notice only; retain the complete R1 body.
    actual = actual.replace(
        "[status.md](../README.md#current-capabilities)", "[status.md](status.md)"
    )
    assert actual == _baseline(path)


def test_pilot_records_and_navigation_remain_accessible():
    # Preserve this pilot's actual evidence, not every historical repository path.
    assert all(
        (ROOT / folder / name).is_file()
        for folder in ("docs", "docs/archive/audits")
        for name in NAMES
    )
    # D3 retires the chronological index; README links the owning references.
    entry = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/architecture/overview.md" in entry
    assert "CONTRIBUTING.md" in entry
