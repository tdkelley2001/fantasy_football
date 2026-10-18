"""Deterministic, non-authoritative data-quality reporting for canonical snapshots."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import json
from typing import Hashable, Iterable

from fantasy_football.canonical.model import InterpretationStatus, LeagueSnapshot, PlayerWeek, ProjectionClass
from fantasy_football.canonical.validation import validate_snapshot


class DiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"


@dataclass(frozen=True, slots=True)
class ValidationDiagnostic:
    code: str
    severity: DiagnosticSeverity
    explanation: str
    entity_type: str | None = None
    field: str | None = None
    context: tuple[tuple[str, str | int | float | bool | None], ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectionCoverage:
    record_count: int
    present_raw_count: int
    explicit_zero_count: int
    missing_raw_count: int
    finite_negative_count: int
    positive_effective_count: int
    present_raw_pct_of_records: float
    explicit_zero_pct_of_records: float
    missing_raw_pct_of_records: float
    finite_negative_pct_of_records: float
    positive_effective_pct_of_records: float


@dataclass(frozen=True, slots=True)
class ProjectionBreakdown:
    key: str | int
    coverage: ProjectionCoverage


@dataclass(frozen=True, slots=True)
class RuleLimitation:
    limitation_type: str
    identifier: str
    status: str
    source_id: str
    affected_capabilities: tuple[str, ...]
    manual_configuration_permitted: bool | None


@dataclass(frozen=True, slots=True)
class SnapshotQualityReport:
    league_id: int
    season: int
    snapshot_id: str | None
    first_simulation_week: int
    final_simulation_week: int
    required_scoring_week_count: int
    team_count: int
    player_count: int
    rostered_player_count: int
    unrostered_player_count: int
    required_player_week_count: int
    observed_player_week_count: int
    fantasy_matchup_count: int
    nfl_team_count: int
    nfl_game_count: int
    source_reference_count: int
    projection_coverage: ProjectionCoverage
    projection_by_week: tuple[ProjectionBreakdown, ...]
    projection_by_default_position: tuple[ProjectionBreakdown, ...]
    projection_by_ownership: tuple[ProjectionBreakdown, ...]
    rule_limitations: tuple[RuleLimitation, ...]
    diagnostics: tuple[ValidationDiagnostic, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n"


def _percentage(count: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else round(count * 100.0 / denominator, 6)


def _coverage(records: Iterable[PlayerWeek]) -> ProjectionCoverage:
    rows = tuple(records)
    total = len(rows)
    present = sum(item.raw_projection is not None for item in rows)
    explicit_zero = sum(item.projection_class is ProjectionClass.EXPLICIT_ZERO for item in rows)
    missing = sum(item.projection_class is ProjectionClass.MISSING for item in rows)
    negative = sum(item.raw_projection is not None and item.raw_projection < 0 for item in rows)
    positive = sum(item.effective_projection > 0 for item in rows)
    return ProjectionCoverage(
        record_count=total,
        present_raw_count=present,
        explicit_zero_count=explicit_zero,
        missing_raw_count=missing,
        finite_negative_count=negative,
        positive_effective_count=positive,
        present_raw_pct_of_records=_percentage(present, total),
        explicit_zero_pct_of_records=_percentage(explicit_zero, total),
        missing_raw_pct_of_records=_percentage(missing, total),
        finite_negative_pct_of_records=_percentage(negative, total),
        positive_effective_pct_of_records=_percentage(positive, total),
    )


def _breakdowns(records: tuple[PlayerWeek, ...], keys: Iterable[Hashable]) -> tuple[ProjectionBreakdown, ...]:
    pairs = tuple(zip(records, keys, strict=True))
    unique = sorted({key for _, key in pairs}, key=lambda value: (type(value).__name__, str(value)))
    return tuple(
        ProjectionBreakdown(key=key, coverage=_coverage(row for row, row_key in pairs if row_key == key))
        for key in unique
    )


def generate_quality_report(snapshot: LeagueSnapshot) -> SnapshotQualityReport:
    """Validate and derive deterministic metrics without modifying canonical state."""

    validate_snapshot(snapshot)
    players = {player.player_id: player for player in snapshot.players}
    owned_ids = {entry.player_id for entry in snapshot.roster_entries}
    weeks = tuple(snapshot.player_weeks)
    required_week_count = snapshot.final_simulation_week - snapshot.first_simulation_week + 1

    gaps = tuple(sorted(snapshot.rule_gaps, key=lambda item: item.gap_id))
    unresolved_interpretations = tuple(
        sorted(
            (item for item in snapshot.rules.interpretations if item.status is not InterpretationStatus.UNDERSTOOD),
            key=lambda item: item.rule_id,
        )
    )
    resolved_gap_ids = {
        item.audited_gap_id
        for item in snapshot.rules.interpretations
        if item.audited_gap_id is not None and item.status is InterpretationStatus.UNDERSTOOD
    }
    limitations = tuple(
        RuleLimitation(
            limitation_type="rule_gap",
            identifier=gap.gap_id,
            status="understood_by_approved_manual_configuration" if gap.gap_id in resolved_gap_ids else "unresolved",
            source_id=gap.source_id,
            affected_capabilities=tuple(sorted(gap.affected_capabilities)),
            manual_configuration_permitted=gap.manual_configuration_permitted,
        )
        for gap in gaps
    ) + tuple(
        RuleLimitation(
            limitation_type="rule_interpretation",
            identifier=item.rule_id,
            status=item.status.value,
            source_id=item.source_id,
            affected_capabilities=(),
            manual_configuration_permitted=None,
        )
        for item in unresolved_interpretations
    )

    diagnostics: list[ValidationDiagnostic] = [
        ValidationDiagnostic(
            code="projection_coverage_summary",
            severity=DiagnosticSeverity.INFORMATION,
            explanation="Projection missingness, explicit zeros, finite negatives, and positive effective values are aggregate data characteristics.",
            entity_type="PlayerWeek",
            field="raw_projection",
            context=(("record_count", len(weeks)),),
        )
    ]
    unconfigured = sorted(
        set(snapshot.lineup_slot_namespace.observed_slot_ids)
        - {slot.slot_id for slot in snapshot.rules.lineup_slots}
    )
    if unconfigured:
        diagnostics.append(
            ValidationDiagnostic(
                code="observed_unconfigured_eligibility_categories",
                severity=DiagnosticSeverity.INFORMATION,
                explanation="Observed player eligibility categories are preserved but are not configured playable roster slots.",
                entity_type="LineupSlotNamespace",
                field="observed_slot_ids",
                context=(("count", len(unconfigured)), ("slot_ids", ",".join(str(value) for value in unconfigured))),
            )
        )
    for gap in gaps:
        if gap.gap_id not in resolved_gap_ids:
            diagnostics.append(
                ValidationDiagnostic(
                    code="unresolved_rule_gap",
                    severity=DiagnosticSeverity.WARNING,
                    explanation=gap.reason,
                    entity_type="RuleGap",
                    field="affected_capabilities",
                    context=(
                        ("gap_id", gap.gap_id),
                        ("source_id", gap.source_id),
                        ("affected_capabilities", ",".join(sorted(gap.affected_capabilities))),
                        ("manual_configuration_permitted", gap.manual_configuration_permitted),
                    ),
                )
            )
    severity_order = {
        DiagnosticSeverity.ERROR: 0,
        DiagnosticSeverity.WARNING: 1,
        DiagnosticSeverity.INFORMATION: 2,
    }
    ordered_diagnostics = tuple(
        sorted(
            diagnostics,
            key=lambda item: (
                severity_order[item.severity], item.code, item.entity_type or "", item.field or "", item.context
            ),
        )
    )

    return SnapshotQualityReport(
        league_id=snapshot.league_id,
        season=snapshot.season,
        snapshot_id=snapshot.snapshot_id,
        first_simulation_week=snapshot.first_simulation_week,
        final_simulation_week=snapshot.final_simulation_week,
        required_scoring_week_count=required_week_count,
        team_count=len(snapshot.teams),
        player_count=len(snapshot.players),
        rostered_player_count=len(owned_ids),
        unrostered_player_count=len(snapshot.players) - len(owned_ids),
        required_player_week_count=len(snapshot.players) * required_week_count,
        observed_player_week_count=len(weeks),
        fantasy_matchup_count=len(snapshot.fantasy_matchups),
        nfl_team_count=len(snapshot.nfl_teams),
        nfl_game_count=len(snapshot.nfl_games),
        source_reference_count=len(snapshot.sources),
        projection_coverage=_coverage(weeks),
        projection_by_week=_breakdowns(weeks, (week.scoring_week for week in weeks)),
        projection_by_default_position=_breakdowns(
            weeks, (players[week.player_id].default_position_id for week in weeks)
        ),
        projection_by_ownership=_breakdowns(
            weeks, ("rostered" if week.player_id in owned_ids else "unrostered" for week in weeks)
        ),
        rule_limitations=tuple(sorted(limitations, key=lambda item: (item.limitation_type, item.identifier))),
        diagnostics=ordered_diagnostics,
    )
