"""Validate the declared D8.1 inventory, not semantic completeness or approval."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from copy import deepcopy
from itertools import pairwise
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = ROOT / "docs/development/d8-authority-transfer-crosswalk.md"
REVISION = "213715ca7493c49a4f272558670eb0a297bae9a0"
GOVERNING = {"MS": "docs/MASTER_SPEC.md", "RM": "docs/ROADMAP.md"}
HISTORICAL = {
    "docs/R1_REPOSITORY_AUDIT.md",
    "docs/R23_DOCUMENTATION_RECONCILIATION.md",
    "docs/R25_ARCHIVE_PILOT.md",
    "docs/R26_DOCUMENTATION_MIGRATION_PLAN.md",
    "docs/PRE_M3_REPOSITORY_AUDIT.md",
    "docs/PRE_M4_INTEGRATION_AUDIT.md",
    "docs/archive/audits/PRE_M3_REPOSITORY_AUDIT.md",
    "docs/archive/audits/PRE_M4_INTEGRATION_AUDIT.md",
    "docs/M8_2_REAL_LEAGUE_VALIDATION.md",
    "docs/M8_3_RUNTIME_AND_RECOVERY.md",
    "docs/M8_4_FINAL_RELEASE_AUDIT.md",
}
CLASSIFICATIONS = {
    "current_implemented_contract",
    "approved_unimplemented_requirement",
    "conditional_approval_or_constraint",
    "proposal_not_yet_authorized",
    "unresolved_conflict_or_decision",
    "historical_or_superseded",
}
STATUSES = {
    "implemented_and_supported_by_tests",
    "partially_implemented",
    "supported_only_in_internal_engine_interface",
    "pending_source_verification",
    "approved_but_unimplemented",
    "proposed_and_awaiting_authorization",
    "contradicted_by_current_behavior",
    "historical_or_superseded",
}
OWNERS = {
    "README.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "docs/architecture/overview.md",
    *(
        f"docs/{name}.md"
        for name in (
            "DATA",
            "RESEARCH",
            "PLAYER_OUTCOME_MODEL",
            "SEASON_SIMULATOR",
            "TRANSACTIONS",
            "MONTE_CARLO",
            "PARTIAL_WEEK",
            "MANUAL_SCENARIOS",
            "UNIFIED_ACTION_SEARCH",
            "APPLICATION_SERVICE",
            "INTERFACE",
            "OPERATIONS",
            "BACKLOG",
        )
    ),
}


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _register() -> dict:
    document = DOCUMENT.read_text(encoding="utf-8")
    return json.loads(
        document.split("```json d8-crosswalk\n", 1)[1].split("\n```", 1)[0]
    )


def _rows(register: dict, name: str) -> list[dict]:
    columns = register[
        "source_group_columns" if name == "source_groups" else "clause_columns"
    ]
    assert len(columns) == len(set(columns)), "duplicate column definitions"
    return [dict(zip(columns, row, strict=True)) for row in register[name]]


def _source_blocks(path: str) -> dict[str, tuple[str, int, int]]:
    """Blank-separated text groups; deliberately no normative-language parser."""
    tag = next(tag for tag, source in GOVERNING.items() if source == path)
    text = _read(path)
    offset = 0
    result = {}
    for part in text.split("\n\n"):
        start = offset
        offset += len(part) + 2
        if not part.strip():
            continue
        start += len(part) - len(part.lstrip("\n"))
        block = part.strip("\n")
        line = text.count("\n", 0, start) + 1
        result[f"{tag}-L{line:04d}"] = (block, line, line + block.count("\n"))
    return result


def _check_reference(target: str) -> None:
    name, _, anchor = target.partition("#")
    assert name in OWNERS, f"unapproved or unresolved destination: {target}"
    assert anchor, f"destination needs exact anchor: {target}"
    headings = re.findall(r"^#{1,6}\s+(.+)$", _read(name), re.MULTILINE)
    anchors = {
        re.sub(r"[^\w\- ]", "", title.casefold()).replace(" ", "-")
        for title in headings
    }
    assert anchor in anchors, f"unknown destination anchor: {target}"


def _validate(register: dict) -> None:
    assert register["accepted_revision"] == REVISION
    assert register["review_status"] == "pending_review"
    assert register["contract"] == "d8.1-review-crosswalk-v1"
    sources = register["sources"]
    assert len({item["path"] for item in sources}) == len(sources)
    assert {item["path"] for item in sources} == set(GOVERNING.values()) | HISTORICAL
    for source in sources:
        assert source["revision"] == REVISION
        assert _hash(_read(source["path"])) == source["sha256"], source["path"]

    backlog_ids = set(
        re.findall(r"^\| (WR-\d{3}) \|", _read("docs/BACKLOG.md"), re.MULTILINE)
    )
    assessments = register["assessments"]
    for name, assessment in assessments.items():
        _check_reference(assessment["primary_destination"])
        for related in assessment["related_destinations"]:
            _check_reference(related)
        for field in (
            "existing_coverage",
            "additional_transfer_text",
            "acceptance_constraints_dependencies",
            "conflict_or_supersession",
        ):
            value = assessment[field]
            assert len(value) > 25, (name, field)
            assert value.casefold() not in {
                "covered by current engine",
                "already implemented",
            }
        assert assessment["classification"] in CLASSIFICATIONS
        assert assessment["implementation_status"] in STATUSES
        assert assessment["reviewer_disposition"] == "pending_review"
        assert assessment["transfer_disposition"] in {
            "already_covered",
            "requires_domain_transfer",
            "requires_backlog_expansion",
            "requires_decision",
            "historical_only",
        }
        assert set(assessment["backlog"]) <= backlog_ids
        assert assessment["supporting_evidence"]
        for evidence in assessment["supporting_evidence"]:
            assert (ROOT / evidence).is_file(), evidence

    expected = {}
    for path in GOVERNING.values():
        expected.update(_source_blocks(path))
    groups = _rows(register, "source_groups")
    assert len({item["id"] for item in groups}) == len(groups), "duplicate source group"
    assert {item["id"] for item in groups} == set(expected), "missing source group"
    by_group = defaultdict(list)
    clauses = _rows(register, "clauses")
    assert len({item["id"] for item in clauses}) == len(clauses), (
        "duplicate crosswalk ID"
    )
    for clause in clauses:
        group_id = clause["id"].removeprefix("D8-").rsplit("-C", 1)[0]
        assert group_id in expected, clause["id"]
        block, _, _ = expected[group_id]
        assert block[clause["start"] : clause["end"]] == clause["statement"], clause[
            "id"
        ]
        assert clause["end"] > clause["start"] >= 0
        assert clause["assessment"] in assessments
        assessment = assessments[clause["assessment"]]
        assert (
            clause["classification_override"] or assessment["classification"]
        ) in CLASSIFICATIONS
        assert (
            clause["status_override"] or assessment["implementation_status"]
        ) in STATUSES
        by_group[group_id].append(clause)
    for group in groups:
        block, _, end = expected[group["id"]]
        assert _hash(block) == group["sha256"], group["id"]
        assert group["line_end"] == end
        assert register["section_titles"][group["section_id"]]
        if group["disposition"] == "context_only":
            assert block.startswith("#")
            assert not by_group[group["id"]]
            assert "PASS:" not in block and "Post-V1 research backlog" not in block
        else:
            assert group["disposition"] == "clause_records"
            selected = sorted(by_group[group["id"]], key=lambda item: item["start"])
            assert selected, f"unmapped clause group {group['id']}"
            assert " ".join(
                " ".join(item["statement"] for item in selected).split()
            ) == " ".join(block.split()), group["id"]
            assert all(
                left["end"] <= right["start"] for left, right in pairwise(selected)
            )

    findings = register["historical_findings"]
    assert len({item["id"] for item in findings}) == len(findings)
    assert {item["source"] for item in findings} == HISTORICAL
    for finding in findings:
        lines = _read(finding["source"]).splitlines()
        assert 1 <= finding["line_start"] <= finding["line_end"] <= len(lines)
        excerpt = "\n".join(lines[finding["line_start"] - 1 : finding["line_end"]])
        assert _hash(excerpt) == finding["source_sha256"]
        assert finding["revision"] == REVISION
        assert finding["assessment"] in assessments
        assert finding["classification"] in CLASSIFICATIONS
        assert finding["implementation_status"] in STATUSES
        assert finding["reviewer_disposition"] == "pending_review"
        assert finding["additional_transfer_text"]


def test_d8_inventory_has_exact_declared_source_coverage_and_pending_destinations() -> (
    None
):
    _validate(_register())


@pytest.mark.parametrize(
    "defect", ("duplicate", "missing", "statement", "destination", "approved")
)
def test_d8_consistency_validation_rejects_forged_or_incomplete_records(
    defect: str,
) -> None:
    register = deepcopy(_register())
    if defect == "duplicate":
        register["clauses"].append(register["clauses"][0])
    elif defect == "missing":
        register["source_groups"].pop()
    elif defect == "statement":
        register["clauses"][0][3] = "covered by current engine"
    elif defect == "destination":
        register["assessments"]["workers"]["primary_destination"] = (
            "docs/MONTE_CARLO.md#not-a-section"
        )
    else:
        register["assessments"]["workers"]["reviewer_disposition"] = "approved"
    with pytest.raises(AssertionError):
        _validate(register)
