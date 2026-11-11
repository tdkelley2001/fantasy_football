# LW2.1 Partial-Week Evidence and Simulation Contract

Status: **IMPLEMENTED — REVIEW PENDING, 11 November 2026**. Governing requirements: the LW2.1 authorization, the LW1 scoring-state addendum in `MASTER_SPEC.md`, and the fail-closed evidence rules in `LIVE_WEEK_SCORING.md`. This milestone changes no Monte Carlo mathematics and does not authorize LW2.2.

## Scope and acceptance contract

Input: one immutable schema-v4 snapshot plus its captured ESPN sources, a current scoring period, complete canonical matchup-period membership, and read-only diagnostic observations. Output: a sanitized evidence report and this implementation contract. Invalid, missing, contradictory, or semantically unverified evidence remains an explicit unresolved capability. No published snapshot is mutated.

Acceptance requires deterministic tests for structural evidence classification, missing-versus-zero preservation, exact game-ID status joins, and provenance-bearing fail-closed behavior. It does not require an in-progress simulation result.

## Existing-engine audit

The accepted engine is reusable, but its boundary is a whole unstarted scoring week:

- `season_simulator._preflight` rejects any `LiveScoringState` that is not a safe, fully unplayed V1 boundary.
- `initialize_standings` copies ESPN cumulative W/L/T, points-for, and points-against, after which the weekly engine adds an entire simulated week. It has no as-of cutoff or current-period reconciliation input.
- the player outcome model generates one complete realized score for every player/week in the horizon. It has no fixed-actual or conditional-remaining component.
- `optimize_starting_lineup` constructs the projected-points optimum from the modeled roster. It does not preserve ESPN's observed current lineup and does not accept per-player locks.
- essential transactions execute before each week's lineup is frozen. No action-effective-week or current lock boundary prevents a hypothetical action from changing the current week.
- `resolve_regular_season_week` requires a complete realized score for every frozen starter, totals those complete scores, decides the matchup, and adds the result to copied standings.
- postseason scoring likewise consumes complete weekly scores. Multiweek state can accumulate modeled weekly totals, but it has no verified ESPN contribution from an earlier week of an already-active matchup period.
- scenario evaluation optimizes baseline and hypothetical lineups from the same full-week projection inputs. Without a new boundary it could retroactively replace a player who already played.
- Monte Carlo fingerprints include the canonical snapshot, model, policy, and initial evolving state, but no partial-week evidence identity or fixed-actual vector.
- trade, waiver, unified-action, and Opportunity Explorer flows ultimately reuse the same season/scenario boundary. A separate partial-week engine would risk divergent legality and scoring behavior and is not approved.

The extension point for LW2.2 is therefore a validated initial-week state supplied to the existing deterministic coordinator. Later weeks should continue through the accepted engine unchanged.

## ESPN evidence audit

### Verified live

The authorized 11 November 2026 diagnostic established the following for this league and retrieval context:

- `proTeamSchedules_wl` schedule rows expose ESPN game ID, scoring period, NFL teams, kickoff, `statsOfficial`, `validForLocking`, and `startTimeTBD`; they do not expose the formerly assumed `status` field.
- the public ESPN NFL scoreboard exposes `status.type.name`, `state`, and `completed`. Exact ESPN game-ID joins classified all 14 current games as scheduled. Kickoff time was not used as status evidence.
- week-specific `kona_player_info` exposes source-0/split-1 actual `appliedTotal` and source-1 weekly projection records. The previous configured period had 688 actual records, including 358 explicit zeros. The unplayed current period had no actual records.
- the current league response contains seven matchup rows and 233 roster entries. Roster entries preserve `lineupSlotId`; player-pool and roster copies expose candidate `lineupLocked`, `rosterLocked`, and `tradeLocked` Boolean fields.
- matchup sides expose `totalPoints`, `totalProjectedPoints`, `totalProjectedPointsLive`, `pointsByScoringPeriod`, `rosterForCurrentScoringPeriod.appliedStatTotal`, and roster entry collections.

In the unplayed observation all 1,061 player-pool and all 233 roster-entry copies reported each candidate lock Boolean as false. All 14 matchup sides had numeric zero `totalPoints`, nonzero projection fields, and equal `totalProjectedPoints`/`totalProjectedPointsLive`. This is a useful pregame baseline only; it does not authenticate what any field means after kickoff.

### Verified only structurally or by fixtures

- lock fields are present and Boolean in the unplayed observation, but their player-specific transition timing and legal meaning are not verified.
- `totalProjectedPointsLive` is present, but an unplayed observation cannot establish whether it becomes ESPN's projected final total, a remaining projection, or another UI aggregate during play.
- current matchup and roster score fields are structurally present, but their refresh latency, corrections, bench inclusion, and multiweek accumulation semantics are unverified.
- deterministic fixtures verify missing/zero separation, status contradictions, current/previous period matching, bye context, schedule/scoreboard joins, and unknown-field failure.

### Unavailable or unresolved

- no verified ESPN field separately reports a player's remaining fantasy points.
- no active-game sample yet proves how source-1 `appliedTotal` changes during play or whether it represents a full-game final estimate.
- no active-game sample correlates the three lock fields with UI-permitted substitutions, flex moves, or transaction effects.
- NFL completion does not prove fantasy matchup settlement, standings incorporation, or stat-correction finality.
- player actual-record presence does not prove participation; missing is not zero and can reflect bye, inactivity, delayed data, or absent coverage.

## Proposed canonical contract for LW2.2

LW2.2 should add one immutable, versioned partial-week companion rather than overloading `PlayerWeek` projections or replacing `LiveScoringState`. Names below are contract proposals, not implemented schema.

`PartialWeekEvidence`:

- snapshot and source IDs, retrieval interval, season, scoring week, and authoritative matchup-period membership;
- evidence classification and unresolved capabilities;
- a standings cutoff declaring exactly which completed matchup periods are incorporated;
- current fantasy matchup observations and any verified prior contribution in a multiweek matchup;
- one `PartialPlayerState` per relevant rostered player;
- one `ObservedLineupAssignment` per roster entry, preserving team, configured slot, starter/bench/reserve class, and source;
- the complete NFL game-state map used by those players.

`PartialPlayerState` must distinguish:

- `actual_points`: confirmed numeric, confirmed zero, unavailable, or ambiguous;
- NFL game state: completed, in progress, scheduled, exceptional, or unknown;
- observed fantasy slot and eligibility;
- lock state: verified locked, verified changeable, or unresolved, with evidence source and observation time;
- ESPN projection value and a semantic classification: verified pregame full-game mean, verified live final estimate, verified remaining mean, or unresolved;
- an optional remaining-performance model reference. A numeric remainder is forbidden unless its semantics and calibration are approved.

`PartialWeekSimulationInput` must contain a validated evidence digest, fixed actual components, uncertain remaining components, the legal frozen/changeable lineup partition, standings cutoff, matchup carry-in totals, and the future-week canonical snapshot. Every player/week must appear in exactly one scoring category: fixed complete, fixed-so-far plus approved conditional remainder, wholly uncertain unstarted, or excluded bench/nonparticipant. Duplicate membership is an invariant violation.

`PartialWeekSimulationOutput` should add fixed-versus-simulated team-score components, the evidence digest, unresolved capability labels, and current-period reconciliation diagnostics to the existing path/team aggregates. It must never relabel a partial run as a standard V1 run.

## Scoring and uncertainty contract

For a future approved engine, team score on a path is:

`verified matchup carry-in + sum(verified fixed starter actuals) + sum(sampled approved remaining components)`.

The following rules are mandatory:

- completed players contribute their confirmed actual exactly once and receive no draw;
- unstarted, legally starting players may use the accepted full-game outcome model only when the ESPN projection retains verified full-game-mean semantics;
- in-progress players require a conditional remaining distribution. `projection - actual`, truncation at zero, or an unconditional redraw is not authorized;
- early injury does not justify forcing the remainder to zero without verified completion/injury semantics;
- explicit actual zero remains a fixed zero when complete and a real observed-so-far zero when in progress; missing never becomes zero;
- kicker and defense/special-teams outcomes follow the same fixed/remainder partition but require position-appropriate conditional calibration;
- the existing independent-player assumption may be retained only as a disclosed provisional limitation for unstarted players. In-game score, clock, teammate/opponent, defense, and game-script correlations make conditional remainder independence especially questionable and require evaluation before promotion.

Calibration of an in-progress model is deferred. An implementation-ready research dataset would need immutable intragame observations keyed by player, game state/clock, actual-so-far, ESPN live projection, final score, position, and pregame projection. Retrospective final ESPN rows cannot reconstruct those vintages.

## Lineup-lock and legality model

Observed ESPN slot assignment is authoritative evidence of the current lineup, not permission to optimize it. Future legality requires a player-specific determination minted from validated source bytes:

- `verified_locked`: the player cannot be moved for the current scoring period;
- `verified_changeable`: the player can legally move among eligible open slots at the observation boundary;
- `unresolved`: no current-week recommendation or hypothetical move may depend on changing that player.

Kickoff or NFL state may corroborate a lock field but must not silently replace it. Flex eligibility still comes from canonical player/slot configuration. A legal lineup change must preserve every locked assignment, ownership, reserve restrictions, slot capacity, eligibility, and the observed score components already earned. Until active observations verify ESPN lock semantics, current-week optimization and lineup advice fail closed.

## Standings, matchup, and postseason reconciliation

A partial-week engine cannot copy standings blindly. It must prove the standings cutoff and separately carry live matchup totals. Regular-season W/L/T changes occur only when the fantasy matchup is authoritatively settled.

For a multiweek matchup, the input must identify prior scoring weeks in the same matchup period and carry their verified team totals exactly once. Starting in week two with zero carry-in is forbidden. Postseason bracket advancement remains blocked until the complete multiweek matchup is settled; current probabilities may simulate the remaining aggregate margin without advancing the bracket prematurely.

Stat corrections require a new immutable refresh. They never mutate an older snapshot or result. A completed NFL game with `statsOfficial=true` still does not authenticate ESPN fantasy settlement or correction finality.

## Integration by capability

- Baseline and weekly matchup simulation: use fixed current evidence plus an approved remainder model, then reuse the existing engine for later weeks.
- Current versus optimal lineup: report the observed lineup; optimize only verified-changeable assignments while pinning locked players. Otherwise mark current-week optimization unsupported.
- Trades, waivers, and free agents: an action may affect the current week only with verified processing/effective timing and lock legality. Future-only evaluation must preserve current fixed points and lineup assignments.
- Opportunity Explorer and scenario evaluation: include the partial evidence digest and action-effective week in state fingerprints. Paired scenarios share identical fixed actuals and path-indexed remaining shocks.
- Playoff/championship probabilities: initialize from reconciled standings and current matchup carry-in; never count the live matchup twice.
- Multiweek postseason: simulate only the unresolved aggregate remainder and delay graph advancement until the matchup period completes.

Unsupported current-week operations fail closed without preventing clearly future-week analysis whose effective boundary is independently verified.

## Performance and reproducibility

The fixed actual vector is common to every path and should be precomputed once. Remaining draws retain path-indexed keys extended by an evidence/model contract version; worker count, batching, checkpoint/resume, and generation order must remain equivalent. Baseline and hypothetical scenarios must reuse fixed evidence and paired remaining draws. The evidence digest, model ID, standings cutoff, carry-in totals, lock determinations, and action-effective boundary belong in fingerprints. Benchmark before adding conditional-distribution caches or new parallel machinery.

## LW2.2 implementation-ready scope and gates

LW2.2 may begin only after independent approval of this contract and new active-game evidence that establishes:

1. source-0 actual behavior for scheduled, in-progress, completed, inactive, bye, kicker, and defense players;
2. source-1 projection semantics and update behavior during play;
3. player-specific lock-field correlation with permitted ESPN UI actions;
4. current matchup score and multiweek carry-in reconciliation;
5. a selected and temporally evaluated conditional remaining-performance method, or a deliberately narrower scope that excludes in-progress players.

The first implementation package should add the canonical partial evidence schema, strict validation/serialization, source translation, and a deterministic reference combiner with hand-checkable fixtures. It must not initially modify Monte Carlo. A second package may extend the deterministic coordinator behind an explicit partial input, prove equivalence with V1 when all players are unstarted, and only then add path generation and application/action integration.

Current blockers are `verified_in_game_projection_semantics`, `conditional_remaining_outcome_model`, `verified_player_lineup_lock_semantics`, `verified_fantasy_matchup_score_reconciliation`, `verified_standings_cutoff`, and `verified_stat_finalization`.

## LW2.2A implemented foundation

Status: **IMPLEMENTED — REVIEW PENDING, 11 November 2026**. Independent acceptance of LW2.1 and explicit authorization of this narrower foundation permit this package without promoting unresolved live semantics.

Input contract: a validated immutable `LeagueSnapshot` plus `PartialWeekEvidence` tied to its snapshot ID, league, season, retrieval interval and referenced source payload hashes. `PartialPlayerState` separates completed fixed, in-progress actual-so-far, approved unstarted, missing, and nonparticipating states. `ObservedLineupAssignment` derives role and eligibility from canonical slot rules and preserves player-specific lock authority. `PartialMatchupEvidence` preserves current-week observed totals, prior-week carry-in, score authority and settlement authority. `StandingsCutoffEvidence` explicitly records settled period IDs and whether the current period is excluded.

`validate_partial_week_evidence` validates preservable records. `require_executable_partial_week_evidence` additionally rejects unresolved capabilities, missing scores, unresolved locks, unapproved in-progress remainders, unverified observed totals and unverified standings cutoffs. Period membership must agree with canonical schedule evidence; independently supported complete membership can include weeks outside the snapshot horizon. Mid-period evidence requires verified carry-in. Authority labels assert the provenance supplied by the caller; they do not independently authenticate ESPN bytes or establish live semantics.

`validate_proposed_lineup` checks exact roster coverage, ownership, eligibility, configured capacity and frozen assignments. Only verified-changeable assignments may move. Started players cannot be marked changeable. Unresolved locks never grant permission. Starter/bench/reserve roles come from configured canonical slot kinds.

Targeted validation follow-up to `6f9f46a`: observed player/team/slot assignments must exactly match the immutable canonical `RosterEntry` records, and observed occupancy must obey configured capacities (including canonical snapshot validation). Individually eligible replacement slots do not establish observed truth. Hypothetical assignments remain separate and may differ only through `validate_proposed_lineup`. Canonical rosters are as-of retrieval records, not historical weekly lineups. Execution therefore additionally requires each assignment's source to include the `mRoster` view and either an explicit matching `scoringPeriodId`, or an unparameterized current roster request with the snapshot's live current scoring period matching the companion period. Unknown or mismatched timing is preservable but fails execution; the simulation horizon alone never establishes roster timing. This gate verifies recorded request context, not independently authenticated live ESPN semantics.

Follow-up regression evidence: `.venv\Scripts\python.exe -m pytest tests/test_partial_week.py tests/test_canonical_snapshot.py tests/test_weekly_engine.py -q` — **113 passed**. The pregame fixture now directly compares the composer with `resolve_regular_season_week` using the same snapshot rules, identical confirmed starter assignments and identical realized player values; all team totals agree. Tests also cover eligible forged starter/bench slots, canonical overcapacity, unchanged observations, and missing or mismatched roster-period context. These establish **Verified by tests** behavior; no additional live ESPN evidence was collected.

`compose_partial_week_scores` accepts legal proposed assignments and explicit `DeterministicPlayerValue` inputs. Completed starters contribute fixed actuals with no input; unstarted starters require a full-game realization; in-progress starters require an approved remaining realization. Negative values are permitted. Bench and reserve assignments contribute no starter points. Unused or duplicate inputs fail. Team output exposes carry-in, fixed and remaining components separately, sums each once, and reconciles fixed starter totals against observed current-week team scores. No distribution or projection subtraction is implemented.

`partial_week_to_json` and `partial_week_from_json` use a separate artifact-version-1 JSON envelope with deterministic ordering and SHA-256 checksum. Deserialization preserves unresolved records; consumers must validate against the referenced snapshot before use. The checksum detects accidental modification, not malicious replacement of the checksum. Existing snapshot schema-v2/v3/v4 documents, identities, stored results and V1 fingerprints are unchanged.

Evidence classification: foundation behavior is **Verified by tests** using synthetic hand-checkable fixtures. No new ESPN field is **Verified live** by this package. Active-game projection semantics, lock permissions, fantasy settlement, carry-in and standings-cutoff translation remain **Unverified**. Automatic live partial-week execution remains **Unsupported**. There is no ESPN translator, network request, season-engine integration, optimizer, API or frontend change.

Acceptance evidence: canonical, adapter, snapshot storage/refresh/CLI, live-scoring, deterministic season/weekly, scenario, Monte Carlo and application regressions are run alongside the new foundation tests. Exact counts and commands are reported with the implementation handoff. No static type checker is configured in this repository; Ruff and Python compilation are used for the new modules.

Final verification: **318 passed**, one existing Starlette/AnyIO deprecation warning, using `.venv\Scripts\python.exe -m pytest tests/test_partial_week.py tests/test_canonical_snapshot.py tests/test_espn_adapter.py tests/test_espn_adapter_cli.py tests/test_snapshot_store.py tests/test_snapshot_refresh.py tests/test_snapshot_quality.py tests/test_snapshot_cli.py tests/test_live_scoring.py tests/test_season_simulator.py tests/test_weekly_engine.py tests/test_scenario_evaluator.py tests/test_monte_carlo.py tests/test_app_service.py -q`. The initial sandbox run encountered temporary-directory/worker access failures; the authorized rerun passed. Ruff check/format, module compilation and `git diff --check` pass. Frontend checks are not affected because no frontend or API files change.

Proposed LW2.2B scope (requires approval): integrate an explicitly validated partial input into the existing deterministic coordinator, reconcile standings and full matchup aggregates, preserve fixed assignments and scores through future weeks, and prove equivalence on wholly unstarted inputs. Add source translation only after live evidence verifies each promoted field. Keep in-progress conditional distributions and Monte Carlo integration behind their separate evidence and statistical gates. Do not enable current-week recommendations until action timing and lock semantics are verified.

## LW2.2B deterministic season integration

Status: **IMPLEMENTED — REVIEW PENDING, 11 November 2026**, under explicit LW2.2B authorization following accepted `75dcae6`.

The existing `simulate_deterministic_season` takes optional `partial_week=DeterministicPartialWeekInput(evidence, lineup, values, prior_postseason_scores=())`. Evidence is the immutable LW2.2A companion; lineup contains all roster assignments, including unchanged observations or separately validated legal changes; values are explicit full-game or approved remaining realizations, never distributions. The ordinary score scenario contains subsequent weeks only. Providing first-week scenario scores as well is rejected. The output retains the existing deterministic result structure, with a `partial_week:v1:<sha256>` configuration-provenance entry covering the complete companion and sorted supplied assignments, realizations and prior scores. Existing V1 calls add no entry and retain their fingerprints and output schemas.

Before scoring, the composer validates snapshot identity, source/timing authority, locks, score semantics and observed-score reconciliation. Evidence authority and standings cutoff must be verified. The cutoff must explicitly exclude the current period, end immediately before its first week, include known preceding configured periods, and never mark a known current/future period settled. This is an explicit supplied evidence assertion: the implementation cannot independently authenticate historical ESPN standings totals. If supplied live metadata describes a different current period or lacks independently supported membership, execution fails. Canonical snapshots without live metadata still require the accepted explicit roster request-period context and canonical membership contract.

First-week modeled transactions are disabled. Hypothetical initial ownership/slot changes or a transaction ledger are rejected; supplied legal lineup-only changes go through the accepted validator. The coordinator builds frozen observed starters rather than optimizing the first week. Empty observed slots are labeled `observed_unfilled_slot` where an eligible owned player exists, without inventing an optimal-lineup explanation; demonstrably absent eligible players retain the existing vacancy reason. Regular results use the existing weekly resolver, with only its positive-projection availability requirement disabled for these already-validated starters (completed players can have zero/negative projections). Ownership, eligibility, capacities and canonical projection values remain checked. Subsequent weeks use the existing transaction, optimizer, scoring and postseason policies without retaining current-week locks.

For postseason starts, seeded participants must agree with current matchup evidence. Explicit canonical byes contribute no matchup score; deterministic values for bye players are unused and rejected. Prior carry-in is not added to the current-week score: the caller supplies every preceding current-period `WeeklyTeamScore`, whose finite values and exact team/week coverage must reconcile to the companion's verified aggregate carry-in. These contributions are replayed through `apply_postseason_team_scores`, using authoritative full period membership even when the canonical horizon excludes earlier weeks. The current composed week and later ordinary weeks enter the same accumulator. Brackets advance only when the complete period is present, using existing configured tie/seed rules.

Supported: partial single-week regular-season matchups; first-round postseason starts with explicit participant/bye evidence; multiweek first-round carry-in with complete preceding contributions; future periods resolved normally. Unsupported inputs fail explicitly: multiweek regular-season periods, missing or mismatched carry history, unknown current roster timing, missing participant/bye evidence, later-round starts requiring unavailable earlier bracket results, unverified standings incorporation, current-week transactions and unresolved conditional remainders. No historical bracket winners, standings correction, carry breakdown, or remaining-performance model is inferred. A partial result remains the existing deterministic coordinator's result, identified by its partial provenance; it does not enable partial inputs in Monte Carlo or applications.

Evidence classification: integration and equivalence are **Verified by tests** using hand-checkable synthetic fixtures. No new ESPN live-data validation was performed. Live source translation, lock semantics, standings incorporation and conditional remainder calibration remain **Unverified**. Automatic live partial-season execution and current-week action recommendations remain **Unsupported**.

Final LW2.2B verification: **340 passed**, one existing Starlette/AnyIO deprecation warning, in 22.51 seconds. Command: `.venv\Scripts\python.exe -m pytest tests/test_partial_season.py tests/test_partial_week.py tests/test_canonical_snapshot.py tests/test_weekly_engine.py tests/test_postseason.py tests/test_season_simulator.py tests/test_weekly_transactions.py tests/test_scenario_evaluator.py tests/test_monte_carlo.py tests/test_monte_carlo_parallel.py tests/test_monte_carlo_execution.py tests/test_monte_carlo_precision.py tests/test_app_service.py -q`. The new integration file contains 19 tests, including full-season all-unstarted equivalence under identical lineups/no first-week acquisitions, fourteen-team postseason/bye equivalence, fixed zero-projection starters, later-week reoptimization, cutoff and carry failures, replay/order invariance and actual-current-period guards. Existing V1 and Monte Carlo tests were not modified. Ruff and formatting checks pass on the new/extended foundation and coordinator modules; compilation and `git diff --check` pass. Legacy formatting in the narrowly edited weekly scorer and vacancy enum module is retained. No static type checker is configured, and no frontend files or application contracts changed.

## LW2.3A Monte Carlo integration for unstarted current players

Status: **IMPLEMENTED — REVIEW PENDING, 11 November 2026**, under explicit authorization following accepted `432a85f`. Input: optional immutable `MonteCarloPartialWeekInput` in `MonteCarloConfig.partial_week`, containing the LW2.2A companion, complete legal supplied lineup and optional LW2.2B prior postseason team/week contributions. Output: the existing Monte Carlo path/batch/precision artifacts, using existing aggregation. Invalid input raises a path-identified `MonteCarloError` during execution; invalid fingerprint evidence also fails validation. No additional ESPN operations or application/UI integration is included.

Before generating a path, every rostered current player must be `UNSTARTED` with `APPROVED` full-game projection semantics. The approved value must equal that player's nonmissing canonical effective projection, because the unchanged model draws from canonical player-week inputs. The gate intentionally includes rostered bench and reserve players; uncertain status cannot be hidden by a proposed lineup change. Completed, in-progress (even with an approved deterministic remainder), missing and nonparticipating current scoring states fail this milestone's gate. Executable evidence, legal assignments and every LW2.2B standings, source timing, membership, carry and action restriction remain required. Current-week observed/verified locks continue to constrain supplied assignments.

Each model invocation generates its existing complete scenario once. The mapper validates current-week draw records, selects legal non-bye starter values, constructs `DeterministicPlayerValue` records, and removes all first-week scores from the ordinary scenario before invoking the same deterministic season coordinator with `partial_week`. No draws, random keys, conditional distributions, correlation assumptions or later-week mathematics change. The summary keeps the complete original scenario digest, enabling paired-lineup comparisons to demonstrate identical path-indexed draws. This is not permission for unsupported current-week transactions or altered initial rosters.

The simulation fingerprint gains a partial-only versioned content entry covering the complete serialized evidence, canonicalized supplied assignment order and prior postseason history. The complete companion identity includes source references/digests, retrieval interval, authorities, observed assignments, score and cutoff evidence; a snapshot/source digest alone cannot hide changed companion content. Existing run identity, workers, batch combination, precision evaluation and checkpoint recovery inherit this fingerprint. Any incompatible evidence or assignment change invalidates recovery. Runs with no partial input retain exactly the former payload and accepted golden outputs.

Equivalence is guaranteed under the same snapshot, outcome model, seed/path index and policies when supplied current starters match the V1 optimized assignments and no first-week acquisitions alter ownership. Regular scores, matchup results, standings, postseason outcomes, path outcomes and aggregated probabilities then agree. The first-week transaction audit and partial-run provenance remain intentionally distinct. Other legal observed lineups can produce different results from V1 while retaining the same draw digest. Later weeks reoptimize normally. Batch size/worker count do not affect any fixed path's outcome; precision checkpoint schedules can still change the number of paths selected by the existing stopping rule, so batch-schedule comparisons use runs reaching the same path cap.

Evidence classification: the integration, equivalence and reproducibility claims are **Verified by tests** using synthetic fixtures. No ESPN field or behavior is newly **Verified live**. Live projection/lock/standings authority remains **Unverified**. Completed/in-progress current players, conditional remainder sampling, automatic live translation and current-week action recommendations remain **Unsupported**. Existing LW2.2B unsupported history and multiweek regular-season cases remain unsupported. Further milestones require independent review; work stops after LW2.3A.

Final LW2.3A verification: `.venv\Scripts\python.exe -m pytest tests/test_partial_monte_carlo.py -q` — **26 passed** in 5.00 seconds. Affected regressions: `.venv\Scripts\python.exe -m pytest tests/test_partial_monte_carlo.py tests/test_partial_season.py tests/test_partial_week.py tests/test_canonical_snapshot.py tests/test_weekly_engine.py tests/test_postseason.py tests/test_season_simulator.py tests/test_weekly_transactions.py tests/test_player_outcomes.py tests/test_scenario_evaluator.py tests/test_monte_carlo.py tests/test_monte_carlo_parallel.py tests/test_monte_carlo_execution.py tests/test_monte_carlo_precision.py tests/test_app_service.py -q` — **374 passed**, one existing Starlette/AnyIO deprecation warning, in 26.63 seconds. The initial sandbox test attempt could not access Windows worker pipes or temporary checkpoint directories; authorized reruns passed. Worker tests cover 1/2/3 workers and different task sizes; recovery tests cover sequential and parallel cancellation/resume. Accepted V1 configuration and complete batch-result goldens were obtained by executing the fingerprint/path code from `432a85f`. No existing regression tests or outcome models were modified. Ruff check/format, Python compilation and `git diff --check` pass; no static type checker is configured and no frontend files changed.
