"""Guard a proposed retention interpretation, without approving it or replacing
the functional search-index and application-retention tests.
"""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from test_d8_crosswalk import DOCUMENT, HISTORICAL, ROOT, _hash, _register, _rows
from test_d82_transfer import _layer, _section

BASE = "38b6f78881e872dd07ff1fc16f6a9785e77d59c5"
PREFIX = "75ccfbc60a8a628f42b846788f12a482f7f48f5489da1d7cf714c9861edd1958"
RESTRICTIONS = {f"D8-MS-L0311-C{n}" for n in (12, 13, 14)}
SUCCESSORS = {
    "D8-MS-L0513-C01",
    "D8-RM-L0145-C01",
    "D8-MS-L0525-C01",
    "D8-MS-L0527-C01",
    "D8-MS-L0531-C05",
    "D8-RM-L0159-C01",
    "D8-RM-L0161-C01",
    "D8-RM-L0165-C01",
}
TARGETS = {
    "docs/APPLICATION_SERVICE.md#c13-proposed-retention-authority",
    "docs/UNIFIED_ACTION_SEARCH.md#c13-proposed-engine-lifecycle",
    "docs/BACKLOG.md#c13-proposed-authority-decision",
}


def _proposal() -> dict:
    text = DOCUMENT.read_text(encoding="utf-8")
    return json.loads(text.split("```json d8-c13-proposal\n")[1].split("\n```")[0])


def _validate(proposal: dict) -> None:
    assert proposal["contract"] == "d8-c13-proposal-v1"
    assert proposal["baseline_revision"] == BASE
    assert proposal["accepted_d82_prefix_sha256"] == PREFIX
    assert proposal["reviewer_disposition"] == "pending_review"
    assert proposal["decision_accepted"] is False
    assert proposal["authority_switch_completed"] is False
    assert proposal["blocks_affected_source_retirement"] is True
    baseline = _register()
    clauses = {c["id"]: c for c in _rows(baseline, "clauses")}
    for name, expected in (
        ("original_restrictions", RESTRICTIONS),
        ("accepted_successors", SUCCESSORS),
    ):
        sources = proposal[name]
        assert len(sources) == len(expected)
        assert {s["clause_id"] for s in sources} == expected
        for source in sources:
            cid = source["clause_id"]
            assert source["statement"] == clauses[cid]["statement"]
            assert source["source_revision"] == baseline["accepted_revision"]
            path = (
                "docs/MASTER_SPEC.md" if cid.startswith("D8-MS") else "docs/ROADMAP.md"
            )
            assert source["source_path"] == path
    dispositions = proposal["proposed_dispositions"]
    assert dispositions.keys() == RESTRICTIONS
    for decision in dispositions.values():
        assert decision["reviewer_disposition"] == "pending_review"
        assert set(decision["accepted_successor_ids"]) == SUCCESSORS
        assert set(decision["destinations"]) == TARGETS
        assert "ephemeral engine context" in decision["scope"]
        assert "bounded application history" in decision["scope"]
    assert {e["destination"] for e in proposal["destination_evidence"]} == TARGETS
    for evidence in proposal["destination_evidence"]:
        assert _hash(_section(evidence["destination"])) == evidence["section_sha256"]
    categories = proposal["categories"]
    assert set(categories) == {
        "temporary_index",
        "in_memory_state",
        "orchestration_result",
        "application_runs",
        "retained_candidates",
        "numerical_checkpoints",
        "canonical_snapshots",
        "user_exports",
    }
    assert categories["temporary_index"]["owner"] == "engine caller"
    assert categories["application_runs"]["owner"] == "application"
    assert categories["retained_candidates"]["owner"] == "application"
    assert categories["user_exports"]["owner"] == "user"
    for category in categories.values():
        assert category["data_class"] and category["lifetime"]
        _section(category["destination"])
    obligations = {o["work_item"]: o for o in proposal["remaining_obligations"]}
    assert obligations.keys() == {"WR-026", "WR-021", "WR-017"}
    assert obligations["WR-026"]["state"] == "Backlog"
    assert "fault injection" in obligations["WR-026"]["acceptance"]
    assert "expiration" in obligations["WR-021"]["acceptance"]
    assert proposal["compatibility"]["production_changes"] is False
    assert proposal["compatibility"]["migration_required_by_proposal"] is False
    amendments = proposal["section_amendments"]
    assert set(amendments) == {
        "docs/UNIFIED_ACTION_SEARCH.md#result-indexing-pagination-and-cleanup"
    }
    for target, amendment in amendments.items():
        # Exact section at accepted BASE, before the ownership wording fix.
        assert amendment["accepted_section_sha256"] == (
            "4738cac39dc2ba5786bbeb6e7689bae99551dfbe79038d66d9fa4a4ca1523531"
        )
        assert amendment["proposed_section_sha256"] == _hash(_section(target))
        assert amendment["reviewer_disposition"] == "pending_review"
    for evidence in proposal["implementation_evidence"]:
        source = (ROOT / evidence["path"]).read_text(encoding="utf-8")
        for symbol in evidence["symbols"]:
            assert f"def {symbol.split('.')[-1]}(" in source
    assert all((ROOT / p).is_file() for p in proposal["functional_evidence"])
    # The accepted conflict is not rewritten to pretend this proposal was approved.
    layer = _layer()
    for row in layer["records"]:
        if row[0] in RESTRICTIONS:
            assert row[5] == "blocked_authority_conflict" and row[7] == "C13"
    assert all((ROOT / path).is_file() for path in HISTORICAL)


def test_c13_additive_proposal_preserves_the_entire_accepted_d82_document() -> None:
    prefix = DOCUMENT.read_text(encoding="utf-8").split(
        "\n## C13 proposed disposition\n", 1
    )[0]
    assert _hash(prefix) == PREFIX
    _validate(_proposal())


@pytest.mark.parametrize(
    "defect",
    [
        "missing_restriction",
        "missing_successor",
        "source_rewrite",
        "approval",
        "retirement",
        "ownership",
        "cleanup_waiver",
        "migration",
        "bad_destination",
    ],
)
def test_c13_rejects_untraceable_or_premature_authority_changes(defect: str) -> None:
    proposal = deepcopy(_proposal())
    if defect == "missing_restriction":
        proposal["original_restrictions"].pop()
    elif defect == "missing_successor":
        proposal["accepted_successors"].pop()
    elif defect == "source_rewrite":
        proposal["original_restrictions"][0]["statement"] = "Durable archive approved"
    elif defect == "approval":
        proposal["decision_accepted"] = True
    elif defect == "retirement":
        proposal["blocks_affected_source_retirement"] = False
    elif defect == "ownership":
        proposal["categories"]["temporary_index"]["owner"] = "application"
    elif defect == "cleanup_waiver":
        proposal["remaining_obligations"][0]["state"] = "Done"
    elif defect == "migration":
        proposal["compatibility"]["production_changes"] = True
    elif defect == "bad_destination":
        proposal["proposed_dispositions"][next(iter(RESTRICTIONS))]["destinations"] = []
    with pytest.raises(AssertionError):
        _validate(proposal)


@pytest.mark.parametrize(
    ("target", "required"),
    [
        (
            "docs/APPLICATION_SERVICE.md#c13-proposed-retention-authority",
            (
                "bounded application-owned analytical history",
                "submission time",
                "Explicit deletion",
                "no continuous TTL sweeper",
                "No production migration",
                "does not delete or rewrite source evidence",
                "No automatic HTTP search resume",
                "dedicated expiration-boundary verification",
                "pending independent review",
            ),
        ),
        (
            "docs/UNIFIED_ACTION_SEARCH.md#c13-proposed-engine-lifecycle",
            (
                "not permanent application history",
                "No cross-refresh reuse",
                "no context-manager methods",
                "WR-026",
                "not automatically reimported",
                "scratch cleanup must not delete them",
                "before a result returns",
            ),
        ),
        (
            "docs/BACKLOG.md#c13-proposed-authority-decision",
            (
                "WR-026 remains Backlog",
                "C13 continues to block",
                "M6.2/M7",
                "proposal In Review",
                "no D8.3 authority switch",
            ),
        ),
    ],
)
def test_c13_scope_and_protections_are_present_in_permanent_owners(
    target: str, required: tuple[str, ...]
) -> None:
    text = _section(target)
    assert all(fragment in text for fragment in required)
