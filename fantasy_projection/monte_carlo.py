"""Frozen V1 marginal scores and seeded season simulation over shared league rules."""
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict, OrderedDict
from dataclasses import asdict, replace
import gzip
import hashlib
import json
import math
from pathlib import Path
import random

from .history import POSITIONS, SAMPLE_VERSION, scoring_version
from .season import SeasonModelError, project_season, season_results

MODEL_VERSION = "empirical-residual-v1"
K = 500


class ResidualModel:
    def __init__(self, rows, scoring_hash, dataset_hash):
        self.scoring_hash, self.dataset_hash = scoring_hash, dataset_hash
        self.rows = defaultdict(list)
        seen = set()
        for r in rows:
            key = (r["season"], r["week"], r["player_id"])
            if key in seen:
                raise SeasonModelError("Duplicate historical residual observation.")
            seen.add(key)
            if (r.get("sample_version") != SAMPLE_VERSION or not r.get("initial_sample")
                    or r.get("sample_exclusions") or r["position"] not in POSITIONS.values()
                    or not math.isfinite(r["projection_points"]) or r["projection_points"] <= 0
                    or not math.isfinite(r["residual"])):
                raise SeasonModelError("Historical sample does not match the frozen V1 contract.")
            self.rows[r["position"]].append((r["projection_points"],r["season"],r["week"],r["player_id"],r["residual"]))
        for rows in self.rows.values():
            rows.sort(key=lambda r:r[:4])
        self._training = {}
        self._pools = OrderedDict()

    @classmethod
    def load(cls, root=None):
        root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
        spec_path = root/"research/v1_model_spec.json"
        source = root/"outputs/history/initial_sample.jsonl.gz"
        if not spec_path.is_file() or not source.is_file():
            raise SeasonModelError("Frozen V1 training data is missing. Build the historical dataset first.")
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        if (spec["model_version"] != MODEL_VERSION or spec["method"] != "D" or spec["neighbors"] != K
                or spec["recency_weighting"] or spec["weights"] != "uniform"
                or spec["centering"] != "subtract_selected_pool_arithmetic_mean" or spec["post_draw_clipping"]):
            raise SeasonModelError("Model specification does not match the implemented frozen V1.")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        snapshot = spec["initial_training_snapshot"]
        if digest != snapshot["sample_sha256"]:
            raise SeasonModelError("Historical dataset differs from the frozen V1 snapshot; version it explicitly.")
        with gzip.open(source,"rt",encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        if len(rows) != snapshot["rows"]:
            raise SeasonModelError("Historical sample row count differs from the frozen specification.")
        return cls(rows,snapshot["scoring_version"],digest)

    def pool(self, position, projection, cutoff):
        key = position, projection, cutoff
        if key in self._pools:
            self._pools.move_to_end(key)
            return self._pools[key]
        training_key = position, cutoff
        if training_key not in self._training:
            rows = [r for r in self.rows.get(position,[]) if r[1:3] < cutoff]
            self._training[training_key] = rows, [r[0] for r in rows]
        rows, values = self._training[training_key]
        if len(rows) < K:
            raise SeasonModelError(f"V1 requires 500 earlier historical observations for position {position}.")
        at = bisect_left(values, projection)
        lo, hi = max(0,at-K), min(len(rows),at+K)
        lo, hi = bisect_left(values,values[lo]), bisect_right(values,values[hi-1])
        nearest = sorted(rows[lo:hi],key=lambda r:(abs(r[0]-projection),*r[:4]))[:K]
        mean = math.fsum(r[4] for r in nearest)/K
        result = tuple(r[4]-mean for r in nearest)
        self._pools[key] = result
        if len(self._pools) > 4096:
            self._pools.popitem(last=False)
        return result


def player_draws(model, position, projection, *, season, week, player_id, cutoff, seed, simulations):
    """Keyed streams preserve shared draws across roster alternatives and ordering."""
    residuals = model.pool(position,projection,cutoff)
    key = json.dumps([MODEL_VERSION,seed,season,week,player_id],separators=(",",":"))
    rng = random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest(),"big"))
    return [projection+residuals[rng.randrange(K)] for _ in range(simulations)]


def percentiles(values):
    ordered = sorted(values)
    def q(probability):
        at = (len(ordered)-1)*probability
        lower = int(at)
        return ordered[lower]+(ordered[min(lower+1,len(ordered)-1)]-ordered[lower])*(at-lower)
    return {"p05":q(.05),"p50":q(.5),"p95":q(.95)}


def simulate_season(state, model, *, simulations=2000, seed=2026, effective_week=None, progress=None):
    if type(simulations) is not int or not 1 <= simulations <= 20000:
        raise SeasonModelError("Simulation count must be an integer from 1 to 20,000.")
    if type(seed) is not int or not 0 <= seed <= 2**32-1:
        raise SeasonModelError("Seed must be an integer from 0 to 4,294,967,295.")
    items = state.settings_payload.get("settings",{}).get("scoringSettings",{}).get("scoringItems")
    try:
        valid_scoring = scoring_version(items or []) == model.scoring_hash
    except (ValueError,KeyError,TypeError):
        valid_scoring = False
    if not valid_scoring:
        raise SeasonModelError("League scoring does not match the frozen historical scoring version.")
    # Known byes are structural zeroes, not random draws from low-projection pools.
    projections = {(r["player_id"],r["week"]):dict(r) for r in state.player_projections}
    for pid,weeks in state.player_bye_weeks.items():
        for week in weeks:
            projections[pid,week] = dict(player_id=pid,week=week,projected_points=0.)
    prepared = replace(state,player_projections=list(projections.values()))
    baseline = project_season(prepared,effective_week)
    missing = [d for d in baseline.diagnostics if d["starter"]]
    if missing:
        d=missing[0]
        raise SeasonModelError(f"Missing starter projection for {d['player_name']}, week {d['week']}; simulation requires coverage.")
    identities = {r["player_id"]:r for r in state.rosters+(state.baseline_rosters or [])+state.available_players}
    weekly = {(r["team_id"],r["week"]):[r["projected_points"]]*simulations
              for r in baseline.weekly_team_projections}
    for row in baseline.weekly_team_projections:
        if row["result_type"] == "PROJECTED":
            weekly[row["team_id"],row["week"]] = [0.]*simulations
    bye_starters = []
    nonpositive = []
    for row in baseline.optimal_lineups:
        pid,week = row["player_id"],row["week"]
        if week in state.player_bye_weeks.get(pid,()):
            bye_starters.append(dict(player_id=pid,week=week,team_id=row["team_id"]))
            continue
        projection = projections[pid,week]["projected_points"]
        position = POSITIONS.get(identities[pid].get("default_position_id"))
        if position is None:
            raise SeasonModelError(f"Unsupported V1 position for {identities[pid]['player_name']}.")
        if projection <= 0:
            nonpositive.append(dict(player_id=pid,week=week,projection=projection))
        draws = player_draws(model,position,projection,season=state.season,week=week,
            player_id=pid,cutoff=(state.season,state.current_week),seed=seed,simulations=simulations)
        scores = weekly[row["team_id"],week]
        for i,value in enumerate(draws):
            scores[i] += value
    stats = {t["team_id"]:dict(wins=[],ties=[],points=[],seed=[],finish=[],remaining=[],playoffs=0,titles=0)
             for t in state.teams}
    unresolved = {(r["team_id"],r["week"]) for r in baseline.weekly_team_projections if r["result_type"]=="PROJECTED"}
    for i in range(simulations):
        scores = [dict(r,projected_points=weekly[r["team_id"],r["week"]][i]) for r in baseline.weekly_team_projections]
        _,standings,_,final,_ = season_results(state,scores)
        for r in standings:
            s=stats[r["team_id"]]
            for field,key in (("wins","wins"),("ties","ties"),("points_for","points"),("seed","seed")):
                s[key].append(r[field])
            s["remaining"].append(sum(weekly[key][i] for key in unresolved if key[0]==r["team_id"]))
        for r in final:
            s=stats[r["team_id"]]
            s["finish"].append(r["final_place"])
            s["playoffs"] += bool(r["made_championship_playoffs"])
            s["titles"] += bool(state.rules.playoff_team_count and r["final_place"]==1)
        if progress and ((i+1)%100==0 or i+1==simulations):
            progress(i+1,simulations)
    outcomes=[]
    for team in state.teams:
        s=stats[team["team_id"]]
        playoff=s["playoffs"]/simulations if state.rules.playoff_team_count else None
        title=s["titles"]/simulations if state.rules.playoff_team_count else None
        outcomes.append(dict(team_id=team["team_id"],team_name=team["team_name"],
            expected_wins=math.fsum(s["wins"])/simulations,expected_ties=math.fsum(s["ties"])/simulations,
            expected_regular_points=math.fsum(s["points"])/simulations,
            expected_remaining_points=math.fsum(s["remaining"])/simulations,
            playoff_probability=playoff,championship_probability=title,
            playoff_mc_se=math.sqrt(playoff*(1-playoff)/simulations) if playoff is not None else None,
            championship_mc_se=math.sqrt(title*(1-title)/simulations) if title is not None else None,
            wins=percentiles(s["wins"]),seed=percentiles(s["seed"]),finish=percentiles(s["finish"]),
            remaining_points=percentiles(s["remaining"]),
            finish_distribution={str(k):v/simulations for k,v in sorted(Counter(s["finish"]).items())}))
    fingerprint = hashlib.sha256(json.dumps(dict(season=state.season,projections=sorted(
        (pid,week,r.get("projected_points")) for (pid,week),r in projections.items())),sort_keys=True).encode()).hexdigest()
    return dict(teams=outcomes,weekly=[dict(team_id=team,week=week,mean=math.fsum(values)/simulations,
                   **percentiles(values)) for (team,week),values in sorted(weekly.items())],
        metadata=dict(model_version=MODEL_VERSION,simulations=simulations,seed=seed,k=K,
            engine_version="monte-carlo-season-v1",
            state_hash=hashlib.sha256(json.dumps(asdict(state),sort_keys=True,separators=(",",":")).encode()).hexdigest(),
            effective_week=baseline.summary["effective_week"],dataset_hash=model.dataset_hash,
            scoring_version=model.scoring_hash,projection_hash=fingerprint,
            dependence="Independent player-week residuals; keyed draws shared across roster scenarios.",
            lineup_policy="Optimize ESPN expected scores before draws; no hindsight optimization.",
            current_week_policy="Full-week scores; live partial results and player locks are not modeled.",
            training_cutoff=[state.season,state.current_week],bye_starters=bye_starters,
            nonpositive_projection_queries=nonpositive,
            limitations=["V1 has measured tail undercoverage, especially WR zero-score outcomes.",
                "Conditional on recorded participation; no new injury, inactive, or availability process.",
                "No NFL teammate, opponent, or cross-week score correlation is modeled.",
                "Monte Carlo standard errors measure sampling noise, not model uncertainty."]),
        diagnostics=baseline.diagnostics)
