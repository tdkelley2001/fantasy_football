# Development Roadmap

Source: extracted from sections 12 through 12.5 of the approved `Fantasy Football Decision Engine — Master Model Specification & Roadmap` (design baseline, 14 October 2026). The [master specification](MASTER_SPEC.md) remains authoritative.

## Status policy

All M0-M7 work packages are **NOT STARTED**. M0 is next but may not begin until the repository transition is reviewed and approved. M7 remains a deferred milestone; its work packages are still not started. No legacy implementation is credited toward these statuses.

Dependencies are sequential within each milestone and across the M0 → M7 milestone order unless the source explicitly identifies independent work with verified shared interfaces. A work package cannot be complete until its stated gate passes.

## 12. Delivery roadmap, gates, and active progress

### 12.1 Milestone sequence and status

#### M0 — ESPN feasibility and historical-data audit [NEXT / NOT STARTED]. Diagnostic script, documented actual API/endpoint coverage, historical pregame projection provenance, complete league settings/waiver/bracket inventory, known blockers. PASS: each critical field verified or explicitly addressed with a defensible path; material gaps and uncertainty written down.

#### M1 — Canonical snapshots and validation [NOT STARTED]. ESPN adapter, standardized league/roster/player-week state, immutable staged and validated refresh, SQLite/Parquet, fixture tests. PASS: deterministic snapshot round-trip, no data corruption on failed refresh, complete identifiable league state and usable future inputs.

#### M2 — Structurally complete full-season simulator [NOT STARTED]. Legal projected-optimal weekly lineups, essential waiver processing/real shared pool, matchups, dynamic standings, exact six-team championship and eight-team consolation, initial report and deterministic tests. PASS: every path is legal and yields coherent championship/placement outcomes; known ESPN settings are honored; provisional models labeled.

#### M3 — Calibrated probabilistic and efficient baseline [NOT STARTED]. Historical ESPN error audit and chosen distribution, adaptive all-team precision, seeded common random numbers, compact high-performance/parallel engine, fast/detailed modes, progressive estimates and detailed-run recovery. PASS: reasonable calibration evidence or explicit limitations, interval/convergence tests, reproducible multiprocessing/resume, representative throughput measurements.

#### M4 — Manual generalized scenario evaluator [NOT STARTED]. Explicit multi-team roster changes, protected pins, deterministic capacity drops then round-robin refills, full legal states, unified replacement-adjusted roster utility, paired baseline comparison and churn diagnostics. PASS: invalid scenarios rejected, no duplicate ownership, all 14 affected outcome estimates and uncertainty reported.

#### M5 — Automated actionable decision search [NOT STARTED]. Candidate trades, standalone waiver evaluator and streaming flexibility, practical sellability/availability constraints, staged screening, combined trade/waiver ranking, multi-transaction paths. PASS: recommendations are grounded in executable modeled transitions; candidate search validates feasibility, quality and time cost.

#### M6 — Integrated CLI V1 and release acceptance [NOT STARTED]. One official versioned model, consolidated commands and reports, documentation, unit/property/statistical/performance tests, operational diagnostics and troubleshooting. PASS: refresh → baseline → manual/automated decision analysis works without spreadsheets and satisfies critical requirements.

#### Post-V1 research backlog — Joint player/game correlations: after the independent baseline is established, investigate same-team and opponent dependence (including QB–receiver stacks), common game-script effects, and across-week player-state persistence. Require defensible joint ESPN-era actuals, stable covariance/factor calibration, efficient multivariate simulation and measured effects on championship probability or decision quality; do not include correlated score draws in V1.

#### Post-V1 research backlog — Player-specific volatility and bias: evaluate regularized, data-sufficient player-level departures from shared position/projection-level distributions only after M3 calibration and sufficient as-of history have been collected. Compare temporally held-out calibration and resulting decision quality, with hierarchical shrinkage/fallback to group estimates; do not include player-specific residual parameters in V1 or presume they improve outcomes. Also revisit forecast-horizon variance only when genuine earlier as-of snapshots exist.

#### M7 — Dashboard and interaction [DEFERRED]. Design an aesthetically polished league-forecast, action-explorer and scenario-lab experience, with probability visualizations, bracket/timeline, concise cards, progress and uncertainty, plus optional detailed tables. PASS: analytics remain accurate, readable, and inspectable without exposing developer-only model alternatives.

### 12.1A Detailed milestone work packages and verification gates

Operating rules: Every numbered task has a concrete inspectable artifact, a small correctness test, explicit dependencies and a status of NOT STARTED / IN PROGRESS / BLOCKED / COMPLETE. No planned task is COMPLETE until its acceptance check passes. Keep each change runnable and integrated; keep all exploratory assumptions visibly provisional, and fail fast on unapproved fallbacks. The simple exhaustive enumerator and reference simulator remain correctness oracles for later optimizations. Items listed within milestones are ordered; only parallelize independent tasks when they share verified interfaces.

#### M0 — ESPN data and feasibility audit (first priority; discovery, not modeling)

M0.1 Create clean Python repository, dependency lockfile, configuration example, test runner, logging and credential loading; verify credentials are excluded from source control. GATE: clean setup and one automated smoke test on a fresh environment.

M0.2 Implement a read-only ESPN connectivity script for the user's actual league/season; enumerate teams, player and team IDs, roster ownership, standings, scoring and eligible lineup slots. GATE: reconcile 14 unique teams and ownership without silent assumptions.

M0.3 Audit projected future player-week scores, zero/missing distinction, available-player pool, bye weeks and future schedule; save sanitized sample responses. GATE: inventory required fields, response provenance and missing/unsupported cases.

M0.4 Audit actual league roster/trade/waiver rules, standings tiebreakers and regular/playoff/consolation brackets against ESPN settings and known results. GATE: verified rule matrix, or explicitly flagged manual league-config inputs/blockers.

M0.5 Probe small samples of historical seasons for as-of pregame ESPN projections and later actuals; detect hindsight/restated projections, date coverage and feasibility of held-out validation. GATE: evidence-backed historical data availability report and unambiguous gaps.

M0.6 Publish data dictionary, exact source paths/IDs, audit script, known errors and go/no-go decision for M1; do not let missing critical rules be silently guessed. GATE: reproducible audit result and an approved list of unresolved limitations.

#### M1 — Versioned canonical snapshots and data contracts

M1.1 Define typed canonical entities and join keys: league, rules, teams, gameweeks, players, ownership, schedule, projections and available free agents. GATE: example JSON/typed fixture passes validation.

M1.2 Build explicit ESPN-to-canonical adapter with source provenance and league-specific editable config only for audited missing rules. GATE: adapter unit tests on real sanitized fixtures.

M1.3 Implement staged immutable refresh, validation checks, separate raw/normalized storage and SQLite/Parquet layouts; never modify an approved snapshot on a failed refresh. GATE: round-trip and interrupted-refresh recovery tests.

M1.4 Validate unique player ownership, league/team counts, player-week availability and week/schedule coverage; distinguish absent values from zeros. GATE: intentional malformed fixtures raise precise errors.

M1.5 Add reproducible snapshot load/list/inspect commands, stable snapshot ID and minimal diagnostics. GATE: two loads of one snapshot reproduce identical canonical state.

#### M2 — Complete deterministic season-path reference simulator

M2.1 Implement per-week legal starting-lineup optimizer using ESPN eligibility, projections and available players. GATE: toy and real-fixture lineup correctness tests, including ties and missing/zero cases.

M2.2 Implement week progression, actual ESPN matchup schedule, points-for/against accumulation, standings, and tie rules. GATE: synthetic schedule results agree with hand-calculated examples.

M2.3 Implement essential future waiver/add-drop policy in real priority order with shared pool and repeated passes, reflecting actual league rules; no speculative manager trades or discretionary adds. GATE: contested pickup, bye, shortage and release/reentry tests.

M2.4 Implement dynamically configured championship and consolation brackets including byes, single-week first rounds and two-week championship where applicable. GATE: bracket entrants, pairings, advancement and final placements reconcile against fixtures.

M2.5 Build one complete deterministic scenario path and output per-team records for all 14 clubs. GATE: every path ends with coherent, legal results and no ownership duplication.

M2.6 Add provisional probabilistic player-score draws behind a swappable interface solely to exercise repeated complete league paths; never describe provisional distributions as calibrated. GATE: repeated seeded runs, baseline report and clear provisional-method labeling.

#### M3 — Empirical forecast uncertainty and high-performance Monte Carlo

M3.1 Build reproducible historical player-week pregame projection versus actual dataset and provenance checks. GATE: leak tests and documented usable sample sizes by week/position/projection level.

M3.2 Compare pooled/position/projection-conditional empirical, parametric and hybrid error models using temporally held-out scoring and calibration, including tail/zero behavior. GATE: documented selection decision or explicit insufficiency.

M3.3 Implement approved draw model, conditional mean bias correction only if validated, and deterministic path-indexed random numbers with matched baseline/scenario player-week draws. GATE: seeded replay and cross-worker equivalence.

M3.4 Implement full-league tallies, playoff/championship/placement probabilities, confidence intervals and all-team stopping criteria; test known toy probabilities and coverage. GATE: transparent intervals and convergence diagnostics for all 14 teams.

M3.5 Optimize hotspots with compact state arrays, limited allocations, safe multi-core worker batches and deterministic aggregation; compare exactly with reference paths. GATE: correctness equivalence plus measured speed/memory benchmarks.

M3.6 Add configurable precision, path/time caps, preview versus detailed workflows, progress estimates and scoped checkpoint/resume for long detailed runs. GATE: incomplete runs labeled and resumptions match uninterrupted paths.

#### M4 — Manual multi-team what-if evaluator and fast V(R)

M4.1 Define immutable explicit scenario transactions, roster pins, initial ownership changes, validation and legal roster requirements. GATE: illegal duplicate ownership/invalid inputs fail promptly.

M4.2 Implement scenario completion: all required automatic capacity drops first; then incidental additions under the approved ordinary round-robin priority and V(R) policy. GATE: same-cycle released players can be selected; final roster checks pass.

M4.3 Implement fast replacement-adjusted V(R) over remaining weeks, with projected lineup utility, bye and essential-access heuristics; no nested MC or speculative injuries. GATE: intuitive marginal-value fixture comparisons and timing benchmark.

M4.4 Integrate paired baseline/scenario season runs with identical path IDs; calculate championship/playoff/placement deltas, confidence intervals and roster/lineup explanations for every team. GATE: identical scenario yields zero paired delta, with all-team results.

M4.5 Add CLI scenario inputs and inspectable compact output; reconcile full-league state and snapshot provenance. GATE: an end-to-end manual what-if can be reproduced from a configuration file.

#### M5 — Automated action searches, divided into explicit release slices

M5.1 Implement simple reference enumerator for all legal single trades in a user-defined universe; preserve requested team, partner, players and trade-shape filters. GATE: exhaustive small-universe count matches hand-generated feasible candidates.

M5.2 Add optional V(R) and separate counterparty-attractiveness screens, with disableable screening and full coverage/status reporting. GATE: exhaustive mode never silently removes a legally feasible candidate.

M5.3 Add canonical completed-state fingerprinting, path-to-state mapping and single shared paired MC evaluation per unique final state. GATE: distinct sequences with same completed state produce byte-identical results, including CIs.

M5.4 Implement staged initial/refined MC search evaluation, all-team paired deltas, independent precision/coverage limits, bounded candidate streaming and queryable current-search result dataset. GATE: no generation-order bias; caps yield explicit incomplete status.

M5.5 Add standalone immediate waiver/drop-add enumerator, shared free-agent constraints and waiver-order/availability feasibility diagnostics; keep completion heuristics separate from actual claims. GATE: small exhaustive waiver universe reconciles and no duplicate acquisitions.

M5.6 Add immediate multi-trade chain enumerator with partner/dependency rules, order-sensitive ownership, vacancy-event ledger, all drops before additions and non-round-robin priority by vacancy chronology. GATE: permutation adversarial tests, no artificial tiebreakers, identical paths preserved where relevant.

M5.7 Add streaming options and combined trade/waiver sequences using the same universe/screen/evaluate interfaces, while explicitly scoping speculative in-season behavior out of V1. GATE: cross-action feasibility and end-to-end comparison fixtures.

M5.8 Add configurable presets, optional current-machine preflight benchmark, bounded queues/parallel pipeline, search/progress diagnostics and current-results filtered/all exports. GATE: sequential and overlapping modes match exhaustive reference on tractable searches.

#### M6 — Integrated CLI V1, validation and release

M6.1 Unify refresh, snapshot inspection, baseline forecast, manual scenario, trade search, waiver search, chain/combined search and result export under coherent commands/config. GATE: commands work from clean environment without notebooks or spreadsheets.

M6.2 Build automated unit, integration, property, negative/adversarial and statistical suites; ensure fail-fast errors identify violating snapshot, transaction, team and player. GATE: verified reference/optimized parity and coverage.

M6.3 Measure realistic end-to-end runtime, memory, path reproducibility, convergence and candidate throughput across modes, worker counts and generation order. GATE: documented hardware-specific results and no silent bias.

M6.4 Freeze approved official model/config versions, user guide, data dictionary, assumptions, reproducible examples and troubleshooting. GATE: independent clean-install walkthrough and signoff checklist.

#### M7 — Optional visual dashboard after CLI V1

M7.1 Prototype compact league/transaction summary views against real CLI output. GATE: high-level insights without overwhelming tables.

M7.2 Add clickable trade details with all-team probability changes, uncertainty, lineup and roster explanations, plus configurable filters and precision/status labels. GATE: visuals reconcile exactly to exported underlying metrics.

M7.3 Add what-if editing, run configuration, progress and exports while keeping the engine independent of presentation. GATE: parity with equivalent CLI commands and no hidden model choices.

M7.4 Usability, responsive rendering and performance tests for data-heavy searches. GATE: representative large-result collection remains usable without inaccurate or incomplete visual claims.

Cross-milestone release discipline: Every task must state its input contract, output artifact, tests and expected behavior on invalid input. Run a minimal end-to-end smoke path after each relevant change, and update this master specification with actual implemented behavior. Benchmark before adopting complex optimization; any optimization must match reference feasible sequences, final states and path-indexed outputs. M0 is currently the next unstarted milestone; every later milestone above is planned, not implemented.

### 12.2 Practical development method

Each increment is a runnable vertical slice. Start with the clean repository and read-only ESPN diagnostic; once actual data is verified, create minimal canonical snapshot, then the complete league path, then upgrade its statistical and roster policies without changing external behavior or data contracts unnecessarily. At each checkpoint, write tests, benchmark end-to-end behavior, document assumptions and decide whether to promote the new algorithm. A toy fixed-roster unit test may support development but is never presented as the first full simulator product.

### 12.3 Immediate first-sprint checklist

[ ] Establish clean repository, Python environment, league_id/season config and secure credential loading.

[ ] Connect a read-only ESPN diagnostic to the actual 2026 league; retrieve team/league/scoring/roster metadata.

[ ] Probe future player-week projections, free-agent IDs/ownership, waiver rules, regular-season and postseason settings; reconcile all league-critical counts.

[ ] Examine a limited sample of prior ESPN seasons for player-week actual and projected scores and pregame-vs-restated forecast provenance.

[ ] Publish a data dictionary, machine-readable coverage checks, sanitized examples and go/no-go gaps; only then finalize M1 canonical input schema.

### 12.4 Primary risks and mitigation

R1 ESPN endpoints or historical forecasts unavailable/revised: verify raw fields and provenance; flag unsupported assumptions, do not quietly import third-party means. R2 waiver/bracket rule ambiguity: test actual ESPN league config and synthetic edge cases before official forecasting. R3 runtime explosion: compact compiled paths, parallel batches, selective logging, staged scenario screening. R4 weak roster value evidence: provisional policy with controlled comparisons and explicit limitations. R5 hindsight/model leakage: immutable as-of snapshots, versioned replays and sealed test periods. R6 document/UI scope growth: work from this single specification; no frontend or scheduled background collection until core evidence and product merit it.

### 12.5 Maintaining this document as actual model documentation

Status labels are prospective until code, tests, benchmarks and source evidence exist. For each implemented subsection, replace the intended-method description or supplement it with exact behavior, algorithms, equations, input/output contracts, verification references, limitations and version. Change log and decisions can be retained in source control or the historical archive but should not reappear as a chronological 76-item appendix here. This document remains the authoritative description of current approved functionality and its development plan.
