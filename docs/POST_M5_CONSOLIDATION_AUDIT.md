# Post-M5 consolidation and repository drift audit

Status: **IMPLEMENTED — REVIEW PENDING**, 26 October 2026.

## Scope and evidence

This checkpoint follows independent acceptance of M5.8. It reviews the active
Python package, tests, documentation, dependency metadata, ignored-file policy,
simulation identities, temporary result storage, and planned application
boundary. It introduces no M6 service, FastAPI dependency, frontend package,
league rule, statistical method, or search behavior.

Implementation facts below come from inspected source and passing tests.
Product direction and future gates come from the approved checkpoint request
and are not claims that the web application already exists.

## Accepted foundation retained

- Canonical snapshots remain immutable, versioned, source-backed, and governed
  by ESPN evidence plus explicit validated configuration.
- League size, lineup capacity, scoring periods, postseason structure, waiver
  capability, acquisition limits, and ownership come from canonical settings;
  current-league numbers occur in diagnostics, historical evidence, tests, and
  benchmarks rather than production league templates.
- M2 references still define lineup, transaction, evolving-state, postseason,
  and deterministic season behavior.
- M3 retains provisional outcome-model evidence labels, path-indexed common
  random numbers, exact batch reconciliation, simultaneous precision,
  multiprocessing equivalence, checkpoints, and recovery.
- M4 retains immutable full-state completion and paired all-team scenario
  comparisons.
- M5 retains exhaustive explicitly bounded universes, optional disclosed
  screening, immediate-predecessor chain dependency, conditional waiver status,
  structural-versus-authorized execution labels, M5.3 full-state identity,
  M5.4 multiplicity protection, and M5.8 bounded indexing/deadline semantics.
- No source inspection found a production branch fixed to 10, 12, 14, or 16
  fantasy teams. Numeric position IDs are ESPN/source-domain mappings; synthetic
  league sizes and current-league counts are evidence fixtures or explicit
  diagnostic arguments.

## Application architecture decision

V1 is now a localhost-only web application. The provisional preferred flow is:

`React/TypeScript/Tailwind frontend → FastAPI application service → accepted Python engine → canonical/application persistence`

The frontend owns presentation and interaction only. Transaction legality,
roster completion, candidate identity, statistical estimation, uncertainty,
and ranking remain Python-engine authority. Existing diagnostic CLIs stay
available, but a second full interactive CLI is not planned. FastAPI, React,
TypeScript, and Tailwind are intentionally absent today and enter only through
their M6/M7 gates.

## Prioritized findings

| Priority | Finding and evidence | Classification | Disposition |
|---|---|---|---|
| High | `simulation_configuration_fingerprint()` and M3.6 checkpoint metadata bind canonical snapshot content, model parameters, policies, seed/run identity, and paths, but do not record a repository code/build revision even though Master Specification §2.3 says every run records one. Changing accepted fingerprints now would affect batch/checkpoint compatibility. | Potential bug requiring independent review | Decide the versioned code-revision contract in M6.1 before exposing durable application runs; do not retrofit silently. |
| High | There is no application service, typed request/response schema, safe error envelope, run lifecycle, bounded application concurrency, or localhost security configuration. `pyproject.toml` correctly has no FastAPI dependency yet. | Documented and deferred | M6.1–M6.4. |
| High | `SearchResultIndex` supplies deterministic candidate/result iteration and state lookup, but application-grade pagination, sorting, compound filters, normalized per-team outcome queries, stable detail DTOs, retention ownership, and interrupted-process cleanup are not implemented. Filtering must not rerun Monte Carlo. | Documented and deferred | M6.2; reuse the M5.8 index rather than creating competing analytical storage. |
| Medium | `ProgressiveStateEvaluationResult.candidate_coverage_complete` describes unique-state evaluation coverage in the action-neutral adapter, while top-level M5.8 correctly exposes separate `candidate_coverage_complete` and `evaluation_coverage_complete`. The inherited name is easy for an API client to misread. | Requires architectural decision | Map to an unambiguous versioned API field in M6.1; avoid changing accepted M5.4 dataclasses without a compatibility review. |
| Medium | M5.8 disk-backs full candidates/states, but compact per-state comparisons, path batches needed for refinement, and JSON state-evaluation summaries remain memory-resident. Total process memory is therefore not bounded solely by queue/index settings. | No action necessary for accepted M5.8; documented and deferred | Measure realistic API workloads in M6.3 and design paged application result records in M6.2. |
| Medium | Cooperative stopping exists at safe M5.8 boundaries, but there is no durable search-level resume or application cancellation owner. An active Monte Carlo batch finishes and reports overrun. | Documented and deferred | M6.2; preserve M3.6 checkpoint semantics rather than inventing another simulation checkpoint format. |
| Medium | Current M5.8 export metadata records scope and analytical identities, but an application query contract must additionally preserve requested sort/filter expressions and distinguish generated, evaluated, precise, and ranking-resolved records. | Documented and deferred | M6.1/M6.2. |
| Low | Master specification, roadmap, README, and four milestone documents contained stale M2.3d/e, M5 parent, M5.5, M5.7, or M5.8 review-pending/deferred text and the obsolete CLI-first M6/M7 plan. | Fixed during checkpoint and final alignment follow-up | High-level and detailed M5 status/history now agree; the M6–M8 roadmap is reconciled without rewriting historical evidence. |
| Low | `.gitignore` covers credentials, environments, SQLite sidecars, outputs, frontend dependencies/builds, caches, and research/checkpoint artifacts. No tracked credential, database, generated frontend, or private output was found. A local unreadable `.pytest-run-m04-final/` directory causes a Git warning but is not tracked. | No repository action necessary | Developer may remove the local artifact manually if desired; the checkpoint does not delete user files. |
| Low | Independent exact references and seemingly duplicated sequential/optimized paths remain intentionally testable correctness oracles. Diagnostic CLI modules remain documented workflows. Static checks found no unused imports or unreachable syntax requiring deletion. | No action necessary | Retain until a future deprecation has explicit replacement and compatibility evidence. |

## Configuration and hardcoding classification

| Category | Examples | Assessment |
|---|---|---|
| API-derived | team count, lineup slots, position limits, scoring, matchup periods, acquisition type/limits, waiver reset, championship/consolation settings | Canonical adapter/validation authority; unsupported semantics remain gaps rather than defaults. |
| Validated configuration | explicit consolation graphs, selected finite candidate universes, precision/resource settings, historical sample periods | Typed and fingerprinted where analytically relevant. |
| Approved modeled policy | projection-based IR recovery, modeled weekly waiver boundary, reverse frozen-priority immediate free-agent ordering, provisional outcome models | Explicitly named in state/results/docs; not presented as verified ESPN behavior. |
| Universal invariant | unique ownership, valid roster capacity/eligibility, complete unique priority permutations where required, deterministic IDs, exact path coverage | Appropriately enforced independent of league size. |
| Source-domain constant | ESPN slot/position/stat-source identifiers, ten PIT reporting bins | Data interpretation or research reporting, not fantasy-league structural hardcoding. |
| Performance/runtime setting | queue/page sizes, worker/task counts, path/checkpoint budgets, preflight samples | Explicit runtime policy; does not change league rules. |
| Problematic hardcoding | none confirmed in the inspected production paths | Continue parity/configuration tests as the application layer is added. |

Traditional waiver processing remains conditioned on supported canonical
acquisition policy and the approved modeled boundary. FAAB/unsupported policies
fail closed. Reverse initial priority is an explicit V1 behavioral policy, not
an ESPN universal. Postseason tie and consolation behavior likewise require
verified or validated rules.

## Interface and statistical consistency

The source contracts consistently preserve candidate ID separately from M5.3
completed-state identity, allowing multiple paths to share one compatible state
evaluation. Baseline/state/snapshot/model identities are validated before
simulation. Execution authorization and acquisition condition are orthogonal.
Candidate generation coverage, state evaluation coverage, all-team precision,
and ranking resolution are distinct at the M5.8 boundary. Resource-limited work
does not claim convergence. Sequential, parallel, partitioned, resumed, and
reference/optimized equivalence are covered by accepted suites.

No audit evidence supports changing Wilson intervals, paired-difference
intervals, M5.4 all-pairs/all-looks multiplicity, candidate screening,
deduplication, or path-index semantics. Those algorithms were not modified.

## Dead/obsolete code assessment

No module was removed. The active tree contains public diagnostics, canonical
storage/inspection, research workflows, accepted reference oracles, optimized
paths, and milestone-specific documentation. Import reachability alone is not a
safe deletion criterion because several modules are executable diagnostics or
independent test references. The obvious obsolete material was prose: stale
milestone statuses, M5.8-as-future descriptions, and CLI-first product planning.

## M6.1 recommended starting scope

1. Add a minimal optional backend dependency set and application package; bind
   localhost only and add no frontend yet.
2. Define versioned DTOs for snapshot summaries, baseline/manual/search requests,
   resource and precision policies, provenance, coverage/precision/ranking, and
   typed errors. Map existing enums/dataclasses rather than copying rules.
3. Define a stable run identity that addresses the code/build-revision finding
   through an explicit compatibility decision.
4. Implement synchronous representative endpoints first and prove byte/value
   parity with direct engine calls. Do not add background execution until the
   contracts pass this gate.
5. Specify ownership of temporary M5.8 indexes and expose candidate/state detail
   through a page contract suitable for M6.2, without rerunning simulation.

M6.1 should not implement the dashboard, cloud deployment, broad authentication,
new analytics, a general plugin framework, or an extensive interactive CLI.

## Verification evidence

- Documentation links and the authoritative product-direction/status contracts:
  36 passed.
- Complete credential-free repository regression suite: 797 passed in 60.18
  seconds on the development Windows host.
- `python -m compileall -q src tests`: passed.
- `python -m ruff check --select F,E9 src tests`: passed.
- `git diff --check`: passed.

The first sandboxed full-suite attempt could not access pytest's Windows system
temporary root or create multiprocessing named pipes. It was rerun unchanged
with those operating-system permissions and passed; this was an execution-host
restriction, not a skipped or repaired test failure.

## Checkpoint conclusion

No accepted analytical correctness blocker was confirmed. Documentation drift
was corrected, including the final stale M5 parent summary. The approved M7
Integrated War Room direction is recorded separately as a design north star.
Application risks were assigned to M6, and the code/build-version provenance
gap remains explicitly assigned to M6.1 for independent architectural review;
the M3.6 checkpoint format and simulation fingerprints were not changed.
Subject to the checkpoint regression results, the repository is ready to begin
the narrowly scoped M6.1 contract/API-foundation package after this checkpoint
is independently accepted.
