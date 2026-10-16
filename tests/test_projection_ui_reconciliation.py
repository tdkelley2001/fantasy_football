from __future__ import annotations

import pytest

from fantasy_football.future_data_audit import PlayerEvidence, PoolPlayer
from fantasy_football.projection_ui_reconciliation import (
    ProjectionUiReconciliationError,
    ReconciliationReport,
    build_examples,
    render_report,
)


def evidence(
    player_id: int,
    value: float | None,
    *,
    pro_team_id: int = 3,
    injury: str | None = "ACTIVE",
) -> PlayerEvidence:
    return PlayerEvidence(
        player_id=player_id,
        status="FREEAGENT",
        owner_team_id=0,
        default_position_id=2,
        eligible_slot_ids=(2, 23),
        pro_team_id=pro_team_id,
        injury_status=injury,
        projections=((7, value),),
    )


def raw(player_id: int, name: str) -> dict:
    return {"id": player_id, "player": {"id": player_id, "fullName": name}}


def sample_inputs():
    raw_players = {
        1: raw(1, "Roster Missing"),
        2: raw(2, "Free Missing"),
        3: raw(3, "Zero Example"),
        4: raw(4, "Positive Example"),
        5: raw(5, "Negative Example"),
    }
    parsed = {
        1: evidence(1, None, injury="QUESTIONABLE"),
        2: evidence(2, None),
        3: evidence(3, 0, pro_team_id=7),
        4: evidence(4, 11.75),
        5: evidence(5, -1.25),
    }
    current = {
        1: PoolPlayer(1, "ONTEAM", 10),
        2: PoolPlayer(2, "FREEAGENT", 0),
        3: PoolPlayer(3, "ONTEAM", 11),
        4: PoolPlayer(4, "ONTEAM", 12),
        5: PoolPlayer(5, "FREEAGENT", 0),
    }
    return raw_players, parsed, current


def test_selects_named_examples_and_prefers_rostered_missing() -> None:
    raw_players, parsed, current = sample_inputs()
    examples, counts, rostered_missing = build_examples(
        raw_players_by_id=raw_players,
        evidence_by_id=parsed,
        current_pool_by_id=current,
        bye_by_pro_team_id={3: 8, 7: 7},
        week=7,
    )
    assert [item.classification for item in examples] == ["missing", "zero", "positive"]
    assert examples[0].player_name == "Roster Missing"
    assert examples[0].position == "RB"
    assert examples[0].raw_projection_exists is False
    assert examples[0].raw_applied_total is None
    assert examples[1].raw_projection_exists is True
    assert examples[1].raw_applied_total == 0
    assert examples[1].is_bye_week is True
    assert counts == {"missing": 2, "zero": 1, "positive": 1, "negative": 1}
    assert rostered_missing == 1


def test_render_is_concise_and_contains_manual_comparison_fields() -> None:
    raw_players, parsed, current = sample_inputs()
    examples, counts, rostered_missing = build_examples(
        raw_players_by_id=raw_players,
        evidence_by_id=parsed,
        current_pool_by_id=current,
        bye_by_pro_team_id={3: 8, 7: 7},
        week=7,
    )
    output = render_report(
        ReconciliationReport(
            season=2026,
            current_week=6,
            audited_week=7,
            pool_player_count=5,
            page_lengths=(5,),
            classification_counts=counts,
            rostered_missing_count=rostered_missing,
            examples=examples,
        )
    )
    assert "Roster Missing (ESPN player ID 1)" in output
    assert "Matching raw projection: no; appliedTotal=absent" in output
    assert "ONTEAM (fantasy team ID 10)" in output
    assert "byeWeek=7; isByeWeek=true" in output
    assert "injuryStatus='QUESTIONABLE'" in output


@pytest.mark.parametrize(
    ("remove_id", "source", "message"),
    [
        (1, "raw", "raw player records and parsed"),
        (1, "current", "current ownership and audited-week"),
    ],
)
def test_rejects_unreconciled_player_universes(remove_id, source, message) -> None:
    raw_players, parsed, current = sample_inputs()
    (raw_players if source == "raw" else current).pop(remove_id)
    with pytest.raises(ProjectionUiReconciliationError, match=message):
        build_examples(
            raw_players_by_id=raw_players,
            evidence_by_id=parsed,
            current_pool_by_id=current,
            bye_by_pro_team_id={3: 8, 7: 7},
            week=7,
        )


def test_requires_all_three_manual_comparison_classes() -> None:
    raw_players, parsed, current = sample_inputs()
    raw_players.pop(4)
    parsed.pop(4)
    current.pop(4)
    with pytest.raises(ProjectionUiReconciliationError, match="positive"):
        build_examples(
            raw_players_by_id=raw_players,
            evidence_by_id=parsed,
            current_pool_by_id=current,
            bye_by_pro_team_id={3: 8, 7: 7},
            week=7,
        )


def test_rejects_unknown_position_mapping() -> None:
    raw_players, parsed, current = sample_inputs()
    bad = parsed[1]
    parsed[1] = PlayerEvidence(
        player_id=bad.player_id,
        status=bad.status,
        owner_team_id=bad.owner_team_id,
        default_position_id=999,
        eligible_slot_ids=bad.eligible_slot_ids,
        pro_team_id=bad.pro_team_id,
        injury_status=bad.injury_status,
        projections=bad.projections,
    )
    with pytest.raises(ProjectionUiReconciliationError, match="no supported"):
        build_examples(
            raw_players_by_id=raw_players,
            evidence_by_id=parsed,
            current_pool_by_id=current,
            bye_by_pro_team_id={3: 8, 7: 7},
            week=7,
        )
