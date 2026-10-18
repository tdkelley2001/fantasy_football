from __future__ import annotations

from dataclasses import replace

from fantasy_football.undroppable_audit import (
    UndroppableAuditError,
    audit_undroppable_evidence,
)
from tests.adapter_fixtures import source_bundle

import pytest


def _bundle(*, enabled: bool | None = True, protected_ids: set[int] = frozenset({2})):
    bundle = source_bundle()
    for response in (bundle.league_initial, bundle.league_reconciliation):
        roster = response.payload["settings"]["rosterSettings"]
        if enabled is None:
            roster.pop("isUsingUndroppableList", None)
        else:
            roster["isUsingUndroppableList"] = enabled

    def apply_player(wrapper):
        player = wrapper["player"]
        player["droppable"] = player["id"] not in protected_ids

    for page in bundle.current_player_pages + bundle.future_player_pages:
        for wrapper in page.response.payload["players"]:
            apply_player(wrapper)
    for response in (bundle.league_initial, bundle.league_reconciliation):
        for team in response.payload["teams"]:
            for entry in team["roster"]["entries"]:
                apply_player(entry["playerPoolEntry"])
    return bundle


@pytest.mark.parametrize("enabled", [True, False, None])
def test_league_setting_preserves_true_false_and_missing(enabled) -> None:
    report = audit_undroppable_evidence(_bundle(enabled=enabled))
    assert report.league_setting_value is enabled
    assert report.league_setting_initial_present is (enabled is not None)
    assert report.league_setting_reconciliation_present is (enabled is not None)


def test_complete_player_field_coverage_distinguishes_false_from_true() -> None:
    report = audit_undroppable_evidence(_bundle(protected_ids={2, 5}))
    assert report.current_player_coverage.record_count == 5
    assert report.current_player_coverage.explicit_undroppable_count == 2
    assert report.current_player_coverage.explicit_droppable_count == 3
    assert report.current_player_coverage.unknown_count == 0
    assert report.rostered_player_coverage.record_count == 4
    assert report.rostered_player_coverage.explicit_undroppable_count == 1
    assert report.current_and_roster_values_reconciled
    assert len(report.future_week_coverage) == 2


def test_missing_player_field_is_unknown_not_false() -> None:
    bundle = _bundle()
    del bundle.current_player_pages[0].response.payload["players"][0]["player"]["droppable"]
    report = audit_undroppable_evidence(bundle)
    assert report.current_player_coverage.unknown_count == 1
    assert report.current_player_coverage.explicit_undroppable_count == 1


@pytest.mark.parametrize("value", [1, 0, "true", None])
def test_malformed_league_setting_fails(value) -> None:
    bundle = _bundle()
    bundle.league_initial.payload["settings"]["rosterSettings"]["isUsingUndroppableList"] = value
    with pytest.raises(UndroppableAuditError, match="expected boolean or absence"):
        audit_undroppable_evidence(bundle)


def test_malformed_player_field_fails() -> None:
    bundle = _bundle()
    bundle.current_player_pages[0].response.payload["players"][0]["player"]["droppable"] = "yes"
    with pytest.raises(UndroppableAuditError, match="player.droppable: expected boolean"):
        audit_undroppable_evidence(bundle)


def test_changed_league_setting_fails_reconciliation() -> None:
    bundle = _bundle()
    bundle.league_reconciliation.payload["settings"]["rosterSettings"]["isUsingUndroppableList"] = False
    with pytest.raises(UndroppableAuditError, match="changed between initial and reconciliation"):
        audit_undroppable_evidence(bundle)


def test_contradictory_player_evidence_fails() -> None:
    bundle = _bundle()
    roster_player = bundle.league_initial.payload["teams"][1]["roster"]["entries"][0]["playerPoolEntry"]["player"]
    roster_player["droppable"] = True
    with pytest.raises(UndroppableAuditError, match="contradictory player.droppable"):
        audit_undroppable_evidence(bundle)


def test_incomplete_future_player_universe_fails() -> None:
    bundle = _bundle()
    bundle = replace(bundle, future_player_pages=bundle.future_player_pages[:-1])
    with pytest.raises(UndroppableAuditError, match="player universe mismatch"):
        audit_undroppable_evidence(bundle)
