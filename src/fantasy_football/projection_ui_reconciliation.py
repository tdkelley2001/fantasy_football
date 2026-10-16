"""Read-only named examples for manual ESPN projection UI reconciliation."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import logging
from typing import Any, Mapping, Sequence

from espn_api.football import League
from espn_api.football.constant import PRO_TEAM_MAP
from espn_api.requests.espn_requests import (
    ESPNAccessDenied,
    ESPNInvalidLeague,
    ESPNUnknownError,
)
from requests import RequestException

from fantasy_football.config import Settings, SettingsError, load_settings
from fantasy_football.future_data_audit import (
    FutureDataAuditError,
    PLAYER_INFO_VIEW,
    POOL_STATUSES,
    PlayerEvidence,
    PoolPlayer,
    parse_player_cards,
    parse_pro_team_byes,
    retrieve_player_pool,
)
from fantasy_football.logging_config import configure_logging


LOGGER = logging.getLogger(__name__)
DEFAULT_POSITION_MAP = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    16: "D/ST",
}


class ProjectionUiReconciliationError(RuntimeError):
    """Raised when named reconciliation evidence is incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class ProjectionExample:
    classification: str
    player_name: str
    player_id: int
    position: str
    nfl_team: str
    fantasy_week: int
    ownership_status: str
    owner_team_id: int
    raw_projection_exists: bool
    raw_applied_total: float | None
    classification_reason: str
    bye_week: int | None
    is_bye_week: bool
    injury_status: str | None


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    season: int
    current_week: int
    audited_week: int
    pool_player_count: int
    page_lengths: tuple[int, ...]
    classification_counts: dict[str, int]
    rostered_missing_count: int
    examples: tuple[ProjectionExample, ...]


def _nonempty_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectionUiReconciliationError(
            f"{field} must be non-empty text; observed {value!r}"
        )
    return value.strip()


def _label(mapping: Mapping[Any, Any], key: int, *, field: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ProjectionUiReconciliationError(
            f"{field}={key} has no supported espn-api label"
        )
    return value


def _classification(value: float | None) -> tuple[str, str]:
    if value is None:
        return (
            "missing",
            "No raw stat matched seasonId, scoringPeriodId, statSourceId=1, and statSplitTypeId=1.",
        )
    if value == 0:
        return (
            "zero",
            "A matching raw projection record exists and appliedTotal is explicitly 0.",
        )
    if value > 0:
        return (
            "positive",
            "A matching raw projection record exists and appliedTotal is greater than 0.",
        )
    return (
        "negative",
        "A matching raw projection record exists and appliedTotal is less than 0.",
    )


def build_examples(
    *,
    raw_players_by_id: Mapping[int, Mapping[str, Any]],
    evidence_by_id: Mapping[int, PlayerEvidence],
    current_pool_by_id: Mapping[int, PoolPlayer],
    bye_by_pro_team_id: Mapping[int, int],
    week: int,
) -> tuple[tuple[ProjectionExample, ...], dict[str, int], int]:
    """Build and select one deterministic example per requested classification."""

    if set(raw_players_by_id) != set(evidence_by_id):
        raise ProjectionUiReconciliationError(
            "raw player records and parsed projection evidence have different ID sets"
        )
    if set(current_pool_by_id) != set(evidence_by_id):
        raise ProjectionUiReconciliationError(
            "current ownership and audited-week player universes have different ID sets"
        )

    candidates: dict[str, list[ProjectionExample]] = {
        "missing": [],
        "zero": [],
        "positive": [],
        "negative": [],
    }
    for player_id, evidence in evidence_by_id.items():
        projection_map = dict(evidence.projections)
        if set(projection_map) != {week}:
            raise ProjectionUiReconciliationError(
                f"player_id={player_id}: expected exactly projection week {week}"
            )
        value = projection_map[week]
        classification, reason = _classification(value)
        wrapper = raw_players_by_id[player_id]
        player = wrapper.get("player")
        if not isinstance(player, Mapping):
            raise ProjectionUiReconciliationError(
                f"player_id={player_id}: raw player must be a mapping"
            )
        current = current_pool_by_id[player_id]
        bye_week = bye_by_pro_team_id.get(evidence.pro_team_id)
        candidates[classification].append(
            ProjectionExample(
                classification=classification,
                player_name=_nonempty_text(
                    player.get("fullName"), field=f"player_id={player_id}: fullName"
                ),
                player_id=player_id,
                position=_label(
                    DEFAULT_POSITION_MAP,
                    evidence.default_position_id,
                    field="defaultPositionId",
                ),
                nfl_team=_label(
                    PRO_TEAM_MAP, evidence.pro_team_id, field="proTeamId"
                ),
                fantasy_week=week,
                ownership_status=current.status,
                owner_team_id=current.owner_team_id,
                raw_projection_exists=value is not None,
                raw_applied_total=value,
                classification_reason=reason,
                bye_week=bye_week,
                is_bye_week=bye_week == week,
                injury_status=evidence.injury_status,
            )
        )

    for values in candidates.values():
        values.sort(
            key=lambda item: (
                item.ownership_status != "ONTEAM",
                item.player_name.casefold(),
                item.player_id,
            )
        )
    required = ("missing", "zero", "positive")
    absent = [classification for classification in required if not candidates[classification]]
    if absent:
        raise ProjectionUiReconciliationError(
            f"week={week}: no examples available for classifications: {', '.join(absent)}"
        )
    selected = tuple(candidates[classification][0] for classification in required)
    counts = {name: len(values) for name, values in candidates.items()}
    rostered_missing = sum(
        item.ownership_status == "ONTEAM" for item in candidates["missing"]
    )
    return selected, counts, rostered_missing


def _fetch_week(
    league: Any, *, week: int, page_size: int
) -> tuple[tuple[PoolPlayer, ...], tuple[int, ...], list[Mapping[str, Any]]]:
    pages: list[Mapping[str, Any]] = []

    def request_page(offset: int, limit: int) -> Mapping[str, Any]:
        filters = {
            "players": {
                "filterStatus": {"value": sorted(POOL_STATUSES)},
                "limit": limit,
                "offset": offset,
                "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
            }
        }
        response = league.espn_request.league_get(
            params={"view": PLAYER_INFO_VIEW, "scoringPeriodId": week},
            headers={"x-fantasy-filter": json.dumps(filters)},
        )
        pages.append(response)
        return response

    pool, lengths = retrieve_player_pool(request_page, page_size=page_size)
    return pool, lengths, pages


def reconcile_live(
    settings: Settings, *, week: int | None = None, page_size: int = 250
) -> ReconciliationReport:
    """Retrieve named examples without persisting live names or IDs."""

    credentials = settings.credentials
    try:
        league = League(
            league_id=settings.league_id,
            year=settings.season,
            espn_s2=credentials.espn_s2 if credentials else None,
            swid=credentials.swid if credentials else None,
        )
        current_week = league.current_week
        regular_end = league.settings.reg_season_count
        audited_week = current_week + 1 if week is None else week
        if isinstance(audited_week, bool) or not isinstance(audited_week, int):
            raise ProjectionUiReconciliationError("fantasy week must be an integer")
        if audited_week < current_week or audited_week > regular_end:
            raise ProjectionUiReconciliationError(
                f"fantasy week must be between current week {current_week} and regular-season end {regular_end}; observed {audited_week}"
            )

        current_pool, _, current_pages = _fetch_week(
            league, week=current_week, page_size=page_size
        )
        if audited_week == current_week:
            target_pool, page_lengths, target_pages = (
                current_pool,
                tuple(len(page["players"]) for page in current_pages),
                current_pages,
            )
        else:
            target_pool, page_lengths, target_pages = _fetch_week(
                league, week=audited_week, page_size=page_size
            )
        current_by_id = {item.player_id: item for item in current_pool}
        target_by_id = {item.player_id: item for item in target_pool}
        if set(current_by_id) != set(target_by_id):
            raise ProjectionUiReconciliationError(
                "current and audited-week player universes do not reconcile"
            )

        raw_by_id: dict[int, Mapping[str, Any]] = {}
        evidence_by_id: dict[int, PlayerEvidence] = {}
        for response in target_pages:
            raw_players = response.get("players")
            if not isinstance(raw_players, list):
                raise ProjectionUiReconciliationError(
                    "audited-week players response is malformed"
                )
            requested_ids = [raw.get("id") for raw in raw_players]
            parsed = parse_player_cards(
                response,
                requested_ids=requested_ids,
                pool_by_id=target_by_id,
                season=settings.season,
                valid_weeks=[audited_week],
            )
            for raw, evidence in zip(raw_players, parsed, strict=True):
                if evidence.player_id in raw_by_id:
                    raise ProjectionUiReconciliationError(
                        f"duplicate raw player_id={evidence.player_id}"
                    )
                raw_by_id[evidence.player_id] = raw
                evidence_by_id[evidence.player_id] = evidence

        pro_schedule = league.espn_request.get_pro_schedule()
        bye_by_team = parse_pro_team_byes(
            pro_schedule, valid_weeks=[audited_week]
        )
        examples, counts, rostered_missing = build_examples(
            raw_players_by_id=raw_by_id,
            evidence_by_id=evidence_by_id,
            current_pool_by_id=current_by_id,
            bye_by_pro_team_id=bye_by_team,
            week=audited_week,
        )
    except (ESPNAccessDenied, ESPNInvalidLeague, ESPNUnknownError, RequestException):
        raise
    except (ProjectionUiReconciliationError, FutureDataAuditError):
        raise
    except (KeyError, TypeError, ValueError, IndexError, json.JSONDecodeError) as exc:
        raise ProjectionUiReconciliationError(
            f"ESPN returned a malformed or unsupported reconciliation response: {exc}"
        ) from exc

    return ReconciliationReport(
        season=settings.season,
        current_week=current_week,
        audited_week=audited_week,
        pool_player_count=len(target_pool),
        page_lengths=page_lengths,
        classification_counts=counts,
        rostered_missing_count=rostered_missing,
        examples=examples,
    )


def render_report(report: ReconciliationReport) -> str:
    lines = [
        "M0.3 projection UI reconciliation",
        f"Season {report.season}; ESPN current week {report.current_week}; audited week {report.audited_week}",
        f"Complete player pool: {report.pool_player_count}; page lengths {list(report.page_lengths)}",
        (
            "Classifications: "
            + ", ".join(
                f"{name}={count}"
                for name, count in report.classification_counts.items()
            )
            + f"; rostered missing={report.rostered_missing_count}"
        ),
        "",
    ]
    for example in report.examples:
        owner = (
            f"ONTEAM (fantasy team ID {example.owner_team_id})"
            if example.ownership_status == "ONTEAM"
            else f"{example.ownership_status} (unrostered)"
        )
        applied = (
            "absent"
            if example.raw_applied_total is None
            else repr(example.raw_applied_total)
        )
        lines.extend(
            (
                f"[{example.classification.upper()}] {example.player_name} (ESPN player ID {example.player_id})",
                f"  Position/NFL team/week: {example.position} / {example.nfl_team} / {example.fantasy_week}",
                f"  Current ownership: {owner}",
                f"  Matching raw projection: {'yes' if example.raw_projection_exists else 'no'}; appliedTotal={applied}",
                f"  Classification: {example.classification_reason}",
                f"  Bye/injury: byeWeek={example.bye_week!r}; isByeWeek={str(example.is_bye_week).lower()}; injuryStatus={example.injury_status!r}",
                "",
            )
        )
    lines.append(
        "Manual check only: compare these names and weeks in ESPN; no values were persisted or substituted."
    )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print named ESPN player-week examples for manual UI reconciliation."
    )
    parser.add_argument(
        "--week",
        type=int,
        help="Fantasy week to inspect; defaults to the week after ESPN's current week.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        report = reconcile_live(settings, week=args.week)
    except (
        SettingsError,
        ProjectionUiReconciliationError,
        FutureDataAuditError,
        ESPNAccessDenied,
        ESPNInvalidLeague,
        ESPNUnknownError,
        RequestException,
    ) as exc:
        LOGGER.error("M0.3 projection UI reconciliation failed: %s", exc)
        return 2
    print(render_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
