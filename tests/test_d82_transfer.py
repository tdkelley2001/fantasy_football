"""Check D8.2 traceability and selected obligations, not independent acceptance.

Semantic coverage still requires review of the clauses against their destinations.
These guards supplement the unchanged D8.1 inventory and functional engine tests.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from copy import deepcopy

import pytest
from test_d8_crosswalk import (
    DOCUMENT,
    HISTORICAL,
    ROOT,
    _check_reference,
    _effective,
    _hash,
    _register,
    _rows,
)

BASE = "2c9c4be560bc3cd1f5839ec1ead54027194b6a0c"
PREFIX_HASH = "8b758316c02f2381c94756c9d1a460c93a02b20a88fe333e0e38595ac26d57a6"
DATED_DOMAIN = {
    "D8-RM-L0139-C02",
    "D8-RM-L0139-C03",
    "D8-RM-L0139-C04",
    "D8-RM-L0139-C05",
    "D8-MS-L0515-C06",
    "D8-MS-L0515-C07",
    "D8-RM-L0147-C02",
}
STATUSES = {
    "verified_existing",
    "transferred_to_domain",
    "transferred_to_backlog",
    "historical_superseded_confirmed",
    "preserved_with_open_implementation_gap",
    "blocked_authority_conflict",
}


def _layer() -> dict:
    text = DOCUMENT.read_text(encoding="utf-8")
    return json.loads(
        text.split("```json d8-transfer-verification\n", 1)[1].split("\n```", 1)[0]
    )


def _section(destination: str) -> str:
    _check_reference(destination)
    name, anchor = destination.split("#")
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if not match:
            continue
        slug = re.sub(r"[^\w\- ]", "", match[2].casefold()).replace(" ", "-")
        if start is None:
            if slug == anchor:
                start, level = i, len(match[1])
        elif len(match[1]) <= level:
            return "\n".join(lines[start:i]).rstrip()
    assert start is not None, destination
    return "\n".join(lines[start:]).rstrip()


def _validate(layer: dict) -> None:
    baseline = _register()
    clauses = _rows(baseline, "clauses")
    by_id = {c["id"]: c for c in clauses}
    assert layer["contract"] == "d8.2-transfer-verification-v1"
    assert layer["accepted_d81_revision"] == BASE
    assert layer["accepted_d81_crosswalk_sha256"] == PREFIX_HASH
    assert layer["reviewer_disposition"] == "pending_review"
    assert layer["authority_switch_completed"] is False
    assert layer["v1_released"] is False
    assert set(layer["status_definitions"]) == STATUSES
    groups = layer["coverage_groups"]
    assert groups.keys() == baseline["assessments"].keys()
    for key, group in groups.items():
        assert group["reviewer_disposition"] == "pending_review"
        assessment = baseline["assessments"][key]
        assert (
            group["preserved_acceptance"]
            == assessment["acceptance_constraints_dependencies"]
        )
        assert group["implementation_evidence"] == assessment["supporting_evidence"]
        targets = [group["primary_destination"], *group["supporting_destinations"]]
        assert targets == [e["destination"] for e in group["evidence"]]
        for evidence in group["evidence"]:
            text = _section(evidence["destination"])
            assert evidence["section_sha256"] == _hash(text)
            assert evidence["excerpts"], key
            assert all(excerpt in text for excerpt in evidence["excerpts"])

    columns = layer["record_columns"]
    assert columns == [
        "clause_id",
        "d81_classification",
        "d81_implementation_status",
        "d81_disposition",
        "destination_group",
        "transfer_status",
        "remaining_gate",
        "authority_conflict",
    ]
    records = [dict(zip(columns, row, strict=True)) for row in layer["records"]]
    assert len(records) == len(by_id) == 2093
    assert {r["clause_id"] for r in records} == by_id.keys()
    decision_ids = set()
    historical_ids = set()
    for r in records:
        cid = r["clause_id"]
        effective = _effective(baseline, by_id[cid])
        for field in ("classification", "implementation_status"):
            assert r[f"d81_{field}"] == effective[field], cid
        disposition = r["d81_disposition"]
        assert disposition == effective["transfer_disposition"], cid
        assert r["destination_group"] in groups, cid
        assert r["transfer_status"] in STATUSES, cid
        assert r["remaining_gate"] in layer["remaining_gates"], cid
        target = groups[r["destination_group"]]["primary_destination"]
        if disposition == "requires_domain_transfer":
            if cid in DATED_DOMAIN:
                assert r["transfer_status"] == "historical_superseded_confirmed"
            else:
                assert r["transfer_status"] == "transferred_to_domain", cid
                assert not target.startswith("docs/BACKLOG.md#"), cid
        if disposition == "requires_backlog_expansion":
            assert r["transfer_status"] == "transferred_to_backlog", cid
            assert target.startswith("docs/BACKLOG.md#"), cid
        if disposition == "requires_decision":
            decision_ids.add(cid)
        if r["transfer_status"] == "historical_superseded_confirmed":
            historical_ids.add(cid)
        if r["authority_conflict"]:
            assert r["authority_conflict"] == "C13"
            assert r["transfer_status"] == "blocked_authority_conflict"
            assert r["remaining_gate"] == "authority"
        for reference in effective["conflict_references"]:
            if reference["relationship"] == "implementation_gap":
                assert r["transfer_status"] in {
                    "preserved_with_open_implementation_gap",
                    "transferred_to_backlog",
                }, cid
                assert r["remaining_gate"] == "implementation", cid
            if reference["relationship"] == "independent_acceptance_gate":
                assert r["remaining_gate"] == "release", cid

    assert len(decision_ids) == 11
    assert layer["decision_dispositions"].keys() == decision_ids
    for cid, decision in layer["decision_dispositions"].items():
        assert decision["reviewer_disposition"] == "pending_review"
        _check_reference(decision["actual_destination"])
        assert set(decision["source_clause_ids"]) <= by_id.keys()
        assert len(decision["disposition"]) > 100
        row = next(r for r in records if r["clause_id"] == cid)
        if cid.startswith("D8-MS-L0311-"):
            assert decision["kind"] == "unresolved_authority_conflict"
            assert decision["authority_conflict"] == row["authority_conflict"] == "C13"
            assert decision["blocks_source_retirement"] is True
            assert row["transfer_status"] == "blocked_authority_conflict"
            assert {
                "D8-MS-L0311-C12",
                "D8-MS-L0513-C01",
                "D8-RM-L0145-C01",
            } <= set(decision["source_clause_ids"])
        else:
            assert decision["authority_conflict"] is None
            assert decision["blocks_source_retirement"] is False
    assert Counter(d["kind"] for d in layer["decision_dispositions"].values()) == {
        "unresolved_authority_conflict": 3,
        "binding_control_with_accepted_execution_scope": 5,
        "binding_requirement_unimplemented": 1,
        "independent_authority_transfer_gate_retained": 2,
    }
    assert layer["historical_preservation"].keys() == historical_ids
    for cid, history in layer["historical_preservation"].items():
        accepted = [
            ref["group"]
            for ref in _effective(baseline, by_id[cid])["conflict_references"]
            if ref["relationship"] == "accepted_supersession"
        ]
        assert history["accepted_successor_groups"] == accepted
        assert history["source_clause_id"] == cid
        assert history["accepted_revision"] == BASE

    expected_counts = {
        "already_covered": 1840,
        "requires_domain_transfer": 67,
        "requires_backlog_expansion": 47,
        "requires_decision": 11,
        "historical_only": 128,
    }
    assert layer["accounting"].keys() == expected_counts.keys()
    for disposition, count in expected_counts.items():
        selected = [r for r in records if r["d81_disposition"] == disposition]
        account = layer["accounting"][disposition]
        assert account["count"] == len(selected) == count
        assert account["clause_ids"] == [r["clause_id"] for r in selected]
        assert account["statuses"] == Counter(r["transfer_status"] for r in selected)
        assert account["destinations"] == Counter(
            groups[r["destination_group"]]["primary_destination"] for r in selected
        )

    historical = layer["historical_transfers"]
    assert len(historical) == 33
    assert {h["finding_id"] for h in historical} == {
        h["id"] for h in baseline["historical_findings"]
    }
    for transfer, finding in zip(
        historical, baseline["historical_findings"], strict=True
    ):
        assert transfer["finding_id"] == finding["id"]
        assert transfer["preserved_requirement"] == finding["statement"]
        assert transfer["source_sha256"] == finding["source_sha256"]
        assert transfer["source_revision"] == finding["revision"]
        assert transfer["reviewer_disposition"] == "pending_review"
        assert transfer["destination_group"] in groups
    held = set(layer["source_retirement"]["held_sources"])
    assert (
        HISTORICAL
        | {
            "docs/MASTER_SPEC.md",
            "docs/ROADMAP.md",
            "docs/development/documentation-consolidation.md",
            "docs/development/d8-authority-transfer-crosswalk.md",
        }
        <= held
    )
    assert all((ROOT / path).is_file() for path in held)
    assert layer["source_retirement"]["ready"] is False
    assert layer["source_retirement"]["blocked_by"] == [
        "D8.2 independent acceptance",
        "C13 unresolved retention authority",
    ]
    for evidence in layer["material_acceptance"]:
        text = _section(evidence["destination"])
        assert _hash(text) == evidence["section_sha256"]
        assert evidence["fragments"]
        assert all(f in text for f in evidence["fragments"])


def test_d82_preserves_accepted_prefix_and_every_effective_clause() -> None:
    prefix = DOCUMENT.read_text(encoding="utf-8").split(
        "\n## D8.2 transfer verification\n", 1
    )[0]
    assert _hash(prefix) == PREFIX_HASH
    # Accepted source hashes are newline-normalized for portable checkouts.
    # Also prohibit mixed newline bytes; local before/after raw hashes are
    # independently compared during this documentation transfer.
    for source in _register()["sources"][:2]:
        path = ROOT / source["path"]
        text = path.read_text(encoding="utf-8")
        assert _hash(text) == source["sha256"]
        assert path.read_bytes() in {
            text.encode("utf-8"),
            text.replace("\n", "\r\n").encode("utf-8"),
        }
    _validate(_layer())


@pytest.mark.parametrize(
    "defect",
    [
        "missing_clause",
        "duplicate_clause",
        "invalid_destination",
        "approved",
        "missing_decision",
        "resolved_retention",
        "hidden_implementation_gap",
        "missing_domain_transfer",
        "missing_backlog_transfer",
        "lost_acceptance",
        "changed_source_text",
        "changed_accounting",
        "retired_source",
        "authority_switch",
    ],
)
def test_d82_rejects_incomplete_or_forged_transfer_evidence(defect: str) -> None:
    layer = deepcopy(_layer())
    if defect == "missing_clause":
        layer["records"].pop()
    elif defect == "duplicate_clause":
        layer["records"][0] = layer["records"][1]
    elif defect == "invalid_destination":
        layer["coverage_groups"]["purpose"]["primary_destination"] = (
            "docs/MASTER_SPEC.md#1-purpose"
        )
    elif defect == "approved":
        layer["coverage_groups"]["purpose"]["reviewer_disposition"] = "approved"
    elif defect == "missing_decision":
        layer["decision_dispositions"].popitem()
    elif defect == "resolved_retention":
        row = next(r for r in layer["records"] if r[0] == "D8-MS-L0311-C12")
        row[5], row[7] = "verified_existing", None
    elif defect == "hidden_implementation_gap":
        row = next(r for r in layer["records"] if r[0] == "D8-MS-L0179-C05")
        row[5] = "verified_existing"
    elif defect in {"missing_domain_transfer", "missing_backlog_transfer"}:
        disposition = (
            "requires_domain_transfer"
            if defect == "missing_domain_transfer"
            else "requires_backlog_expansion"
        )
        row = next(r for r in layer["records"] if r[3] == disposition)
        row[5] = "verified_existing"
    elif defect == "lost_acceptance":
        layer["coverage_groups"]["precision"]["preserved_acceptance"] = ""
    elif defect == "changed_source_text":
        layer["historical_transfers"][0]["preserved_requirement"] = "fulfilled"
    elif defect == "changed_accounting":
        layer["accounting"]["requires_domain_transfer"]["count"] = 66
    elif defect == "retired_source":
        layer["source_retirement"]["held_sources"].remove("docs/MASTER_SPEC.md")
    elif defect == "authority_switch":
        layer["authority_switch_completed"] = True
    with pytest.raises(AssertionError):
        _validate(layer)


@pytest.mark.parametrize(
    ("destination", "requirements"),
    [
        (
            "docs/MONTE_CARLO.md#precision-and-stopping",
            (
                "95% family confidence",
                "h=0.005",
                "outstanding default/evidence/time-control obligations",
            ),
        ),
        (
            "docs/BACKLOG.md#wr-008-representative-performance-and-diagnostics",
            ("higher-fidelity", "ordering and selected drops/additions", "preflight"),
        ),
        (
            "docs/BACKLOG.md#wr-017-query-export-and-unit-compatibility",
            ("multi-sort", "without resimulation", "does not perform the conversion"),
        ),
        (
            "docs/BACKLOG.md#wr-021-output-provenance-and-numerical-lifecycle",
            (
                "p95 below 100 ms",
                "one active/at most eight pending",
                "explicit independent signoff",
            ),
        ),
    ],
)
def test_material_duties_cannot_be_removed_by_editing_transfer_metadata(
    destination: str, requirements: tuple[str, ...]
) -> None:
    text = _section(destination)

    def require_obligations(candidate: str) -> None:
        assert all(requirement in candidate for requirement in requirements)

    require_obligations(text)
    for requirement in requirements:
        with pytest.raises(AssertionError):
            require_obligations(text.replace(requirement, ""))


def test_open_defects_partial_support_and_numerical_identity_stay_visible() -> None:
    backlog = (ROOT / "docs/BACKLOG.md").read_text(encoding="utf-8")
    for token in ("WR-018", "WR-023", "WR-024", "WR-025", "WR-026"):
        assert token in backlog
    model = (ROOT / "docs/PLAYER_OUTCOME_MODEL.md").read_text(encoding="utf-8")
    for token in (
        "missing_projection_outcome",
        "deterministic-zero-v1",
        "draw",
        "Signed",
    ):
        assert token in model
    partial = (ROOT / "docs/PARTIAL_WEEK.md").read_text(encoding="utf-8")
    for token in ("unstarted", "cutoff", "carry", "locked", "No automatic ESPN"):
        assert token in partial
    assert "WR-002" in backlog and "D8.2" in backlog
