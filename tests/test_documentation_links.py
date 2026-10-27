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
        assert "m0–m5.8" in normalized
        assert "complete and accepted" in normalized
        assert "m6–m8" in normalized
        assert "not started" in normalized

    assert "local web application" in readme
    assert "FastAPI" in master_spec
    assert "M6.1 Define stable application-facing operations" in roadmap
    assert "M8 — Local V1 release" in roadmap
    assert "Integrated CLI V1" not in master_spec
    assert "Optional visual dashboard" not in master_spec
