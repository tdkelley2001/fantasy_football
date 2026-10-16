"""Bounded read-only M0.5 audit of historical ESPN player-week data."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
from numbers import Real
from typing import Any, Callable, Mapping, Sequence

from espn_api.football import League
from espn_api.requests.espn_requests import ESPNAccessDenied, ESPNInvalidLeague, ESPNUnknownError
from requests import RequestException

from fantasy_football.config import Settings, SettingsError, load_settings
from fantasy_football.logging_config import configure_logging


LOGGER = logging.getLogger(__name__)
PLAYER_INFO_VIEW = "kona_player_info"
PLAYER_CARD_VIEW = "kona_playercard"
POOL_STATUSES = ("FREEAGENT", "ONTEAM", "WAIVERS")
POSITION_LABELS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
PROVENANCE_CLASS = "historical_projection_pregame_provenance_unverified"


class HistoricalProjectionAuditError(RuntimeError):
    """Raised when historical ESPN evidence is malformed or contradictory."""


@dataclass(frozen=True, slots=True)
class HistoricalPlayerWeek:
    player_id: int
    season: int
    week: int
    position_id: int
    pro_team_id: int
    projection: float | None
    actual: float | None
    projection_status: str
    actual_status: str
    actual_stat_breakdown_present: bool
    as_of_metadata_present: bool
    provenance_class: str


@dataclass(frozen=True, slots=True)
class SampleCoverage:
    season: int
    week: int
    phase: str
    retrieved_at_utc: str
    endpoint: str
    view: str
    parameters: dict[str, object]
    scoring_signature: str
    scoring_item_count: int
    player_count: int
    player_week_count: int
    present_projections: int
    missing_projections: int
    explicit_zero_projections: int
    negative_projections: int
    present_actuals: int
    missing_actuals: int
    explicit_zero_actuals: int
    matched_pairs: int
    missing_projection_with_actual: int
    exact_projection_actual_matches: int
    hindsight_exact_tracking_signal: str
    actual_stat_breakdown_present: int
    counts_by_position: dict[str, dict[str, int]]
    counts_by_projection_magnitude: dict[str, int]
    pagination_page_lengths: tuple[int, ...]
    repeat_first_page_stable: bool


@dataclass(frozen=True, slots=True)
class HistoricalProjectionReport:
    league_id: int
    retrieved_at_utc: str
    samples: tuple[SampleCoverage, ...]
    total_unique_player_seasons: int
    total_player_weeks: int
    total_present_projections: int
    total_missing_projections: int
    total_explicit_zero_projections: int
    total_present_actuals: int
    total_missing_actuals: int
    total_matched_pairs: int
    total_missing_projection_with_actual: int
    playercard_comparison: tuple[dict[str, object], ...]
    scoring_signatures_by_season: dict[str, str]
    temporal_provenance_class: str
    revision_checks: tuple[str, ...]
    verified_live: tuple[str, ...]
    verified_pregame_as_of: tuple[str, ...]
    verified_by_tests: tuple[str, ...]
    unverified: tuple[str, ...]
    unsupported: tuple[str, ...]
    recommendation: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HistoricalProjectionAuditError(f"{field} must be a mapping; observed {type(value).__name__}")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise HistoricalProjectionAuditError(f"{field} must be a list; observed {type(value).__name__}")
    return value


def _integer(value: Any, field: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise HistoricalProjectionAuditError(f"{field} must be an integer >= {minimum}; observed {value!r}")
    return value


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
        raise HistoricalProjectionAuditError(f"{field} must be a finite number; observed {value!r}")
    return float(value)


def _value_status(value: float | None) -> str:
    if value is None:
        return "missing"
    if value == 0:
        return "explicit_zero"
    if value < 0:
        return "negative"
    return "positive"


def _as_of_metadata_present(stat: Mapping[str, Any]) -> bool:
    keys = {str(key).casefold() for key in stat}
    return bool(keys.intersection({"asof", "as_of", "created", "createddate", "updated", "updateddate", "timestamp", "revision"}))


def parse_historical_player_page(response: Mapping[str, Any], *, season: int, week: int, allow_other_weeks: bool = False) -> tuple[HistoricalPlayerWeek, ...]:
    """Match raw weekly projection/actual records without applying model policy."""

    players = _list(response.get("players"), "historical response.players")
    result: list[HistoricalPlayerWeek] = []
    seen_players: set[int] = set()
    for index, value in enumerate(players):
        wrapper = _mapping(value, f"players[{index}]")
        player_id = wrapper.get("id")
        if isinstance(player_id, bool) or not isinstance(player_id, int) or player_id == 0:
            raise HistoricalProjectionAuditError(f"players[{index}].id must be a nonzero integer")
        if player_id in seen_players:
            raise HistoricalProjectionAuditError(f"historical page duplicates player_id={player_id}")
        seen_players.add(player_id)
        player = _mapping(wrapper.get("player"), f"player_id={player_id}.player")
        if player.get("id") != player_id:
            raise HistoricalProjectionAuditError(f"player_id={player_id}: wrapper and player IDs disagree")
        projection: float | None = None
        actual: float | None = None
        projection_seen = False
        actual_seen = False
        actual_breakdown = False
        as_of = False
        for stat_index, stat_value in enumerate(_list(player.get("stats"), f"player_id={player_id}.stats")):
            stat = _mapping(stat_value, f"player_id={player_id}.stats[{stat_index}]")
            split = stat.get("statSplitTypeId")
            scoring_period = stat.get("scoringPeriodId")
            stat_season = stat.get("seasonId")
            source = stat.get("statSourceId")
            if split != 1:
                continue
            if allow_other_weeks and (scoring_period != week or stat_season != season):
                continue
            if scoring_period != week or stat_season != season:
                raise HistoricalProjectionAuditError(
                    f"player_id={player_id}: weekly stat association is season={stat_season!r}, week={scoring_period!r}; requested season={season}, week={week}"
                )
            if source not in {0, 1}:
                raise HistoricalProjectionAuditError(f"player_id={player_id}: weekly stat has unsupported statSourceId={source!r}")
            as_of = as_of or _as_of_metadata_present(stat)
            if "appliedTotal" not in stat:
                raise HistoricalProjectionAuditError(f"player_id={player_id}, source={source}: weekly stat lacks appliedTotal")
            numeric = _finite(stat["appliedTotal"], f"player_id={player_id}, source={source}.appliedTotal")
            if source == 1:
                if projection_seen:
                    raise HistoricalProjectionAuditError(f"player_id={player_id}: duplicate historical projection record")
                projection_seen = True
                projection = numeric
            else:
                if actual_seen:
                    raise HistoricalProjectionAuditError(f"player_id={player_id}: duplicate historical actual record")
                actual_seen = True
                actual = numeric
                breakdown = stat.get("stats")
                if breakdown is not None and not isinstance(breakdown, Mapping):
                    raise HistoricalProjectionAuditError(f"player_id={player_id}: actual stats breakdown must be a mapping")
                actual_breakdown = bool(breakdown)
        result.append(HistoricalPlayerWeek(
            player_id=player_id,
            season=season,
            week=week,
            position_id=_integer(player.get("defaultPositionId"), f"player_id={player_id}.defaultPositionId"),
            pro_team_id=_integer(player.get("proTeamId"), f"player_id={player_id}.proTeamId", allow_zero=True),
            projection=projection,
            actual=actual,
            projection_status=_value_status(projection),
            actual_status=_value_status(actual),
            actual_stat_breakdown_present=actual_breakdown,
            as_of_metadata_present=as_of,
            provenance_class=PROVENANCE_CLASS,
        ))
    return tuple(result)


def retrieve_historical_week(request_page: Callable[[int, int], Mapping[str, Any]], *, season: int, week: int, page_size: int) -> tuple[tuple[HistoricalPlayerWeek, ...], tuple[int, ...], Mapping[str, Any]]:
    if page_size <= 0:
        raise HistoricalProjectionAuditError("page_size must be positive")
    offset = 0
    result: list[HistoricalPlayerWeek] = []
    seen: set[int] = set()
    lengths: list[int] = []
    first_response: Mapping[str, Any] | None = None
    while True:
        response = request_page(offset, page_size)
        if first_response is None:
            first_response = response
        page = parse_historical_player_page(response, season=season, week=week)
        if len(page) > page_size:
            raise HistoricalProjectionAuditError(f"season={season}, week={week}, offset={offset}: page exceeds requested limit")
        duplicates = [record.player_id for record in page if record.player_id in seen]
        if duplicates:
            raise HistoricalProjectionAuditError(f"season={season}, week={week}: duplicate player IDs across pages: {duplicates[:5]}")
        seen.update(record.player_id for record in page)
        result.extend(page)
        lengths.append(len(page))
        if len(page) < page_size:
            break
        offset += page_size
        if len(lengths) > 100:
            raise HistoricalProjectionAuditError("historical pagination exceeded 100 full pages")
    if not result or first_response is None:
        raise HistoricalProjectionAuditError(f"season={season}, week={week}: historical player universe is empty")
    return tuple(result), tuple(lengths), first_response


def scoring_signature(raw_league: Mapping[str, Any]) -> tuple[str, int]:
    scoring = _mapping(_mapping(raw_league.get("settings"), "settings").get("scoringSettings"), "settings.scoringSettings")
    items = _list(scoring.get("scoringItems"), "scoringSettings.scoringItems")
    normalized: list[dict[str, object]] = []
    stat_ids: set[int] = set()
    for index, value in enumerate(items):
        item = _mapping(value, f"scoringItems[{index}]")
        stat_id = _integer(item.get("statId"), f"scoringItems[{index}].statId")
        if stat_id in stat_ids:
            raise HistoricalProjectionAuditError(f"duplicate scoring statId={stat_id}")
        stat_ids.add(stat_id)
        normalized.append({
            "statId": stat_id,
            "points": _finite(item.get("points"), f"scoringItems[{index}].points"),
            "pointsOverrides": item.get("pointsOverrides"),
        })
    payload = json.dumps(sorted(normalized, key=lambda item: item["statId"]), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), len(items)


def _records_digest(records: Sequence[HistoricalPlayerWeek]) -> str:
    payload = [(record.player_id, record.projection, record.actual) for record in records]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()


def summarize_sample(records: Sequence[HistoricalPlayerWeek], *, season: int, week: int, regular_season_end: int, retrieved_at_utc: str, endpoint: str, scoring_signature_value: str, scoring_item_count: int, page_size: int, page_lengths: tuple[int, ...], repeat_first_page_stable: bool) -> SampleCoverage:
    if any(record.season != season or record.week != week for record in records):
        raise HistoricalProjectionAuditError("sample contains an incorrect season/week association")
    projection_counts = Counter(record.projection_status for record in records)
    actual_counts = Counter(record.actual_status for record in records)
    positions: dict[str, Counter[str]] = {}
    magnitudes: Counter[str] = Counter()
    for record in records:
        label = POSITION_LABELS.get(record.position_id, f"OTHER_{record.position_id}")
        positions.setdefault(label, Counter())[record.projection_status] += 1
        if record.projection is None:
            magnitudes["missing"] += 1
        elif record.projection == 0:
            magnitudes["zero"] += 1
        elif record.projection < 5:
            magnitudes["low_positive_lt_5"] += 1
        elif record.projection < 15:
            magnitudes["medium_5_to_lt_15"] += 1
        else:
            magnitudes["high_ge_15"] += 1
    matched = [record for record in records if record.projection is not None and record.actual is not None]
    exact = sum(math.isclose(record.projection or 0, record.actual or 0, abs_tol=1e-12) for record in matched)
    return SampleCoverage(
        season=season,
        week=week,
        phase="regular_season" if week <= regular_season_end else "postseason",
        retrieved_at_utc=retrieved_at_utc,
        endpoint=endpoint,
        view=PLAYER_INFO_VIEW,
        parameters={"scoringPeriodId": week, "page_size": page_size},
        scoring_signature=scoring_signature_value,
        scoring_item_count=scoring_item_count,
        player_count=len({record.player_id for record in records}),
        player_week_count=len(records),
        present_projections=len(records) - projection_counts["missing"],
        missing_projections=projection_counts["missing"],
        explicit_zero_projections=projection_counts["explicit_zero"],
        negative_projections=projection_counts["negative"],
        present_actuals=len(records) - actual_counts["missing"],
        missing_actuals=actual_counts["missing"],
        explicit_zero_actuals=actual_counts["explicit_zero"],
        matched_pairs=len(matched),
        missing_projection_with_actual=sum(record.projection is None and record.actual is not None for record in records),
        exact_projection_actual_matches=exact,
        hindsight_exact_tracking_signal="potential_hindsight_contamination" if len(matched) >= 5 and exact / len(matched) >= 0.95 else "no_obvious_exact_tracking_signal",
        actual_stat_breakdown_present=sum(record.actual_stat_breakdown_present for record in records),
        counts_by_position={key: dict(sorted(value.items())) for key, value in sorted(positions.items())},
        counts_by_projection_magnitude=dict(sorted(magnitudes.items())),
        pagination_page_lengths=page_lengths,
        repeat_first_page_stable=repeat_first_page_stable,
    )


def compare_playercard(records_by_week: Mapping[int, Sequence[HistoricalPlayerWeek]], response: Mapping[str, Any], *, season: int) -> dict[str, object]:
    requested_ids = {record.player_id for records in records_by_week.values() for record in records}
    parsed_by_week: dict[int, dict[int, HistoricalPlayerWeek]] = {week: {} for week in records_by_week}
    for week in records_by_week:
        parsed = parse_historical_player_page(response, season=season, week=week, allow_other_weeks=True)
        parsed_by_week[week] = {record.player_id: record for record in parsed if record.player_id in requested_ids}
    compared = agreements = missing = 0
    for week, records in records_by_week.items():
        for expected in records:
            observed = parsed_by_week[week].get(expected.player_id)
            if observed is None or (observed.projection is None and observed.actual is None):
                missing += 1
                continue
            compared += 1
            if (expected.projection, expected.actual) == (observed.projection, observed.actual):
                agreements += 1
    return {
        "season": season,
        "view": PLAYER_CARD_VIEW,
        "selected_player_count": len(requested_ids),
        "compared_player_weeks": compared,
        "exact_projection_actual_agreements": agreements,
        "missing_player_weeks": missing,
        "proves_pregame_timing": False,
    }


def _request_filters(offset: int, limit: int) -> dict[str, object]:
    return {"players": {"filterStatus": {"value": list(POOL_STATUSES)}, "limit": limit, "offset": offset, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}


def audit_live(settings: Settings, *, samples: Sequence[tuple[int, int]], page_size: int = 250, comparison_player_count: int = 25) -> HistoricalProjectionReport:
    if not samples or len(set(samples)) != len(samples):
        raise HistoricalProjectionAuditError("samples must be non-empty and unique")
    credentials = settings.credentials
    reports: list[SampleCoverage] = []
    all_records: dict[tuple[int, int], tuple[HistoricalPlayerWeek, ...]] = {}
    comparisons: list[dict[str, object]] = []
    signatures: dict[str, str] = {}
    for season in sorted({season for season, _ in samples}):
        league = League(league_id=settings.league_id, year=season, espn_s2=credentials.espn_s2 if credentials else None, swid=credentials.swid if credentials else None)
        raw_league = league.espn_request.get_league()
        signature, item_count = scoring_signature(raw_league)
        signatures[str(season)] = signature
        regular_end = _integer(_mapping(_mapping(raw_league.get("settings"), "settings").get("scheduleSettings"), "scheduleSettings").get("matchupPeriodCount"), "matchupPeriodCount")
        season_records: dict[int, tuple[HistoricalPlayerWeek, ...]] = {}
        first_ids: list[int] = []
        for sample_season, week in samples:
            if sample_season != season:
                continue
            _integer(week, "sample week")
            first_page_raw: Mapping[str, Any] | None = None

            def request_page(offset: int, limit: int) -> Mapping[str, Any]:
                nonlocal first_page_raw
                response = league.espn_request.league_get(
                    params={"view": PLAYER_INFO_VIEW, "scoringPeriodId": week},
                    headers={"x-fantasy-filter": json.dumps(_request_filters(offset, limit))},
                )
                if offset == 0:
                    first_page_raw = response
                return response

            retrieved_at = datetime.now(timezone.utc).isoformat()
            records, lengths, _ = retrieve_historical_week(request_page, season=season, week=week, page_size=page_size)
            if first_page_raw is None:
                raise HistoricalProjectionAuditError("first historical page was not captured")
            repeated_raw = league.espn_request.league_get(
                params={"view": PLAYER_INFO_VIEW, "scoringPeriodId": week},
                headers={"x-fantasy-filter": json.dumps(_request_filters(0, page_size))},
            )
            original_first = parse_historical_player_page(first_page_raw, season=season, week=week)
            repeated_first = parse_historical_player_page(repeated_raw, season=season, week=week)
            stable = _records_digest(original_first) == _records_digest(repeated_first)
            all_records[(season, week)] = records
            season_records[week] = records
            if not first_ids:
                first_ids = [record.player_id for record in records[:comparison_player_count]]
            reports.append(summarize_sample(
                records,
                season=season,
                week=week,
                regular_season_end=regular_end,
                retrieved_at_utc=retrieved_at,
                endpoint=league.espn_request.LEAGUE_ENDPOINT,
                scoring_signature_value=signature,
                scoring_item_count=item_count,
                page_size=page_size,
                page_lengths=lengths,
                repeat_first_page_stable=stable,
            ))
        if first_ids:
            card_response = league.espn_request.get_player_card(first_ids, league.finalScoringPeriod)
            selected = {week: tuple(record for record in records if record.player_id in set(first_ids)) for week, records in season_records.items()}
            comparisons.append(compare_playercard(selected, card_response, season=season))
    flat = [record for records in all_records.values() for record in records]
    return HistoricalProjectionReport(
        league_id=settings.league_id,
        retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
        samples=tuple(sorted(reports, key=lambda item: (item.season, item.week))),
        total_unique_player_seasons=len({(record.season, record.player_id) for record in flat}),
        total_player_weeks=len(flat),
        total_present_projections=sum(record.projection is not None for record in flat),
        total_missing_projections=sum(record.projection is None for record in flat),
        total_explicit_zero_projections=sum(record.projection == 0 for record in flat),
        total_present_actuals=sum(record.actual is not None for record in flat),
        total_missing_actuals=sum(record.actual is None for record in flat),
        total_matched_pairs=sum(record.projection is not None and record.actual is not None for record in flat),
        total_missing_projection_with_actual=sum(record.projection is None and record.actual is not None for record in flat),
        playercard_comparison=tuple(comparisons),
        scoring_signatures_by_season=signatures,
        temporal_provenance_class=PROVENANCE_CLASS,
        revision_checks=(
            "Repeated same-session first-page requests were compared exactly for every sample; stability is reported per sample and does not prove original timing.",
            "A bounded player subset was compared between kona_player_info and kona_playercard; agreement does not prove either value existed pregame.",
            "Projection/actual exact matches are counted as a leakage screen; isolated equality is not itself evidence of hindsight.",
            "Season-total and average records at scoringPeriodId=0 are excluded from weekly matching.",
        ),
        verified_live=(
            "Raw historical weekly records expose player ID, season, scoring week, position, pro team, stat source/split indicators, appliedTotal, and actual stat breakdowns.",
            "statSourceId=1 and statSplitTypeId=1 identify the returned weekly projection; statSourceId=0 and statSplitTypeId=1 identify the returned weekly actual.",
            "Missing projections, explicit zeros, finite negatives, actuals, and missing actuals remain distinct; no effective-zero policy is applied.",
        ),
        verified_pregame_as_of=(),
        verified_by_tests=(
            "Synthetic fixtures validate matching, missing/zero states, malformed associations, duplicates, source confusion, scoring mismatches, and temporal-classification safeguards.",
        ),
        unverified=(
            "No returned weekly stat record exposes a creation, update, revision, or original as-of timestamp.",
            "Repeated retrieval and cross-view agreement establish current response stability only, not that the value existed before kickoff.",
            "Current historical scoring settings may not reproduce the configuration in force at the original game time if a league manager changed scoring retroactively.",
            "The returned player pool is conditioned by ESPN's present historical endpoint behavior and may omit players outside that candidate universe.",
        ),
        unsupported=(
            "The investigated ESPN responses expose no authenticated projection vintages or forecast-horizon labels.",
            "No verified endpoint provides a sequence of one-week-ahead and multiweek-ahead historical projection revisions.",
        ),
        recommendation="Do not use these returned historical projections as the primary genuine-pregame calibration sample without independent timestamped corroboration. Begin explicit prospective ESPN snapshot capture only if separately approved; retain historical actuals and unverified projections as separate research evidence.",
    )


def render_summary(report: HistoricalProjectionReport) -> str:
    lines = [
        "M0.5 historical ESPN projection audit",
        f"Samples: {len(report.samples)}; player-weeks: {report.total_player_weeks}; unique player-seasons: {report.total_unique_player_seasons}",
        f"Projections present={report.total_present_projections}, missing={report.total_missing_projections}, explicit zero={report.total_explicit_zero_projections}",
        f"Actuals present={report.total_present_actuals}, missing={report.total_missing_actuals}; matched pairs={report.total_matched_pairs}",
        f"Temporal provenance: {report.temporal_provenance_class}",
        "",
    ]
    for sample in report.samples:
        lines.append(f"- {sample.season} week {sample.week} ({sample.phase}): players={sample.player_count}, matched={sample.matched_pairs}, projection missing/zero={sample.missing_projections}/{sample.explicit_zero_projections}, actual missing={sample.missing_actuals}, repeat stable={sample.repeat_first_page_stable}")
    lines.extend(("", "Recommendation:", report.recommendation))
    return "\n".join(lines)


def _sample(value: str) -> tuple[int, int]:
    try:
        season_text, week_text = value.split(":", 1)
        season, week = int(season_text), int(week_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("sample must use SEASON:WEEK, for example 2025:8") from exc
    if season < 2000 or week < 1:
        raise argparse.ArgumentTypeError("sample season must be >= 2000 and week must be positive")
    return season, week


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the bounded read-only M0.5 historical projection audit.")
    parser.add_argument("--sample", action="append", type=_sample, required=True, help="Historical SEASON:WEEK; repeat for a bounded sample.")
    parser.add_argument("--page-size", type=int, default=250)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        report = audit_live(settings, samples=args.sample, page_size=args.page_size)
    except (SettingsError, HistoricalProjectionAuditError, ESPNAccessDenied, ESPNInvalidLeague, ESPNUnknownError, RequestException) as exc:
        LOGGER.error("M0.5 historical projection audit failed: %s", exc)
        return 2
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True) if args.json else render_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
