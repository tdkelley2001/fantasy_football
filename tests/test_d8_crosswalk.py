"""Validate the declared D8.1 inventory, not semantic completeness or approval."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
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
TRANSFERS = {
    "already_covered",
    "requires_domain_transfer",
    "requires_backlog_expansion",
    "requires_decision",
    "historical_only",
}
PRESERVED_KEYS = (
    "accepted_revision",
    "sources",
    "source_groups",
    "clauses",
    "historical_findings",
    "assessments",
    "section_titles",
)
PRESERVED_INVENTORY_SHA256 = (
    "030a5133e9a8beef2aa7b1ebad01e6977fa9ce057c963faf8d41c7fed175dacc"
)


def _effective(register: dict, clause: dict, *, baseline: bool = False) -> dict:
    """Resolve only explicit clause fields; assessment conflict prose is context."""
    assessment = register["assessments"][clause["assessment"]]
    result = {
        "classification": clause["classification_override"]
        or assessment["classification"],
        "implementation_status": clause["status_override"]
        or assessment["implementation_status"],
        "transfer_disposition": assessment["transfer_disposition"],
        "conflict_references": [],
    }
    if not baseline:
        override = register["clause_overrides"].get(clause["id"], {})
        result.update({key: value for key, value in override.items() if key in result})
    return result


def _validate_clause_decisions(register: dict, clauses: list[dict]) -> None:
    # Explicitly preserve the accepted f7e347e inventory, not the flawed inherited
    # decisions. No network/history lookup or assertion of semantic completeness.
    preserved = {key: register[key] for key in PRESERVED_KEYS}
    digest = _hash(
        json.dumps(preserved, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    )
    assert digest == PRESERVED_INVENTORY_SHA256
    assert register["preserved_inventory_sha256"] == digest
    by_id = {clause["id"]: clause for clause in clauses}
    audits = register["conflict_audit"]
    assert set(audits) == {f"C{number:02d}" for number in range(1, 20)}
    relations = {
        "accepted_supersession",
        "implementation_gap",
        "reference_contract",
        "remaining_evidence_gate",
        "open_scope_decision",
        "authority_transfer_gate",
        "independent_acceptance_gate",
    }
    assert (
        set(register["clause_override_resolution"]["relationship_kinds"]) == relations
    )
    overrides = register["clause_overrides"]
    assert overrides.keys() <= by_id.keys()
    for cid, override in overrides.items():
        assert set(override) <= {
            "classification",
            "implementation_status",
            "transfer_disposition",
            "conflict_references",
            "reason_ref",
            "reviewer_disposition",
        }
        assert override["reviewer_disposition"] == "pending_review"
        assert len(register["clause_override_reasons"][override["reason_ref"]]) > 30
        effective = _effective(register, by_id[cid])
        assert effective["classification"] in CLASSIFICATIONS
        assert effective["implementation_status"] in STATUSES
        assert effective["transfer_disposition"] in TRANSFERS
        refs = effective["conflict_references"]
        assert isinstance(refs, list)
        assert len({ref["group"] for ref in refs}) == len(refs)
        for ref in refs:
            assert set(ref) == {"group", "relationship"}
            assert ref["group"] in audits
            assert ref["relationship"] in relations
            if ref["relationship"] in {
                "implementation_gap",
                "open_scope_decision",
                "independent_acceptance_gate",
            }:
                assert effective["classification"] in {
                    "conditional_approval_or_constraint",
                    "approved_unimplemented_requirement",
                    "unresolved_conflict_or_decision",
                }, cid
                assert effective["implementation_status"] in {
                    "partially_implemented",
                    "approved_but_unimplemented",
                    "contradicted_by_current_behavior",
                    "pending_source_verification",
                }, cid
            if ref["relationship"] == "accepted_supersession":
                assert ref["group"] in {"C01", "C02", "C04", "C08", "C11"}
                assert effective["classification"] != "unresolved_conflict_or_decision"
                assert effective["transfer_disposition"] != "requires_decision"

    for group, audit in audits.items():
        assert audit["reviewer_disposition"] == "pending_review"
        expected_assessments = sorted(
            key
            for key, value in register["assessments"].items()
            if group in re.findall(r"\bC\d{2}\b", value["conflict_or_supersession"])
        )
        assert audit["audited_assessments"] == expected_assessments
        assert audit["audited_clause_ids"] == sorted(
            clause["id"]
            for clause in clauses
            if clause["assessment"] in expected_assessments
        )
        assert audit["related_clause_ids"] == sorted(
            clause["id"]
            for clause in clauses
            if any(
                ref["group"] == group
                for ref in _effective(register, clause)["conflict_references"]
            )
        )

    # Independent obligation anchors: fields cannot hide actual defects, missing
    # scientific evidence, unimplemented lifecycle, or unfinished release gates.
    guards = {
        "D8-MS-L0061-C01": ("C03", "open_scope_decision"),
        "D8-MS-L0033-C08": ("C02", "remaining_evidence_gate"),
        "D8-MS-L0123-C01": ("C05", "remaining_evidence_gate"),
        "D8-MS-L0173-C01": ("C06", "implementation_gap"),
        "D8-MS-L0179-C05": ("C07", "implementation_gap"),
        "D8-MS-L0237-C05": ("C08", "remaining_evidence_gate"),
        "D8-MS-L0223-C02": ("C09", "implementation_gap"),
        "D8-MS-L0227-C01": ("C10", "implementation_gap"),
        "D8-MS-L0311-C06": ("C12", "implementation_gap"),
        "D8-MS-L0311-C12": ("C13", "open_scope_decision"),
        "D8-MS-L0507-C03": ("C14", "implementation_gap"),
        "D8-MS-L0335-C05": ("C15", "implementation_gap"),
        "D8-MS-L0335-C02": ("C16", "open_scope_decision"),
        "D8-MS-L0361-C04": ("C17", "implementation_gap"),
        "D8-MS-L0541-C03": ("C18", "implementation_gap"),
        "D8-MS-L0547-C02": ("C19", "independent_acceptance_gate"),
        "D8-MS-L0549-C01": ("C19", "independent_acceptance_gate"),
        "D8-MS-L0543-C01": ("C19", "independent_acceptance_gate"),
        "D8-MS-L0007-C05": ("C01", "authority_transfer_gate"),
    }
    for cid, (group, relationship) in guards.items():
        effective = _effective(register, by_id[cid])
        assert effective["classification"] not in {
            "historical_or_superseded",
            "proposal_not_yet_authorized",
            "current_implemented_contract",
        }, cid
        assert effective["implementation_status"] in {
            "partially_implemented",
            "approved_but_unimplemented",
            "contradicted_by_current_behavior",
            "pending_source_verification",
        }, cid
        assert effective["transfer_disposition"] != "historical_only", cid
        assert {"group": group, "relationship": relationship} in effective[
            "conflict_references"
        ], cid

    # These are accepted rules, not new WR-024/dependency/statistical decisions.
    unaffected = (
        "D8-MS-L0179-C02",
        "D8-MS-L0299-C03",
        "D8-MS-L0499-C04",
        "D8-MS-L0173-C03",
        "D8-MS-L0061-C02",
    )
    for cid in unaffected:
        effective = _effective(register, by_id[cid])
        assert effective == {
            "classification": "current_implemented_contract",
            "implementation_status": "implemented_and_supported_by_tests",
            "transfer_disposition": "already_covered",
            "conflict_references": [],
        }, cid

    changed = []
    status_only = []
    transitions = Counter()
    fields = ("classification", "implementation_status", "transfer_disposition")
    for clause in clauses:
        old = _effective(register, clause, baseline=True)
        new = _effective(register, clause)
        if any(old[field] != new[field] for field in fields):
            changed.append(clause["id"])
            transitions[
                (old[fields[0]], new[fields[0]], old[fields[2]], new[fields[2]])
            ] += 1
            if old[fields[0]] == new[fields[0]] and old[fields[2]] == new[fields[2]]:
                status_only.append(clause["id"])
    summary = register["followup_change_summary"]
    assert summary["baseline_commit"] == "f7e347e04618edf2ad05f85ac48f9b783f69920e"
    assert summary["changed_clause_ids"] == changed
    assert summary["status_only_clause_ids"] == status_only
    assert summary["grouped_transitions"] == [
        {
            "old_classification": a,
            "new_classification": b,
            "old_transfer": c,
            "new_transfer": d,
            "count": n,
        }
        for (a, b, c, d), n in sorted(transitions.items())
    ]


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
    _validate_clause_decisions(register, clauses)
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


def test_clause_override_precedence_is_explicit_and_does_not_inherit_context() -> None:
    register = _register()
    clauses = {row["id"]: row for row in _rows(register, "clauses")}
    clause = deepcopy(clauses["D8-MS-L0179-C02"])
    # Even a conflicting row-level value loses to the named clause override.
    clause["classification_override"] = "historical_or_superseded"
    clause["status_override"] = "historical_or_superseded"
    effective = _effective(register, clause)
    assert effective["classification"] == "current_implemented_contract"
    assert effective["implementation_status"] == "implemented_and_supported_by_tests"
    assert effective["transfer_disposition"] == "already_covered"
    assert effective["conflict_references"] == []
    assert "C07" in register["assessments"]["essential"]["conflict_or_supersession"]


@pytest.mark.parametrize(
    ("cid", "group"),
    (("D8-MS-L0295-C03", "C11"), ("D8-MS-L0115-C01", "C04")),
)
def test_accepted_successor_confirmation_is_not_a_new_decision(
    cid: str, group: str
) -> None:
    register = _register()
    clause = next(row for row in _rows(register, "clauses") if row["id"] == cid)
    effective = _effective(register, clause)
    assert effective["transfer_disposition"] != "requires_decision"
    assert effective["classification"] != "unresolved_conflict_or_decision"
    assert {"group": group, "relationship": "accepted_supersession"} in effective[
        "conflict_references"
    ]


@pytest.mark.parametrize(
    "defect",
    (
        "history",
        "implemented",
        "missing_reference",
        "false_successor",
        "unrelated_conflict",
        "approved",
        "unknown_reference",
    ),
)
def test_overrides_cannot_hide_open_requirements_or_invent_conflicts(
    defect: str,
) -> None:
    register = deepcopy(_register())
    override = register["clause_overrides"]["D8-MS-L0179-C05"]
    if defect == "history":
        override["classification"] = "historical_or_superseded"
    elif defect == "implemented":
        override["implementation_status"] = "implemented_and_supported_by_tests"
    elif defect == "missing_reference":
        override["conflict_references"] = []
    elif defect == "false_successor":
        override["conflict_references"][0]["relationship"] = "accepted_supersession"
    elif defect == "unrelated_conflict":
        register["clause_overrides"]["D8-MS-L0179-C02"]["classification"] = (
            "unresolved_conflict_or_decision"
        )
    elif defect == "approved":
        override["reviewer_disposition"] = "approved"
    else:
        override["conflict_references"][0]["group"] = "C99"
    with pytest.raises(AssertionError):
        _validate(register)


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
