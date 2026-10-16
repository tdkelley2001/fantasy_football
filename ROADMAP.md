# Season engine and dashboard roadmap

This is the target direction, not a request to implement every stage at once.
Complete and validate one milestone before expanding the next. Existing search
and dashboard features are migration inputs, not a reason to skip foundations.

## Product direction

Build a sports analytics dashboard around this sequence:

**Decision summary → visual explanation → detailed table.**

Use the existing React app as the primary dashboard. Refactor its components and
layout as each workflow is migrated. The target is one app. Remove superseded
Streamlit screens, CLI workflows, and launchers as their responsibilities move
into the app; maintaining legacy entry points is not a requirement.

- Lead with four to six decision metrics. Comparisons show before → after with
  the delta emphasized. Use points, wins, and percentage points consistently.
- Explain trades with side-by-side player cards: identity, position, team,
  projection horizon, and meaningful deltas. Add headshots/team marks where data
  is available, with graceful fallbacks.
- Browse search results as compact ranked cards, targeting 120–160 px on desktop
  for simple packages. Show assets exchanged, your impact, partner impact, and
  an analysis action. Allow larger cards for larger packages and mobile screens.
- Open analysis in a detail drawer with expandable weekly impact, roster impact,
  and model details. Provide a sortable table toggle using the same filtered data.
- Keep search controls pinned on desktop and accessible on small screens.
- Use weekly scoring sparklines and position-by-week delta heatmaps when they
  explain timing or lineup changes. Only label bye risk when supported by data;
  missing projections alone do not establish a bye.
- Show a league race before exact standings. Add probability bars and finish
  percentile ranges only when the simulation engine supplies those outputs.
- Tables use restrained gridlines, aligned numbers, sticky identity columns,
  subtle hover states, and a small default set of relevant columns. Extra metrics
  belong in expandable detail.
- Support keyboard navigation, visible focus, accessible drawers, responsive
  layouts, and text/signs alongside colors. Charts must answer a specific question.

Deterministic results are single scenarios: projected wins, seed, finish, and
playoff result. Do not label them expected wins or convert qualification into
0%/100% odds. Fractional expected wins, playoff/championship probabilities,
variance badges, and outcome distributions belong to calibrated Monte Carlo.

## First milestone: deterministic foundation and league screen

Implementation now lives in `fantasy_projection/season.py`; ESPN ingestion lives
in `pipeline.py`. The former `project_from_normalized_inputs` entry point has
been removed and app evaluators use the shared state engine directly.

Implemented public contract:

```python
project_season(state: LeagueState, effective_week: int) -> SeasonProjection
```

`LeagueState` should describe league identity, teams, player ownership and
eligibility, available players, lineup/roster rules, scoring-period boundaries,
schedule, completed results, and player-week projections with coverage metadata.
ESPN fetching and normalization produce this state; the engine itself needs no
credentials, network calls, dashboard dependencies, or output-file side effects.

Define effective-week semantics explicitly: roster scenarios change unresolved
weeks from that boundary forward; completed results remain fixed. Preserve the
baseline for unresolved weeks before a future effective week. Establish how the
state carries that baseline before wiring future-effective transactions into it.
Document current-week locks and partial results rather than silently treating
them as completed or making historical results hypothetical.

Return standardized team outcomes, optimized weekly lineups, weekly scores,
actual/projected matchup provenance, seeds, postseason results, final placements,
champion, and missing-projection diagnostics. Migrate active app callers directly
to this contract and remove superseded callers instead of adding compatibility
wrappers for obsolete interfaces.

Acceptance criteria:

- The same state and effective week produce identical results without mutation.
- Real and hypothetical ownership states run through the same engine.
- Completed scores survive scenario changes; effective-week boundaries are tested.
- Tests cover lineup eligibility, missing projections, ties/seeding, multi-week
  postseason rounds, and already-completed-season behavior where supported.
- Unsupported league rules are explicit rather than silently approximated.
- The league screen leads with the selected team's projected record, seed,
  finish, and remaining starter points; follows with a league race and weekly
  scoring explanation; then offers exact standings and matchup detail.
- UI values reconcile with engine outputs, and migrated app workflows have
  validated behavior, including documented corrections found during the audit.
- Superseded implementations, unused dependencies, obsolete launchers, and their
  outdated tests and documentation are removed as part of the milestone.

This milestone excludes historical-error research, Monte Carlo, new trade sizes,
stacking, and a predictive model. Its UI establishes reusable summary, delta,
player identity, visual, and detail components for later screens.

### First-milestone implementation

Status: implemented and validated for the documented supported formats.

- Added `LeagueState`, `SeasonRules`, `SeasonProjection`, isolated hypothetical
  ownership states, and explicit effective-week boundaries.
- Preserved completed regular-season and postseason results; modeled partial
  multi-week periods using supplied finished-week actuals.
- Corrected tie-aware standings and scoring-week/period boundaries; added
  explicit supported-rule validation and projection-coverage diagnostics.
- Migrated manual app evaluators and cached search season scoring to shared logic.
- Rebuilt the league view with summary cards, a selectable league race, weekly
  scoring trends, coverage detail, and expandable exact standings.
- Removed the Streamlit app, standalone analysis launchers and exporters, unused
  streaming/unified planners, their obsolete tests, and the Streamlit dependency.
- Documented supported formats and modeling assumptions in `README.md`. Historical
  ESPN coverage and calibration research are still the next milestone.

Validation: 41 Python tests and 7 frontend tests passed, and the production
frontend built successfully. Browser checks covered summary rendering, team
selection, playoff brackets, trade analysis, and a 390 px viewport without page
overflow. A read-only live ESPN run projected 14 teams, 98 regular-season games,
and 19 postseason games with no missing starter projections in that snapshot.
Live coverage can change when ESPN projections update.

## Subsequent milestones, in order

Historical availability audit: complete. See [ESPN_HISTORY.md](research/ESPN_HISTORY.md)
for verified 2018–2025 weekly projection/actual coverage and league-history limits.
Raw scoring matched ESPN in 9,715 comparisons. Current D/ST rules require
rescoring historical components; forecast-generation timestamps remain unverified.
The [canonical player-week dataset and initial diagnostics](research/HISTORY_DATASET.md)
are implemented: 366,612 classified rows, with a separate 54,564-row strict sample
rescored under current rules. Unknown participation and inactive designations
remain explicit; omitted cancelled games are reconciled against ESPN schedules.
All excluded rows are retained. A post-diagnostics exclusion review identified
targeted participation/team/position questions; no excluded category was admitted.
The [chronological A–E comparison](research/RESIDUAL_VALIDATION.md) is implemented:
2020–2025 season holdouts and 2025 weekly updates, with 50/80/90/95% coverage,
width, and CRPS. Position plus projection-local residuals lead centered final-year
CRPS, but tail coverage (especially WR zero-score outcomes) remains inadequate.
The tested recency weighting does not improve the centered final-year result.
The [development-only k sensitivity check](research/LOCALITY_SENSITIVITY.md)
compares 250/500/750/1,000 neighbors on 2020–2024 only. CRPS is stable across
500–1,000; retain 500 as the working default, with WR tail-coverage sensitivity
documented separately. No 2025 retuning was performed. Reserve 2026 for an eventual
prospective check using a frozen specification and forecasts saved before outcomes.
**V1 is frozen by product decision on September 18, 2026:**
[authoritative specification](research/V1_MODEL.md). Use Method D, 500 nearest
historical projections within position, equal weights, mean-center each selected
residual pool, and add a sampled residual to ESPN's projection. No recency
weighting. Record 500–750 as a demonstrated stable region, not an optimum.
Further tuning is closed for V1. The measured tail/zero-score and availability
limitations remain accepted and documented; they are not a prerequisite for
reopening V1 research. The Monte Carlo season engine is now implemented. Any future
sample expansion, inactive-list enrichment, or distribution adjustment requires
explicit versioning.

1. **Historical ESPN projection-error dataset.** First establish retrievable
   seasons/weeks and provenance. Store season, week, player, position, historical
   game-week ESPN projection, actual points, and actual minus projection. Audit
   missingness, scoring compatibility, and projection timing. Long-range
   historical projections are outside V1.
2. **V1 error distribution — specification frozen.** Chronological comparisons
   and development-only neighborhood sensitivity are complete. Implement the
   exact Method D specification linked above; ESPN remains the scoring expectation.
   Preserve the observed calibration limitations and reserve future pre-outcome
   2026 forecasts for prospective evaluation. Further tuning belongs to a new version.
3. **Monte Carlo season engine.** Use current ESPN projections as expectations
   for current and future weeks with the same V1 error methodology. Document
   dependence assumptions. Reuse seeded player-week simulated outcomes across
   roster alternatives. Return expected wins, playoff/title odds, finish
   distributions, and scoring percentiles. Add probability bars, finish ranges,
   and current/proposed distribution visuals with simulation metadata.
   **Engine and baseline Simulation view implemented:** shared standings/brackets,
   fixed expected-score lineups, independent keyed player-week draws, explicit
   bye/scoring coverage, background progress, probability cards/bars, finish
   distribution, and exact score ranges. The API supports hypothetical states and
   effective weeks; current/proposed UI comparisons follow the transaction milestones.
   Validation: 91 Python tests, 7 frontend tests, and production build passed.
   A read-only 14-team live check ran 2,000 seasons in about 6.4 seconds; playoff
   probability summed to 6 spots and title probability to 1. Desktop and 390 px
   browser checks verified simulation execution and rendering without page overflow.
4. **Shared transaction backend.** Implement LeagueState → Transaction → new
   LeagueState → season engine. Validate ownership, roster limits, required drops,
   and open slots. Free agents are a special participant, not a fantasy team.
5. **Manual trade evaluator.** Start with 1-for-1, list-shaped player inputs, and
   effective-week selection. Show deterministic impacts for both teams first;
   run Monte Carlo on request. Use summary cards, roster exchange, then details.
6. **Manual waiver evaluator.** Evaluate an add/drop pair through the same state
   and season machinery, with its own focused interface.
7. **Trade search.** Separate candidate generation from evaluation. Add partner,
   package, player/position inclusion/exclusion, untouchable, target, effective-week,
   and K/DST controls. Trade eligibility never changes lineup scoring rules.
8. **Waiver search.** Generate legal 1-for-1 moves and rank them through the same
   evaluator, using waiver-specific cards and controls.
9. **Runtime and pruning.** Before larger packages, implement constraints →
   legal/lossless filters → loose approximate-value filters → deterministic
   evaluation → feasibility filters → Monte Carlo finalists. Cache baselines,
   unchanged-team computations, simulation draws, and evaluated final states with
   keys covering rules, projections, horizon, and model version. Show search-space
   estimates, progress, and Quick/Standard/Deep plus Custom controls.
   **Implemented:** constrained-space estimates; lossless transaction legality;
   deterministic projection-value pruning; Quick, Standard, Deep, and Custom
   budgets; existing lineup/scenario caches; loaded-snapshot result caching;
   progress by stage; and seeded Monte Carlo for ranked finalists. Capped modes
   disclose that approximate pruning can reduce recall. ESPN refresh invalidates
   search-result caches.
10. **Uneven trades and roster resolution.** Add 1-for-2 and 2-for-1 before more
    complex sizes. Evaluate required drops as part of the complete resulting
    state; later consider waiver fills for open slots. Show those moves explicitly.
    **Implemented:** manual and search evaluation support 1-for-2 and 2-for-1;
    real open slots are honored; otherwise required drops are part of the atomic
    transaction, legality checks, deterministic projection, Monte Carlo state,
    and result display. Search defaults to the legal drop with the least projected
    optimized-lineup benefit across the remaining weeks, with lowest total ESPN
    projection available as an alternate strategy. Automatic waiver fills for
    newly open slots remain deferred.
11. **Larger packages.** The current search includes 2-for-2. Add selective 3+
    player packages using meaningful-asset and replacement-level logic. Avoid
    unlimited brute force.
12. **Linked transaction plans.** Track currently owned acquired stack assets.
    Every later trade must send an active stack asset; remove sent assets and add
    newly acquired ones. Exclude the immediately previous partner, permit earlier
    partners again, and preserve user restrictions. Compare the final state with
    the original baseline.
13. **Efficient stacking search.** Use beam-style pruning, deduplicate final
    states, expose depth/breadth controls, and simulate surviving plans only.
14. **Waiver pressure.** Estimate availability/urgency separately from player
    value using historical activity and roster circumstances. Do not project an
    entire future waiver market deterministically.
15. **Predictive research.** Only after the above, test whether pre-week features
    can predict ESPN residuals out of sample. If a correction improves ESPN,
    recalibrate uncertainty around that model's out-of-sample residuals.

## Migration discipline

Retain useful current code after validation rather than rewriting by default.
Keep domain computation in Python, transport/view adapters separate, and React
components focused on presentation and interaction. Extract boundaries as each
milestone needs them instead of scaffolding every future subsystem now.

Cleanup is part of each milestone, not a separate future project. Delete old
unused code once its app responsibilities are migrated or deliberately retired.
Do not retain archive copies, duplicate implementations, legacy compatibility
layers, or unnecessary fallback paths just in case. Keep error handling and
validation that the active app actually needs.

The repository currently includes uncommitted implementation work. Inspect it
before replacing or deleting it so unrelated work is preserved; uncommitted
status alone does not require keeping superseded code. Check active references
and validate the affected app workflows when removing code or dependencies.
Each milestone should record its changed behavior, removals, validation,
assumptions, and next dependency before work advances.
# Transaction evaluation

- [x] Shared atomic transaction state builder for trades, waivers, free agency, open slots, required drops, and roster and position limits.
- [x] Manual 1-for-1 trade and add/drop evaluators with effective-week ownership, deterministic two-team impact, and optional Monte Carlo comparison.
- [x] Candidate generation controls separated from trade and waiver evaluation, including partner/package/player/position/target/untouchable/effective-week/K-DST inputs.
- [x] Trade and waiver search candidates pass through shared transaction legality before season scoring and ranking.

Status after consolidation: milestones 4–10 are implemented for the current
scope. Shared transaction validation is authoritative for ownership, roster
capacity, position limits, open slots, required drops, and locked/undroppable
players. Manual evaluation and search detail preserve effective-week semantics.
Candidate filters run before evaluation and have direct unit coverage. Trade
search supports 1-for-1, 1-for-2, 2-for-1, and 2-for-2 candidates with runtime
controls and pruning. Current validation: 110 Python tests, 10 frontend tests,
and the production frontend build. The next milestone is selective 3+ player
package support.

The current interface follows the decision-summary → visual-explanation →
detailed-table hierarchy. Search results provide ranked card and compact table
views, weekly sparklines, impact chips, and a detail drawer with lineup heatmaps.
League projection uses the league-race view, while Monte Carlo uses probability
bars, finish distributions, and 5th-to-95th percentile ranges.
