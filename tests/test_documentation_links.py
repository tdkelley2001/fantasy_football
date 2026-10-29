from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]*]\(([^)]+)\)")


def _documentation_files() -> tuple[Path, ...]:
    return (REPOSITORY_ROOT / "README.md", *sorted((REPOSITORY_ROOT / "docs").glob("*.md")))


@pytest.mark.parametrize("document", _documentation_files(), ids=lambda path: path.name)
def test_relative_documentation_links_resolve(document: Path) -> None:
    missing: list[str] = []
    for raw_target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
        target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        relative_path = unquote(target.split("#", 1)[0])
        if relative_path and not (document.parent / relative_path).resolve().exists():
            missing.append(raw_target)
    assert not missing, f"{document.relative_to(REPOSITORY_ROOT)} has missing links: {missing}"


def test_authoritative_documents_share_current_product_direction() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    master_spec = (REPOSITORY_ROOT / "docs" / "MASTER_SPEC.md").read_text(encoding="utf-8")
    roadmap = (REPOSITORY_ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")

    for document in (readme, master_spec, roadmap):
        normalized = document.casefold()
        assert "m0–m6.4" in normalized
        assert "complete and accepted" in normalized
        assert "m7.1" in normalized
        assert "implemented" in normalized
        assert "review pending" in normalized
        assert "m7.2–m8" in normalized
        assert "not started" in normalized

    assert "local web application" in readme
    assert "FastAPI" in master_spec
    assert "M6.1 [COMPLETE AND ACCEPTED" in roadmap
    assert "M6.2 [COMPLETE AND ACCEPTED" in roadmap
    assert "M6.3 [COMPLETE AND ACCEPTED" in roadmap
    assert "M6.4 [COMPLETE AND ACCEPTED" in roadmap
    assert "Pre-M7 consolidation [COMPLETE AND ACCEPTED" in roadmap
    assert "M7.1 [IMPLEMENTED — REVIEW PENDING" in roadmap
    assert "BACKEND_READINESS.md" in roadmap
    assert "docs/BACKEND_READINESS.md" in readme
    assert "docs/PRE_M7_REPOSITORY_AUDIT.md" in readme
    assert "docs/M7_1_FRONTEND_FOUNDATION.md" in readme
    assert "M8 — Local V1 release" in roadmap
    assert "Integrated CLI V1" not in master_spec
    assert "Optional visual dashboard" not in master_spec


def test_current_m5_parent_status_and_ui_vision_are_aligned() -> None:
    master_spec = (REPOSITORY_ROOT / "docs" / "MASTER_SPEC.md").read_text(encoding="utf-8")
    roadmap = (REPOSITORY_ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

    heading = re.compile(r"^#### M5 — .*?$", re.MULTILINE)
    for name, document in (("MASTER_SPEC.md", master_spec), ("ROADMAP.md", roadmap)):
        parent = heading.search(document)
        assert parent is not None, f"{name} has no current M5 parent summary"
        summary = parent.group(0)
        assert "[COMPLETE AND ACCEPTED]" in summary
        assert "IN PROGRESS" not in summary
        assert "REVIEW PENDING" not in summary
        assert "M5.1–M5.8" in summary

    design_link = "UI_DESIGN_VISION.md"
    assert design_link in roadmap
    assert f"docs/{design_link}" in readme
