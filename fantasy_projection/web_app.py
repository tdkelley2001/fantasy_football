"""Local JSON API and static frontend; credentials never leave Python."""
import json
import hashlib
import threading
import webbrowser
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .config import load_config
from .pipeline import load_league_state, load_simulation_state
from .monte_carlo import ResidualModel, simulate_season
from .season import project_season, SeasonModelError
from .trade_config import load_my_team_id, TradeConfig
from .trades import evaluate_all_trades, select_trade_resolution, TradeSearchOptions
from .waivers import analyze_waivers, WaiverSearchOptions
from .espn import EspnClient, pull_available_players
from .trade_analysis import evaluate_trade
from .waiver_analysis import evaluate_waiver
from .search_runtime import runtime_profile


def comparison_payload(result):
    summary = getattr(result, "trade_summary", None) or getattr(result, "waiver_summary", None)
    return dict(summary=summary, teams=result.team_comparison, weekly=result.weekly_comparison,
                lineups=result.lineup_comparison, league=result.league_comparison)


class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.busy = False
        self.error = None
        self.baseline = None
        self.available = []
        self.trades = []
        self.waivers = []
        self.loaded = None
        self.revision = 0
        self.simulation = None
        self.residual_model = None
        self.progress = None
        self.search_cache = {}
        self.search_simulation_cache = {}
        self.trade_search = None
        self.waiver_search = None

    def update_progress(self, stage, done=None, total=None, unit="items"):
        with self.lock:
            self.progress = dict(stage=stage, done=done, total=total, unit=unit)

    def simulate_search_finalists(self, kind, rows, runtime):
        valid = [row for row in rows if row.get("evaluation_status") == "VALID"]
        score = ((lambda row: row.get("mutual_sustained_weekly_lineup_gain", float("-inf")))
                 if kind == "trades" else
                 (lambda row: row.get("team_sustained_weekly_lineup_gain", float("-inf"))))
        finalists = sorted(valid, key=score, reverse=True)[:runtime.monte_carlo_finalists]
        if not finalists:
            return dict(finalists_requested=runtime.monte_carlo_finalists,
                        finalists_simulated=0, simulations=runtime.simulations)
        self.update_progress("Loading Monte Carlo finalist model")
        if self.residual_model is None:
            self.residual_model = ResidualModel.load()
        client = EspnClient(self.config)
        before_state = load_simulation_state(self.baseline.state, client)
        total = (len(finalists) + 1) * runtime.simulations
        def before_progress(done, count):
            self.update_progress("Simulating search finalists", done, total, "seasons")
        baseline_mc = self._cached_search_simulation(
            before_state, runtime.simulations, before_state.current_week, before_progress)
        before = {row["team_id"]: row for row in baseline_mc["teams"]}
        completed = runtime.simulations
        simulated = 0
        for rank, row in enumerate(finalists, start=1):
            try:
                week = int(row["current_scoring_week"])
                if kind == "trades":
                    comparison = evaluate_trade(baseline=self.baseline, my_team_id=self.my_id,
                        give_player_ids=map(int, str(row["my_give_player_ids"]).split(",")),
                        receive_player_ids=map(int, str(row["my_receive_player_ids"]).split(",")),
                        my_drop_player_ids=[int(p) for p in str(row.get("my_drop_player_ids") or "").split(",") if p],
                        partner_drop_player_ids=[int(p) for p in str(row.get("partner_drop_player_ids") or "").split(",") if p],
                        effective_week=week)
                else:
                    comparison = evaluate_waiver(baseline=self.baseline, my_team_id=self.my_id,
                        available_players=self.available, add_player_id=int(row["add_player_id"]),
                        drop_player_id=int(row["drop_player_id"]), effective_week=week)
                after_state = load_simulation_state(comparison.after.state, client)
                offset = completed
                def scenario_progress(done, count, offset=offset):
                    self.update_progress("Simulating search finalists", offset + done, total, "seasons")
                after_mc = self._cached_search_simulation(
                    after_state, runtime.simulations, week, scenario_progress)
                after = {team["team_id"]: team for team in after_mc["teams"]}
                team_ids = [self.my_id]
                if kind == "trades":
                    team_ids.append(int(row["partner_team_id"]))
                for prefix, team_id in zip(("my", "partner"), team_ids):
                    old, new = before[team_id], after[team_id]
                    row[f"{prefix}_mc_expected_wins_change"] = new["expected_wins"] - old["expected_wins"]
                    row[f"{prefix}_mc_playoff_probability_change"] = (
                        new["playoff_probability"] - old["playoff_probability"]
                        if new["playoff_probability"] is not None else None)
                    row[f"{prefix}_mc_championship_probability_change"] = (
                        new["championship_probability"] - old["championship_probability"]
                        if new["championship_probability"] is not None else None)
                row["monte_carlo_rank"] = rank
                row["monte_carlo_simulations"] = runtime.simulations
                row["monte_carlo_status"] = "COMPLETE"
                simulated += 1
            except SeasonModelError as exc:
                row["monte_carlo_status"] = "UNAVAILABLE"
                row["monte_carlo_reason"] = str(exc)
            completed += runtime.simulations
        return dict(finalists_requested=runtime.monte_carlo_finalists,
                    finalists_simulated=simulated, simulations=runtime.simulations,
                    feasibility_filtered=max(0, len(valid)-len(finalists)))

    def _cached_search_simulation(self, state, simulations, effective_week, progress):
        state_hash = hashlib.sha256(json.dumps(
            asdict(state), sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
        key = (state_hash, simulations, 2026, effective_week)
        cached = self.search_simulation_cache.get(key)
        if cached is not None:
            return cached
        result = simulate_season(state, self.residual_model, simulations=simulations,
                                 seed=2026, effective_week=effective_week, progress=progress)
        self.search_simulation_cache[key] = result
        return result

    def start(self, action, options=None):
        options = options or {}
        if action not in ("refresh", "trades", "waivers", "simulate"):
            raise ValueError("Unknown analysis action")
        simulations, seed = options.get("simulations",2000), options.get("seed",2026)
        if action == "simulate" and (type(simulations) is not int or not 1 <= simulations <= 20000
                                    or type(seed) is not int or not 0 <= seed <= 2**32-1):
            raise ValueError("Use 1–20,000 simulations and an integer seed from 0 to 4,294,967,295.")
        with self.lock:
            if self.busy:
                raise ValueError("An analysis is already running.")
            if action != "refresh" and self.baseline is None:
                raise ValueError("Load ESPN data first.")
            self.busy, self.error = action, None
            self.progress = dict(stage="Starting analysis", done=None, total=None, unit="items")
            if action == "simulate":
                self.simulation = None
        def work():
            try:
                if action == "refresh":
                    config, my_id = load_config(), load_my_team_id()
                    state = load_league_state(config, progress_callback=self.update_progress)
                    self.update_progress("Optimizing lineups and projecting the season")
                    baseline = project_season(state)
                    self.update_progress("Loading free agents and waiver players")
                    available = pull_available_players(
                        EspnClient(config), scoring_period_id=int(baseline.summary["current_scoring_period"])
                    )
                    if my_id not in {t["team_id"] for t in baseline.state.teams}:
                        raise ValueError("MY_TEAM_ID is not in this league.")
                    with self.lock:
                        self.config, self.my_id, self.baseline = config, my_id, baseline
                        self.trades, self.waivers, self.available = [], [], available
                        self.search_cache = {}
                        self.search_simulation_cache = {}
                        self.trade_search = self.waiver_search = None
                        self.simulation = None
                        self.loaded = datetime.now().astimezone().isoformat(timespec="seconds")
                elif action == "simulate":
                    self.update_progress("Loading historical residual distributions")
                    if self.residual_model is None:
                        self.residual_model = ResidualModel.load()
                    self.update_progress("Checking ESPN schedules and bye weeks")
                    state = load_simulation_state(self.baseline.state, EspnClient(self.config))
                    self.update_progress("Preparing lineups and sampling player scores")
                    def update_progress(done,total):
                        self.update_progress("Simulating seasons", done, total, "seasons")
                    result = simulate_season(state,self.residual_model,simulations=simulations,
                                             seed=seed,progress=update_progress)
                    with self.lock:
                        self.simulation = result
                elif action == "trades":
                    search = options.get("search", {})
                    runtime = runtime_profile(search.get("mode", "standard"),
                        candidate_limit=search.get("candidate_limit"),
                        monte_carlo_finalists=search.get("monte_carlo_finalists"),
                        simulations=search.get("simulations"))
                    cache_key = (action, json.dumps(search, sort_keys=True, separators=(",", ":")), self.loaded)
                    if cache_key in self.search_cache:
                        self.update_progress("Loading cached trade search")
                        cached = self.search_cache[cache_key]
                        with self.lock:
                            self.trades, self.trade_search = cached
                        return
                    trade_options = TradeSearchOptions(
                        partner_ids=tuple(map(int, search.get("partner_ids", []))),
                        package_shapes=tuple(tuple(map(int, shape.split("x")))
                                             for shape in search.get("package_shapes", ["1x1", "1x2", "2x1", "2x2"])),
                        include_player_ids=tuple(map(int, search.get("include_player_ids", []))),
                        exclude_player_ids=tuple(map(int, search.get("exclude_player_ids", []))),
                        untouchable_player_ids=tuple(map(int, search.get("untouchable_player_ids", []))),
                        target_player_ids=tuple(map(int, search.get("target_player_ids", []))),
                        include_positions=tuple(map(int, search.get("include_positions", []))),
                        exclude_positions=tuple(map(int, search.get("exclude_positions", []))),
                        include_special_teams=bool(search.get("include_special_teams", True)),
                        drop_strategy=str(search.get("drop_strategy", "least_lineup_benefit")),
                        effective_week=int(search.get("effective_week") or self.baseline.state.current_week),
                        balance_filter=bool(search.get("balance_filter", False)),
                        minimum_value_ratio=float(search.get("minimum_value_ratio", 0.5)),
                        runtime=runtime,
                    )
                    result = evaluate_all_trades(baseline=self.baseline, trade_config=TradeConfig(self.my_id), progress_callback=self.update_progress, options=trade_options)
                    mc = self.simulate_search_finalists("trades", result.all_evaluations, runtime)
                    with self.lock:
                        self.trades = result.all_evaluations
                        self.trade_search = dict(types=result.search_summary, runtime=runtime.__dict__, monte_carlo=mc, cached=False)
                        self.search_cache[cache_key] = (self.trades, self.trade_search)
                else:
                    search = options.get("search", {})
                    runtime = runtime_profile(search.get("mode", "standard"),
                        candidate_limit=search.get("candidate_limit"),
                        monte_carlo_finalists=search.get("monte_carlo_finalists"),
                        simulations=search.get("simulations"))
                    cache_key = (action, json.dumps(search, sort_keys=True, separators=(",", ":")), self.loaded)
                    if cache_key in self.search_cache:
                        self.update_progress("Loading cached waiver search")
                        cached = self.search_cache[cache_key]
                        with self.lock:
                            self.waivers, self.waiver_search = cached
                        return
                    waiver_options = WaiverSearchOptions(
                        add_positions=tuple(map(int, search.get("add_positions", []))),
                        drop_positions=tuple(map(int, search.get("drop_positions", []))),
                        exclude_add_player_ids=tuple(map(int, search.get("exclude_add_player_ids", []))),
                        untouchable_drop_player_ids=tuple(map(int, search.get("untouchable_drop_player_ids", []))),
                        target_add_player_ids=tuple(map(int, search.get("target_add_player_ids", []))),
                        include_special_teams=bool(search.get("include_special_teams", True)),
                        effective_week=int(search.get("effective_week") or self.baseline.state.current_week),
                        runtime=runtime,
                    )
                    self.update_progress("Loading available players from ESPN")
                    available = pull_available_players(EspnClient(self.config), scoring_period_id=int(self.baseline.summary["current_scoring_period"]))
                    result = analyze_waivers(baseline=self.baseline, my_team_id=self.my_id, available_players=available, progress_callback=self.update_progress, options=waiver_options)
                    self.available = available
                    mc = self.simulate_search_finalists("waivers", result.transactions, runtime)
                    with self.lock:
                        self.available, self.waivers = available, result.transactions
                        self.waiver_search = dict(summary=result.summary, runtime=runtime.__dict__, monte_carlo=mc, cached=False)
                        self.search_cache[cache_key] = (self.waivers, self.waiver_search)
            except Exception as exc:
                # Do not serialize request URLs, cookies, or configuration.
                with self.lock:
                    self.error = str(exc) if isinstance(exc, SeasonModelError) else f"{type(exc).__name__}: analysis failed. Check league settings and ESPN access, then retry."
            finally:
                with self.lock:
                    self.busy = False
                    self.revision += 1
        threading.Thread(target=work, daemon=True).start()

    def snapshot(self):
        with self.lock:
            b = self.baseline
            if b is None:
                return None
            return dict(my_id=self.my_id, loaded=self.loaded, summary=b.summary,
                        teams=b.state.teams, rosters=b.state.rosters, available=self.available,
                        projections=b.state.player_projections, lineups=b.optimal_lineups,
                        starter_slots=b.state.starter_slots,
                        player_bye_weeks=b.state.player_bye_weeks,
                        weekly=b.weekly_team_projections, standings=b.projected_standings,
                        final=b.final_standings, matchups=b.regular_season_matchups,
                        playoffs=b.postseason_matchups, outcomes=b.team_outcomes, diagnostics=b.diagnostics,
                        trades=self.trades, waivers=self.waivers, simulation=self.simulation,
                        trade_search=self.trade_search, waiver_search=self.waiver_search)


STATE = AppState()
STATIC = Path(__file__).resolve().parents[1] / "frontend" / "dist"
APP_URL = "http://127.0.0.1:8502"
APP_ID = "fantasy-football-studio"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, payload, status=200):
        data = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/lifecycle":
            self.send_json({"application": APP_ID})
        elif path == "/api/status":
            with STATE.lock:
                self.send_json(dict(busy=STATE.busy, error=STATE.error, revision=STATE.revision, progress=STATE.progress))
        elif path == "/api/snapshot":
            self.send_json(STATE.snapshot())
        elif path in ("/", "/app.js", "/app.css"):
            target = STATIC / ("index.html" if path == "/" else path[1:])
            if not target.is_file():
                self.send_error(404, "Run npm run build in frontend first")
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[target.suffix])
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host')}":
            self.send_json({"error": "Origin rejected"}, 403)
            return
        if self.headers.get("Content-Type") != "application/json":
            self.send_json({"error": "JSON required"}, 415)
            return
        try:
            size = int(self.headers.get("Content-Length", 0))
            if size > 10000:
                raise ValueError("Request too large")
            body = json.loads(self.rfile.read(size) or b"{}")
            action = self.path.removeprefix("/api/")
            if action == "shutdown":
                if self.headers.get("X-Studio-Control") != "shutdown":
                    self.send_json({"error": "Use stop_app.py to stop the app."}, 403)
                    return
                self.send_json({"application": APP_ID, "stopping": True})
                # shutdown must run outside serve_forever's thread. This path
                # deliberately does not acquire the analysis state lock.
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            elif action in ("refresh", "trades", "waivers", "simulate"):
                STATE.start(action, body)
                self.send_json({"started": action}, 202)
            elif action in ("compare", "compare-simulate"):
                with STATE.lock:
                    if STATE.busy or STATE.baseline is None:
                        raise ValueError("Wait for analysis or load data first")
                    args = dict(baseline=STATE.baseline, my_team_id=STATE.my_id)
                    STATE.busy = action
                    STATE.error = None
                    STATE.progress = dict(stage="Projecting roster changes and comparing outcomes", done=None, total=None, unit="items")
                try:
                    effective_week = int(body.get("effective_week") or STATE.baseline.state.current_week)
                    if body.get("kind") == "waivers":
                        drop = body.get("drop")
                        result = evaluate_waiver(**args, available_players=STATE.available,
                            add_player_id=int(body["add"]), drop_player_id=int(drop) if drop not in (None, "") else None,
                            effective_week=effective_week)
                    else:
                        give, receive = [int(p) for p in body["give"]], [int(p) for p in body["receive"]]
                        my_drops = [int(p) for p in body.get("my_drops", [])]
                        partner_drops = [int(p) for p in body.get("partner_drops", [])]
                        if body.get("auto_drop") and not my_drops and not partner_drops:
                            owners = {int(row["player_id"]): int(row["team_id"])
                                      for row in STATE.baseline.state.rosters}
                            partner_ids = {owners.get(player_id) for player_id in receive}
                            if None in partner_ids or len(partner_ids) != 1:
                                raise ValueError("Received players must belong to one trade partner")
                            my_drops, partner_drops = select_trade_resolution(
                                STATE.baseline, STATE.my_id, partner_ids.pop(), tuple(give),
                                tuple(receive), effective_week,
                                TradeSearchOptions(
                                    drop_strategy=str(body.get("drop_strategy", "least_lineup_benefit")),
                                    effective_week=effective_week))
                        result = evaluate_trade(**args, give_player_ids=give, receive_player_ids=receive,
                            my_drop_player_ids=my_drops,
                            partner_drop_player_ids=partner_drops,
                            effective_week=effective_week, available_players=STATE.available,
                            fill_open_slots=bool(body.get("fill_open_slots", False)),
                            roster_target=int(body.get("roster_target", 17)))
                    payload = comparison_payload(result)
                    if action == "compare-simulate":
                        STATE.update_progress("Loading historical residual distributions")
                        if STATE.residual_model is None:
                            STATE.residual_model = ResidualModel.load()
                        before_state = load_simulation_state(result.before.state, EspnClient(STATE.config))
                        after_state = load_simulation_state(result.after.state, EspnClient(STATE.config))
                        simulations, seed = int(body.get("simulations", 2000)), int(body.get("seed", 2026))
                        def progress(done, total):
                            STATE.update_progress("Simulating current and proposed rosters", done, total * 2, "seasons")
                        before_mc = simulate_season(before_state, STATE.residual_model, simulations=simulations,
                                                    seed=seed, effective_week=effective_week, progress=progress)
                        def after_progress(done, total):
                            STATE.update_progress("Simulating current and proposed rosters", total + done, total * 2, "seasons")
                        after_mc = simulate_season(after_state, STATE.residual_model, simulations=simulations,
                                                   seed=seed, effective_week=effective_week, progress=after_progress)
                        before = {row["team_id"]: row for row in before_mc["teams"]}
                        payload["monte_carlo"] = [dict(team_id=row["team_id"], team_name=row["team_name"],
                            expected_wins_before=before[row["team_id"]]["expected_wins"], expected_wins_after=row["expected_wins"],
                            expected_wins_change=row["expected_wins"]-before[row["team_id"]]["expected_wins"],
                            playoff_probability_before=before[row["team_id"]]["playoff_probability"], playoff_probability_after=row["playoff_probability"],
                            playoff_probability_change=(row["playoff_probability"]-before[row["team_id"]]["playoff_probability"]) if row["playoff_probability"] is not None else None,
                            championship_probability_before=before[row["team_id"]]["championship_probability"], championship_probability_after=row["championship_probability"],
                            championship_probability_change=(row["championship_probability"]-before[row["team_id"]]["championship_probability"]) if row["championship_probability"] is not None else None)
                            for row in after_mc["teams"] if row["team_id"] in {t["team_id"] for t in result.team_comparison}]
                        payload["monte_carlo_metadata"] = dict(simulations=simulations, seed=seed)
                    self.send_json(payload)
                finally:
                    with STATE.lock:
                        STATE.busy = False

            else:
                self.send_error(404)
        except SeasonModelError as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception:
            self.send_json({"error": "Unable to complete request. Check the selection and loaded data, or wait for the current analysis."}, 400)


def _open_browser():
    try:
        opened = webbrowser.open(APP_URL, new=2)
    except webbrowser.Error:
        opened = False
    if not opened:
        print(f"Open {APP_URL} in your browser.", flush=True)


def main(*, open_browser=True):
    server = ThreadingHTTPServer(("127.0.0.1", 8502), Handler)
    print(f"Fantasy Football Studio: {APP_URL} - Ctrl+C or run stop_app.py to stop", flush=True)
    try:
        if open_browser:
            threading.Thread(target=_open_browser, daemon=True).start()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("Fantasy Football Studio stopped.", flush=True)
