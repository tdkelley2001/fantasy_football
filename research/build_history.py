"""Fetch frozen ESPN sources, build canonical player-weeks, and diagnose V1 sample.

python -m research.build_history --output outputs/history
Rerunning reuses the frozen sources. Use a new output directory for a new snapshot.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import html
import json
from pathlib import Path

from fantasy_projection.config import load_config
from fantasy_projection.espn import BASE, EspnClient
from fantasy_projection.history import canonical_rows, diagnose, scoring_version


def write_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    temp.replace(path)


def frozen_source(session, root, label, url, params, filters=None, extract=None):
    path = root / (label + ".json.gz")
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    response = session.get(url, params=params, headers={"X-Fantasy-Filter":json.dumps(filters)} if filters else {}, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(f"ESPN source {label} returned HTTP {response.status_code}")
    payload = response.json()
    if extract:
        payload = extract(payload)
    envelope = dict(retrieved_at=datetime.now(timezone.utc).isoformat(), label=label,
                    params=params, payload=payload)
    temp = path.with_suffix(".tmp")
    with gzip.open(temp, "wt", encoding="utf-8") as f:
        json.dump(envelope, f, allow_nan=False)
    temp.replace(path)
    print(f"Saved source: {label}", flush=True)
    return envelope


def players_only(payload):
    if not isinstance(payload, list):
        raise ValueError("Expected global player array")
    players = [{k:p[k] for k in ("id", "fullName", "defaultPositionId", "eligibleSlots", "proTeamId", "stats") if k in p}
               for p in payload if isinstance(p.get("id"), int) and p.get("fullName")]
    if not players or len({p["id"] for p in players}) != len(players):
        raise ValueError("Missing or duplicate player identities")
    return players


def events_only(payload):
    return [{k:e[k] for k in ("id", "date", "season", "week", "status", "competitions") if k in e}
            for e in payload.get("events", [])]


def schedule_only(payload):
    games = {}
    for team in payload["settings"]["proTeams"]:
        for entries in team.get("proGamesByScoringPeriod", {}).values():
            for game in entries:
                games[str(game["id"])] = game
    return list(games.values())


def summary_event(payload):
    header = payload["header"]
    return dict(id=header["id"], season=header["season"], week={"number":header["week"]},
                competitions=header["competitions"])


def read_rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def report_html(report):
    overall = report["overall"]
    def table(groups):
        return "<table><thead><tr><th>Group</th><th>N</th><th>Mean error</th><th>SD</th><th>MAE</th><th>P05</th><th>P95</th></tr></thead><tbody>" + "".join(
            f"<tr><td>{html.escape(k)}</td><td>{v['n']:,}</td><td>{v['mean_error']:.2f}</td><td>{v['sd'] or 0:.2f}</td><td>{v['mae']:.2f}</td><td>{v['quantiles']['0.05']:.2f}</td><td>{v['quantiles']['0.95']:.2f}</td></tr>"
            for k,v in groups.items()) + "</tbody></table>"
    # Empirical error intervals: no fitted normal distribution or assumed independence.
    positions = report["by_position"]
    low = min(v["quantiles"]["0.01"] for v in positions.values())
    high = max(v["quantiles"]["0.99"] for v in positions.values())
    scale = lambda x: 110 + (x-low)/(high-low or 1)*630
    svg = f'<svg viewBox="0 0 800 {len(positions)*55+65}" role="img" aria-label="Residual ranges by position: first to ninety-ninth percentiles, thick fifth to ninety-fifth, dot median">'
    svg += f'<line x1="{scale(0)}" x2="{scale(0)}" y1="10" y2="{len(positions)*55}" stroke="#8291a6" stroke-dasharray="4"/>'
    for n,(pos,v) in enumerate(positions.items()):
        y=35+n*55; q=v["quantiles"]
        svg += f'<text x="15" y="{y+5}" fill="#dce6f2">{pos}</text>'
        for a,b,width in (("0.01","0.99",2),("0.05","0.95",9)):
            svg += f'<line x1="{scale(q[a])}" x2="{scale(q[b])}" y1="{y}" y2="{y}" stroke="#5fc9b5" stroke-width="{width}"/>'
        svg += f'<circle cx="{scale(q["0.5"])}" cy="{y}" r="5" fill="#fff"/>'
    svg += f'<text x="110" y="{len(positions)*55+35}" fill="#dce6f2">{low:.1f} points</text><text x="670" y="{len(positions)*55+35}" fill="#dce6f2">{high:.1f} points</text></svg>'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Historical scoring diagnostics</title><style>body{{font:16px system-ui;background:#101925;color:#dce6f2;max-width:1000px;margin:auto;padding:30px}}h1,h2{{color:white}}.cards{{display:flex;gap:20px;flex-wrap:wrap}}.card{{padding:20px;background:#1b293c;border-radius:12px}}b{{font-size:26px}}table{{width:100%;border-collapse:collapse;margin:24px 0}}th,td{{padding:12px;text-align:right;border-bottom:1px solid #344258}}th:first-child,td:first-child{{text-align:left}}svg{{width:100%}}.scroll{{overflow-x:auto}}</style>
<h1>Archived ESPN scoring errors</h1><p>Strict completed-game sample. Error = actual minus projection, rescored under current rules.</p>
<div class="cards"><div class="card">Canonical rows<br><b>{report['canonical_rows']:,}</b></div><div class="card">Initial sample<br><b>{overall['n']:,}</b></div><div class="card">Mean error<br><b>{overall['mean_error']:+.2f}</b></div><div class="card">Mean absolute error<br><b>{overall['mae']:.2f}</b></div></div>
<h2>How wide are scoring errors?</h2><p>Thin lines: P01–P99. Thick lines: P05–P95. White dots: median. Dashed line: zero error.</p>{svg}
<h2>Position detail</h2><div class="scroll">{table(positions)}</div><h2>Season stability</h2><div class="scroll">{table(report['by_season'])}</div>
<h2>Projection level</h2><div class="scroll">{table(report['by_projection_band'])}</div>
<p>This sample conditions on recorded participation and positive forecasts. It excludes uncertain availability and is not a full-season uncertainty model. These are descriptive statistics, not out-of-sample calibration. Forecast-generation timestamps are unknown. No excluded category has been reincorporated.</p></html>'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/history"))
    parser.add_argument("--start", type=int, default=2018)
    parser.add_argument("--end", type=int, default=2025)
    args=parser.parse_args()
    if not 2018 <= args.start <= args.end <= 2025:
        parser.error("This audited build supports completed seasons 2018–2025")
    root=args.output
    sources=root/"sources"
    sources.mkdir(parents=True,exist_ok=True)
    client=EspnClient(load_config())
    rules=frozen_source(client.session,sources,"scoring_rules",client.league_url,{"view":"mSettings"},
                        extract=lambda p:dict(season=p["seasonId"], items=p["settings"]["scoringSettings"]["scoringItems"]))
    items=rules["payload"]["items"]
    version=scoring_version(items)
    filters={"filterSlotIds":{"value":[0,2,4,6,16,17]},"filterStatsForSourceIds":{"value":[0,1]},"filterStatsForSplitTypeIds":{"value":[1]}}
    path=root/"player_weeks.jsonl.gz"
    temp=path.with_suffix(".tmp")
    manifest=dict(schema_version=1,created_at=datetime.now(timezone.utc).isoformat(),
                  scoring_version=version, scoring_season=rules["payload"]["season"],
                  scoring_retrieved_at=rules["retrieved_at"], seasons=[])
    canonical_digest=hashlib.sha256()
    with gzip.open(temp,"wt",encoding="utf-8") as out:
        for year in range(args.start,args.end+1):
            players=frozen_source(client.session,sources,f"players_{year}",f"{BASE}/seasons/{year}/players",
                                  {"view":"kona_player_info"},filters,players_only)
            calendars=[frozen_source(client.session,sources,f"calendar_{calendar}",
                       "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
                       {"dates":str(calendar),"limit":1000},extract=events_only)
                       for calendar in (year,year+1)]
            events={"payload":[e for c in calendars for e in c["payload"]],
                    "retrieved_at":[c["retrieved_at"] for c in calendars]}
            schedule=frozen_source(client.session,sources,f"schedule_{year}",f"{BASE}/seasons/{year}",
                                   {"view":"proTeamSchedules_wl"},extract=schedule_only)
            available={str(e["id"]) for e in events["payload"]
                       if e.get("season",{}).get("year")==year and e.get("season",{}).get("type")==2}
            expected={str(g["id"]) for g in schedule["payload"]}
            recovered=[]
            for game_id in sorted(expected-available):
                detail=frozen_source(client.session,sources,f"game_{game_id}",
                                     "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary",
                                     {"event":game_id},extract=summary_event)
                events["payload"].append(detail["payload"])
                recovered.append(dict(source=f"game_{game_id}",retrieved_at=detail["retrieved_at"]))
            final_ids={str(e["id"]) for e in events["payload"]
                       if e.get("season",{}).get("year")==year and e.get("season",{}).get("type")==2}
            if expected != final_ids:
                raise ValueError(f"Fantasy and scoreboard schedules disagree for {year}")
            provenance=dict(player_source=f"players_{year}",game_source=[f"calendar_{year}",f"calendar_{year+1}"],
                            player_retrieved_at=players["retrieved_at"],game_retrieved_at=events["retrieved_at"])
            provenance.update(schedule_source=f"schedule_{year}",recovered_game_sources=recovered)
            counts=0
            for row in canonical_rows(players["payload"],events["payload"],year,items,provenance):
                line=json.dumps(row,separators=(",",":"),allow_nan=False)+"\n"
                out.write(line)
                canonical_digest.update(line.encode("utf-8"))
                counts+=1
            manifest["seasons"].append(dict(season=year,players=len(players["payload"]),rows=counts))
            print(f"Classified {year}: {counts:,} player-weeks",flush=True)
    temp.replace(path)
    report=diagnose(read_rows(path))
    if not report["overall"]["n"]:
        raise ValueError("Initial sample is empty; investigate source/classification coverage")
    write_json(root/"diagnostics.json",report)
    (root/"diagnostics.html").write_text(report_html(report),encoding="utf-8")
    with gzip.open(root/"initial_sample.jsonl.gz","wt",encoding="utf-8") as out:
        for row in read_rows(path):
            if row["initial_sample"]:
                out.write(json.dumps({k:v for k,v in row.items() if not k.startswith("raw_")},separators=(",",":"))+"\n")
    manifest["source_sha256"]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.glob("*.json.gz")}
    manifest["canonical_content_sha256"]=canonical_digest.hexdigest()
    manifest["implementation_sha256"]={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in
                                       ("fantasy_projection/history.py","research/build_history.py")}
    manifest["artifacts"]={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
                           ("player_weeks.jsonl.gz","initial_sample.jsonl.gz","diagnostics.json","diagnostics.html")}
    write_json(root/"manifest.json",manifest)
    print(json.dumps(dict(canonical_rows=report["canonical_rows"],sample=report["overall"])),flush=True)


if __name__ == "__main__":
    main()
