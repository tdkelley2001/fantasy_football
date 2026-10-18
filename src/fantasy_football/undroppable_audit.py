"""Read-only ESPN undroppable-setting and player-field evidence audit."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from typing import Any, Mapping, Sequence

from fantasy_football.config import SettingsError, load_settings
from fantasy_football.espn_adapter import EspnAdapterError, EspnSourceBundle, retrieve_bundle


class UndroppableAuditError(ValueError):
    """Raised when source evidence is malformed, contradictory, or incomplete."""


@dataclass(frozen=True, slots=True)
class FieldCoverage:
    record_count: int
    explicit_droppable_count: int
    explicit_undroppable_count: int
    unknown_count: int


@dataclass(frozen=True, slots=True)
class WeeklyFieldCoverage:
    scoring_week: int
    coverage: FieldCoverage


@dataclass(frozen=True, slots=True)
class UndroppableEvidenceReport:
    season: int
    league_setting_path: str
    league_setting_value: bool | None
    league_setting_initial_present: bool
    league_setting_reconciliation_present: bool
    player_field_path: str
    roster_player_field_path: str
    current_player_coverage: FieldCoverage
    rostered_player_coverage: FieldCoverage
    future_week_coverage: tuple[WeeklyFieldCoverage, ...]
    current_and_roster_values_reconciled: bool
    current_and_future_values_reconciled: bool


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise UndroppableAuditError(f"{context}: expected object")
    return value


def _rows(value: Any, context: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise UndroppableAuditError(f"{context}: expected array")
    return value


def _setting(payload: Mapping[str, Any], context: str) -> tuple[bool, bool | None]:
    settings = _mapping(payload.get("settings"), f"{context}.settings")
    roster = _mapping(settings.get("rosterSettings"), f"{context}.settings.rosterSettings")
    if "isUsingUndroppableList" not in roster:
        return False, None
    value = roster["isUsingUndroppableList"]
    if not isinstance(value, bool):
        raise UndroppableAuditError(
            f"{context}.settings.rosterSettings.isUsingUndroppableList: expected boolean or absence"
        )
    return True, value


def _player_values(rows: Sequence[Any], context: str) -> dict[int, bool | None]:
    result: dict[int, bool | None] = {}
    for index, raw in enumerate(rows):
        wrapper = _mapping(raw, f"{context}[{index}]")
        player = _mapping(wrapper.get("player"), f"{context}[{index}].player")
        player_id = player.get("id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id == 0:
            raise UndroppableAuditError(f"{context}[{index}].player.id: expected nonzero integer")
        if player_id in result:
            raise UndroppableAuditError(f"{context}: duplicate player ID {player_id}")
        if "droppable" not in player:
            result[player_id] = None
            continue
        value = player["droppable"]
        if not isinstance(value, bool):
            raise UndroppableAuditError(
                f"{context}[{index}].player.droppable: expected boolean or absence"
            )
        result[player_id] = value
    return result


def _coverage(values: Mapping[int, bool | None]) -> FieldCoverage:
    return FieldCoverage(
        record_count=len(values),
        explicit_droppable_count=sum(value is True for value in values.values()),
        explicit_undroppable_count=sum(value is False for value in values.values()),
        unknown_count=sum(value is None for value in values.values()),
    )


def _page_values(pages, context: str) -> dict[int, bool | None]:
    result: dict[int, bool | None] = {}
    for page in sorted(pages, key=lambda item: item.offset):
        payload = _mapping(page.response.payload, f"{context} offset={page.offset}")
        values = _player_values(
            _rows(payload.get("players"), f"{context} offset={page.offset}.players"),
            f"{context} offset={page.offset}.players",
        )
        overlap = set(result).intersection(values)
        if overlap:
            raise UndroppableAuditError(
                f"{context}: duplicate player IDs across pages: {sorted(overlap)[:5]}"
            )
        result.update(values)
    return result


def _roster_values(payload: Mapping[str, Any]) -> dict[int, bool | None]:
    rows: list[Mapping[str, Any]] = []
    teams = _rows(payload.get("teams"), "league_initial.teams")
    for team_index, raw_team in enumerate(teams):
        team = _mapping(raw_team, f"league_initial.teams[{team_index}]")
        roster = _mapping(team.get("roster"), f"league_initial.teams[{team_index}].roster")
        entries = _rows(roster.get("entries"), f"league_initial.teams[{team_index}].roster.entries")
        for entry_index, raw_entry in enumerate(entries):
            entry = _mapping(
                raw_entry,
                f"league_initial.teams[{team_index}].roster.entries[{entry_index}]",
            )
            pool = _mapping(
                entry.get("playerPoolEntry"),
                f"league_initial.teams[{team_index}].roster.entries[{entry_index}].playerPoolEntry",
            )
            rows.append(pool)
    return _player_values(rows, "league_initial roster playerPoolEntry")


def _reconcile(
    left: Mapping[int, bool | None],
    right: Mapping[int, bool | None],
    *,
    context: str,
    require_same_universe: bool,
) -> None:
    if require_same_universe and set(left) != set(right):
        raise UndroppableAuditError(
            f"{context}: player universe mismatch; left={len(left)}, right={len(right)}"
        )
    common = set(left).intersection(right)
    contradictions = sorted(
        player_id
        for player_id in common
        if left[player_id] is not None
        and right[player_id] is not None
        and left[player_id] != right[player_id]
    )
    if contradictions:
        raise UndroppableAuditError(
            f"{context}: contradictory player.droppable values for {len(contradictions)} player(s)"
        )


def audit_undroppable_evidence(bundle: EspnSourceBundle) -> UndroppableEvidenceReport:
    """Return sanitized field coverage without retaining player identities."""

    initial = _mapping(bundle.league_initial.payload, "league_initial")
    reconciliation = _mapping(bundle.league_reconciliation.payload, "league_reconciliation")
    initial_present, initial_value = _setting(initial, "league_initial")
    reconciliation_present, reconciliation_value = _setting(reconciliation, "league_reconciliation")
    if initial_present and reconciliation_present and initial_value != reconciliation_value:
        raise UndroppableAuditError(
            "isUsingUndroppableList changed between initial and reconciliation requests"
        )
    setting_value = initial_value if initial_present else reconciliation_value

    current = _page_values(bundle.current_player_pages, "current player pool")
    rostered = _roster_values(initial)
    _reconcile(current, rostered, context="current player pool versus roster", require_same_universe=False)

    pages_by_week: dict[int, list[Any]] = {}
    for page in bundle.future_player_pages:
        pages_by_week.setdefault(page.scoring_week, []).append(page)
    weekly: list[WeeklyFieldCoverage] = []
    for week in sorted(pages_by_week):
        values = _page_values(pages_by_week[week], f"future player pool week={week}")
        _reconcile(
            current,
            values,
            context=f"current versus future player pool week={week}",
            require_same_universe=True,
        )
        weekly.append(WeeklyFieldCoverage(week, _coverage(values)))

    return UndroppableEvidenceReport(
        season=bundle.season,
        league_setting_path="settings.rosterSettings.isUsingUndroppableList",
        league_setting_value=setting_value,
        league_setting_initial_present=initial_present,
        league_setting_reconciliation_present=reconciliation_present,
        player_field_path="players[].player.droppable",
        roster_player_field_path="teams[].roster.entries[].playerPoolEntry.player.droppable",
        current_player_coverage=_coverage(current),
        rostered_player_coverage=_coverage(rostered),
        future_week_coverage=tuple(weekly),
        current_and_roster_values_reconciled=True,
        current_and_future_values_reconciled=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit sanitized ESPN undroppable evidence")
    parser.add_argument("--first-simulation-week", type=int, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        bundle = retrieve_bundle(settings, first_simulation_week=args.first_simulation_week)
        report = audit_undroppable_evidence(bundle)
    except (SettingsError, EspnAdapterError, UndroppableAuditError, ValueError) as exc:
        parser.error(str(exc))
    data = asdict(report)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print(
            f"season={report.season} undroppable_list_enabled={report.league_setting_value!r}"
        )
        print(
            "current player.droppable coverage: "
            f"records={report.current_player_coverage.record_count} "
            f"droppable={report.current_player_coverage.explicit_droppable_count} "
            f"undroppable={report.current_player_coverage.explicit_undroppable_count} "
            f"unknown={report.current_player_coverage.unknown_count}"
        )
        print(
            "rostered player.droppable coverage: "
            f"records={report.rostered_player_coverage.record_count} "
            f"droppable={report.rostered_player_coverage.explicit_droppable_count} "
            f"undroppable={report.rostered_player_coverage.explicit_undroppable_count} "
            f"unknown={report.rostered_player_coverage.unknown_count}"
        )
        print(f"future weeks checked={len(report.future_week_coverage)}; values reconciled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
