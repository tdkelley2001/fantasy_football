"""Canonical historical player-weeks and an explicitly separate modeling policy.

No network, credentials, or file writes. Unknown evidence is never a zero or DNP.
"""
from collections import Counter, defaultdict
import hashlib
import json
import math
import statistics

SCHEMA_VERSION = 1
SAMPLE_VERSION = "completed-positive-played-v1"
POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}
# Actual attempts, receptions/targets, sacks taken, fumbles, kicks, tackles,
# and return yards/counts prove on-field activity when the GP field is absent.
ACTIVITY_STATS = ("0", "23", "41", "58", "64", "68", "84", "87", "109", "114", "115", "118")


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def scoring_version(items):
    validate_rules(items)
    return hashlib.sha256(json.dumps(sorted(items, key=lambda x: x["statId"]),
                                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_rules(items):
    if not items or len({i["statId"] for i in items}) != len(items):
        raise ValueError("Scoring items must be nonempty and have unique stat IDs")
    for item in items:
        if item.get("isReverseItem") or not finite(item.get("points")):
            raise ValueError("Only finite additive scoring rules are supported")
        if any(not finite(v) for v in item.get("pointsOverrides", {}).values()):
            raise ValueError("Invalid scoring override")


def score_record(record, position, items):
    stats = record.get("stats")
    if not isinstance(stats, dict) or any(not finite(v) for v in stats.values()):
        return None
    return sum(stats.get(str(i["statId"]), 0) *
               i.get("pointsOverrides", {}).get(str(position), i["points"]) for i in items)


def resolve_records(records, position, items):
    """Preserve every input, collapse exact duplicates, never choose a conflict."""
    unique = {json.dumps(r, sort_keys=True, separators=(",", ":")): r for r in records}
    if not unique:
        return "missing", None, None
    if len(unique) > 1:
        return "conflicting", None, None
    record = next(iter(unique.values()))
    points = score_record(record, position, items)
    return ("valid" if points is not None else "invalid"), points, record


def index_games(events, year):
    """Index regular-season events, retaining duplicate/team schedule ambiguity."""
    result = defaultdict(dict)
    for event in events:
        if event.get("season", {}).get("year") != year or event.get("season", {}).get("type") != 2:
            continue
        week = event.get("week", {}).get("number")
        for competition in event.get("competitions", []):
            status = competition.get("status", event.get("status", {})).get("type", {})
            name = status.get("name", "UNKNOWN")
            state = ("cancelled" if name == "STATUS_CANCELED" or name == "STATUS_CANCELLED"
                     else "completed" if status.get("completed") and name in
                     {"STATUS_FINAL", "STATUS_FINAL_OVERTIME", "STATUS_FINAL_OVERTIME_2"}
                     else "not_completed")
            teams = [int(c["team"]["id"]) for c in competition.get("competitors", []) if "team" in c]
            for team in teams:
                result[team, week][str(event["id"])] = dict(
                    id=str(event["id"]), status=state, espn_status=name,
                    date=event.get("date"), opponents=[t for t in teams if t != team])
    return {k: list(v.values()) for k, v in result.items()}


def sample_exclusions(row):
    reasons = []
    if row["game_status"] != "completed":
        reasons.append("game_" + row["game_status"])
    if row["team_evidence"] not in {"weekly_actual", "weekly_projection", "dst_identity"}:
        reasons.append("team_not_directly_observed")
    if row["participation_status"] != "played":
        reasons.append("participation_" + row["participation_status"])
    for source in ("projection", "actual"):
        if row[source + "_status"] != "valid":
            reasons.append(source + "_" + row[source + "_status"])
    if row["projection_points"] is not None and row["projection_points"] <= 0:
        reasons.append("nonpositive_projection")
    if row["position"] not in POSITIONS.values():
        reasons.append("unmapped_position")
    if row["participation_conflict"]:
        reasons.append("participation_conflict")
    if row["team_conflict"]:
        reasons.append("team_conflict")
    return reasons


def canonical_rows(players, events, year, items, provenance):
    """Full returned player pool × regular-season weeks, including absent records.

    This universe includes retired/unattached identities, which remain unknown.
    It is not a claim that every returned player was on an NFL roster that year.
    """
    version = scoring_version(items)
    games = index_games(events, year)
    weeks = range(1, 18 if year <= 2020 else 19)
    if not games or set(w for _, w in games) != set(weeks):
        raise ValueError(f"Incomplete regular-season schedule for {year}")
    known_teams = {t for t, _ in games}
    expected_games = 16 if year <= 2020 else 17
    appearances = Counter(t for (t, _), matches in games.items() for _ in matches)
    if len(known_teams) != 32 or any(n != expected_games for n in appearances.values()):
        raise ValueError(f"Incomplete or ambiguous team schedule for {year}: {dict(appearances)}")
    for player in sorted(players, key=lambda p: p["id"]):
        pid, position = player["id"], player.get("defaultPositionId")
        grouped = defaultdict(list)
        for stat in player.get("stats", []):
            if (stat.get("seasonId") == year and stat.get("statSplitTypeId") == 1
                    and stat.get("statSourceId") in (0, 1) and stat.get("scoringPeriodId") in weeks):
                grouped[stat["scoringPeriodId"], stat["statSourceId"]].append(stat)
        # Only use agreement between earlier and later observed teams to infer gaps.
        observed = {}
        for week in weeks:
            teams = {s.get("proTeamId") for s in grouped[week, 0] + grouped[week, 1]
                     if s.get("proTeamId") in known_teams}
            if len(teams) == 1:
                observed[week] = next(iter(teams))
        for week in weeks:
            actuals, projections = grouped[week, 0], grouped[week, 1]
            ast, av, actual = resolve_records(actuals, position, items)
            pst, pv, projection = resolve_records(projections, position, items)
            direct_teams = {r.get("proTeamId") for r in (actual, projection)
                            if r and r.get("proTeamId") in known_teams}
            team_conflict = len(direct_teams) > 1
            team, team_evidence = None, "unknown"
            for record, label in ((actual, "weekly_actual"), (projection, "weekly_projection")):
                if record and record.get("proTeamId") in known_teams:
                    team, team_evidence = record["proTeamId"], label
                    break
            if team is None and position == 16 and player.get("proTeamId") in known_teams:
                team, team_evidence = player["proTeamId"], "dst_identity"
            if team is None:
                before = [w for w in observed if w < week]
                after = [w for w in observed if w > week]
                if before and after and observed[max(before)] == observed[min(after)]:
                    team, team_evidence = observed[max(before)], "bracketed_same_team_inference"
            matches = games.get((team, week), [])
            game_status = ("unknown" if team is None else "bye" if not matches else
                           matches[0]["status"] if len(matches) == 1 else "conflicting")
            # An absent schedule entry with only inferred team evidence is an inferred bye.
            if game_status == "bye" and team_evidence == "bracketed_same_team_inference":
                game_status = "inferred_bye"
            gp = (actual or {}).get("stats", {}).get("210") if ast == "valid" else None
            participation = "unknown"
            participation_evidence = "none"
            activity = ast == "valid" and any(actual["stats"].get(k, 0) != 0 for k in ACTIVITY_STATS)
            if finite(gp):
                participation = "played" if gp == 1 else "did_not_play" if gp == 0 else "conflicting"
                participation_evidence = "actual_games_played"
            elif activity:
                participation, participation_evidence = "played", "actual_recorded_activity"
            # D/ST is a team unit: a final game plus a valid nonempty actual establishes appearance.
            if position == 16 and ast == "valid" and actual.get("stats") and game_status == "completed":
                participation = "played"
                participation_evidence = "dst_completed_game_with_actual"
            conflict = ((participation == "played" and game_status in {"bye", "inferred_bye", "cancelled"})
                        or (gp == 0 and activity))
            row = dict(schema_version=SCHEMA_VERSION, season=year, week=week, player_id=pid,
                       name=player.get("fullName"), position=POSITIONS.get(position, "OTHER"),
                       default_position_id=position, eligible_slots=player.get("eligibleSlots", []),
                       historical_team_id=team, team_evidence=team_evidence,
                       team_conflict=team_conflict,
                       game_status=game_status, games=matches, participation_status=participation,
                       participation_evidence=participation_evidence,
                       games_played=gp, participation_conflict=conflict,
                       inactive_status="unknown",  # GP=0 cannot distinguish inactive from active DNP.
                       projection_status=pst, actual_status=ast,
                       projection_points=pv, actual_points=av,
                       residual=av-pv if av is not None and pv is not None else None,
                       zero_projection=pv == 0 if pv is not None else None,
                       zero_actual=av == 0 if av is not None else None,
                       raw_actual_records=actuals, raw_projection_records=projections,
                       exact_duplicate_count=len(actuals)+len(projections)-
                       len({json.dumps(r, sort_keys=True) for r in actuals})-
                       len({json.dumps(r, sort_keys=True) for r in projections}),
                       scoring_version=version, provenance=provenance,
                       forecast_generated_at=None, sample_version=SAMPLE_VERSION)
            row["quality_flags"] = [f"projection_{pst}", f"actual_{ast}",
                                    f"game_{game_status}", f"participation_{participation}"]
            row["quality_flags"] += [k for k in ("zero_projection", "zero_actual", "participation_conflict", "team_conflict") if row[k]]
            row["sample_exclusions"] = sample_exclusions(row)
            row["initial_sample"] = not row["sample_exclusions"]
            yield row


def quantile(values, q):
    ordered = sorted(values)
    at = (len(ordered)-1)*q
    lo = int(at)
    return ordered[lo] + (ordered[min(lo+1, len(ordered)-1)]-ordered[lo])*(at-lo)


def distribution(rows):
    values = [r["residual"] for r in rows]
    if not values:
        return {"n": 0}
    mean = statistics.mean(values)
    variance = statistics.mean((v-mean)**2 for v in values)
    edges = [-math.inf, -20, -15, -10, -5, 0, 5, 10, 15, 20, math.inf]
    histogram = []
    for left, right in zip(edges, edges[1:]):
        histogram.append(dict(lower=left if math.isfinite(left) else None,
                              upper=right if math.isfinite(right) else None,
                              count=sum(left <= v < right for v in values)))
    return dict(n=len(values), players=len({r["player_id"] for r in rows}),
                mean_projection=statistics.mean(r["projection_points"] for r in rows),
                mean_actual=statistics.mean(r["actual_points"] for r in rows),
                mean_error=mean, median_error=statistics.median(values),
                sd=statistics.stdev(values) if len(values)>1 else None,
                mae=statistics.mean(abs(v) for v in values),
                rmse=math.sqrt(statistics.mean(v*v for v in values)),
                skewness=statistics.mean((v-mean)**3 for v in values)/variance**1.5 if variance else None,
                excess_kurtosis=statistics.mean((v-mean)**4 for v in values)/variance**2-3 if variance else None,
                quantiles={str(q):quantile(values,q) for q in (.01,.05,.25,.5,.75,.95,.99)},
                minimum=min(values), maximum=max(values),
                zero_actual_rate=sum(r["zero_actual"] for r in rows)/len(rows),
                negative_actual_rate=sum(r["actual_points"]<0 for r in rows)/len(rows),
                histogram=histogram)


def diagnose(rows):
    counts = {k: Counter() for k in ("game_status", "participation_status", "participation_evidence", "inactive_status",
                                    "projection_status", "actual_status", "sample_exclusions", "quality_flags")}
    sample, by_year, by_position, by_band, by_position_band = [], defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    total = 0
    for r in rows:
        total += 1
        for k,c in counts.items():
            c.update(r[k] if k in {"sample_exclusions", "quality_flags"} else [r[k]])
        if not r["initial_sample"]:
            continue
        p = r["projection_points"]
        band = "(0,5)" if p<5 else "[5,10)" if p<10 else "[10,15)" if p<15 else "[15,20)" if p<20 else "[20,inf)"
        compact = {k:r[k] for k in ("player_id", "projection_points", "actual_points", "residual", "zero_actual")}
        sample.append(compact)
        by_year[str(r["season"])].append(compact)
        by_position[r["position"]].append(compact)
        by_band[band].append(compact)
        by_position_band[r["position"]+" "+band].append(compact)
    return dict(canonical_rows=total, sample_version=SAMPLE_VERSION, counts=counts,
                overall=distribution(sample), by_season={k:distribution(v) for k,v in sorted(by_year.items())},
                by_position={k:distribution(v) for k,v in sorted(by_position.items())},
                by_projection_band={k:distribution(v) for k,v in sorted(by_band.items())},
                by_position_projection_band={k:distribution(v) for k,v in sorted(by_position_band.items())})
