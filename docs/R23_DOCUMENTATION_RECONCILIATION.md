# R2.3 technical documentation reconciliation

Baseline: independently accepted R2.2 `a7c0ff41778673ab7809b95b7b500e8db0bc552b`. Scope is WR-002 technical reference reconciliation and a concise [architecture overview](architecture/overview.md), governed by [MASTER_SPEC sections 2–4, 8–9 and 12](MASTER_SPEC.md#2-system-architecture-and-execution-lifecycle), standing rules and accepted [R1 inventory](R1_REPOSITORY_AUDIT.md). No source/schema/model/API/persistence/dependency changes or historical archive migration are authorized. R2.3 awaits independent PR review; this report does not replace current [status](../README.md#current-capabilities) or the [backlog](BACKLOG.md).

## Bounded statement inventory

Classification describes documentation, not ESPN verification. **Verified by tests** concerns behavior under fixtures; existing **Verified live** observations remain bounded to their original retrievals. No live evidence was collected here.

| ID | Statement / classification at baseline | Source and test evidence | Reconciliation |
|---|---|---|---|
| R23-01 | Canonical guide title/new-publication/serializer says v3; storage intro says new v3/read v2. **Outdated**, contradicted by later v4 paragraphs. | [model constants](../src/fantasy_football/canonical/model.py), [serialization](../src/fantasy_football/canonical/serialization.py), [publication gate](../src/fantasy_football/snapshot_store.py); canonical/storage/adapter tests. | State new v4/read 2,3,4; reject v1/unknown; separate SQLite snapshot schema 1 and partial artifact 1. |
| R23-02 | Immutable bytes/UUID/checksum/raw provenance and no migration. **Accurate**, but historical compatibility wording implies all documents authorize all consumers or typed reserialization always reproduces old optional-field omissions. | `SnapshotStore.load` returns original verified `canonical_json`; serializer materializes typed defaults; historical v2/v3 tests and legacy-v4 adapter/service tests. | Preserve stored byte identity; distinguish typed serialization from stored bytes and readable from executable/protected. No new migration promise. |
| R23-03 | M1/M2 work, M3.5 resume and M6/M7 packaging described in future tense. **Accurate historical scope**, misleading as current status. | Season, transaction, checkpoint and local-server modules; accepted later sections in the same contracts. | Add explicit historical labels/current pointers, clarify local M3.6 engine resume versus HTTP interruption; preserve original measurements/gates. |
| R23-04 | Projection policy table uses `projection_status`/`effective_projection_source`. **Outdated field names**. | `PlayerWeek.projection_class` / `effective_source`, validation and adapter tests. | Correct technical field names without changing missing/zero policy or historical observations. |
| R23-05 | Normal and empirical families share immutable projection inputs but handle missing/zero draw records differently. **Accurate**, not clearly separated from lineup availability. | [player_outcomes.py](../src/fantasy_football/player_outcomes.py), [optimizer](../src/fantasy_football/lineup_optimizer.py), [weekly engine](../src/fantasy_football/weekly_engine.py); player-model tests. | Explain complete universe, unused draws, positive-projection selection, empirical zero records and signed realized outcomes. HTTP only exposes Normal; models remain provisional. |
| R23-06 | Missing policy says unavailable for stochastic scoring; Normal generates zero-mean records with potentially positive dispersion. **Ambiguous policy/implementation relationship**. | Normal generation and ordinary weekly availability checks; `test_zero_missing_and_negative_effective_values_keep_distinct_source_records`. | Preserve approved policy, disclose unused-record distinction and request independent interpretation below. Do not silently change policy or draws. |
| R23-07 | LW2.1 audit/proposed names read as if no integration exists; later accepted packages implement it. **Historical/proposal**, superseded in bounded scope. | [partial_week.py](../src/fantasy_football/partial_week.py), companion serialization, deterministic/MC partial paths and tests. | Add current capability matrix: composer versus deterministic season versus unstarted-only MC versus browser. Retain proposal names and delivery-time notes as history. |
| R23-08 | Cutoff, roster timing, locks, full membership/carry and prior postseason history restrictions. **Accurate**; broad “partial-week supported” would overclaim. | Composer execution gate, `season_simulator._prepare_partial_week`, prior score accumulation, MC pregame gate; partial tests. | Make restrictions visible at entry; distinguish caller assertions from independent authentication. Completed/in-progress deterministic inputs do not authorize their MC sampling or live translation. |
| R23-09 | API introductory refresh requires explicit week; server described only as development; route table omits refresh routes and is interrupted by prose. **Outdated/contradictory**. | [http.py](../src/fantasy_football/app/http.py), [contracts.py](../src/fantasy_football/app/contracts.py), server and refresh tests. | Repair exact `/api/v1` route table, nullable override/default, public 1.0 versus other versions, built assets, strict DTO/model/partial limitations. Retain old Python-only setup with historical warning. |
| R23-10 | Durable requests/results, coarse cancellation, retained queries, lease and interrupted startup; refresh jobs look similar. **Accurate**, distinction needed. | [background.py](../src/fantasy_football/app/background.py), [refresh.py](../src/fantasy_football/app/refresh.py), background/refresh tests. | Separate transient refresh jobs from durable analysis runs; completed lifecycle need not imply analytical completeness; terminal-run retention is not snapshot deletion or engine resume. |
| R23-11 | R2.2 awaiting review and configuration guide still outstanding in current summary. **Outdated**, independent acceptance supplied. | R2.3 authorization and accepted main `a7c0ff4` ([PR #115](https://github.com/tdkelley2001/fantasy_football/pull/115)). | Record R2.2 acceptance, R2.3 pending; retain M8.4 release gate and original delivery statements. |
| R23-12 | Live lock/settlement/remainder meaning and authenticated pregame calibration. **Not fully verifiable** from source/fixtures; explicitly unresolved. | Existing LW1/LW2 evidence tables and historical research provenance. | Preserve **Unverified/Unsupported** labels; do not infer from game time, score presence or a fixture. No new live claim. |

## Unresolved semantic question

**Subsequent disposition:** the explicit WR-022 authorization resolves the policy question: missing-projection outcomes must be deterministically zero in every supported family. The [separate correction record](MISSING_PROJECTION_ZERO_CORRECTION.md) identifies implementation, compatibility, checks and review state. This supersedes the unresolved policy status below; the original R2.3 inventory and question are retained as historical evidence. Implementation acceptance is pending independent WR-022 PR review, not claimed by this disposition.

R23-06 requires independent review of the approved phrase “unavailable for ... stochastic scoring” in [MISSING_PROJECTION_POLICY](MISSING_PROJECTION_POLICY.md#decision). Ordinary V1 does not select nonpositive effective-projection players; nevertheless Normal generation emits records for every in-horizon player/week and can assign a nonzero unused value to a missing/zero projection (with positive base dispersion). Empirical emits deterministic zero records for those classes. Existing tests preserve this accepted model behavior. There is no demonstrated ordinary team-score discrepancy from the unused records, but a literal policy prohibition on any random record would disagree with implementation. R2.3 cannot decide that interpretation, amend an approved requirement or change draws. Any clarification or numerical correction needs separate independent disposition and existing fingerprint/golden compatibility review. The report records the question under WR-002; it does not auto-authorize new work.

MASTER_SPEC research requirements for empirically evaluated distributions, calibrated tails/zeros, temporal evidence and later improvements remain binding. Provisional implementation acceptance is not a claim those scientific/model-release gates are all satisfied. No other new implementation-versus-approved-requirement discrepancy was established in this bounded inspection; this is not a full numerical re-audit.

## Verification and limitations

Executed:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_documentation_links.py tests/test_contributor_documentation.py tests/test_technical_documentation.py tests/test_repository_security.py -q -p no:cacheprovider
```

**119 passed**. Coverage includes Markdown/image targets, relevant anchors in all changed references, historical accessibility/R1 inventory, canonical/source version constants, exact `/api/v1` methods/paths extracted from route decorators, refresh DTO shape, public Normal-only/whole-week inputs and opt-in partial entry-point defaults. The initial documentation run found one field-format mismatch (`season` had its constraint inside the code span); it was corrected before the passing run.

```powershell
.venv\Scripts\python.exe -m pytest tests/test_canonical_snapshot.py tests/test_snapshot_store.py tests/test_espn_adapter.py tests/test_live_scoring.py tests/test_player_outcomes.py tests/test_m33_player_outcomes.py tests/test_weekly_engine.py tests/test_season_simulator.py tests/test_partial_week.py tests/test_partial_season.py tests/test_partial_monte_carlo.py tests/test_monte_carlo.py tests/test_monte_carlo_parallel.py tests/test_monte_carlo_execution.py tests/test_monte_carlo_precision.py tests/test_app_service.py tests/test_background_runs.py tests/test_snapshot_refresh.py -m "not windows_process" -q -p no:cacheprovider
```

**413 passed**, one existing Starlette/AnyIO alias deprecation warning, 32.61 s. Run outside the restrictive Windows sandbox to permit disposable temp stores and existing multiprocessing worker tests. All inputs are synthetic/mocked; Windows real-process recovery is excluded. These tests establish implementation/compatibility behavior, not live ESPN semantics.

```powershell
.venv\Scripts\python.exe -m ruff check tests/test_technical_documentation.py tests/test_contributor_documentation.py
.venv\Scripts\python.exe -m ruff format --check tests/test_technical_documentation.py tests/test_contributor_documentation.py
git diff --check
```

All passed. Source comparison against accepted R2.2 confirms `MASTER_SPEC.md`, `ROADMAP.md` and `R1_REPOSITORY_AUDIT.md` are byte-equivalent after normalizing checkout line endings; all production source, dependency/configuration files and historical assets remain unchanged. Only Markdown and documentation-focused tests change. No numerical policy, schema, API, seed, fingerprint, stored artifact or compatibility handling is modified.

Not executed: full repository regression, browser/frontend build, dependency install, clean-machine workflow, live ESPN, private database access or real-process recovery. Static route/DTO checks verify implemented shape, not a running deployment. The R23-06 interpretation and existing source/model gates remain limitations; no broader archive or acceptance-gate migration is performed. M8.4 release remains pending.

## Files changed

- New [architecture overview](architecture/overview.md) and this bounded reconciliation report.
- Technical references: [canonical](DATA.md#canonical-validation-and-serialization), [snapshot storage](DATA.md#immutable-storage), [missing policy](MISSING_PROJECTION_POLICY.md), [outcome models](PLAYER_OUTCOME_MODEL.md), [Monte Carlo](MONTE_CARLO.md), [season](SEASON_SIMULATOR.md), [LW1](DATA.md#live-and-temporal-evidence), [partial-week contract](LW2_PARTIAL_WEEK_CONTRACT.md), [application service](APPLICATION_SERVICE.md), [run management](APPLICATION_SERVICE.md#analysis-lifecycle), [backend handoff](APPLICATION_SERVICE.md#api-evolution).
- Navigation/status: [README](../README.md), [index](../README.md#understand-the-system), [status](../README.md#current-capabilities), [backlog](BACKLOG.md).
- Documentation tests: [contributor/anchor checks](../tests/test_contributor_documentation.py), new [technical source-contract checks](../tests/test_technical_documentation.py). Existing engine and application tests are unchanged.
