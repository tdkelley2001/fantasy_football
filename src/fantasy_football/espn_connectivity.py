"""Read-only M0.2 ESPN connectivity and ownership diagnostic."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib.metadata import version
import json
import logging
from typing import Any, Mapping, Protocol, Sequence

from espn_api.football import League
from espn_api.football.constant import POSITION_MAP
from espn_api.requests.espn_requests import (
    ESPNAccessDenied,
    ESPNInvalidLeague,
    ESPNUnknownError,
)
from requests import RequestException

from fantasy_football.config import Settings, SettingsError, load_settings
from fantasy_football.logging_config import configure_logging


LOGGER = logging.getLogger(__name__)


class ConnectivityAuditError(RuntimeError):
    """Raised when ESPN data violates an M0.2 connectivity invariant."""


class LeagueLike(Protocol):
    league_id: int
    year: int
    current_week: int
    settings: Any
    teams: Sequence[Any]


@dataclass(frozen=True, slots=True)
class PlayerOwnership:
    player_id: int
    player_name: str
    team_id: int
    primary_position: str
    current_lineup_slot: str
    eligible_lineup_slots: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TeamAudit:
    team_id: int
    team_name: str
    manager_ids: tuple[str, ...]
    standing: int
    wins: int
    losses: int
    ties: int
    points_for: float
    roster_size: int
    players: tuple[PlayerOwnership, ...]


@dataclass(frozen=True, slots=True)
class ConnectivityReport:
    retrieved_at_utc: str
    source_library: str
    source_endpoint: str
    source_views: tuple[str, ...]
    league_id: int
    season: int
    league_name: str
    current_week: int
    expected_team_count: int
    reported_team_count: int
    observed_team_count: int
    observed_player_count: int
    position_slot_counts: dict[str, int]
    scoring_format: tuple[dict[str, object], ...]
    teams: tuple[TeamAudit, ...]
    verified_information: tuple[str, ...]
    missing_or_inaccessible_information: tuple[str, ...]
    requires_further_investigation: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _positive_int(value: Any, *, field: str, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConnectivityAuditError(
            f"{context}: {field} must be a positive integer; observed {value!r}"
        )
    return value


def _nonzero_int(value: Any, *, field: str, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value == 0:
        raise ConnectivityAuditError(
            f"{context}: {field} must be a nonzero integer; observed {value!r}"
        )
    return value


def _nonempty_text(value: Any, *, field: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConnectivityAuditError(
            f"{context}: {field} must be non-empty text; observed {value!r}"
        )
    return value.strip()


def _nonnegative_int(value: Any, *, field: str, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConnectivityAuditError(
            f"{context}: {field} must be a non-negative integer; observed {value!r}"
        )
    return value


def _number(value: Any, *, field: str, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConnectivityAuditError(
            f"{context}: {field} must be numeric; observed {value!r}"
        )
    return float(value)


def _audit_slots(raw_league_data: Mapping[str, Any]) -> dict[str, int]:
    raw_counts = (
        raw_league_data.get("settings", {})
        .get("rosterSettings", {})
        .get("lineupSlotCounts")
    )
    if not isinstance(raw_counts, dict) or not raw_counts:
        raise ConnectivityAuditError(
            "raw league settings: lineupSlotCounts is missing or empty"
        )

    counts: dict[str, int] = {}
    for raw_slot_id, raw_count in raw_counts.items():
        if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count < 0:
            raise ConnectivityAuditError(
                "raw league settings: lineup slot count must be a non-negative "
                f"integer; slot_id={raw_slot_id!r}, observed={raw_count!r}"
            )
        if raw_count == 0:
            continue
        try:
            slot_id = int(raw_slot_id)
        except (TypeError, ValueError) as exc:
            raise ConnectivityAuditError(
                f"raw league settings: invalid lineup slot id {raw_slot_id!r}"
            ) from exc
        slot = POSITION_MAP.get(slot_id)
        if not slot:
            raise ConnectivityAuditError(
                "raw league settings: configured lineup slot has no verified "
                f"espn-api mapping; slot_id={slot_id}, count={raw_count}"
            )
        if slot in counts:
            raise ConnectivityAuditError(
                "raw league settings: multiple configured slot IDs map to "
                f"the same label {slot!r}"
            )
        counts[slot] = raw_count
    if not counts:
        raise ConnectivityAuditError(
            "raw league settings: every lineup slot count is zero"
        )
    return counts


def _audit_scoring(settings: Any) -> tuple[dict[str, object], ...]:
    scoring = getattr(settings, "scoring_format", None)
    if not isinstance(scoring, list) or not scoring:
        raise ConnectivityAuditError("league settings: scoring_format is missing or empty")

    result: list[dict[str, object]] = []
    stat_ids: set[int] = set()
    for index, item in enumerate(scoring):
        context = f"league settings scoring item {index}"
        if not isinstance(item, dict):
            raise ConnectivityAuditError(f"{context}: expected a mapping")
        stat_id = _positive_int(item.get("id"), field="id", context=context)
        if stat_id in stat_ids:
            raise ConnectivityAuditError(f"{context}: duplicate stat id {stat_id}")
        stat_ids.add(stat_id)
        label = item.get("label")
        abbreviation = item.get("abbr")
        points = item.get("points")
        if not isinstance(points, (int, float)) or isinstance(points, bool):
            raise ConnectivityAuditError(
                f"{context}: points must be numeric; observed {points!r}"
            )
        result.append(
            {
                "stat_id": stat_id,
                "label": _nonempty_text(label, field="label", context=context),
                "abbreviation": _nonempty_text(
                    abbreviation, field="abbr", context=context
                ),
                "points": points,
            }
        )
    return tuple(result)


def audit_league(
    league: LeagueLike,
    *,
    raw_league_data: Mapping[str, Any],
    source_endpoint: str,
    expected_league_id: int,
    expected_season: int,
    expected_team_count: int,
) -> ConnectivityReport:
    """Validate and convert the M0.2 subset of an already fetched league."""

    _positive_int(
        expected_team_count,
        field="expected_team_count",
        context="audit input",
    )
    if league.league_id != expected_league_id:
        raise ConnectivityAuditError(
            "league identity mismatch: "
            f"expected league_id={expected_league_id}, observed={league.league_id}"
        )
    if league.year != expected_season:
        raise ConnectivityAuditError(
            "season mismatch: "
            f"expected season={expected_season}, observed={league.year}"
        )
    endpoint = _nonempty_text(
        source_endpoint, field="source_endpoint", context="audit input"
    )
    if not endpoint.startswith("https://"):
        raise ConnectivityAuditError(
            f"audit input: source_endpoint must use HTTPS; observed {endpoint!r}"
        )

    settings = league.settings
    reported_team_count = _positive_int(
        getattr(settings, "team_count", None),
        field="team_count",
        context="league settings",
    )
    teams = list(league.teams)
    if reported_team_count != expected_team_count:
        raise ConnectivityAuditError(
            "league team-count mismatch: "
            f"expected={expected_team_count}, ESPN settings={reported_team_count}"
        )
    if len(teams) != expected_team_count:
        raise ConnectivityAuditError(
            "fetched team-count mismatch: "
            f"expected={expected_team_count}, fetched={len(teams)}"
        )

    team_ids: set[int] = set()
    player_owners: dict[int, int] = {}
    standings: set[int] = set()
    audited_teams: list[TeamAudit] = []
    for team in teams:
        team_id = _positive_int(
            getattr(team, "team_id", None),
            field="team_id",
            context="team",
        )
        if team_id in team_ids:
            raise ConnectivityAuditError(f"duplicate team_id={team_id}")
        team_ids.add(team_id)
        context = f"team_id={team_id}"
        team_name = _nonempty_text(
            getattr(team, "team_name", None), field="team_name", context=context
        )
        owners = list(getattr(team, "owners", ()))
        manager_ids: list[str] = []
        for owner_index, owner in enumerate(owners):
            if not isinstance(owner, dict):
                raise ConnectivityAuditError(
                    f"{context}: manager record {owner_index} is not a mapping"
                )
            manager_ids.append(
                _nonempty_text(
                    owner.get("id"),
                    field="manager id",
                    context=f"{context}, manager record {owner_index}",
                )
            )
        standing = _positive_int(
            getattr(team, "standing", None), field="standing", context=context
        )
        if standing in standings:
            raise ConnectivityAuditError(
                f"duplicate standing={standing}; offending {context}"
            )
        standings.add(standing)

        roster = list(getattr(team, "roster", ()))
        if not roster:
            raise ConnectivityAuditError(f"{context}: roster is empty")
        audited_players: list[PlayerOwnership] = []
        for player in roster:
            player_id = _nonzero_int(
                getattr(player, "playerId", None),
                field="playerId",
                context=context,
            )
            previous_owner = player_owners.get(player_id)
            if previous_owner is not None:
                raise ConnectivityAuditError(
                    "duplicate player ownership: "
                    f"player_id={player_id}, first_team_id={previous_owner}, "
                    f"second_team_id={team_id}"
                )
            observed_owner = _positive_int(
                getattr(player, "onTeamId", None),
                field="onTeamId",
                context=f"{context}, player_id={player_id}",
            )
            if observed_owner != team_id:
                raise ConnectivityAuditError(
                    "player ownership mismatch: "
                    f"player_id={player_id}, roster_team_id={team_id}, "
                    f"player_onTeamId={observed_owner}"
                )
            eligible_slots = tuple(getattr(player, "eligibleSlots", ()))
            if not eligible_slots:
                raise ConnectivityAuditError(
                    f"{context}, player_id={player_id}: eligibleSlots is empty"
                )
            for slot in eligible_slots:
                _nonempty_text(
                    slot,
                    field="eligible slot",
                    context=f"{context}, player_id={player_id}",
                )
            player_owners[player_id] = team_id
            audited_players.append(
                PlayerOwnership(
                    player_id=player_id,
                    player_name=_nonempty_text(
                        getattr(player, "name", None),
                        field="player name",
                        context=f"{context}, player_id={player_id}",
                    ),
                    team_id=team_id,
                    primary_position=_nonempty_text(
                        getattr(player, "position", None),
                        field="primary position",
                        context=f"{context}, player_id={player_id}",
                    ),
                    current_lineup_slot=_nonempty_text(
                        getattr(player, "lineupSlot", None),
                        field="current lineup slot",
                        context=f"{context}, player_id={player_id}",
                    ),
                    eligible_lineup_slots=eligible_slots,
                )
            )

        audited_teams.append(
            TeamAudit(
                team_id=team_id,
                team_name=team_name,
                manager_ids=tuple(manager_ids),
                standing=standing,
                wins=_nonnegative_int(
                    getattr(team, "wins", None), field="wins", context=context
                ),
                losses=_nonnegative_int(
                    getattr(team, "losses", None), field="losses", context=context
                ),
                ties=_nonnegative_int(
                    getattr(team, "ties", None), field="ties", context=context
                ),
                points_for=_number(
                    getattr(team, "points_for", None),
                    field="points_for",
                    context=context,
                ),
                roster_size=len(audited_players),
                players=tuple(audited_players),
            )
        )

    missing_information: list[str] = []
    if any(not team.manager_ids for team in audited_teams):
        missing_information.append(
            "One or more ESPN team records did not expose a manager identifier."
        )

    roster_sizes = {team.roster_size for team in audited_teams}
    investigation = [
        "Future player-week projections, free-agent availability, byes and future "
        "schedule semantics are deferred to M0.3.",
        "Standings tiebreak, waiver and postseason rule semantics are deferred to M0.4.",
        "espn-api 1.0.1 derives position_slot_counts incorrectly for sparse ESPN slot "
        "IDs; this diagnostic instead validates raw lineupSlotCounts IDs.",
    ]
    if len(roster_sizes) > 1:
        investigation.append(
            "Current ESPN roster sizes vary across teams "
            f"({sorted(roster_sizes)}); vacancy and capacity semantics require later audit."
        )

    return ConnectivityReport(
        retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
        source_library=f"espn-api {version('espn-api')}",
        source_endpoint=endpoint,
        source_views=("mTeam", "mRoster", "mMatchup", "mSettings", "mStandings"),
        league_id=league.league_id,
        season=league.year,
        league_name=_nonempty_text(
            getattr(settings, "name", None),
            field="name",
            context="league settings",
        ),
        current_week=_positive_int(
            league.current_week,
            field="current_week",
            context="league",
        ),
        expected_team_count=expected_team_count,
        reported_team_count=reported_team_count,
        observed_team_count=len(audited_teams),
        observed_player_count=len(player_owners),
        position_slot_counts=_audit_slots(raw_league_data),
        scoring_format=_audit_scoring(settings),
        teams=tuple(sorted(audited_teams, key=lambda item: item.team_id)),
        verified_information=(
            "League ID, season and league name were returned by ESPN.",
            "Expected, metadata-reported and fetched team counts reconcile.",
            "Team IDs and standings positions are unique.",
            "Rostered player IDs have exactly one observed owner and agree with onTeamId.",
            "Rostered players expose current and eligible lineup slots.",
            "Configured nonzero roster-slot IDs and scoring items are available.",
        ),
        missing_or_inaccessible_information=tuple(missing_information),
        requires_further_investigation=tuple(investigation),
    )


def fetch_and_audit(settings: Settings, *, expected_team_count: int) -> ConnectivityReport:
    """Fetch one league through espn-api and apply M0.2 validation."""

    credentials = settings.credentials
    try:
        league = League(
            league_id=settings.league_id,
            year=settings.season,
            espn_s2=credentials.espn_s2 if credentials else None,
            swid=credentials.swid if credentials else None,
        )
        raw_league_data = league.espn_request.get_league()
    except (
        ESPNAccessDenied,
        ESPNInvalidLeague,
        ESPNUnknownError,
        RequestException,
    ):
        raise
    except (KeyError, TypeError, ValueError, IndexError, json.JSONDecodeError) as exc:
        raise ConnectivityAuditError(
            f"ESPN returned a malformed or unsupported league response: {exc}"
        ) from exc
    return audit_league(
        league,
        raw_league_data=raw_league_data,
        source_endpoint=league.espn_request.LEAGUE_ENDPOINT,
        expected_league_id=settings.league_id,
        expected_season=settings.season,
        expected_team_count=expected_team_count,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the read-only M0.2 ESPN league connectivity diagnostic."
    )
    parser.add_argument(
        "--expected-team-count",
        type=int,
        required=True,
        help="Explicit expected league team count used as a reconciliation invariant.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the complete machine-readable report, including rostered player IDs.",
    )
    return parser


def render_summary(report: ConnectivityReport) -> str:
    """Render a credential-free human-readable M0.2 report."""

    lines = [
        "M0.2 ESPN connectivity diagnostic",
        f"League: {report.league_name} ({report.league_id}), season {report.season}",
        f"Source: {report.source_library}",
        f"Endpoint: {report.source_endpoint}",
        f"Views: {', '.join(report.source_views)}",
        (
            "Teams: "
            f"expected={report.expected_team_count}, "
            f"metadata={report.reported_team_count}, "
            f"observed={report.observed_team_count}"
        ),
        f"Unique rostered players: {report.observed_player_count}",
        "",
        "Teams and current standings:",
    ]
    for team in report.teams:
        manager_ids = ", ".join(team.manager_ids) if team.manager_ids else "unavailable"
        lines.append(
            f"- ID {team.team_id}: {team.team_name}; standing {team.standing}; "
            f"record {team.wins}-{team.losses}-{team.ties}; "
            f"PF {team.points_for:.2f}; roster {team.roster_size}; "
            f"manager IDs {manager_ids}"
        )
    lines.extend(("", "Verified information:"))
    lines.extend(f"- {item}" for item in report.verified_information)
    lines.extend(("", "Missing or inaccessible information:"))
    lines.extend(
        f"- {item}" for item in report.missing_or_inaccessible_information
    )
    if not report.missing_or_inaccessible_information:
        lines.append("- None within the M0.2 scope.")
    lines.extend(("", "Requires further investigation:"))
    lines.extend(f"- {item}" for item in report.requires_further_investigation)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        report = fetch_and_audit(
            settings, expected_team_count=args.expected_team_count
        )
    except (
        SettingsError,
        ConnectivityAuditError,
        ESPNAccessDenied,
        ESPNInvalidLeague,
        ESPNUnknownError,
        RequestException,
    ) as exc:
        LOGGER.error("M0.2 connectivity diagnostic failed: %s", exc)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
