"""Development-only k sensitivity for method D; no 2025/2026 evaluation."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from research.build_history import read_rows, write_json
from research.validate_residuals import Empirical, Metrics, Pools, band, time_key

KS = (250, 500, 750, 1000)
YEARS = (2020, 2021, 2022, 2023, 2024)


def development_folds(rows):
    # Filter before constructing training or evaluation folds.
    development = [r for r in rows if 2018 <= r["season"] <= 2024]
    for year in YEARS:
        training = [r for r in development if r["season"] < year]
        evaluation = [r for r in development if r["season"] == year]
        if not training or not evaluation:
            raise ValueError(f"Missing training/evaluation observations for {year}")
        yield year, training, evaluation


def neighborhood(pool, row):
    if row["season"] not in YEARS or pool.latest >= time_key(row):
        raise ValueError("Sensitivity is restricted to chronological 2020–2024 holdouts")
    return pool.local(row["position"], row["projection_points"], max(KS))


def render(metrics):
    sections=[]
    for mode in ("centered", "raw"):
        for group in ("overall",)+tuple("season:"+str(y) for y in YEARS):
            chosen=[r for r in metrics if r["mode"]==mode and r["group"]==group]
            body="".join(f"<tr><td>{r['k']}</td><td>{r['n']:,}</td><td>{r['crps']:.5f}</td>"+
                "".join(f"<td>{100*r[str(l)+'_covered']:.2f}%</td><td>{r[str(l)+'_width']:.3f}</td>" for l in (50,80,90,95))+"</tr>" for r in chosen)
            sections.append(f"<h2>{mode} · {group}</h2><div class='scroll'><table><tr><th>k</th><th>N</th><th>CRPS</th>"+
                "".join(f"<th>{l}% coverage</th><th>Width</th>" for l in (50,80,90,95))+"</tr>"+body+"</table></div>")
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Development-only locality sensitivity</title>
<style>body{font:16px system-ui;background:#101925;color:#dce6f2;padding:30px;max-width:1400px;margin:auto}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%}th,td{text-align:right;padding:10px;border-bottom:1px solid #344258}h2{margin-top:36px}</style>
<h1>Method D: development-only locality sensitivity</h1><p>Fixed k grid: 250, 500, 750, 1000. Expanding annual holdouts: 2020–2024. No 2025 or 2026 observations enter training or evaluation. This tests stability, not a search for the smallest score.</p>
<p>Primary: mean-centered residuals preserving ESPN's expectation. Secondary: raw residuals. No recency weighting or sample changes. Coverage targets are the column labels; widths and CRPS are fantasy points.</p>"""+"".join(sections)+"</html>"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=Path("outputs/history"))
    parser.add_argument("--output",type=Path,default=Path("outputs/locality_sensitivity"))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    source=args.source/"initial_sample.jsonl.gz"
    manifest=json.loads((args.source/"manifest.json").read_text())
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if digest!=manifest["artifacts"][source.name]:
        raise ValueError("Frozen source checksum mismatch")
    rows=[r for r in read_rows(source) if 2018 <= r["season"] <= 2024]
    if any(not r["initial_sample"] or r["sample_exclusions"] for r in rows):
        raise ValueError("Source is not the frozen initial sample")
    protocol=dict(method="D",ks=KS,evaluation_seasons=YEARS,training_start=2018,
        forbidden_seasons=[2025,2026],source_sha256=digest,scoring_version=manifest["scoring_version"],
        primary_mode="centered",secondary_mode="raw",recency=False,
        purpose="Stability assessment; no automatic argmin selection",
        implementation_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
                               ("research/check_locality.py","research/validate_residuals.py")})
    write_json(args.output/"protocol.json",protocol)
    aggregate=defaultdict(Metrics)
    radii=defaultdict(float)
    audit=[]
    for year,training,evaluation in development_folds(rows):
        pool=Pools(training)
        audit.append(dict(season=year,training_n=len(training),evaluation_n=len(evaluation),
                          latest_training=pool.latest,earliest_evaluation=min(time_key(r) for r in evaluation),
                          training_by_position={p:len(v) for p,v in pool.groups.items() if p!="all"}))
        for row in evaluation:
            nearest=neighborhood(pool,row)
            groups=("overall","season:"+str(year),"position:"+row["position"],
                    "season_position:"+str(year)+":"+row["position"],
                    "projection:"+band(row["projection_points"]),
                    "week:"+str(year)+":"+str(row["week"]))
            for k in KS:
                selected=nearest[:k]
                empirical=Empirical([r["residual"] for r in selected])
                radius=max(abs(r["projection_points"]-row["projection_points"]) for r in selected)
                for centered in (True,False):
                    mode="centered" if centered else "raw"
                    result=empirical.evaluate(row["residual"],centered)
                    for group in groups:
                        key=(mode,k,group)
                        aggregate[key].add(result)
                        radii[key]+=radius
        print(f"Completed {year}: {len(training):,} training, {len(evaluation):,} held out, all four k values",flush=True)
    metrics=[dict(mode=m,k=k,group=g,mean_neighbor_radius=radii[m,k,g]/v.n,**v.result())
             for (m,k,g),v in sorted(aggregate.items())]
    results=dict(protocol=protocol,folds=audit,metrics=metrics)
    write_json(args.output/"results.json",results)
    (args.output/"comparison.html").write_text(render(metrics),encoding="utf-8")
    for r in metrics:
        if r["group"]=="overall":print(json.dumps(r),flush=True)


if __name__=="__main__":
    main()
