"""Read-only ESPN data-availability research; not an app ingestion pipeline.

Run from the repository root: python -m research.espn_history_probe
Writes summaries only to outputs/espn_history_probe; never persists credentials,
request headers, member profiles, or raw league responses.
"""
from collections import Counter
from datetime import datetime, timezone
import json
import argparse
from pathlib import Path
import time

from fantasy_projection.config import load_config
from fantasy_projection.espn import BASE, EspnClient, find_player_nodes

OUT = Path("outputs/espn_history_probe")


class Probe:
    def __init__(self, name="requests"):
        self.config = load_config()
        self.client = EspnClient(self.config)
        self.results = []
        self.name = name
        OUT.mkdir(parents=True, exist_ok=True)

    def fetch(self, label, season=None, *, view=None, week=None, filters=None,
              route="league", extra=None):
        season = self.config.season if season is None else season
        if route == "league":
            url = f"{BASE}/seasons/{season}/segments/0/leagues/{self.config.league_id}"
        elif route == "history":
            url = f"{BASE}/leagueHistory/{self.config.league_id}"
        elif route == "players":
            url = f"{BASE}/seasons/{season}/players"
        elif route == "season":
            url = f"{BASE}/seasons/{season}"
        elif route == "communication":
            url = f"{BASE}/seasons/{season}/segments/0/leagues/{self.config.league_id}/communication/"
        else:
            raise ValueError(route)
        params = dict(extra or {})
        if route == "history":
            params["seasonId"] = season
        if view is not None:
            params["view"] = view
        if week is not None:
            params["scoringPeriodId"] = week
        record = dict(label=label, requested_season=season, route=route, params=params,
                      filters=filters, retrieved_at=datetime.now(timezone.utc).isoformat())
        payload = None
        try:
            response = self.client.session.get(url, params=params,
                headers={"X-Fantasy-Filter": json.dumps(filters)} if filters else {}, timeout=25)
            record["http_status"] = response.status_code
            record["response_bytes"] = len(response.content)
            if response.status_code == 200:
                payload = response.json()
                record.update(summarize(payload))
            else:
                record["content_type"] = response.headers.get("Content-Type")
        except Exception as exc:
            record["error_type"] = type(exc).__name__
        self.results.append(record)
        (OUT / f"{self.name}.json").write_text(json.dumps(self.results, indent=2), encoding="utf-8")
        print(json.dumps({k: record[k] for k in ("label", "http_status", "player_count", "matching_pairs", "error_type") if k in record}), flush=True)
        time.sleep(.15)
        return payload, record


def player_nodes(payload):
    nodes = {}
    for player in find_player_nodes(payload):
        key = player.get("id")
        # Stat records also have id/proTeamId/stats fields. They are not players.
        if not isinstance(key, int) or not player.get("fullName"):
            continue
        if key not in nodes or len(player.get("stats", [])) > len(nodes[key].get("stats", [])):
            nodes[key] = player
    return nodes


def summarize(payload):
    root = payload[0] if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "seasonId" in payload[0] else payload
    result = {"shape": type(payload).__name__}
    if isinstance(root, dict):
        result["root_keys"] = sorted(root)
        result["payload_season"] = root.get("seasonId")
        result["status"] = {k: v for k, v in root.get("status", {}).items()
                            if "season" in k.lower() or "scoring" in k.lower()}
        result["team_count"] = len(root.get("teams", []))
        result["schedule_count"] = len(root.get("schedule", []))
        result["draft_pick_count"] = len(root.get("draftDetail", {}).get("picks", []))
        result["topic_count"] = len(root.get("topics", []))
    nodes = player_nodes(payload)
    signatures = Counter()
    raw_keys = set()
    values = {}
    pairs = []
    result["player_count"] = len(nodes)
    result["player_keys"] = sorted(set().union(*(set(p) for p in nodes.values()))) if nodes else []
    for pid, player in nodes.items():
        for stat in player.get("stats", []):
            key = (stat.get("seasonId"), stat.get("scoringPeriodId"), stat.get("statSourceId"), stat.get("statSplitTypeId"))
            signatures[str(key)] += 1
            if key[0] is not None and key[1] and key[2] in (0,1) and key[3] == 1 and isinstance(stat.get("stats"), dict):
                raw_keys.add((pid,key[0],key[1],key[2]))
            if key[2] in (0, 1) and key[3] == 1 and key[1] and isinstance(stat.get("appliedTotal"), (int, float)):
                values[(pid, key[0], key[1], key[2])] = stat["appliedTotal"]
    for (pid, year, week, source), projection in values.items():
        if source == 1 and (pid, year, week, 0) in values:
            actual = values[pid, year, week, 0]
            pairs.append(dict(player_id=pid, name=nodes[pid].get("fullName"), position=nodes[pid].get("defaultPositionId"),
                              season=year, week=week, projection=projection, actual=actual, residual=actual-projection))
    result["stat_signatures"] = dict(signatures)
    result["matching_pairs"] = len(pairs)
    result["raw_matching_pairs"] = sum(source == 1 and (pid,year,week,0) in raw_keys for pid,year,week,source in raw_keys)
    result["pair_examples"] = sorted(pairs, key=lambda r: -r["projection"])[:6]
    result["pair_counts_by_season"] = dict(Counter(str(r["season"]) for r in pairs))
    result["stat_keys"] = sorted({k for p in nodes.values() for s in p.get("stats", []) for k in s})
    return result


def main():
    probe = Probe()
    pool_filter = {"players": {"limit": 100, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
    for year in (probe.config.season, 2025, 2024, 2023, 2018, 2017):
        probe.fetch(f"league_settings_{year}", year, view="mSettings")
    for year in (2025, 2024, 2023):
        probe.fetch(f"pool_{year}_week1", year, view="kona_player_info", week=1, filters=pool_filter)
    payload, _ = probe.fetch("current_pool_week1", view="kona_player_info", week=1, filters=pool_filter)
    nodes = player_nodes(payload)
    ids = [2330, 2580] + list(nodes)[:6]
    card_filter = {"players": {"filterIds": {"value": ids}, "filterStatsForTopScoringPeriodIds": {
        "value": 18, "additionalValue": [f"{source}{split}{year}" for year in (2010,2017,2018,2019,2023,2024,2025,probe.config.season) for source in (0,1) for split in (0,1)]}}}
    probe.fetch("cross_season_cards", view="kona_playercard", filters=card_filter)
    for year in (2025,2024):
        probe.fetch(f"scoreboard_{year}_week1", year, view=["mMatchupScore","mScoreboard"], week=1,
                    filters={"schedule":{"filterMatchupPeriodIds":{"value":[1]}}})
    for year in (2023,2017):
        probe.fetch(f"legacy_history_{year}", year, route="history", view="mSettings")
    for year in (2023,2018,2010):
        probe.fetch(f"global_players_{year}", year, route="players", view="players_wl",
                    filters={"filterActive":{"value":True}})


def deeper():
    probe = Probe("deeper")
    ids = [2330,2580,3139477,3918298]
    base = {"filterIds":{"value":ids}}
    explicit = [f"{source}1{year}{week}" for year in (2010,2017,2018,2019,2023,2024,2025)
                for week in (1,8) for source in (0,1)]
    probe.fetch("current_cards_explicit_ids",view="kona_playercard",filters={"players":{
        **base,"filterStatsForTopScoringPeriodIds":{"value":0,"additionalValue":explicit}}})
    probe.fetch("current_cards_season_filter",view="kona_playercard",filters={"players":{
        **base,"filterStatsForSeasonIds":{"value":[2023]},"filterStatsForSplitTypeIds":{"value":[1]},
        "filterStatsForSourceIds":{"value":[0,1]}}})
    for year in (2010,2017,2018,2023,2025):
        probe.fetch(f"global_weekly_{year}",year,route="players",view="kona_player_info",week=1,
                    filters={**base,"filterStatsForSourceIds":{"value":[0,1]},"filterStatsForSplitTypeIds":{"value":[1]}})
    for year in (2018,2023):
        probe.fetch(f"global_card_{year}",year,route="players",view="kona_playercard",filters={
            **base,"filterStatsForTopScoringPeriodIds":{"value":18,"additionalValue":[f"1120231",f"0120231"]}})
        probe.fetch(f"global_directory_stats_{year}",year,route="players",view="players_wl",week=1,filters={
            **base,"filterStatsForSourceIds":{"value":[0,1]},"filterStatsForSplitTypeIds":{"value":[1]}})
    probe.fetch("historical_cards_2025",2025,view="kona_playercard",filters={"players":{
        "filterIds":{"value":[3139477,3918298]},"filterStatsForTopScoringPeriodIds":{"value":18,
        "additionalValue":[f"112025{w}" for w in range(1,19)]}}})


def weekly_records(nodes, year):
    """Keep unambiguous weekly raw records; quarantine conflicting duplicates."""
    records = {}
    seen = set()
    ambiguous = set()
    duplicates = 0
    for pid, player in nodes.items():
        for stat in player.get("stats", []):
            if (stat.get("seasonId") != year or stat.get("statSourceId") not in (0,1)
                    or stat.get("statSplitTypeId") != 1
                    or not isinstance(stat.get("scoringPeriodId"), int)
                    or stat["scoringPeriodId"] <= 0
                    or not isinstance(stat.get("stats"), dict)):
                continue
            key = (pid,stat["scoringPeriodId"],stat["statSourceId"])
            duplicates += key in seen
            seen.add(key)
            if key in ambiguous:
                continue
            if key in records and records[key] != stat:
                ambiguous.add(key)
                del records[key]
                continue
            records[key] = stat
    return records, duplicates


def score_stat(stat, position, scoring_items):
    """Audit this league's additive per-stat rules; not a general scoring engine."""
    return sum(stat["stats"].get(str(item["statId"]),0) *
               item.get("pointsOverrides",{}).get(str(position),item["points"])
               for item in scoring_items)


def coverage():
    probe = Probe("coverage_requests")
    settings, _ = probe.fetch("current_scoring_rules",view="mSettings")
    items = settings["settings"]["scoringSettings"]["scoringItems"]
    scoring_rules = [{k:item[k] for k in ("statId","points","pointsOverrides","isReverseItem") if k in item} for item in items]
    report = dict(retrieved_at=datetime.now(timezone.utc).isoformat(), scoring_rules=scoring_rules, seasons=[], comparisons=[])
    filters = {"filterSlotIds":{"value":[0,2,4,6,16,17]},
               "filterStatsForSourceIds":{"value":[0,1]},"filterStatsForSplitTypeIds":{"value":[1]}}
    for year in range(2016,probe.config.season+1):
        payload, request = probe.fetch(f"global_full_coverage_{year}",year,route="players",view="kona_player_info",filters=filters)
        if payload is None:
            continue
        nodes = player_nodes(payload)
        records, duplicates = weekly_records(nodes,year)
        counts = Counter()
        by_position = {}
        by_week = {}
        for pid,week,source in records:
            if source != 1:
                continue
            pos = str(nodes[pid]["defaultPositionId"])
            pc = by_position.setdefault(pos,Counter())
            wc = by_week.setdefault(str(week),Counter())
            key = (pid,week,1)
            projection = score_stat(records[key],nodes[pid]["defaultPositionId"],items)
            for counter in (counts,pc,wc):
                counter["projection_records"] += 1
                counter["positive_projection_records"] += projection > 0
            actual = records.get((pid,week,0))
            if actual is None:
                for counter in (counts,pc,wc):
                    counter["missing_actual_records"] += 1
                    counter["positive_projection_missing_actual"] += projection > 0
                continue
            for counter in (counts,pc,wc):
                counter["paired_records"] += 1
                counter["positive_projection_pairs"] += projection > 0
                counter["empty_actual_statline_pairs"] += not bool(actual["stats"])
                counter["zero_projection_pairs"] += projection == 0
            actual_score = score_stat(actual,nodes[pid]["defaultPositionId"],items)
            counts["nonzero_actual_pairs"] += actual_score != 0
        entry = dict(season=year,players=len(nodes),actual_records=sum(k[2]==0 for k in records),
                     duplicates=duplicates,counts=dict(counts),by_position=by_position,by_week=by_week)
        report["seasons"].append(entry)
        if year in (2024,2025):
            historical, _ = probe.fetch(f"historical_scoring_{year}",year,view="mSettings")
            old_items = historical["settings"]["scoringSettings"]["scoringItems"]
            old_rules = [{k:i[k] for k in ("statId","points","pointsOverrides","isReverseItem") if k in i} for i in old_items]
            report.setdefault("historical_scoring_rules",{})[str(year)] = old_rules
            for week in (1,8,18):
                league, _ = probe.fetch(f"league_scoring_validation_{year}_{week}",year,view="kona_player_info",week=week,
                                       filters={"players":{"limit":2000,"sortPercOwned":{"sortPriority":1,"sortAsc":False}}})
                league_nodes = player_nodes(league)
                league_records,_ = weekly_records(league_nodes,year)
                errors=[]
                missing_global=[]
                checked=Counter()
                max_difference=0
                for key,stat in league_records.items():
                    if key[1] != week or not isinstance(stat.get("appliedTotal"),(int,float)):
                        continue
                    pid,_,source = key
                    if key not in records:
                        missing_global.append(dict(player_id=pid,source=source,points=stat["appliedTotal"],empty=not bool(stat.get("stats"))))
                        continue
                    rescored = score_stat(records[key],nodes[pid]["defaultPositionId"],old_items)
                    diff = abs(rescored-stat["appliedTotal"])
                    checked[str(nodes[pid]["defaultPositionId"])] += 1
                    max_difference=max(max_difference,diff)
                    if diff>1e-6:
                        errors.append(dict(player_id=pid,source=source,difference=diff,espn=stat["appliedTotal"],rescored=rescored))
                report["comparisons"].append(dict(season=year,week=week,checked_by_position=checked,
                    mismatches=len(errors),max_abs_difference=max_difference,examples=errors[:5],
                    missing_global_count=len(missing_global),missing_global_nonzero=sum(r["points"]!=0 for r in missing_global),
                    missing_global_nonempty=sum(not r["empty"] for r in missing_global),missing_examples=missing_global[:5]))
        (OUT / "coverage.json").write_text(json.dumps(report,indent=2),encoding="utf-8")


def context():
    probe = Probe("context_requests")
    report={"retrieved_at":datetime.now(timezone.utc).isoformat(),"seasons":[],"schedule_examples":[]}
    for year in (2024,2025,probe.config.season):
        entry={"season":year}
        draft, _ = probe.fetch(f"draft_{year}",year,view="mDraftDetail")
        entry["draft_picks"] = len((draft or {}).get("draftDetail",{}).get("picks",[]))
        roster_sets={}
        for week in (1,8):
            roster, _ = probe.fetch(f"roster_{year}_{week}",year,view="mRoster",week=week)
            roster_sets[week]={(team["id"],r["playerId"]) for team in (roster or {}).get("teams",[])
                               for r in team.get("roster",{}).get("entries",[])}
        entry["roster_memberships_changed_week1_to8"] = len(roster_sets[1] ^ roster_sets[8])
        board,_ = probe.fetch(f"boxscore_{year}_week1",year,view=["mMatchupScore","mScoreboard"],week=1,
                              filters={"schedule":{"filterMatchupPeriodIds":{"value":[1]}}})
        membership=set()
        slots=Counter()
        for game in (board or {}).get("schedule",[]):
            for side in ("home","away"):
                team=game.get(side) or {}
                for r in team.get("rosterForCurrentScoringPeriod",{}).get("entries",[]):
                    membership.add((team["teamId"],r["playerId"]))
                    slots[str(r.get("lineupSlotId"))]+=1
        entry["boxscore_week1_memberships"]=len(membership)
        entry["boxscore_week1_slot_counts"]=slots
        entry["mRoster_vs_boxscore_week1_difference"]=len(roster_sets[1]^membership)
        activity, request = probe.fetch(f"activity_{year}",year,route="communication",view="kona_league_communication",
            filters={"topics":{"filterType":{"value":["ACTIVITY_TRANSACTIONS"]},"limit":25,"limitPerMessageSet":{"value":25},
            "offset":0,"sortMessageDate":{"sortPriority":1,"sortAsc":False},"sortFor":{"sortPriority":2,"sortAsc":False},
            "filterIncludeMessageTypeIds":{"value":[178,180,179,239,181,244]}}})
        entry["activity_http_status"]=request.get("http_status")
        entry["activity_topics"]=len((activity or {}).get("topics",[]))
        tx,request=probe.fetch(f"transactions_view_{year}",year,view="mTransactions2",week=1)
        entry["transaction_rows"]=len((tx or {}).get("transactions",[]))
        entry["transaction_http_status"]=request.get("http_status")
        report["seasons"].append(entry)
    for year in (2018,2024,2025):
        schedule,_=probe.fetch(f"nfl_schedule_{year}",year,route="season",view="proTeamSchedules_wl")
        teams=(schedule or {}).get("settings",{}).get("proTeams",[])
        if not teams:
            teams=(schedule or {}).get("proTeams",[])
        games=[g for team in teams for rows in team.get("proGamesByScoringPeriod",{}).values() for g in rows]
        report["schedule_examples"].append(dict(season=year,pro_teams=len(teams),game_entries=len(games),
            sample=games[:1]))
    (OUT/'context.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


def quality():
    probe=Probe('quality_requests')
    settings,_=probe.fetch('quality_scoring',view='mSettings')
    items=settings['settings']['scoringSettings']['scoringItems']
    filters={"filterSlotIds":{"value":[0,2,4,6,16,17]},"filterStatsForSourceIds":{"value":[0,1]},"filterStatsForSplitTypeIds":{"value":[1]}}
    report={"seasons":[]}
    for year in (2018,2020,2022,2024,2025):
        payload,_=probe.fetch(f'quality_{year}',year,route='players',view='kona_player_info',filters=filters)
        nodes=player_nodes(payload)
        records={}
        duplicates=[]
        for pid,p in nodes.items():
            for s in p.get('stats',[]):
                if s.get('seasonId')!=year or s.get('statSplitTypeId')!=1 or not s.get('scoringPeriodId') or s.get('statSourceId') not in (0,1): continue
                key=(pid,s['scoringPeriodId'],s['statSourceId'])
                if key in records:
                    old=records[key]
                    duplicates.append(dict(player_id=pid,name=p['fullName'],week=key[1],source=key[2],
                        identical=old==s,old_score=score_stat(old,p['defaultPositionId'],items),new_score=score_stat(s,p['defaultPositionId'],items),
                        old_id=old.get('id'),new_id=s.get('id'),old_team=old.get('proTeamId'),new_team=s.get('proTeamId')))
                records[key]=s
        missing=[]
        for (pid,week,source),stat in records.items():
            if source==1 and (pid,week,0) not in records:
                value=score_stat(stat,nodes[pid]['defaultPositionId'],items)
                if value>0:
                    missing.append(dict(player_id=pid,name=nodes[pid]['fullName'],week=week,projection=value,position=nodes[pid]['defaultPositionId']))
        unusual=[dict(player_id=pid,name=p['fullName'],position=p['defaultPositionId'],slots=p['eligibleSlots'])
                 for pid,p in nodes.items() if p['defaultPositionId'] not in (1,2,3,4,5,16)]
        report['seasons'].append(dict(season=year,duplicates=duplicates,positive_projection_missing_actual=missing,unusual_position_players=unusual[:10]))
    (OUT/'quality.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


def transactions():
    probe = Probe("transaction_requests")
    report = {"retrieved_at": datetime.now(timezone.utc).isoformat(), "samples": []}
    for year in (2024, 2025):
        for week in (1, 8, 18):
            payload, request = probe.fetch(f"transactions_{year}_{week}", year,
                                           view="mTransactions2", week=week)
            rows = (payload or {}).get("transactions", [])
            report["samples"].append(dict(
                season=year, requested_week=week, http_status=request.get("http_status"),
                rows=len(rows), types=dict(Counter(r.get("type") for r in rows)),
                fields=sorted({k for r in rows for k in r}),
                periods=dict(Counter(str(r.get("scoringPeriodId")) for r in rows)),
                empty_items_by_type=dict(Counter(r.get("type") for r in rows if not r.get("items"))),
            ))
    (OUT / "transactions.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase",choices=["discovery","deeper","coverage","context","quality","transactions"],default="discovery")
    args=parser.parse_args()
    {"discovery":main,"deeper":deeper,"coverage":coverage,"context":context,"quality":quality,"transactions":transactions}[args.phase]()
