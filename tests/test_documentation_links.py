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


def test_historical_milestone_contracts_remain_accessible_from_index() -> None:
    master_spec = (REPOSITORY_ROOT / "docs" / "MASTER_SPEC.md").read_text(
        encoding="utf-8"
    )
    roadmap = (REPOSITORY_ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    index = (REPOSITORY_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
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
    for reference in (
        "APPLICATION_SERVICE.md",
        "M7_1_FRONTEND_FOUNDATION.md",
        "M7_2_LEAGUE_ANALYTICS.md",
        "M7_3_OPPORTUNITY_EXPLORER.md",
        "M7_4_TRADE_LAB.md",
        "M7_5_SIMULATION_CENTER.md",
        "POST_M7_CONSOLIDATION_AUDIT.md",
        "OPERATIONS.md",
        "M8_2_REAL_LEAGUE_VALIDATION.md",
        "M7_1_VISUAL_DIRECTION_REVIEW.md",
        "M8_3_RUNTIME_AND_RECOVERY.md",
        "M8_4_FINAL_RELEASE_AUDIT.md",
        "LOCAL_V1_USER_GUIDE.md",
        "BACKLOG.md",
    ):
        assert reference in index
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
    status = (REPOSITORY_ROOT / "docs" / "status.md").read_text(encoding="utf-8")
    checkpoint = (
        REPOSITORY_ROOT / "docs" / "LW23A_PERFORMANCE_CHECKPOINT.md"
    ).read_text(encoding="utf-8")
    assert "not formally released" in readme
    assert "M8.4 release disposition remains pending" in status
    assert (
        "performance/consolidation checkpoint implemented at `d630887` is **independently accepted**"
        in status
    )
    assert "Current disposition: **ACCEPTED**" in checkpoint
    assert "Status at delivery: implemented for independent review" in checkpoint
    assert "not permission to begin LW2.3B" in checkpoint


def test_m8_4_release_documents_and_verification_entrypoint_are_present() -> None:
    audit = (REPOSITORY_ROOT / "docs" / "M8_4_FINAL_RELEASE_AUDIT.md").read_text(
        encoding="utf-8"
    )
    guide = (REPOSITORY_ROOT / "docs" / "LOCAL_V1_USER_GUIDE.md").read_text(
        encoding="utf-8"
    )
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
    assert "locally hosted" in guide
    assert "Confidence intervals" in guide
    assert "never executes real transactions" in guide
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
    index = (REPOSITORY_ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    assert "UI_DESIGN_VISION.md" in index


def test_m7_visual_first_standard_is_authoritative_and_applied() -> None:
    vision = (REPOSITORY_ROOT / "docs" / "UI_DESIGN_VISION.md").read_text(
        encoding="utf-8"
    )
    m7_2 = (REPOSITORY_ROOT / "docs" / "M7_2_LEAGUE_ANALYTICS.md").read_text(
        encoding="utf-8"
    )
    master_spec = (REPOSITORY_ROOT / "docs" / "MASTER_SPEC.md").read_text(
        encoding="utf-8"
    )
    roadmap = (REPOSITORY_ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")

    assert "## Visual-first information design standard" in vision
    assert "Default to visual communication" in vision
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
    assert "## Visual representation decisions" in m7_2
    for representation in (
        "ranked dot-and-whisker plot",
        "ranked probability bands",
        "team-by-placement heatmap",
        "focused detail panel",
        "progressive disclosure",
    ):
        assert representation in m7_2
