# Fantasy Football Studio

A React app backed by deterministic and Monte Carlo Python season engines. Load an ESPN league,
explore its projected season and outcome probabilities, and compare trade or waiver moves. The staged
product and engineering direction lives in [ROADMAP.md](ROADMAP.md).

The [ESPN historical-data audit](research/ESPN_HISTORY.md) documents verified
2018–2025 player projection/actual coverage, scoring compatibility, and remaining
data-quality requirements for the Monte Carlo milestone.
The [canonical dataset and diagnostics](research/HISTORY_DATASET.md) now preserve
all classifications separately from the strict initial modeling sample. Run
`python -m research.build_history` to reproduce the frozen-source build and open
`outputs/history/diagnostics.html` for the visual report.
The [chronological residual comparison](research/RESIDUAL_VALIDATION.md) evaluates
universal, position, projection-local, combined, and recency-weighted methods.
Run `python -m research.validate_residuals` and open
`outputs/residual_validation/comparison.html` for coverage, width, and CRPS results.
The [development-only k sensitivity check](research/LOCALITY_SENSITIVITY.md)
supports retaining 500 neighbors as a working default while documenting remaining
tail-calibration sensitivity. Reproduce with `python -m research.check_locality`.

**[V1 is now frozen](research/V1_MODEL.md): Method D, 500 nearest historical
projections within position, uniformly sampled mean-centered residuals, and no
recency weighting.** The demonstrated stable region is 500–750, not a claim of
optimality. The Simulation view now runs this frozen model; known calibration
limitations remain documented.

## Run the app

From the repository root in PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
.\venv\Scripts\python.exe run_app.py
```

The app opens **http://127.0.0.1:8502** in your default browser automatically.
Use `run_app.py --no-browser` to start without opening a tab. Rebuild the frontend
after editing its source.

Stop with Ctrl+C, or run this from another terminal if the original terminal is
unavailable:

```powershell
.\venv\Scripts\python.exe stop_app.py
```

The stop script asks this app to shut down without killing other Python programs.
In-progress analyses and the in-memory snapshot are discarded. The browser tab
stays open. An app started before this update needs one manual restart before it
can respond to the stop script.

Keep `ESPN_LEAGUE_ID`, `ESPN_SEASON`, and `MY_TEAM_ID` in `.env`. Private leagues
also need `ESPN_S2` and `ESPN_SWID`; see `.env.example`. Find your team ID in the
`teamId` parameter of your ESPN team's URL. Credentials stay on the Python server.

Click **Load ESPN data**. The league screen leads with a selected team's record,
seed, finish, and remaining starter points, then shows the league race and weekly
scoring outlook. Exact standings, weekly values, and projection coverage are
expandable. Schedule and playoff screens distinguish recorded and projected
results. Trade and waiver searches run in the background; refreshing data clears
previous searches and comparisons. No transactions are submitted to ESPN.

## Deterministic model

The public computation contract is:

```python
from fantasy_projection import project_season

baseline = project_season(state)
scenario = state.with_rosters(proposed_rosters)
after = project_season(scenario, effective_week=5)
```

`state` is a `LeagueState` containing supplied teams, ownership, slot eligibility,
player-week points, schedule, completed results, and explicit `SeasonRules`.
`load_league_state` in `fantasy_projection/pipeline.py` is the ESPN ingestion
adapter. The season engine performs no fetching or file writes and does not need
credentials. Returned data is isolated from the caller's input.

Before the effective week, a hypothetical state uses its baseline ownership.
From that week onward it uses the proposed roster. Completed matchup winners
and scores remain fixed, including postseason games. Partially completed
multi-week periods require final team-week scores for their finished weeks.
Current-week projections represent full-week scores; live partial points are
not added to them, and player locks are not modeled.

Outputs include optimized lineups, weekly team scores, matchup provenance,
standings, team outcomes, playoff results, final placements, champion, and
missing-projection diagnostics. These are deterministic scenarios, not expected
values or probabilities. The separate Simulation view provides Monte Carlo estimates.

Supported rules and explicit assumptions:

- Any supplied starter slots and player eligibility that permit a complete
  lineup; one player can fill only one slot per week. K/DST scoring is retained.
- Missing player-week projections use zero and remain visible in coverage
  details. Zero and negative projections are valid values.
- Standings use winning percentage with half credit for ties, then total points
  scored. Exact remaining ties use team ID for reproducibility.
- No playoffs, or 2/4/6/8-team seeded playoffs; optional reseeding and multi-week
  rounds. Projected playoff ties use higher regular-season seed. Recorded
  advancing teams take precedence for completed games.
- Full placement games for 2/4/8-team brackets. Six-team brackets give the top two
  seeds byes, play 3 vs 6 and 4 vs 5, resolve fifth place in round two, and resolve
  the title and third place in round three.
- Even-sized consolation ladders use adjacent initial seeds and winner/loser
  ladder movement. Disabled ladders retain regular-season order.

Division-based or custom bracket seeding, other tiebreak rules, odd consolation
ladders, and multiple matchups per team in a period are not supported. The engine
rejects incompatible rules or incomplete required results instead of silently
substituting a different format. The ESPN adapter also checks that postseason
week mappings agree with configured round lengths.

Current search tools remain immediate-effect 1-for-1/2-for-2 trades and one-for-one
waivers. Search and manual comparisons now share the deterministic season logic.
Searches rank by sustained weekly lineup gain by default. This removes the move's
single best week before averaging, so a recurring improvement outranks a larger
one-week bye replacement. Raw average and median gain remain available as alternate
ranking metrics. The dashboard's default positive threshold hides moves whose only
benefit occurs in one week; set the minimum score to zero to reveal those fallback
and bye-week options.
Their broader controls and transaction refactor follow later in the roadmap.

## Monte Carlo model

After loading ESPN data, open **Simulation** and select **Run Monte Carlo**.
The default is 2,000 simulated seasons with seed 2026; controls allow 1–20,000 runs
and a reproducible integer seed. Computation runs in the background with progress.
Refreshing ESPN clears the previous simulation. Restart the Python app after
updating its code, and rebuild the frontend as shown above.

Summary cards show expected regular-season wins, playoff/title probabilities,
and median final finish. Probability bars and a finish distribution explain the
results; exact standings, weekly scoring ranges, and assumptions expand below.
No-playoff leagues show playoff/title probabilities as not configured.

```python
from fantasy_projection import ResidualModel, simulate_season

model = ResidualModel.load()
result = simulate_season(state, model, simulations=2000, seed=2026)
scenario = simulate_season(state.with_rosters(proposed_rosters), model,
                           simulations=2000, seed=2026, effective_week=5)
```

`state` must include matching `settings_payload.settings.scoringSettings.scoringItems`.
The app loads confirmed NFL bye weeks before simulation. For programmatic callers,
`load_simulation_state(state, EspnClient(config))` in `pipeline.py` attaches that
schedule evidence; the simulation engine itself has no network calls. Explicit
`player_bye_weeks` may also be supplied by another trusted adapter.

Behavior and assumptions:

- Frozen Method D: 500 nearest historical projections within position, uniform
  sampling with replacement, selected-pool mean centering, no recency weights,
  and no post-draw clipping. Nonpositive target projections use the same nearest
  pool and are listed in metadata; a zero forecast alone does not establish a bye
  or inactive status. The positive-projection requirement applies to training rows.
- Historical observations must precede the state's current week. The frozen
  sample hash and current scoring-rule hash are checked; incompatible scoring,
  missing starter projections, unsupported positions, and pools smaller than
  500 fail explicitly rather than substituting an unrelated distribution.
- Each team's lineup is optimized from ESPN expectations **before drawing scores**.
  There is no perfect-hindsight bench selection. Effective-week ownership follows
  the deterministic engine, including pre-effective baseline rosters.
- Confirmed NFL byes score zero. The schedule adapter uses current NFL affiliations
  for future weeks; future NFL transfers or schedule changes are not predicted.
- Completed matchup results remain fixed, including playoff upsets. Supplied
  final team-week scores survive partial multi-week rounds. Unresolved current-week
  scores use full-week projections; live partial scores and player locks are not modeled.
- Player-week residuals are independent. NFL teammate/opponent correlations,
  persistent player form, and new injury/inactive processes are not modeled.
- Player ID, scoring week, season, model version, and seed identify a random stream.
  The same unchanged player-week has the same draws across roster scenarios and
  input ordering. Increasing the run count preserves the earlier draws as a prefix.
- League rules, seeding, tiebreaks, and brackets use the existing shared season
  resolution functions. The same supported-format limits apply to both engines.

Outputs include expected wins/ties/points, playoff/title probabilities, finish
distributions, P05/P50/P95 score and finish summaries, and estimated Monte Carlo
standard errors for probabilities. These errors describe simulation noise, not
uncertainty about the model. Dataset/scoring/projection hashes, seed, draw count,
effective week, and assumptions identify each result.

`outputs/history/initial_sample.jsonl.gz` must match the snapshot pinned in
`research/v1_model_spec.json`. The model does not silently rebuild or replace it.
Current search and manual move screens still show deterministic results; the
shared simulation function supports hypothetical states for their later integration.

The recorded WR/tail undercoverage and conditional-on-participation limitation
remain. Implementation does not retune V1 or constitute the future prospective
2026 evaluation; collecting pre-outcome timestamped forecasts remains separate work.

## Validation

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
cd frontend
npm test
npm run build
```

Engine tests use synthetic states without ESPN access. They cover effective-week
boundaries, completed results, multi-week playoffs, lineup eligibility, missing
projections, standings, bracket placements, and search/full-evaluation agreement.
The old Streamlit UI, standalone analysis launchers, file exporters, streaming
planner, and unified-move planner have been removed.

Dashboard progress is shown for ESPN loading, season projection, trade and waiver searches, manual comparisons, and Monte Carlo runs. Counted stages show completed work and a percentage; network requests and preparation without a fixed count show an indeterminate bar. Percentages describe the current stage, not estimated total runtime. Results loading also displays a progress indicator.

Trade and waiver scenarios use the shared transaction engine in `fantasy_projection/transactions.py`. It treats free agents as a special participant, validates ownership, locked and undroppable players, active-roster capacity, position limits, required drops, and open slots, then sends the resulting isolated league state through the season engine. An effective week preserves original ownership before the selected week. Transaction validation never changes league starter slots or scoring rules.

The dashboard provides separate manual Trade Evaluator and Waiver Evaluator screens. The manual trade UI begins with 1-for-1 exchanges and sends list-shaped player fields. Both evaluators show deterministic effects first and offer a 2,000-season Monte Carlo comparison on request. Search controls generate candidates by partner, package size, player, position, targets, untouchables, effective week, and K/DST policy before legal candidates are evaluated and ranked.

Move searches expose four runtime modes. Quick evaluates at most 1,000 legal candidates and simulates 3 finalists for 500 seasons each. Standard evaluates at most 5,000 and simulates 5 finalists for 1,000 seasons. Deep evaluates the entire constrained legal space and simulates 10 finalists for 2,000 seasons. Custom accepts explicit limits. When a cap applies, the approximate stage retains packages with the closest total remaining ESPN projection value; this changes recall and is disclosed before execution. Full lineup and season evaluation determines final ranks. Identical searches against the same loaded snapshot reuse cached results. Refreshing ESPN clears that cache.

Trades support 1-for-1, 1-for-2, 2-for-1, and 2-for-2 packages. Uneven trades are evaluated as complete atomic roster states. If the team receiving the extra player has a real open active-roster slot, no drop is added. Both the manual evaluator and Trade Search can automatically drop the legal player with the least projected lineup benefit: the engine optimizes every remaining weekly lineup for each possible resolution and keeps the drop that preserves the most starter points. A lowest-total-ESPN-projection strategy and explicit manual player selection are also available. The selected drop appears in the resulting analysis. Released players return to the free-agent participant. Open slots created by sending away more players remain open; automatic waiver fills are outside this version.

The dashboard uses a sports-analysis hierarchy: summary metrics first, visual evidence second, and exact tables behind disclosure controls. Trade and waiver searches support ranked cards or a compact sortable-style table view. Move cards include player identities, impact chips, Monte Carlo deltas, and remaining-season sparklines. The detail drawer includes two-team impact summaries, a position-by-week lineup heatmap, weekly lineup changes, and exact model output. Monte Carlo results use probability bars, finish distributions, and league-wide percentile ranges.
