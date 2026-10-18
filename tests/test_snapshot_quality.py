from __future__ import annotations

from dataclasses import replace

import pytest

from fantasy_football.canonical.model import RuleGap
from fantasy_football.canonical.validation import CanonicalValidationError
from fantasy_football.espn_adapter import translate_bundle
from fantasy_football.quality import DiagnosticSeverity, generate_quality_report
from fantasy_football.snapshot_store import SnapshotStore
from tests.adapter_fixtures import source_bundle
from tests.canonical_fixtures import canonical_snapshot


def test_quality_report_is_deterministic_and_projection_classes_remain_distinct() -> None:
    snapshot = canonical_snapshot()
    first = generate_quality_report(snapshot)
    second = generate_quality_report(snapshot)

    assert first == second
    assert first.to_json() == second.to_json()
    assert first.team_count == 4
    assert first.player_count == 5
    assert first.rostered_player_count == 3
    assert first.unrostered_player_count == 2
    assert first.required_player_week_count == first.observed_player_week_count == 15
    assert first.projection_coverage.record_count == 15
    assert first.projection_coverage.present_raw_count == 12
    assert first.projection_coverage.explicit_zero_count == 3
    assert first.projection_coverage.missing_raw_count == 3
    assert first.projection_coverage.finite_negative_count == 3
    assert first.projection_coverage.positive_effective_count == 6


def test_breakdowns_reconcile_and_missingness_does_not_create_warning_flood() -> None:
    report = generate_quality_report(canonical_snapshot())

    for breakdowns in (
        report.projection_by_week,
        report.projection_by_default_position,
        report.projection_by_ownership,
    ):
        assert sum(item.coverage.record_count for item in breakdowns) == report.projection_coverage.record_count
        assert sum(item.coverage.missing_raw_count for item in breakdowns) == report.projection_coverage.missing_raw_count
        assert sum(item.coverage.explicit_zero_count for item in breakdowns) == report.projection_coverage.explicit_zero_count
        assert sum(item.coverage.finite_negative_count for item in breakdowns) == report.projection_coverage.finite_negative_count
        assert sum(item.coverage.positive_effective_count for item in breakdowns) == report.projection_coverage.positive_effective_count

    assert not any(item.code == "missing_projection" for item in report.diagnostics)
    warnings = [item for item in report.diagnostics if item.severity is DiagnosticSeverity.WARNING]
    assert {dict(item.context)["gap_id"] for item in warnings} == {"consolation_ladder", "regular_tie"}
    slot_info = next(item for item in report.diagnostics if item.code == "observed_unconfigured_eligibility_categories")
    assert slot_info.severity is DiagnosticSeverity.INFORMATION
    assert dict(slot_info.context)["slot_ids"] == "25"


def test_rule_limitations_preserve_status_capability_source_and_manual_eligibility() -> None:
    report = generate_quality_report(canonical_snapshot())
    consolation = next(item for item in report.rule_limitations if item.identifier == "consolation_ladder")
    unsupported = next(item for item in report.rule_limitations if item.identifier == "consolation_structure")

    assert consolation.status == "unresolved"
    assert consolation.affected_capabilities == ("full_placement_simulation",)
    assert consolation.manual_configuration_permitted is True
    assert consolation.source_id == "league-request-1"
    assert unsupported.status == "unsupported"


def test_reports_work_before_and_after_persistence(tmp_path) -> None:
    result = translate_bundle(source_bundle())
    before = generate_quality_report(result.snapshot)
    store = SnapshotStore(tmp_path / "quality.sqlite3")
    store.initialize()
    metadata = store.publish(result)
    after = generate_quality_report(store.load(metadata.snapshot_id).snapshot)

    assert before.snapshot_id is None
    assert after.snapshot_id == metadata.snapshot_id
    assert replace(after, snapshot_id=None) == before


@pytest.mark.parametrize(
    ("capabilities", "message"),
    [
        ((), "at least one downstream capability"),
        (("simulation", "simulation"), "duplicate"),
        (("",), "must be non-empty text"),
    ],
)
def test_rule_gap_capabilities_are_structurally_valid(capabilities, message) -> None:
    snapshot = canonical_snapshot()
    gap = replace(snapshot.rule_gaps[0], affected_capabilities=capabilities)
    malformed = replace(snapshot, rule_gaps=(gap,) + snapshot.rule_gaps[1:])

    with pytest.raises(CanonicalValidationError, match=message):
        generate_quality_report(malformed)


def test_empty_rule_gap_identifier_is_rejected() -> None:
    snapshot = canonical_snapshot()
    gap = RuleGap("", "reason", "league-request-1", ("simulation",), True)
    with pytest.raises(CanonicalValidationError, match="gap_id.*non-empty"):
        generate_quality_report(replace(snapshot, rule_gaps=(gap,)))

