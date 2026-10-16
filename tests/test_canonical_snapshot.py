from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
import math

import pytest

from fantasy_football.canonical.model import (
    InterpretationStatus,
    LineupSlotRule,
    PlayerWeek,
    ProjectionClass,
    ProjectionSource,
    RosterEntry,
    RuleInterpretation,
    SlotKind,
)
from fantasy_football.canonical.serialization import (
    CanonicalSerializationError,
    snapshot_from_json,
    snapshot_to_json,
)
from fantasy_football.canonical.validation import (
    CanonicalValidationError,
    require_understood_rules,
    validate_snapshot,
)
from tests.canonical_fixtures import canonical_snapshot


def replace_player_week(snapshot, key: tuple[int, int], **changes):
    player_id, scoring_week = key
    weeks = tuple(
        replace(item, **changes) if (item.player_id, item.scoring_week) == key else item
        for item in snapshot.player_weeks
    )
    return replace(snapshot, player_weeks=weeks)


def test_representative_snapshot_is_valid_and_immutable() -> None:
    snapshot = canonical_snapshot()
    validate_snapshot(snapshot)

    with pytest.raises(FrozenInstanceError):
        snapshot.season = 2027  # type: ignore[misc]
    assert next(item for item in snapshot.player_weeks if item.player_id == -101).projected_lineup_available is False
    assert next(item for item in snapshot.player_weeks if item.player_id == 1).projected_lineup_available is True


def test_deterministic_round_trip_preserves_null_zero_negative_and_unresolved_rules() -> None:
    snapshot = canonical_snapshot()
    payload = snapshot_to_json(snapshot)
    restored = snapshot_from_json(payload)

    assert restored == snapshot
    assert snapshot_to_json(restored) == payload
    assert '"player_id": -101' in payload
    assert '"raw_projection": null' in payload
    assert '"raw_projection": 0.0' in payload
    assert '"raw_projection": -1.0' in payload
    assert restored.rules.consolation.structure_rule_id == "consolation_structure"
    assert next(item for item in restored.rules.interpretations if item.rule_id == "consolation_structure").status is InterpretationStatus.UNSUPPORTED


def test_serialization_order_is_independent_of_input_record_order() -> None:
    snapshot = canonical_snapshot()
    reversed_snapshot = replace(
        snapshot,
        teams=tuple(reversed(snapshot.teams)),
        players=tuple(reversed(snapshot.players)),
        player_weeks=tuple(reversed(snapshot.player_weeks)),
        sources=tuple(reversed(snapshot.sources)),
    )
    assert snapshot_to_json(reversed_snapshot) == snapshot_to_json(snapshot)


@pytest.mark.parametrize(
    ("raw", "classification", "effective", "source", "available"),
    [
        (8.125, ProjectionClass.PRESENT, 8.125, ProjectionSource.ESPN, True),
        (-2.75, ProjectionClass.PRESENT, -2.75, ProjectionSource.ESPN, False),
        (0.0, ProjectionClass.EXPLICIT_ZERO, 0.0, ProjectionSource.ESPN, False),
        (None, ProjectionClass.MISSING, 0.0, ProjectionSource.MISSING_PROJECTION_POLICY, False),
    ],
)
def test_projection_contract_accepts_approved_states(raw, classification, effective, source, available) -> None:
    snapshot = replace_player_week(
        canonical_snapshot(),
        (1, 15),
        raw_projection=raw,
        projection_class=classification,
        effective_projection=effective,
        effective_source=source,
    )
    validate_snapshot(snapshot)
    item = next(item for item in snapshot.player_weeks if item.player_id == 1 and item.scoring_week == 15)
    assert item.projected_lineup_available is available


@pytest.mark.parametrize(
    "changes",
    [
        {"raw_projection": None, "projection_class": ProjectionClass.PRESENT, "effective_projection": 0.0, "effective_source": ProjectionSource.ESPN},
        {"raw_projection": 0.0, "projection_class": ProjectionClass.MISSING, "effective_projection": 0.0, "effective_source": ProjectionSource.MISSING_PROJECTION_POLICY},
        {"raw_projection": 2.0, "projection_class": ProjectionClass.PRESENT, "effective_projection": 0.0, "effective_source": ProjectionSource.ESPN},
        {"raw_projection": 0.0, "projection_class": ProjectionClass.EXPLICIT_ZERO, "effective_projection": 0.0, "effective_source": ProjectionSource.MISSING_PROJECTION_POLICY},
    ],
)
def test_projection_contract_rejects_inconsistent_states(changes) -> None:
    snapshot = replace_player_week(canonical_snapshot(), (1, 15), **changes)
    with pytest.raises(CanonicalValidationError, match="PlayerWeek.*projection contract"):
        validate_snapshot(snapshot)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_projection_contract_rejects_nonfinite_values(value: float) -> None:
    snapshot = replace_player_week(
        canonical_snapshot(), (1, 15), raw_projection=value, effective_projection=value
    )
    with pytest.raises(CanonicalValidationError, match="raw_projection.*finite"):
        validate_snapshot(snapshot)


def test_duplicate_ownership_is_rejected_with_player_context() -> None:
    snapshot = canonical_snapshot()
    invalid = replace(snapshot, roster_entries=snapshot.roster_entries + (RosterEntry(1, 2, 20, 2),))
    with pytest.raises(CanonicalValidationError, match="RosterEntry 1.*duplicate owners"):
        validate_snapshot(invalid)


def test_duplicate_player_week_is_rejected() -> None:
    snapshot = canonical_snapshot()
    invalid = replace(snapshot, player_weeks=snapshot.player_weeks + (snapshot.player_weeks[0],))
    with pytest.raises(CanonicalValidationError, match="PlayerWeek.*duplicate identifier"):
        validate_snapshot(invalid)


def test_duplicate_player_record_is_rejected() -> None:
    snapshot = canonical_snapshot()
    invalid = replace(snapshot, players=snapshot.players + (snapshot.players[0],))
    with pytest.raises(CanonicalValidationError, match="Player.*duplicate identifier"):
        validate_snapshot(invalid)


def test_wrong_identifier_type_fails_with_entity_and_field() -> None:
    snapshot = canonical_snapshot()
    bad_team = replace(snapshot.teams[0], team_id="1")  # type: ignore[arg-type]
    invalid = replace(snapshot, teams=(bad_team, snapshot.teams[1]))
    with pytest.raises(CanonicalValidationError, match="FantasyTeam '1'.*team_id.*must be an integer"):
        validate_snapshot(invalid)


def test_mutable_collection_is_rejected_at_validation_boundary() -> None:
    snapshot = canonical_snapshot()
    invalid = replace(snapshot, players=list(snapshot.players))  # type: ignore[arg-type]
    with pytest.raises(CanonicalValidationError, match="players.*immutable tuple"):
        validate_snapshot(invalid)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("team_id", 999, "unknown team"),
        ("player_id", 999, "unknown player"),
        ("lineup_slot_id", 999, "unknown or zero-capacity slot"),
    ],
)
def test_invalid_roster_references_are_rejected(field: str, value: int, message: str) -> None:
    snapshot = canonical_snapshot()
    entry = replace(snapshot.roster_entries[0], **{field: value})
    invalid = replace(snapshot, roster_entries=(entry,) + snapshot.roster_entries[1:])
    with pytest.raises(CanonicalValidationError, match=message):
        validate_snapshot(invalid)


def test_roster_capacity_overflow_is_rejected() -> None:
    snapshot = canonical_snapshot()
    extras = (RosterEntry(3, 1, 20, 1), RosterEntry(4, 1, 20, 1), RosterEntry(2, 1, 20, 1))
    invalid = replace(snapshot, roster_entries=(snapshot.roster_entries[0], snapshot.roster_entries[1]) + extras)
    with pytest.raises(CanonicalValidationError, match="roster capacity.*exceeds"):
        validate_snapshot(invalid)


def test_missing_forward_week_is_rejected() -> None:
    snapshot = canonical_snapshot()
    invalid = replace(snapshot, player_weeks=tuple(item for item in snapshot.player_weeks if not (item.player_id == 4 and item.scoring_week == 17)))
    with pytest.raises(CanonicalValidationError, match="Player 4.*forward week coverage"):
        validate_snapshot(invalid)


def test_nfl_game_and_bye_contradiction_is_rejected() -> None:
    snapshot = canonical_snapshot()
    conflict = replace(snapshot.nfl_games[0], home_nfl_team_id=1)
    invalid = replace(snapshot, nfl_games=(conflict,) + snapshot.nfl_games[1:])
    with pytest.raises(CanonicalValidationError, match="also marked on bye"):
        validate_snapshot(invalid)


def test_incomplete_regular_schedule_is_rejected_without_inventing_pairing() -> None:
    snapshot = canonical_snapshot()
    invalid = replace(snapshot, fantasy_matchups=tuple(item for item in snapshot.fantasy_matchups if item.matchup_period_id != 1))
    with pytest.raises(CanonicalValidationError, match="regular schedule coverage"):
        validate_snapshot(invalid)


def test_unknown_source_reference_is_rejected() -> None:
    snapshot = replace_player_week(canonical_snapshot(), (1, 15), source_id="missing-source")
    with pytest.raises(CanonicalValidationError, match="PlayerWeek.*unknown source"):
        validate_snapshot(snapshot)


def test_unresolved_rules_preserve_snapshot_but_block_named_capability_requirement() -> None:
    snapshot = canonical_snapshot()
    validate_snapshot(snapshot)
    require_understood_rules(snapshot, ["playoff_tie"])
    with pytest.raises(CanonicalValidationError, match="requires understood rule; observed unverified"):
        require_understood_rules(snapshot, ["regular_matchup_tie"])


def test_contradictory_rule_record_is_rejected() -> None:
    snapshot = canonical_snapshot()
    contradictory = RuleInterpretation(
        "bad", "settings.bad", None, "invented", InterpretationStatus.MISSING, snapshot.sources[0].source_id
    )
    invalid = replace(snapshot, rules=replace(snapshot.rules, interpretations=snapshot.rules.interpretations + (contradictory,)))
    with pytest.raises(CanonicalValidationError, match="missing rule cannot carry"):
        validate_snapshot(invalid)


def test_alternate_valid_roster_structure_without_ir_and_with_multiple_flex_slots() -> None:
    snapshot = canonical_snapshot()
    slots = (
        LineupSlotRule(0, 1, SlotKind.STARTER, "QB"),
        LineupSlotRule(16, 1, SlotKind.STARTER, "D/ST"),
        LineupSlotRule(20, 3, SlotKind.BENCH, "Bench"),
        LineupSlotRule(23, 2, SlotKind.STARTER, "Flex"),
    )
    players = tuple(replace(player, eligible_lineup_slot_ids=tuple(sorted(set(player.eligible_lineup_slot_ids) - {21} | {23}))) for player in snapshot.players)
    alternate = replace(snapshot, rules=replace(snapshot.rules, lineup_slots=slots), players=players)
    validate_snapshot(alternate)


def test_incompatible_schema_and_malformed_timestamp_are_rejected() -> None:
    data = json.loads(snapshot_to_json(canonical_snapshot()))
    data["schema_version"] = 2
    with pytest.raises(CanonicalSerializationError, match="unsupported schema_version"):
        snapshot_from_json(json.dumps(data))

    data["schema_version"] = 1
    data["retrieval_started_at_utc"] = "not-a-time"
    with pytest.raises(CanonicalSerializationError, match="not a valid ISO-8601"):
        snapshot_from_json(json.dumps(data))
