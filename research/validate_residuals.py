"""Chronological empirical-error comparison; never changes the frozen sample."""
import argparse
from bisect import bisect_left, bisect_right
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path

from research.build_history import read_rows, write_json

LEVELS = (.5, .8, .9, .95)
NEIGHBORS = 500
HALF_LIFE = 36  # Scoring-week index, including the unused 18th slot before 2021.


def time_key(row):
    return row["season"], row["week"]


class Empirical:
    """Exact discrete weighted CDF, quantiles and CRPS, with optional mean shift."""
    def __init__(self, values, weights=None):
        if not values:
            raise ValueError("Empty residual pool")
        weights = [1.] * len(values) if weights is None else weights
        if len(values) != len(weights) or any(not math.isfinite(w) or w <= 0 for w in weights):
            raise ValueError("Weights must be finite and positive")
        if any(not math.isfinite(v) for v in values):
            raise ValueError("Residuals must be finite")
        pairs = sorted(zip(values, weights))
        total = sum(weights)
        self.x = [x for x, _ in pairs]
        self.cdf, self.moment = [], []
        cumulative = moment = pair_term = squares = 0.
        for x, w in pairs:
            w /= total
            pair_term += w * (x*cumulative-moment)
            cumulative += w
            moment += w*x
            squares += w*w
            self.cdf.append(cumulative)
            self.moment.append(moment)
        self.mean = moment
        self.pair_term = pair_term  # One half E|X-X'|.
        self.ess = 1/squares

    def quantile(self, q):
        return self.x[min(bisect_left(self.cdf, q), len(self.x)-1)]

    def crps(self, observation, centered=True):
        y = observation + (self.mean if centered else 0)
        i = bisect_right(self.x, y)-1
        c = self.cdf[i] if i >= 0 else 0
        m = self.moment[i] if i >= 0 else 0
        return max(0., y*(2*c-1)+self.mean-2*m-self.pair_term)

    def evaluate(self, observation, centered=True):
        shift = self.mean if centered else 0
        result = dict(crps=self.crps(observation, centered), removed_mean=shift,
                      pool_size=len(self.x), effective_sample_size=self.ess)
        for level in LEVELS:
            alpha = (1-level)/2
            lo, hi = self.quantile(alpha)-shift, self.quantile(1-alpha)-shift
            label = str(round(level*100))
            result[label] = dict(lower=lo, upper=hi, covered=lo <= observation <= hi,
                                 width=hi-lo, below=observation < lo, above=observation > hi)
        return result


class Pools:
    def __init__(self, training):
        if not training:
            raise ValueError("No historical training records")
        self.training = training
        self.latest = max(time_key(r) for r in training)
        self.groups = {"all": sorted(training, key=lambda r: (r["projection_points"],time_key(r),r["player_id"]))}
        for pos in sorted({r["position"] for r in training}):
            self.groups[pos] = [r for r in self.groups["all"] if r["position"] == pos]
        self.projections = {k:[r["projection_points"] for r in v] for k,v in self.groups.items()}
        self.empirical = {k:Empirical([r["residual"] for r in v]) for k,v in self.groups.items()}

    def local(self, group, projection, neighbors=NEIGHBORS):
        rows, projections = self.groups[group], self.projections[group]
        if len(rows) < neighbors:
            raise ValueError(f"Insufficient {group} support for {neighbors} neighbors")
        at = bisect_left(projections, projection)
        left, right = max(0,at-neighbors), min(len(rows),at+neighbors)
        # Expand boundary ties so ordering does not depend on the search window.
        left = bisect_left(projections, projections[left])
        right = bisect_right(projections, projections[right-1])
        nearby = rows[left:right]
        return sorted(nearby, key=lambda r:(abs(r["projection_points"]-projection),
                                          r["projection_points"],time_key(r),r["player_id"]))[:neighbors]

    def forecast(self, model, row):
        if self.latest >= time_key(row):
            raise ValueError("Training includes forecast week or future observations")
        if model in ("A", "B"):
            return self.empirical["all" if model == "A" else row["position"]]
        selected = self.local("all" if model == "C" else row["position"],row["projection_points"])
        weights = None
        if model == "E":
            target = row["season"]*18+row["week"]
            weights = [2**(-(target-(r["season"]*18+r["week"]))/HALF_LIFE) for r in selected]
        elif model not in ("C", "D"):
            raise ValueError(model)
        return Empirical([r["residual"] for r in selected], weights)


class Metrics:
    def __init__(self):
        self.n = 0
        self.sums = defaultdict(float)

    def add(self, result):
        self.n += 1
        for k in ("crps", "removed_mean", "pool_size", "effective_sample_size"):
            self.sums[k] += result[k]
        for level in LEVELS:
            label = str(round(level*100))
            for k in ("covered", "width", "below", "above"):
                self.sums[label+"_"+k] += result[label][k]

    def result(self):
        return dict(n=self.n, **{k:v/self.n for k,v in self.sums.items()})


def band(projection):
    return "0–5" if projection<5 else "5–10" if projection<10 else "10–15" if projection<15 else "15–20" if projection<20 else "20+"


def folds(rows, protocol):
    if protocol == "season_holdout":
        for year in range(2020,2026):
            yield str(year), [r for r in rows if r["season"]<year], [r for r in rows if r["season"]==year]
    else:
        for week in range(1,19):
            cutoff=(2025,week)
            yield f"2025-W{week:02}", [r for r in rows if time_key(r)<cutoff], [r for r in rows if time_key(r)==cutoff]


def run_stage(rows, output, models, stage):
    aggregate = defaultdict(Metrics)
    fold_audit = []
    predictions = output / (stage+"_predictions.jsonl.gz")
    with gzip.open(predictions,"wt",encoding="utf-8") as out:
        for protocol in ("season_holdout", "weekly_2025"):
            for fold, train, test in folds(rows,protocol):
                pool = Pools(train)
                fold_audit.append(dict(protocol=protocol,fold=fold,training_n=len(train),test_n=len(test),
                                       training_latest=pool.latest,test_earliest=min(time_key(r) for r in test)))
                for row in test:
                    groups = ["overall", "season:"+str(row["season"]), "position:"+row["position"],
                              "projection:"+band(row["projection_points"]),
                              "position_projection:"+row["position"]+":"+band(row["projection_points"]),
                              "week:"+str(row["season"])+":"+str(row["week"])]
                    groups.append("development" if row["season"]<2025 else "final_2025")
                    for model in models:
                        empirical = pool.forecast(model,row)
                        for centered in (True,False):
                            mode="centered" if centered else "raw"
                            result=empirical.evaluate(row["residual"],centered)
                            for group in groups:
                                aggregate[protocol,mode,model,group].add(result)
                            out.write(json.dumps(dict(protocol=protocol,fold=fold,model=model,mode=mode,
                                season=row["season"],week=row["week"],player_id=row["player_id"],
                                position=row["position"],projection=row["projection_points"],actual=row["actual_points"],
                                residual=row["residual"],metrics=result),separators=(",",":"))+"\n")
                print(f"{stage} {protocol} {fold}: {len(train):,} earlier -> {len(test):,} held out",flush=True)
    summary=[dict(protocol=p,mode=c,model=m,group=g,**v.result()) for (p,c,m,g),v in sorted(aggregate.items())]
    write_json(output/(stage+".json"),dict(folds=fold_audit,metrics=summary))
    return summary


def render(metrics):
    sections=[]
    for protocol,group,title in (("season_holdout","development","2020–2024 expanding season holdouts"),
                                 ("season_holdout","final_2025","2025 season holdout"),
                                 ("weekly_2025","final_2025","2025 weekly walk-forward")):
        for mode in ("centered","raw"):
            rows=[r for r in metrics if r["protocol"]==protocol and r["group"]==group and r["mode"]==mode]
            body="".join("<tr><td>"+r["model"]+f"</td><td>{r['n']:,}</td><td>{r['crps']:.3f}</td>"+
                "".join(f"<td>{100*r[str(l)+'_covered']:.1f}%</td><td>{r[str(l)+'_width']:.2f}</td>" for l in (50,80,90,95))+"</tr>" for r in rows)
            sections.append(f"<h2>{title} · {mode}</h2><div class='scroll'><table><tr><th>Method</th><th>N</th><th>CRPS ↓</th>"+
                "".join(f"<th>{l}% coverage</th><th>Width</th>" for l in (50,80,90,95))+"</tr>"+body+"</table></div>")
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chronological residual validation</title><style>body{font:16px system-ui;background:#101925;color:#dce6f2;padding:30px;max-width:1450px;margin:auto}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:right;border-bottom:1px solid #344258}.scroll{overflow-x:auto}h2{margin-top:40px}</style>
<h1>Chronological residual validation</h1><p>A: universal · B: position · C: projection-local · D: position + projection-local · E: D + recency.</p>
<p>Local pools: nearest 500 historical projections. E: 36-scoring-week half-life. Centered results preserve ESPN's mean; raw results are a separate sensitivity check. A–D were run before E. No hyperparameters were tuned to the results.</p>
<p>Coverage should approach its stated level; smaller width is useful only alongside adequate coverage. Lower CRPS is better. Width and CRPS use fantasy points. 2025 weekly and annual results reuse the same outcomes and are not independent replications.</p>"""+"".join(sections)+"<p>This is conditional-on-participation archived-forecast validation, not a live as-of replay or a calibrated season simulator.</p></html>"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=Path("outputs/history"))
    parser.add_argument("--output",type=Path,default=Path("outputs/residual_validation"))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    source=args.source/"initial_sample.jsonl.gz"
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    manifest=json.loads((args.source/"manifest.json").read_text())
    if manifest["artifacts"][source.name]!=digest:
        raise ValueError("Frozen sample hash mismatch")
    rows=list(read_rows(source))
    if any(not r["initial_sample"] or r["sample_exclusions"] for r in rows):
        raise ValueError("Sample contains excluded rows")
    protocol=dict(neighbors=NEIGHBORS,half_life_scoring_weeks=HALF_LIFE,levels=LEVELS,
                  sample_sha256=digest,scoring_version=manifest["scoring_version"],
                  primary_mode="centered",secondary_mode="raw",development_seasons=list(range(2020,2025)),
                  final_season=2025,stages=["A-D","E"],quantiles="inverse weighted empirical CDF",
                  code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    write_json(args.output/"protocol.json",protocol)
    first=run_stage(rows,args.output,"ABCD","stage_abcd")
    second=run_stage(rows,args.output,"E","stage_e")
    combined=first+second
    write_json(args.output/"comparison.json",dict(protocol=protocol,metrics=combined))
    (args.output/"comparison.html").write_text(render(combined),encoding="utf-8")
    for r in combined:
        if r["protocol"]=="season_holdout" and r["group"]=="final_2025" and r["mode"]=="centered":
            print(json.dumps(r),flush=True)


if __name__=="__main__":
    main()
