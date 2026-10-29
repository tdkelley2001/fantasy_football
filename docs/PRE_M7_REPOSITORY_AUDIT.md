# Pre-M7 repository consolidation audit

Status: **IMPLEMENTED — REVIEW PENDING** (28 October 2026).

## Scope

This checkpoint reviewed all production modules under `src/fantasy_football`,
the complete test suite, diagnostic command entry points, benchmark scripts,
dependency declarations/lockfile, application contracts and storage, and the
authoritative README/Master Spec/Roadmap/M6/UI documents. It changes no fantasy
rule, outcome model, estimator, search method, or frontend behavior.

## Confirmed findings and corrections

| Severity | Finding | Disposition |
|---|---|---|
| High | A failure between durable run creation and `ThreadPoolExecutor.submit()` left a queued record and cancellation event indefinitely. | Fixed with a conditional queued-to-failed compensation carrying stable `background_submission_failed` metadata; the event is removed and the original executor error remains chained. |
| Medium | A rapidly completed future could run its callback before `_futures` registration. | Fixed by submitting and registering under the coordinator lock, then attaching the callback after registration. |
| Medium | Failure during stale-run recovery occurred after lease acquisition and could strand the instance lease. | Constructor now releases the acquired lease before propagating initialization failure. |
| High (Windows) | Unix-style `os.kill(pid, 0)` was used as a cross-platform liveness probe; on Windows the controlled cross-process test interrupted the target instead of safely querying it. | Windows now uses read-only `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` and closes the handle; Unix retains signal-zero probing. |
| Low | Accepted M6.4 and completed M6 status were stale in current-status sections. | README, Master Spec, Roadmap, M6.3 validation, and readiness references reconciled; historical review notes remain unchanged. |
| Low | M7 proxy arrangement was implicit. | Documented loopback frontend development proxy and same-origin relative API policy without weakening Host/Origin checks. |

Submission compensation is state-conditional. If queued cancellation wins, it
remains cancelled; the failure path cannot overwrite a terminal record. Normal
completion/cancellation/failure semantics, result ownership, queue admission,
terminal immutability, cleanup, and engine behavior are unchanged.

## Code inventory and dead-code disposition

Production code separates canonical retrieval/validation/storage, deterministic
league engines, research/probability execution, candidate/search engines, and
the M6 application layer. Ruff and manual import/call-site review found no
unused production import, unreachable accepted path, obsolete adapter, or dead
configuration option warranting deletion.

- **Active:** canonical, evolving-state, lineup, weekly/postseason/season,
  outcome/Monte Carlo, scenario/candidate/search, snapshot, and application
  modules used by tests, public APIs, or documented entry points.
- **Compatibility/reference:** exact exhaustive allocators and sequential
  execution references. These are intentionally retained correctness oracles.
- **Diagnostic/research:** ESPN audits, snapshot inspection, historical research
  workflow, healthcheck, scenario CLI, and benchmark scripts. They remain
  documented, credential-scoped or sanitized, and are not parallel products.
- **Genuinely obsolete:** none established. No code was deleted merely because
  the local web application is now primary.

Repeated DTO mapping at the application boundary is deliberate typed isolation,
not an alternative serializer. No circular dependency was found: HTTP depends
on service/contracts, the service depends on accepted engines, and engines do
not import the application layer. Declared runtime/app/test dependencies all
have active imports or supported tooling roles; no removal is justified.

## League/model authority and hardcoding

Repository-wide searches covered team/roster counts, slot IDs, scoring/PPR,
qualifiers/byes, bracket schedules, waiver/acquisition behavior, transaction
ordering, random seeds/distributions, confidence thresholds, screening, and
resource budgets.

- League rules and structures come from canonical ESPN-derived fields or
  validated explicit configurations.
- Approved V1 behavioral policies remain named and provenance-labeled.
- Seeds, distributions, precision, candidate universes, and search bounds are
  explicit request/model configuration.
- M6 synchronous/background numeric ceilings are documented transport resource
  policies, not league rules or analytical defaults.
- Concrete 4/6/8/10/12/14-team, slot, seed, and path values occur in tests and
  benchmarks as independent fixtures/evidence only.
- Quick/detailed execution profiles are named runtime policies.

No suspicious league-specific production hardcoding was confirmed. Existing
generic slot IDs reflect canonical ESPN slot namespaces rather than the current
league roster. No accepted behavior was changed by this audit.

## Lease, lifecycle, and process evidence

Tests cover stale-owner recovery, same-process competing owners, a genuinely
different live process, normal release, initialization-failure release, queued
and running cancellation, atomic completion/cancellation, executor rejection,
quick completion, worker failure, restart classification, and transient
future/event cleanup. The SQLite lease is intentionally single-host/local and
is not a distributed scheduler.

PID reuse cannot be induced safely and reproducibly in the credential-free
suite. The current lease uses instance ID plus OS process liveness; an unrelated
future process reusing a stale PID could conservatively block startup until
manual inspection. It cannot authorize concurrent writes. This is a documented
local-V1 availability limitation, not a public-deployment guarantee. The
cross-process regression also proves that the Windows liveness check itself is
non-destructive.

## M7 integration and security

API 1.0 exposes snapshot/team/player/roster/matchup joins, baseline/manual/search
inputs, all-team probabilities, uncertainty/provenance, run lifecycle/progress,
candidate pages/actions, shared states, resource and completion semantics, and
typed errors. The frontend data-readiness matrix remains in
`BACKEND_READINESS.md`; unsupported acceptance probabilities, live trajectories,
and public deployment remain explicit gaps.

M7 should use relative `/api/v1` URLs through a loopback development proxy.
League rules, legality, statistics, null/zero meaning, units, and coverage must
come from backend DTOs. Host/Origin protection, localhost binding, bounded
pagination, safe errors, SQLite ownership, and private-path rules remain intact.

`.env`, credentials, local configuration, outputs, databases, checkpoints,
Python caches, test caches, build outputs, and frontend dependency/build folders
are ignored. No credential or private row-level artifact is tracked. The
pre-existing inaccessible `.pytest-run-m04-final` directory is not modified or
claimed as repository content.

## Documentation drift

Authoritative current-status sections now mark M6.4 and M6 complete/accepted,
the pre-M7 checkpoint review-pending, and M7.1 not started. M6.1–M6.4 API and
run-management descriptions agree with the implementation. Historical milestone
evidence retains its original wording and context. UI design vision is unchanged.

## Verification and readiness

Final verification passed:

- 94 focused application/background/backend/documentation tests;
- all 855 credential-free repository tests in 66.21 seconds;
- 35 Windows multiprocessing/orchestration tests;
- 41 documentation link/status tests;
- compilation, Ruff `F,E9`, `pip check`, and Git whitespace checks;
- a clean-start hidden loopback server on port 8766 using a fresh private
  SQLite path: health returned service `fantasy-football-application`, schema
  `1.0`, and `local_only=true`; OpenAPI reported version `1.0`; shutdown and
  smoke-directory cleanup succeeded.

No test failed or was skipped. The only warning is the unchanged upstream
Starlette test-client AnyIO alias deprecation. Static dead-code assistance was
limited to installed Ruff plus manual call-site/configuration review; no
unreviewed third-party dead-code report was used as deletion authority.

**Readiness decision:** ready for M7.1 after independent acceptance of this
checkpoint. There is no unresolved foundational backend architecture decision.
M7.1 is not started by this work.
