"""Frozen R2.6 inventory/accounting, not authorization for future migrations."""

from __future__ import annotations

import io
import posixpath
import re
import subprocess
import tarfile
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from tests.test_archive_pilot import NAMES

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "fd9855162f373b961f9774bbea054899aa0014be"
PLAN = "docs/R26_DOCUMENTATION_MIGRATION_PLAN.md"
LINK = re.compile(r"!?\[[^]]*]\(([^)]+)\)")


@lru_cache(maxsize=1)
def _tree() -> dict[str, bytes]:
    # Git objects only; no extraction, network, private stores or subprocess tests.
    raw = subprocess.check_output(
        ["git", "archive", "--format=tar", BASELINE], cwd=ROOT
    )
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {
            item.name: archive.extractfile(item).read()
            for item in archive
            if item.isfile()
        }


def _plan() -> str:
    return (ROOT / PLAN).read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    return _plan().split(start, 1)[1].split(end, 1)[0]


def _rows() -> dict[str, list[str]]:
    section = _section("## Complete Markdown inventory", "## R1 reconciliation")
    result = {}
    for line in section.splitlines():
        if re.match(r"^\| `[^`]+\.md` \| [ABC] \|", line):
            fields = [part.strip() for part in line.strip("|").split("|")]
            path = fields[0].strip("`")
            assert path not in result
            assert len(fields) == 7
            result[path] = fields
    return result


def test_every_baseline_markdown_and_r26_addition_has_one_complete_disposition():
    baseline = {name for name in _tree() if name.endswith(".md")}
    rows = _rows()
    assert len(baseline) == 73
    assert set(rows) == baseline | {PLAN}
    assert Counter(row[1] for row in rows.values()) == {"A": 30, "B": 10, "C": 34}
    # This inventory describes accepted R2.6 Git objects, not perpetual live paths.
    # Current navigation/targets are verified by test_documentation_links instead.
    assert all(all(row[index] for index in (2, 3, 4, 5, 6)) for row in rows.values())


def test_r1_map_and_completed_archive_compatibility_are_reconciled_without_new_work():
    r1 = _tree()["docs/R1_REPOSITORY_AUDIT.md"].decode("utf-8")
    section = r1.split("## 7. File-by-file documentation migration map", 1)[1].split(
        "## 8.", 1
    )[0]
    original = set(re.findall(r"^\| `([^`]+\.md)` \|", section, re.MULTILINE))
    rows = _rows()
    assert len(original) == 56
    assert original == {path for path, row in rows.items() if row[2].startswith("R1")}
    assert sum(row[2].startswith("Add") for row in rows.values()) == 17
    assert sum(row[2] == "New" for row in rows.values()) == 1
    done = {path for path, row in rows.items() if row[5].endswith("/ DONE")}
    expected = {
        f"{prefix}/{name}"
        for prefix in ("docs", "docs/archive/audits")
        for name in NAMES
    }
    assert done == expected
    for path in expected:
        # Only the current-guide citation changes in D2; historical bodies,
        # inventory rows and original evidence remain compared in full.
        actual = (ROOT / path).read_text(encoding="utf-8")
        prefix = "../../../" if "/archive/" in path else "../"
        actual = actual.replace(
            f"({prefix}CONTRIBUTING.md#tier-1-fast-local-checks)",
            "(../../development/verification.md)"
            if "/archive/" in path
            else "(development/verification.md)",
        )
        # D3 retargets only the current navigation citation after retiring index.
        actual = actual.replace(
            "[documentation index](../README.md#understand-the-system)",
            "[documentation index](index.md)",
        )
        assert actual == _tree()[path].decode("utf-8").replace("\r\n", "\n")


def test_primary_package_scopes_are_exact_disjoint_and_not_approvals():
    section = _section("## Proposed implementation packages", "## Dependency order")
    assigned = {}
    packages = set()
    for line in section.splitlines():
        if not re.match(r"^\| `[A-Z][A-Z0-9]*` \|", line):
            continue
        fields = [part.strip() for part in line.strip("|").split("|")]
        assert len(fields) == 5
        package = fields[0].strip("`")
        assert package not in packages
        packages.add(package)
        for path in re.findall(r"`([^`]+\.md)`", fields[1]):
            assert path not in assigned, (path, package)
            assigned[path] = package
        assert all(fields[2:])
    expected = {
        path: row[5].rsplit("/ ", 1)[1]
        for path, row in _rows().items()
        if not row[5].endswith(("/ KEEP", "/ DONE"))
    }
    assert assigned == expected
    assert len(packages) == 23
    assert "Every package is **pending authorization**" in section
    assert "WR-002 stays open" in _plan()


def test_supporting_evidence_and_tools_are_completely_accounted_for_and_untouched():
    tree = _tree()
    assets = {
        name
        for name in tree
        if name.startswith(("docs/images/", "docs/examples/", "benchmarks/results/"))
    }
    section = _section(
        "### Complete evidence and example asset manifest", "### Supporting tools"
    )
    recorded = re.findall(r"^\| `([^`]+)` \|", section, re.MULTILINE)
    assert len(recorded) == len(set(recorded)) == 72
    assert set(recorded) == assets
    assert sum(name.endswith(".png") for name in assets) == 65
    for path in assets:
        assert (ROOT / path).read_bytes() == tree[path]
    tools = {
        name
        for name in tree
        if (
            name.startswith("benchmarks/")
            and not name.startswith("benchmarks/results/")
        )
        or name.startswith("frontend/dev/")
    }
    section = _section(
        "### Supporting tools outside docs", "## Proposed implementation packages"
    )
    recorded = re.findall(r"^\| `([^`]+)` \|", section, re.MULTILINE)
    assert len(recorded) == len(set(recorded)) == 19
    assert set(recorded) == tools
    assert all((ROOT / path).is_file() for path in tools)


def test_baseline_reference_counts_are_reproducible_not_guessed_from_milestone_names():
    texts = {}
    for path, data in _tree().items():
        try:
            texts[path] = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass
    incoming = defaultdict(set)
    fragments = 0
    for source, text in texts.items():
        if not source.endswith(".md"):
            continue
        for raw in LINK.findall(text):
            target = raw.strip().split(maxsplit=1)[0].strip("<>")
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            name, _, fragment = target.partition("#")
            destination = (
                posixpath.normpath(posixpath.join(posixpath.dirname(source), name))
                if name
                else source
            )
            if destination != source:
                incoming[destination].add(source)
            fragments += bool(fragment)
    for path, row in _rows().items():
        if path == PLAN:
            continue
        mentions = sum(
            Path(path).name in text for other, text in texts.items() if other != path
        )
        assert row[4].startswith(f"{len(incoming[path])}/{mentions};"), path
    assert fragments == 64
