# Developer verification and documentation maintenance

Use this guide to select checks, not to waive an approved acceptance gate. [AGENTS](../../AGENTS.md), [MASTER_SPEC sections 2, 8–9 and 12](../MASTER_SPEC.md#2-system-architecture-and-execution-lifecycle) and applicable [preserved roadmap gates](../ROADMAP.md) remain binding. Coordinate scope/review through [CONTRIBUTING](../../CONTRIBUTING.md); keep actionable work in the [backlog](../BACKLOG.md). Historical test totals are evidence at their stated revision, not today's required count or a reason to skip a regression.

## Environment and reporting

Run commands from the repository root with the locked environment prepared by [developer setup](../getting-started/development.md): Windows/PowerShell for supplied scripts, Python 3.12 and the existing tested Node **24.19.0**/npm frontend toolchain. WR-003's broader Node version-policy mismatch remains open. Do not repair a verification failure by upgrading dependencies, loosening assertions, disabling validation or changing a lockfile without authorized scope.

Record revision/working tree, exact commands, results, warnings, skipped tiers/reasons and limitations in the PR. Distinguish **Verified by tests** from **Verified live**, **Unverified** and **Unsupported**. Tests on an installed checkout do not establish clean-machine setup, live ESPN semantics, real-process recovery or a release decision. Report sandbox/temp/worker permission failures as environment failures; if using a permitted rerun, retain both outcomes rather than changing production rules to bypass them.

## Tier 1: Fast local checks

Use for documentation-only and small edits; then add targeted tests when behavior is affected. Requires installed Python test/Ruff dependencies and Git; no ESPN credentials or frontend build. These checks cover local Markdown/image targets, selected fragments, backlog/source-contract invariants, tracked-data/privacy rules and whitespace. They do not prove analytical correctness, browser rendering, remote-link availability or dependency security.

```powershell
.venv\Scripts\python.exe -m pytest tests/test_documentation_links.py tests/test_contributor_documentation.py tests/test_technical_documentation.py tests/test_repository_security.py -q -p no:cacheprovider
git diff --check HEAD
```

Repository-wide correctness lint is the established narrow gate, not a full style baseline:

```powershell
.venv\Scripts\python.exe -m ruff check --select E9,F63,F7,F82 .
```

Run full Ruff/format checks on newly written or intentionally maintained files when relevant, without reformatting unrelated source. Existing broader lint debt is not permission to ignore new findings. Pytest can create bytecode and temporary files; `-p no:cacheprovider` disables only its cache provider. Ruff can create cache data. These commands do not modify approved source or contact ESPN. Inspect `git status --short` before submitting; keep generated/private files out of the PR.

## Tier 2: Targeted tests

Use the change matrix below to choose existing modules, plus focused positive/negative/adversarial cases for the invariant being changed. For example, adapter mapping work starts with:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_espn_adapter.py tests/test_espn_adapter_cli.py tests/test_canonical_snapshot.py -m "not windows_process" -q -p no:cacheprovider
```

Requirements and side effects follow the selected tests: existing tests use injected/synthetic sources and disposable stores; multiprocessing tests also spawn numerical workers. Selecting an adapter test does not authorize a live diagnostic. A focused pass proves only the selected contract/fixtures; use relevant reference, compatibility, identity and broader regressions when interfaces or shared semantics change. Inspect fixtures before extending them; never point them at private user stores.

## Tier 3: Credential-free regression

For shared behavior changes and the affected analytical/application surfaces, run the established synthetic Python tier and relevant frontend checks after locked installation:

```powershell
.venv\Scripts\python.exe -m pytest -m "not windows_process"
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
```

The Python selector excludes marked real Windows application/process-recovery tests, not ordinary multiprocessing workers or in-process HTTP tests. Frontend tests use synthetic DOM/API fixtures; they do not demonstrate a real browser or live refresh. Typecheck is `tsc -b --pretty false`; build is `tsc -b && vite build`. Build-mode TypeScript may write build metadata even with `noEmit` source options, and production build writes `frontend/dist`. Tests may create caches/temp files. No dependency install or audit is part of these commands. Credential-free is not a guarantee that arbitrary newly added tests are offline: maintain the injected-network/private-store boundaries.

For an isolated credential-free source/publication exercise, reuse `tests/test_snapshot_refresh.py` and its `tmp_path`/injected adapter/settings pattern. [Fixture modules](../../tests/adapter_fixtures.py) and [canonical fixtures](../../tests/canonical_fixtures.py) are synthetic, not real-league defaults. There is no installed persistent demo loader. Never populate an existing private database merely to test a UI, or label fixture probabilities/source fields live evidence.

## Tier 4: Release verification

Use for release-readiness work when that scope is agreed, after setup. The authoritative executable is [verify-release.ps1](../../scripts/verify-release.ps1); the [release checklist](../RELEASE_CHECKLIST.md) retains human signoff. This is **credential-free but networked**, not an offline or read-only command:

```powershell
.\scripts\verify-release.ps1
```

It runs these steps in order and stops on a failing step:

| Step | Script operation |
|---|---|
| Python credential-free default suite | `pytest -m "not windows_process"` |
| Python compilation | `python -m compileall -q src tests` |
| Ruff correctness | `ruff check --select E9,F63,F7,F82 .` |
| Python dependency consistency | `python -m pip check` |
| Frontend tests | `npm.cmd --prefix frontend test` |
| TypeScript typecheck | `npm.cmd --prefix frontend run typecheck` |
| Production frontend build | `npm.cmd --prefix frontend run build` |
| Production dependency audit | `npm.cmd --prefix frontend audit --omit=dev --audit-level=high` |
| Working-tree whitespace | `git diff --check HEAD` |
| Committed-revision whitespace | `git show --check --format= HEAD` |

The script supplies `.venv\Scripts\python.exe` for Python operations and changes to the repository root. Short `python`/`pytest`/`ruff` names in the table describe its arguments, not instructions to choose a global interpreter. Compilation creates bytecode; tests/builds create temporary/generated files; npm audit contacts the configured registry and evaluates production dependencies at the high threshold. It is not a full dependency-security assessment or permission to run `audit fix`/upgrade packages. `pip check` verifies installed dependency consistency, not vulnerability absence. Record audit date/output and all skipped gates; historical vulnerability counts are not a current security pass.

The default script performs no ESPN request and controls no real application/launcher process; it still spawns ordinary analytical test workers. It does not exercise browser workflows, clean setup, live permissions or recovery. Passing it does not declare M8.4 accepted or V1 released. Do not infer success for later steps if an earlier step failed.

## Tier 5: Explicitly authorized integration

These are separate scopes, not routine consequences of editing documentation or running the default release gate. **Do not run them without the applicable explicit authorization and disposable/private-data plan.**

| Scope | Command or procedure after authorization | Evidence and side effects |
|---|---|---|
| Windows process/recovery | `.venv\Scripts\python.exe -m pytest -m windows_process`; alternatively `.\scripts\verify-release.ps1 -IncludeWindowsProcessTests` for the complete release gate plus that tier. | Windows and PowerShell required. Creates/starts/stops and sometimes terminates authenticated disposable processes/stores. The release switch first repeats the full networked default gate; choose the intended route, not both unnecessarily. Unsupported platforms skip existing platform-guarded tests. |
| Live ESPN diagnostics | `.venv\Scripts\python.exe -m fantasy_football.live_scoring_diagnostic --json` for an expressly scoped live evidence question. | Read-only ESPN network requests using authorized local profile/credentials. Aggregate diagnostic output is not proof of settlement, lock permissions or unsupported in-game semantics. Retain sanitized provenance; no credential/payload dumps. |
| Browser workflow | Follow [first-run steps](../getting-started/first-run.md) with an expressly chosen disposable synthetic or separately authorized live profile. | Requires built frontend/server and an actual supported browser. Record revision, URLs, ownership and evidence. Clicking refresh can retrieve live data and append snapshots; synthetic component tests do not authorize it. |
| Clean-machine installation | Follow [installation](../getting-started/installation.md) in an isolated checkout/machine, then separately scoped first-run checks. | Dependency downloads, venv/node_modules/build/output creation. Record actual Python/Node/npm and install logs. Existing installed-environment passes cannot substitute. |

Historical capture scripts under `frontend/dev/` may assume a fixed Windows Edge executable/URL and may operate live refresh controls. `playwright-core` does not install a browser. Inspect the specific capture before agreeing a browser scope. Preserve launcher ownership/lease checks; use [authenticated shutdown/recovery](../getting-started/operations.md#shutdown-and-recovery), never guessed PIDs, metadata deletion or another contributor's database. No unverified-process termination is a troubleshooting shortcut.

## Change-based verification matrix

The [application API and execution reference](../APPLICATION_SERVICE.md) owns current routes/DTOs, refresh, analysis lifecycle, limits, retained results and process-ownership guarantees. Use its [source/test entry points](../APPLICATION_SERVICE.md#source-and-verification) for application-only contract work; it replaces the separate backend/run handoffs, not the numerical or operational test tiers below.

Start with Tier 1, then select relevant tests below. The module lists are useful starting points, not exhaustive signoff or permission to omit an applicable reference/acceptance gate. All test paths are relative to the repository root and can follow `python -m pytest` using the prepared interpreter. Include `-m "not windows_process"` for ordinary credential-free selection.

| Change | Targeted starting points | Additional evidence when affected |
|---|---|---|
| Documentation only | Tier 1, `tests/test_release_verification.py` for verification-guide/script references. | Modified links/fragments, current versus historical status and source/command cross-check. Frozen inventories describe their baseline, not a requirement that retired files remain forever. Preserve applicable technical gates; no numerical rerun merely to revalidate prose. |
| Canonical model/serialization | `tests/test_canonical_snapshot.py`, `tests/test_snapshot_store.py`, `tests/test_snapshot_cli.py`. | Historical v2/v3/v4 bytes, IDs/checksums, schema rejection, projection distinctions, capability fail-closed cases; adapter/consumer tests for interface changes. |
| ESPN adapter/ingestion | `tests/test_espn_adapter.py`, `tests/test_espn_adapter_cli.py`, `tests/test_snapshot_refresh.py`, `tests/test_live_scoring.py`. | Pagination/identity, source provenance, missing versus zero, safe boundary and publication/rollback checks. New live-field claims require separately authorized observations; fixtures alone cannot promote semantics. |
| Simulation/Monte Carlo | `tests/test_season_simulator.py`, `tests/test_weekly_engine.py`, `tests/test_postseason.py`, `tests/test_monte_carlo.py`. | Hand-checkable/reference outcomes, negative scores, standings/carry, path IDs, worker/batch and checkpoint suites: `tests/test_monte_carlo_parallel.py`, `tests/test_monte_carlo_execution.py`, `tests/test_monte_carlo_precision.py`; relevant partial suites. |
| Outcome model/numerical policy | `tests/test_player_outcomes.py`, `tests/test_m33_player_outcomes.py`, `tests/test_missing_projection_zero.py`, `tests/test_partial_monte_carlo.py`. | Exact nonaffected draws, approved expected changes, model identity/serialization, old-checkpoint rejection, golden/reference and matched-scenario/worker/resume protection. See numerical standards below. |
| Trade/waiver/action search | `tests/test_weekly_transactions.py`, `tests/test_transaction_cycle.py`, `tests/test_scenario_evaluator.py`, `tests/test_trade_search.py`, `tests/test_unified_actions.py`, `tests/test_search_orchestration.py`. | Complete finite-universe/reference and ordering/legality tests, paired draws, authorization, shared-state identities, capped-work coverage and cleanup; narrower candidate/chain suites for the changed generator. |
| API/application service | `tests/test_app_service.py`, `tests/test_background_runs.py`, `tests/test_backend_validation.py`, `tests/test_technical_documentation.py`. | DTO/route/error/privacy contracts, numerical engine parity, provenance, admission/retention/completeness; frontend request fixtures if public shape changes. |
| Frontend/UI | `npm.cmd --prefix frontend test`, `npm.cmd --prefix frontend run typecheck`, `npm.cmd --prefix frontend run build`. | Synthetic request/render/accessibility coverage; authorized real-browser captures for material layout/interaction changes. Do not fabricate analytical data or widen local security to make a browser check pass. |
| Persistence/background runs | `tests/test_snapshot_store.py`, `tests/test_snapshot_refresh.py`, `tests/test_background_runs.py`, `tests/test_snapshot_cli.py`. | Exact-byte historical/source compatibility, atomic commit versus verification failure, leases, cancellation races, interrupted startup and retained queries. Real Windows recovery needs Tier 5 scope. |
| Installation/dependencies/config | `tests/test_config.py`, `tests/test_release_verification.py`, `tests/test_local_installation.py` with the ordinary marker exclusion. | Locked dependency consistency, frontend engine compatibility and script/parser checks; networked audit/install, clean machine and marked process tests only in agreed scopes. Never silently change configuration precedence. |

Partial changes also select `tests/test_partial_week.py`, `tests/test_partial_season.py`, `tests/test_partial_monte_carlo.py`: preserve observed slots/locks, cutoff/carry, current-versus-future-week behavior and the unstarted-only MC boundary. Privacy/security tests accompany changes to requests, logs, source payloads, storage paths or artifacts. Approved modeling/source semantics and dynamic league configuration remain independent requirements across all rows.

## Numerical verification standards

- Preserve immutable source evidence, raw/effective projections, snapshot IDs/bytes/checksums and historical compatibility. A valid schema is not proof of consumer permission.
- Compare exact deterministic path-level scores, standings, postseason outcomes and shared path-indexed draws before only comparing aggregate probabilities. Match snapshot, seed, path indices, policies and outcome model; ownership/action order must not generate independent baseline/scenario samples.
- Test worker counts, batch partitions/order and checkpoint/resume against the reference. Fixed-path equivalence differs from adaptive stopping: changing the look schedule can change how many paths execute. Checkpoint execution-policy compatibility can be stricter than draw equivalence.
- Separate intentional approved model changes from regressions. Document expected changed outputs and identity consequences before changing goldens. **Never update golden outputs merely to obtain passing tests.** Retain historical reference evidence and use an independent oracle where the supported policy changes.
- Version numerical identity when semantics change; test adversarial custom identifiers/parameters and old-checkpoint refusal without rewriting stored bytes. Preserve nonaffected random-key bytes, not just approximate distributions. Retained historical output is not automatically reproducible under a new model.

[Accepted WR-022](../MISSING_PROJECTION_ZERO_CORRECTION.md) is the example, not a reopened decision: missing outcomes are deterministic zero, while nonmissing draws use original version/three draw parameters. Public Normal identity additionally includes `missing_projection_outcome="deterministic-zero-v1"`; a suffix alone could equal a historical custom version. Public serialization/configuration/run fingerprints now distinguish the policy and old checkpoints fail closed. The original golden constants remain protected by the historical test oracle. R2.4 changes none of that implementation or analytical meaning.

## Documentation maintenance

Keep one current answer and link to it. A code PR should update its corresponding technical reference and affected user/developer procedure when behavior, input/output shape, compatibility, operational side effects or supported capability changes. Pure internal changes with unchanged contracts need truthful verification evidence, not a rewritten user guide. Resolve code/specification disagreements explicitly; current code is not permission to silently amend an approved model.

| Document | Maintain when |
|---|---|
| [README](../../README.md) / [index](../index.md) | Product entry/navigation changes. Keep setup and verification details in their guides; preserve discoverability. |
| [status](../status.md) | Supported capabilities, limitations or independent acceptance changes. Do not turn implementation/test success into release acceptance. |
| [backlog](../BACKLOG.md) | Work is proposed/claimed/blocked/reviewed/completed. Follow its existing ordinary-PR workflow; retain stable IDs and actual decision references. |
| Technical references | Public shape, behavior, source authority, versioning or extension boundaries change. Cite source/tests and distinguish fixture claims from live evidence. |
| [MASTER_SPEC](../MASTER_SPEC.md) | Approved analytical requirements change under explicit authorization. Explain rationale and preserve compatibility/gates; an editorial cleanup cannot adopt a new model. |
| Historical audits/delivery records and [ROADMAP](../ROADMAP.md) | Preserve original baselines, test/benchmark counts, evidence labels and acceptance gates. Add a clearly separated subsequent disposition/current-guide pointer when needed; do not overwrite old measurements with today's counts. |

Use an ordinary reviewed PR; no extra committee, tracker, template or workflow is required. Cross-check edited commands against their executable source and update affected links/anchors. For source/evidence changes, record raw field/endpoint, transformations, retrieval context and verification class as required by AGENTS. Report actual checks in the PR/backlog; avoid duplicating execution logs across multiple current guides. Currentness should come from status/contract references, not maintaining parallel milestone catalogs.

## Archive pilot candidate

R2.5 follow-through: the explicitly authorized two-audit pilot uses `docs/archive/audits/` and retains heading-compatible original paths. See the [migration record](../R25_ARCHIVE_PILOT.md) for actual scope, baseline comparisons and review state. The R2.4 proposal below is preserved historical planning evidence, not authorization for additional groups.

Proposal only, for subsequent separately approved scope: move **`docs/PRE_M3_REPOSITORY_AUDIT.md` and `docs/PRE_M4_INTEGRATION_AUDIT.md` together** to the R1-proposed audit archive. They are text-only dated consolidation evidence at `381fdb2` / `87cdbbb`, with no linked screenshots/JSON to migrate. Their module inventories, old lint/tool status, test counts and “M3/M4 not started” statements are historical, not current developer instructions. Neither file moves in R2.4.

Use the current [architecture overview](../architecture/overview.md), [configuration guide](../getting-started/configuration.md), [canonical](../CANONICAL_MODEL.md) / [storage](../SNAPSHOT_STORAGE.md) references, [Monte Carlo/identity contract](../MONTE_CARLO.md) and this verification guide as current replacements for navigation, **not replacements for the audits' accepted evidence**. Preserve all original audit text, baseline IDs, configuration/provenance limits, exact-oracle rationale, pre-M4 reusable-worker seed-identity correction and recommendation/gate language. R1's [56-file migration inventory](../R1_REPOSITORY_AUDIT.md#7-file-by-file-documentation-migration-map) remains unchanged.

Known inbound references are the historical-records section of `docs/index.md`, the R1 map's literal paths, and pre-M4 acceptance citations in `MASTER_SPEC.md` / `ROADMAP.md` (including inline-code/plain-path references, not only Markdown links). Pre-M3 links out to `LEAGUE_CONFIGURATION_AUDIT.md`; a move changes its relative base. External bookmarks may include any audit heading. The future pilot must inventory backlinks again at its own baseline, preserve the original paths as compatibility stubs with all relevant anchors, link full archived texts and rebase outbound links. Do not discard or rewrite governing spec/roadmap clauses merely to remove an old path.

Safe-migration evidence would include normalized original-text comparison allowing only reviewed link relocation, complete original-heading/anchor mapping, old and new path/image/link resolution, R1 inventory accessibility, unchanged spec/roadmap gates, documentation/privacy tests and a two-contributor navigation review. This is a small candidate selection, not authorization to relocate files or begin R2.5. Mixed current contracts, live-source evidence, M8.4 release records and asset-heavy UI documents are excluded from this first candidate group.

## Reconciliation and remaining concerns

R2.4 source review found duplicated contributor/setup test blocks, an ambiguous credential-free-versus-offline release label, dispersed side-effect warnings and historical Ruff `F,E9`/test counts that should not be read as current commands. Current recipes are consolidated here; release steps and human gates are unchanged. Commands were checked against [release script](../../scripts/verify-release.ps1), [pytest/tool configuration](../../pyproject.toml), [frontend scripts](../../frontend/package.json), [TypeScript project references](../../frontend/tsconfig.json) and [existing release-marker tests](../../tests/test_release_verification.py).

Remaining concerns: WR-003 Node-policy mismatch, broader lint/type tooling decisions, fixed-browser capture assumptions, unresolved historical gate extraction and separately gated fresh-machine/release acceptance. Those remain backlog/review work, not implicitly delivered by guidance. Actual R2.4 verification and exclusions are recorded in [BACKLOG](../BACKLOG.md#r24-verification-for-review).
