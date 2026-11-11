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
