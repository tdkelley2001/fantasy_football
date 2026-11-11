from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^]]*]\(([^)]+)\)")


def _documentation_files() -> tuple[Path, ...]:
    return (
        *sorted(REPOSITORY_ROOT.glob("*.md")),
        *sorted((REPOSITORY_ROOT / "docs").rglob("*.md")),
    )


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
    assert not missing, (
        f"{document.relative_to(REPOSITORY_ROOT)} has missing links: {missing}"
    )


def test_governing_milestone_acceptance_contracts_remain_intact() -> None:
    master_spec = (REPOSITORY_ROOT / "docs" / "MASTER_SPEC.md").read_text(
        encoding="utf-8"
    )
    roadmap = (REPOSITORY_ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    assert "FastAPI" in master_spec
    for milestone in (
        "M6.1",
        "M6.2",
        "M6.3",
        "M6.4",
        "M7.1",
        "M7.2",
        "M7.3",
        "M7.4",
        "M7.5",
    ):
        assert f"{milestone} [COMPLETE AND ACCEPTED" in roadmap
    assert "Pre-M7 consolidation [COMPLETE AND ACCEPTED" in roadmap
    assert "Post-M7 consolidation [COMPLETE AND ACCEPTED" in roadmap
    assert "analytics-first" in roadmap.casefold()
    assert "Integrated CLI V1" not in master_spec
    assert "Optional visual dashboard" not in master_spec


def test_historical_acceptance_and_current_release_disposition_are_distinct() -> None:
    for name in ("MASTER_SPEC.md", "ROADMAP.md"):
        text = (REPOSITORY_ROOT / "docs" / name).read_text(encoding="utf-8")
        parent = re.search(r"^#### M7 — .*?$", text, re.MULTILINE)
        assert parent is not None, name
        assert "[COMPLETE AND ACCEPTED]" in parent.group(0)
        assert "IN PROGRESS" not in parent.group(0)
        assert "REVIEW PENDING" not in parent.group(0)
        assert "M8.4" in text and "READY FOR INDEPENDENT REVIEW" in text
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    checkpoint = (
        REPOSITORY_ROOT / "docs" / "LW23A_PERFORMANCE_CHECKPOINT.md"
    ).read_text(encoding="utf-8")
    assert "not formally released" in readme
    assert "M8.4 release disposition remains pending" in readme
    assert "Current disposition: **ACCEPTED**" in checkpoint
    assert "Status at delivery: implemented for independent review" in checkpoint
    assert "not permission to begin LW2.3B" in checkpoint


def test_m8_4_release_documents_and_verification_entrypoint_are_present() -> None:
    audit = (REPOSITORY_ROOT / "docs" / "M8_4_FINAL_RELEASE_AUDIT.md").read_text(
        encoding="utf-8"
    )
    guide = (REPOSITORY_ROOT / "docs" / "INTERFACE.md").read_text(encoding="utf-8")
    checklist = (REPOSITORY_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    verifier = (REPOSITORY_ROOT / "scripts" / "verify-release.ps1").read_text(
        encoding="utf-8"
    )

    for heading in (
        "Release requirement traceability",
        "Security assessment",
        "Known limitations",
        "Final recommendation",
    ):
        assert heading in audit
    assert "does not declare" in audit
    assert "OPERATIONS.md" in guide
    assert "Confidence intervals" in guide
    assert "ESPN submission remain unsupported" in guide
    assert "never submits real transactions" in (
        REPOSITORY_ROOT / "README.md"
    ).read_text(encoding="utf-8")
    assert "performs no ESPN request" in checklist
    for required_step in (
        "Python credential-free default suite",
        "Frontend tests",
        "TypeScript typecheck",
        "Production frontend build",
        "Ruff correctness",
        "Python dependency consistency",
        "Production dependency audit",
        "Working-tree whitespace",
        "Committed-revision whitespace",
    ):
        assert required_step in verifier


def test_historical_m5_parent_status_and_ui_vision_are_preserved() -> None:
    for name in ("MASTER_SPEC.md", "ROADMAP.md"):
        text = (REPOSITORY_ROOT / "docs" / name).read_text(encoding="utf-8")
        parent = re.search(r"^#### M5 — .*?$", text, re.MULTILINE)
        assert parent is not None, name
        assert "[COMPLETE AND ACCEPTED]" in parent.group(0)
        assert "IN PROGRESS" not in parent.group(0)
        assert "REVIEW PENDING" not in parent.group(0)
        assert "M5.1–M5.8" in parent.group(0)
        assert "UI_DESIGN_VISION.md" in text


def test_m7_visual_first_standard_is_authoritative_and_applied() -> None:
    vision = (REPOSITORY_ROOT / "docs" / "INTERFACE.md").read_text(encoding="utf-8")
    master_spec = (REPOSITORY_ROOT / "docs" / "MASTER_SPEC.md").read_text(
        encoding="utf-8"
    )
    roadmap = (REPOSITORY_ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")

    assert "## Visual-first design standard" in vision
    assert "Meaningful visualizations take priority" in vision
    for workspace in (
        "League Overview",
        "Opportunity Explorer",
        "Trade Lab",
        "Simulation Center",
        "League Insights",
    ):
        assert workspace in vision
    assert "table as the primary form only" in vision
    assert "decorative charts" in vision
    assert "visual-first information design standard" in master_spec
    assert "visual-first information standard" in roadmap
    for representation in (
        "dot-and-whisker plot",
        "probability bands",
        "placement heatmap",
        "Focused team panel",
        "Progressive technical disclosure",
    ):
        assert representation in vision
