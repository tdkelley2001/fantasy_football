"""Read-only M0.3 audit of future ESPN player-week data."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import math
from numbers import Real
from typing import Any, Callable, Mapping, Sequence

from espn_api.football import League
from espn_api.requests.espn_requests import (
    ESPNAccessDenied,
    ESPNInvalidLeague,
    ESPNUnknownError,
)
from requests import RequestException

from fantasy_football.config import Settings, SettingsError, load_settings
from fantasy_football.logging_config import configure_logging


LOGGER = logging.getLogger(__name__)
PLAYER_INFO_VIEW = "kona_player_info"
PRO_SCHEDULE_VIEW = "proTeamSchedules_wl"
LEAGUE_VIEWS = ("mTeam", "mRoster", "mMatchup", "mSettings", "mStandings")
POOL_STATUSES = frozenset({"FREEAGENT", "WAIVERS", "ONTEAM"})


class FutureDataAuditError(RuntimeError):
    """Raised when ESPN data violates an M0.3 discovery invariant."""


def schedule_coverage_statement(expected_team_count: int) -> str:
    """Describe verified schedule coverage without assuming one league size."""
    return (
        "Every future regular-season fantasy week contains each of the "
        f"{expected_team_count} expected teams exactly once across home/away matchups."
    )


@dataclass(frozen=True, slots=True)
class PoolPlayer:
    player_id: int
    status: str
    owner_team_id: int


@dataclass(frozen=True, slots=True)
class PlayerEvidence:
    player_id: int
    status: str
    owner_team_id: int
    default_position_id: int
    eligible_slot_ids: tuple[int, ...]
    pro_team_id: int
    injury_status: str | None
    projections: tuple[tuple[int, float | None], ...]


@dataclass(frozen=True, slots=True)
class MatchupEvidence:
    week: int
    matchup_id: int
    home_team_id: int
    away_team_id: int


@dataclass(frozen=True, slots=True)
class RetrievalEvidence:
    name: str
    endpoint: str
    view: str
    request_count: int
    scoring_period: int | None
    started_at_utc: str
    finished_at_utc: str
    detail: str


@dataclass(frozen=True, slots=True)
class FutureDataReport:
    league_id: int
    season: int
    current_week: int
    regular_season_end: int
    expected_team_count: int
    pool_player_count: int
    rostered_player_count: int
    unrostered_player_count: int
    free_agent_count: int
    waiver_count: int
    pool_page_lengths: tuple[int, ...]
    weekly_player_request_count: int
    player_week_count: int
    projection_present_count: int
    projection_missing_count: int
    projection_zero_count: int
    projection_negative_count: int
    projection_coverage_by_week: dict[str, dict[str, int]]
    projection_coverage_by_status: dict[str, dict[str, int]]
    future_bye_player_week_count: int
    bye_projection_status_counts: dict[str, int]
    future_matchup_count: int
    future_matchup_weeks: tuple[int, ...]
    status_counts: dict[str, int]
    injury_status_counts: dict[str, int]
    future_view_status_variation_count: int
    retrievals: tuple[RetrievalEvidence, ...]
    verified_live: tuple[str, ...]
    verified_by_tests: tuple[str, ...]
    unverified: tuple[str, ...]
    unsupported: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _integer(value: Any, *, field: str, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FutureDataAuditError(f"{field} must be an integer; observed {value!r}")
    if (allow_zero and value < 0) or (not allow_zero and value <= 0):
        qualifier = "non-negative" if allow_zero else "positive"
        raise FutureDataAuditError(
            f"{field} must be a {qualifier} integer; observed {value!r}"
        )
    return value


def _nonzero_integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value == 0:
        raise FutureDataAuditError(
            f"{field} must be a nonzero integer; observed {value!r}"
        )
    return value


def _mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FutureDataAuditError(f"{field} must be a mapping; observed {type(value).__name__}")
    return value


def _list(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise FutureDataAuditError(f"{field} must be a list; observed {type(value).__name__}")
    return value


def parse_pool_page(
    response: Mapping[str, Any], *, offset: int, page_size: int
) -> tuple[PoolPlayer, ...]:
    """Parse one raw ``kona_player_info`` page without library defaults."""

    players = _list(response.get("players"), field=f"player pool offset={offset}: players")
    if len(players) > page_size:
        raise FutureDataAuditError(
            f"player pool offset={offset}: received {len(players)} records above limit {page_size}"
        )
    result: list[PoolPlayer] = []
    local_ids: set[int] = set()
    for index, raw in enumerate(players):
        wrap = _mapping(raw, field=f"player pool offset={offset}, index={index}")
        player_id = _nonzero_integer(
            wrap.get("id"), field=f"player pool offset={offset}, index={index}: id"
        )
        inner = _mapping(
            wrap.get("player"), field=f"player pool player_id={player_id}: player"
        )
        if inner.get("id") != player_id:
            raise FutureDataAuditError(
                f"player pool player_id={player_id}: outer and inner player IDs disagree"
            )
        if player_id in local_ids:
            raise FutureDataAuditError(
                f"player pool offset={offset}: duplicate player_id={player_id} within page"
            )
        local_ids.add(player_id)
        status = wrap.get("status")
        if status not in POOL_STATUSES:
            raise FutureDataAuditError(
                f"player pool player_id={player_id}: unsupported status {status!r}"
            )
        owner = _integer(
            wrap.get("onTeamId"),
            field=f"player pool player_id={player_id}: onTeamId",
            allow_zero=True,
        )
        if status == "ONTEAM" and owner == 0:
            raise FutureDataAuditError(
                f"player pool player_id={player_id}: ONTEAM entry has onTeamId=0"
            )
        if status != "ONTEAM" and owner != 0:
            raise FutureDataAuditError(
                f"player pool player_id={player_id}: {status} entry has owner team {owner}"
            )
        result.append(PoolPlayer(player_id, status, owner))
    return tuple(result)


def retrieve_player_pool(
    request_page: Callable[[int, int], Mapping[str, Any]], *, page_size: int
) -> tuple[tuple[PoolPlayer, ...], tuple[int, ...]]:
    """Retrieve all pool pages, requiring an observable pagination terminator."""

    _integer(page_size, field="player pool page_size")
    offset = 0
    found: list[PoolPlayer] = []
    seen: set[int] = set()
    lengths: list[int] = []
    while True:
        page = parse_pool_page(request_page(offset, page_size), offset=offset, page_size=page_size)
        lengths.append(len(page))
        duplicates = sorted(item.player_id for item in page if item.player_id in seen)
        if duplicates:
            raise FutureDataAuditError(
                "player pool pagination returned duplicate player IDs across pages: "
                + ", ".join(map(str, duplicates[:5]))
            )
        seen.update(item.player_id for item in page)
        found.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
        if len(lengths) > 100:
            raise FutureDataAuditError(
                "player pool pagination exceeded 100 full pages without a terminating page"
            )
    if not found:
        raise FutureDataAuditError("player pool is empty")
    return tuple(found), tuple(lengths)


def _extract_card_player(
    wrap: Mapping[str, Any], *, requested_ids: set[int]
) -> tuple[int, Mapping[str, Any]]:
    player_id = _nonzero_integer(wrap.get("id"), field="player card wrapper: id")
    if player_id not in requested_ids:
        raise FutureDataAuditError(
            f"player card returned unrequested player_id={player_id}"
        )
    player = _mapping(wrap.get("player"), field=f"player card player_id={player_id}: player")
    if player.get("id") != player_id:
        raise FutureDataAuditError(
            f"player card player_id={player_id}: outer and inner player IDs disagree"
        )
    return player_id, player


def parse_player_cards(
    response: Mapping[str, Any],
    *,
    requested_ids: Sequence[int],
    pool_by_id: Mapping[int, PoolPlayer],
    season: int,
    valid_weeks: Sequence[int],
) -> tuple[PlayerEvidence, ...]:
    """Parse raw player cards and preserve absent projections as ``None``."""

    requested = set(requested_ids)
    if len(requested) != len(requested_ids):
        raise FutureDataAuditError("player card request contains duplicate player IDs")
    raw_players = _list(response.get("players"), field="player card response: players")
    parsed: dict[int, PlayerEvidence] = {}
    weeks = tuple(valid_weeks)
    valid_week_set = set(weeks)
    for index, raw in enumerate(raw_players):
        wrap = _mapping(raw, field=f"player card index={index}")
        player_id, player = _extract_card_player(wrap, requested_ids=requested)
        if player_id in parsed:
            raise FutureDataAuditError(f"player card response duplicates player_id={player_id}")
        pool = pool_by_id.get(player_id)
        if pool is None:
            raise FutureDataAuditError(f"player card player_id={player_id} is absent from pool")
        if wrap.get("status") != pool.status or wrap.get("onTeamId") != pool.owner_team_id:
            raise FutureDataAuditError(
                f"player card player_id={player_id}: ownership/status conflicts with pool page"
            )
        slots_raw = _list(
            player.get("eligibleSlots"),
            field=f"player card player_id={player_id}: eligibleSlots",
        )
        if not slots_raw:
            raise FutureDataAuditError(
                f"player card player_id={player_id}: eligibleSlots is empty"
            )
        slots = tuple(
            _integer(value, field=f"player card player_id={player_id}: eligible slot", allow_zero=True)
            for value in slots_raw
        )
        projections: dict[int, float | None] = {week: None for week in weeks}
        seen_projection_weeks: set[int] = set()
        for stat_index, stat_raw in enumerate(
            _list(player.get("stats"), field=f"player card player_id={player_id}: stats")
        ):
            stat = _mapping(
                stat_raw, field=f"player card player_id={player_id}: stat index={stat_index}"
            )
            if stat.get("statSourceId") != 1 or stat.get("seasonId") != season:
                continue
            week = stat.get("scoringPeriodId")
            if week == 0:
                continue
            if stat.get("statSplitTypeId") != 1:
                raise FutureDataAuditError(
                    f"player card player_id={player_id}, week={week}: projected stat has unsupported statSplitTypeId={stat.get('statSplitTypeId')!r}"
                )
            if isinstance(week, bool) or not isinstance(week, int) or week not in valid_week_set:
                raise FutureDataAuditError(
                    f"player card player_id={player_id}: projected stat has unknown fantasy week {week!r}"
                )
            if week in seen_projection_weeks:
                raise FutureDataAuditError(
                    f"player card player_id={player_id}: duplicate projection for week={week}"
                )
            seen_projection_weeks.add(week)
            if "appliedTotal" not in stat:
                raise FutureDataAuditError(
                    f"player card player_id={player_id}, week={week}: projection lacks appliedTotal"
                )
            value = stat["appliedTotal"]
            if isinstance(value, bool) or not isinstance(value, Real):
                raise FutureDataAuditError(
                    f"player card player_id={player_id}, week={week}: appliedTotal must be numeric"
                )
            numeric_value = float(value)
            if not math.isfinite(numeric_value):
                raise FutureDataAuditError(
                    f"player card player_id={player_id}, week={week}: appliedTotal must be finite"
                )
            projections[week] = numeric_value
        injury = player.get("injuryStatus")
        if injury is not None and (not isinstance(injury, str) or not injury.strip()):
            raise FutureDataAuditError(
                f"player card player_id={player_id}: injuryStatus must be text or null"
            )
        parsed[player_id] = PlayerEvidence(
            player_id=player_id,
            status=pool.status,
            owner_team_id=pool.owner_team_id,
            default_position_id=_integer(
                player.get("defaultPositionId"),
                field=f"player card player_id={player_id}: defaultPositionId",
            ),
            eligible_slot_ids=slots,
            pro_team_id=_integer(
                player.get("proTeamId"),
                field=f"player card player_id={player_id}: proTeamId",
                allow_zero=True,
            ),
            injury_status=injury.strip() if isinstance(injury, str) else None,
            projections=tuple((week, projections[week]) for week in weeks),
        )
    missing = requested - parsed.keys()
    if missing:
        raise FutureDataAuditError(
            "player card response omitted requested player IDs: "
            + ", ".join(map(str, sorted(missing)[:5]))
        )
    return tuple(parsed[player_id] for player_id in requested_ids)


def parse_pro_team_byes(
    response: Mapping[str, Any], *, valid_weeks: Sequence[int], expected_team_count: int
) -> dict[int, int]:
    """Validate ESPN's explicit ``byeWeek`` against its pro-team schedule."""

    settings = _mapping(response.get("settings"), field="pro schedule: settings")
    teams = _list(settings.get("proTeams"), field="pro schedule: proTeams")
    weeks = set(valid_weeks)
    result: dict[int, int] = {}
    for index, raw in enumerate(teams):
        team = _mapping(raw, field=f"pro schedule team index={index}")
        team_id = _integer(team.get("id"), field=f"pro schedule team index={index}: id", allow_zero=True)
        if team_id == 0:
            continue
        if team_id in result:
            raise FutureDataAuditError(f"pro schedule duplicates pro team id={team_id}")
        bye = _integer(team.get("byeWeek"), field=f"pro team id={team_id}: byeWeek")
        schedule = _mapping(
            team.get("proGamesByScoringPeriod"),
            field=f"pro team id={team_id}: proGamesByScoringPeriod",
        )
        if str(bye) in schedule and schedule[str(bye)]:
            raise FutureDataAuditError(
                f"pro team id={team_id}: byeWeek={bye} conflicts with a scheduled game"
            )
        for week in weeks:
            games = schedule.get(str(week), [])
            if week != bye and not isinstance(games, list):
                raise FutureDataAuditError(
                    f"pro team id={team_id}, week={week}: schedule entry is not a list"
                )
        result[team_id] = bye
    if not result:
        raise FutureDataAuditError("pro schedule contains no NFL teams")
    if len(result) != expected_team_count:
        raise FutureDataAuditError(
            f"pro schedule contains {len(result)} distinct NFL teams; expected {expected_team_count}"
        )
    return result


def parse_remaining_schedule(
    response: Mapping[str, Any],
    *,
    team_ids: set[int],
    future_weeks: Sequence[int],
    expected_team_count: int,
) -> tuple[MatchupEvidence, ...]:
    """Validate one complete round of fantasy matchups for every future week."""

    if len(team_ids) != expected_team_count:
        raise FutureDataAuditError(
            f"schedule input has {len(team_ids)} teams; expected {expected_team_count}"
        )
    raw_schedule = _list(response.get("schedule"), field="league schedule")
    wanted = set(future_weeks)
    matchups: list[MatchupEvidence] = []
    seen_matchup_ids: set[int] = set()
    teams_by_week: dict[int, list[int]] = {week: [] for week in future_weeks}
    for index, raw in enumerate(raw_schedule):
        matchup = _mapping(raw, field=f"league schedule index={index}")
        week = matchup.get("matchupPeriodId")
        if week not in wanted:
            continue
        matchup_id = _integer(matchup.get("id"), field=f"schedule week={week}: id")
        if matchup_id in seen_matchup_ids:
            raise FutureDataAuditError(f"league schedule duplicates matchup id={matchup_id}")
        seen_matchup_ids.add(matchup_id)
        home = _mapping(matchup.get("home"), field=f"schedule matchup={matchup_id}: home")
        away = _mapping(matchup.get("away"), field=f"schedule matchup={matchup_id}: away")
        home_id = _integer(home.get("teamId"), field=f"schedule matchup={matchup_id}: home teamId")
        away_id = _integer(away.get("teamId"), field=f"schedule matchup={matchup_id}: away teamId")
        if home_id == away_id or home_id not in team_ids or away_id not in team_ids:
            raise FutureDataAuditError(
                f"schedule matchup={matchup_id}: invalid home/away relationship {home_id}/{away_id}"
            )
        teams_by_week[week].extend((home_id, away_id))
        matchups.append(MatchupEvidence(week, matchup_id, home_id, away_id))
    for week, observed in teams_by_week.items():
        if len(observed) != expected_team_count or set(observed) != team_ids:
            raise FutureDataAuditError(
                f"league schedule week={week}: expected every team exactly once; observed {len(observed)} slots and {len(set(observed))} distinct teams"
            )
        duplicates = [team for team, count in Counter(observed).items() if count != 1]
        if duplicates:
            raise FutureDataAuditError(
                f"league schedule week={week}: duplicate team IDs {sorted(duplicates)}"
            )
    return tuple(sorted(matchups, key=lambda item: (item.week, item.matchup_id)))


def _raw_roster_owners(league: Any) -> tuple[dict[int, int], set[int]]:
    owners: dict[int, int] = {}
    team_ids: set[int] = set()
    for team in league.teams:
        team_id = _integer(team.team_id, field="league team_id")
        if team_id in team_ids:
            raise FutureDataAuditError(f"league duplicates team_id={team_id}")
        team_ids.add(team_id)
        for player in team.roster:
            player_id = _nonzero_integer(player.playerId, field=f"team_id={team_id}: playerId")
            if player_id in owners:
                raise FutureDataAuditError(f"rosters duplicate player_id={player_id}")
            owners[player_id] = team_id
    return owners, team_ids


def audit_live(settings: Settings, *, expected_team_count: int, page_size: int = 250) -> FutureDataReport:
    """Run the read-only M0.3 live audit and return only sanitized aggregates."""

    credentials = settings.credentials
    started = _utc_now()
    try:
        league = League(
            league_id=settings.league_id,
            year=settings.season,
            espn_s2=credentials.espn_s2 if credentials else None,
            swid=credentials.swid if credentials else None,
        )
        endpoint = league.espn_request.LEAGUE_ENDPOINT
        raw_league = league.espn_request.get_league()
        base_finished = _utc_now()
        current_week = _integer(league.current_week, field="league current_week")
        regular_end = _integer(
            league.settings.reg_season_count, field="league regular-season end"
        )
        if current_week > regular_end:
            raise FutureDataAuditError(
                f"current week {current_week} is after regular-season end {regular_end}"
            )
        weeks = tuple(range(current_week, regular_end + 1))
        roster_owners, team_ids = _raw_roster_owners(league)
        if len(team_ids) != expected_team_count:
            raise FutureDataAuditError(
                f"league has {len(team_ids)} teams; expected {expected_team_count}"
            )

        pool_started = _utc_now()
        weekly_pages: dict[int, list[Mapping[str, Any]]] = {}
        weekly_lengths: dict[int, tuple[int, ...]] = {}
        weekly_pools: dict[int, tuple[PoolPlayer, ...]] = {}
        for week in weeks:
            captured_pages: list[Mapping[str, Any]] = []

            def request_pool(offset: int, limit: int, *, scoring_week: int = week) -> Mapping[str, Any]:
                filters = {
                    "players": {
                        "filterStatus": {"value": sorted(POOL_STATUSES)},
                        "limit": limit,
                        "offset": offset,
                        "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
                    }
                }
                response = league.espn_request.league_get(
                    params={"view": PLAYER_INFO_VIEW, "scoringPeriodId": scoring_week},
                    headers={"x-fantasy-filter": json.dumps(filters)},
                )
                captured_pages.append(response)
                return response

            week_pool, lengths = retrieve_player_pool(request_pool, page_size=page_size)
            weekly_pages[week] = captured_pages
            weekly_lengths[week] = lengths
            weekly_pools[week] = week_pool
        pool_finished = _utc_now()
        pool = weekly_pools[current_week]
        page_lengths = weekly_lengths[current_week]
        pool_by_id = {item.player_id: item for item in pool}
        observed_rostered = {
            item.player_id: item.owner_team_id for item in pool if item.status == "ONTEAM"
        }
        if observed_rostered != roster_owners:
            missing = len(roster_owners.keys() - observed_rostered.keys())
            extra = len(observed_rostered.keys() - roster_owners.keys())
            conflicts = sum(
                observed_rostered.get(player_id) not in (None, owner)
                for player_id, owner in roster_owners.items()
            )
            raise FutureDataAuditError(
                "player-pool ownership does not reconcile with M0.2 rosters: "
                f"missing={missing}, extra={extra}, conflicting={conflicts}"
            )

        baseline_ids = set(pool_by_id)
        evidence_by_id: dict[int, PlayerEvidence] = {}
        status_variations: set[int] = set()
        projection_by_id: dict[int, dict[int, float | None]] = {
            player_id: {} for player_id in baseline_ids
        }
        for week in weeks:
            observed_pool = {item.player_id: item for item in weekly_pools[week]}
            if set(observed_pool) != baseline_ids:
                raise FutureDataAuditError(
                    f"week={week} player universe conflicts with week={current_week}: "
                    f"missing={len(baseline_ids - set(observed_pool))}, extra={len(set(observed_pool) - baseline_ids)}"
                )
            ownership_changes = [
                player_id
                for player_id, baseline in pool_by_id.items()
                if observed_pool[player_id] != baseline
            ]
            status_variations.update(ownership_changes)
            for response in weekly_pages[week]:
                raw_page = response["players"]
                batch_ids = [raw["id"] for raw in raw_page]
                parsed_page = parse_player_cards(
                    response,
                    requested_ids=batch_ids,
                    pool_by_id=observed_pool,
                    season=settings.season,
                    valid_weeks=[week],
                )
                for player in parsed_page:
                    previous = evidence_by_id.get(player.player_id)
                    if previous and (
                        previous.default_position_id,
                        previous.eligible_slot_ids,
                        previous.pro_team_id,
                    ) != (
                        player.default_position_id,
                        player.eligible_slot_ids,
                        player.pro_team_id,
                    ):
                        raise FutureDataAuditError(
                            f"player_id={player.player_id}: identity/eligibility fields changed across weekly requests"
                        )
                    evidence_by_id[player.player_id] = player
                    projection_by_id[player.player_id][week] = player.projections[0][1]
        evidence = [
            PlayerEvidence(
                player_id=player_id,
                status=pool_by_id[player_id].status,
                owner_team_id=pool_by_id[player_id].owner_team_id,
                default_position_id=evidence_by_id[player_id].default_position_id,
                eligible_slot_ids=evidence_by_id[player_id].eligible_slot_ids,
                pro_team_id=evidence_by_id[player_id].pro_team_id,
                injury_status=evidence_by_id[player_id].injury_status,
                projections=tuple((week, projection_by_id[player_id][week]) for week in weeks),
            )
            for player_id in sorted(baseline_ids)
        ]
        pro_started = _utc_now()
        pro_response = league.espn_request.get_pro_schedule()
        byes = parse_pro_team_byes(
            pro_response, valid_weeks=weeks, expected_team_count=32
        )
        pro_finished = _utc_now()
        schedule = parse_remaining_schedule(
            raw_league,
            team_ids=team_ids,
            future_weeks=weeks,
            expected_team_count=expected_team_count,
        )
    except (ESPNAccessDenied, ESPNInvalidLeague, ESPNUnknownError, RequestException):
        raise
    except FutureDataAuditError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, json.JSONDecodeError) as exc:
        raise FutureDataAuditError(
            f"ESPN returned a malformed or unsupported M0.3 response: {exc}"
        ) from exc

    values = [value for player in evidence for _, value in player.projections]
    present = [value for value in values if value is not None]
    status_counts = Counter(item.status for item in pool)
    injury_counts = Counter(player.injury_status or "MISSING" for player in evidence)
    bye_player_weeks = sum(
        player.pro_team_id in byes and byes[player.pro_team_id] in weeks
        for player in evidence
    )
    coverage_by_week: dict[str, dict[str, int]] = {}
    for week in weeks:
        week_values = [dict(player.projections)[week] for player in evidence]
        coverage_by_week[str(week)] = {
            "present": sum(value is not None for value in week_values),
            "missing": sum(value is None for value in week_values),
            "zero": sum(value == 0 for value in week_values if value is not None),
            "negative": sum(value < 0 for value in week_values if value is not None),
        }
    coverage_by_status: dict[str, dict[str, int]] = {}
    for status in sorted(POOL_STATUSES):
        status_values = [
            value
            for player in evidence
            if player.status == status
            for _, value in player.projections
        ]
        coverage_by_status[status] = {
            "player_weeks": len(status_values),
            "present": sum(value is not None for value in status_values),
            "missing": sum(value is None for value in status_values),
            "zero": sum(value == 0 for value in status_values if value is not None),
            "negative": sum(value < 0 for value in status_values if value is not None),
        }
    bye_values = [
        dict(player.projections)[byes[player.pro_team_id]]
        for player in evidence
        if player.pro_team_id in byes and byes[player.pro_team_id] in weeks
    ]
    retrievals = (
        RetrievalEvidence(
            "league and fantasy schedule", endpoint, ",".join(LEAGUE_VIEWS), 2, None,
            started, base_finished,
            "League construction and one raw response; identity/current-week context matched.",
        ),
        RetrievalEvidence(
            "week-specific player pool and projections", endpoint, PLAYER_INFO_VIEW,
            sum(len(lengths) for lengths in weekly_lengths.values()), None,
            pool_started, pool_finished,
            f"weeks={list(weeks)}; page lengths by week={weekly_lengths}; every week ended on a short page and returned the same player IDs; current-week ownership was authoritative.",
        ),
        RetrievalEvidence(
            "NFL schedule and byes", league.espn_request.ENDPOINT, PRO_SCHEDULE_VIEW, 1, None,
            pro_started, pro_finished,
            f"validated explicit byeWeek for {len(byes)} NFL teams against proGamesByScoringPeriod.",
        ),
    )
    return FutureDataReport(
        league_id=settings.league_id,
        season=settings.season,
        current_week=current_week,
        regular_season_end=regular_end,
        expected_team_count=expected_team_count,
        pool_player_count=len(pool),
        rostered_player_count=status_counts["ONTEAM"],
        unrostered_player_count=status_counts["FREEAGENT"] + status_counts["WAIVERS"],
        free_agent_count=status_counts["FREEAGENT"],
        waiver_count=status_counts["WAIVERS"],
        pool_page_lengths=page_lengths,
        weekly_player_request_count=sum(len(lengths) for lengths in weekly_lengths.values()),
        player_week_count=len(values),
        projection_present_count=len(present),
        projection_missing_count=sum(value is None for value in values),
        projection_zero_count=sum(value == 0 for value in present),
        projection_negative_count=sum(value < 0 for value in present),
        projection_coverage_by_week=coverage_by_week,
        projection_coverage_by_status=coverage_by_status,
        future_bye_player_week_count=bye_player_weeks,
        bye_projection_status_counts={
            "present": sum(value is not None for value in bye_values),
            "missing": sum(value is None for value in bye_values),
            "zero": sum(value == 0 for value in bye_values if value is not None),
            "negative": sum(value < 0 for value in bye_values if value is not None),
        },
        future_matchup_count=len(schedule),
        future_matchup_weeks=weeks,
        status_counts=dict(sorted(status_counts.items())),
        injury_status_counts=dict(sorted(injury_counts.items())),
        future_view_status_variation_count=len(status_variations),
        retrievals=retrievals,
        verified_live=(
            "Week-specific raw kona_player_info statSourceId=1/statSplitTypeId=1 records preserve projections; absence is represented as missing, not zero.",
            "Every weekly player-pool retrieval terminated on a short page with no duplicate IDs and returned an identical player-ID universe.",
            "Pool ONTEAM ownership exactly reconciles with the M0.2 roster view.",
            "Raw player IDs, default positions, eligible slot IDs, pro-team IDs, pool status, ownership and injury status were validated.",
            "ESPN exposes byeWeek directly and it did not conflict with proGamesByScoringPeriod.",
            schedule_coverage_statement(expected_team_count),
        ),
        verified_by_tests=(
            "Missing, zero and negative projections remain distinct.",
            "Duplicate, omitted, unrequested and wrong-week player-card data fail explicitly.",
            "Duplicate pagination, conflicting ownership, malformed payloads and incomplete schedules fail explicitly.",
        ),
        unverified=(
            "ESPN provides no total-count field proving that its paginated player universe includes every conceivable NFL player.",
            "Projection update timing and consistency across requests are not transactionally guaranteed; retrieval timestamps bound this audit.",
            "The semantic reason for a non-bye missing or zero projection is not established by these fields alone.",
            "Future scoring-period views can expose status/ownership values different from the current-week view; only the current-week view is treated as current ownership.",
        ),
        unsupported=(
            "Neither kona_player_info nor kona_playercard provides one authoritative field explaining every missing or zero projection.",
            "kona_playercard's top-scoring-period filter did not return future weekly projections; week-specific kona_player_info requests were required.",
            "espn-api Player parsing cannot preserve a missing appliedTotal because it uses stats.get('appliedTotal', 0).",
        ),
    )


def render_summary(report: FutureDataReport) -> str:
    lines = [
        "M0.3 future player-week data audit",
        f"League ID: {report.league_id}; season: {report.season}",
        f"Weeks audited: {report.current_week}-{report.regular_season_end}",
        f"Player pool: {report.pool_player_count} ({report.rostered_player_count} rostered, {report.unrostered_player_count} unrostered)",
        f"Pagination page lengths: {list(report.pool_page_lengths)}",
        f"Player-weeks: {report.player_week_count}; projections present={report.projection_present_count}, missing={report.projection_missing_count}, zero={report.projection_zero_count}, negative={report.projection_negative_count}",
        f"Future bye player-weeks: {report.future_bye_player_week_count}",
        f"Players with future-view status/ownership variation: {report.future_view_status_variation_count}",
        f"Remaining regular-season matchups: {report.future_matchup_count}",
        "",
        "Verified live:",
        *(f"- {item}" for item in report.verified_live),
        "",
        "Verified by tests:",
        *(f"- {item}" for item in report.verified_by_tests),
        "",
        "Unverified:",
        *(f"- {item}" for item in report.unverified),
        "",
        "Unsupported:",
        *(f"- {item}" for item in report.unsupported),
    ]
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the read-only M0.3 ESPN future-data audit.")
    parser.add_argument("--expected-team-count", type=int, required=True)
    parser.add_argument("--json", action="store_true", help="Emit sanitized aggregate JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        report = audit_live(settings, expected_team_count=args.expected_team_count)
    except (
        SettingsError,
        FutureDataAuditError,
        ESPNAccessDenied,
        ESPNInvalidLeague,
        ESPNUnknownError,
        RequestException,
    ) as exc:
        LOGGER.error("M0.3 future-data audit failed: %s", exc)
        return 2
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True) if args.json else render_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
