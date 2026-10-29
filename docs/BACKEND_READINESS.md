# M6.4 backend readiness and API 1.0 handoff

Status: **COMPLETE AND ACCEPTED** (28 October 2026).

Governing requirements are `MASTER_SPEC.md` Sections 8, 9, and 12 and the M6.4
roadmap gate. The dependency direction remains HTTP → application service →
accepted analytical engine → local snapshot/result storage. The frontend must
never reconstruct league rules, transaction legality, probability estimates,
precision, or ranking.

## API 1.0 compatibility policy

`/api/v1` and frozen DTOs in `fantasy_football.app.contracts` define schema 1.0.
Within 1.0, existing fields retain names, types, units, null semantics, and
meaning. Additive response fields with safe defaults are permitted. Removing or
renaming a field, changing units/meaning, making an optional request field
required, or changing an enum incompatibly requires a new API version. Bugs may
be corrected without preserving incorrect behavior, with a regression test and
release note. Unknown request fields and unsupported schema versions fail.

Probabilities use `[0,1]`; paired changes and interval bounds named
`*_probability_points` are probability-point differences, not percentages.
Missing values are null and never converted to zero. Coverage, precision,
ranking resolution, authorization, acquisition condition, and stop reason are
independent dimensions.

Stable inventory: snapshot list/detail; baseline, manual, and action-search
submission; background lifecycle/progress/cancellation/result; globally
filtered/sorted candidate pages; candidate ordered actions; shared completed
states; all-team paired impacts; provenance; limits; and typed errors. OpenAPI
at `/openapi.json` is the machine-readable contract.

## Frontend data-readiness matrix

Classification: **API**, **engine-only**, **presentation**, or **unsupported**.

| Experience/data | Class | Source and frontend use | Disposition |
|---|---|---|---|
| League identity/settings, teams, records, standing/seeds | API | `SnapshotSummary`; Living League labels and structure | Ready |
| Player identity, eligibility, NFL team, injury/acquisition status | API | `PlayerSummary`; selection and action labels | Added in M6.4 from canonical data |
| Current roster/slot ownership | API | `RosterAssignment`; roster joins | Added in M6.4 from canonical data |
| Matchup periods, weeks, schedule/team IDs | API | `MatchupPeriodSummary`/`MatchupSummary`; schedule context | Added in M6.4 from canonical data |
| Championship/playoff/final-placement probabilities | API | baseline and all-team scenario results | Ready |
| Uncertainty, paths, convergence, provenance | API | probability/result/provenance DTOs | Ready |
| League-wide comparisons and probability formatting | presentation | Transform complete all-team API vectors | M7; no recalculation |
| Ordered transactions, dependencies, authorization and waiver condition | API | candidate detail/action DTOs | Ready |
| Completed-state identity and shared all-team outcomes | API | candidate/state endpoints | Ready |
| Manual scenario construction and protected pins | API | `ManualScenarioRequest` | Ready |
| Before/after projected starters, bench, reserve, vacancies | API | manual scenario lineup explanations | Ready for manual scenarios |
| Equivalent lineup explanation for every automated candidate | engine-only | Accepted completed states can be evaluated, but not retained in candidate DTOs | Consider M7.x only if required; do not infer client-side |
| Candidate counts, sorting, filtering, pagination/detail | API | retained SQLite query endpoints | Ready; queries do not simulate |
| Comparing several candidates in one UI view | presentation | Fetch candidate/state details | M7 client composition |
| Execution configuration, lifecycle, progress, cancellation/history/expiry | API | request, run and progress DTOs | Ready |
| Named quick/detailed presets | presentation/configuration | Existing explicit precision/resource fields | M7 may offer labels; submitted values stay explicit |
| Live score trajectories or time-series probability history | unsupported | No accepted analytical contract | Future research; do not fabricate |
| Trade acceptance or waiver-success probabilities | unsupported | Explicitly excluded by accepted models | Do not display as known |
| Public/multi-user deployment | unsupported | Local V1 has no authentication/TLS | Future release architecture |

## Local setup and clean start

Requirements: CPython 3.12, repository lockfile, and a writable private local
directory. Credentials are unnecessary for credential-free development.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install -e ".[app,test]"
New-Item -ItemType Directory -Force outputs | Out-Null
python -m fantasy_football.app.server --database outputs/fantasy_football.sqlite3 --port 8000
```

The same snapshot database path is the server `--database`; the background run
store is the adjacent `.runs.sqlite3` file. `FANTASY_FOOTBALL_BUILD_REVISION`
optionally supplies immutable build provenance. ESPN credential variables are
only for separate authorized retrieval and must stay in ignored `.env` files.

Inspect `http://127.0.0.1:8000/api/v1/health`, `/docs`, and `/openapi.json`.
List snapshots with `GET /api/v1/snapshots`. Submit a small credential-free
analysis only after a sanitized snapshot exists: POST a schema-1.0 request to a
`/api/v1/runs/*` endpoint, poll `/runs/{id}` or `/progress`, then fetch `/result`.
Action candidates and states use their paged/detail endpoints. Stop with Ctrl+C;
the coordinator closes workers and releases the SQLite lease.

For M7 development, run the frontend dev server on loopback and configure its
development proxy to forward `/api` to `http://127.0.0.1:8000`. Browser code
then uses relative `/api/v1/...` URLs through a same-origin frontend surface;
the proxy, not browser CORS, reaches FastAPI. Direct localhost origins remain
accepted for development, but Host/Origin protections must not be widened to
arbitrary networks. The eventual local release should likewise present one
loopback origin; static-asset packaging belongs to M8, not this checkpoint.

Synchronous `/analyses/*` routes are conservative diagnostics. Action search
requires finite wall-clock and evaluated-state limits. Background `/runs/*`
routes have separate admission, concurrency, worker, path, storage, retention,
and deadline limits. Neither transport policy changes engine semantics.

## Troubleshooting and operations

- `snapshot_not_found`: verify database path and snapshot ID.
- `background_store_in_use`: stop the other local instance; never delete a
  live lease to bypass ownership.
- `resource_exhausted`: lower declared budgets or use a supported background
  profile; response row limits do not limit computation.
- `interrupted`: a prior process ended while work was active; M6.2 classifies
  but does not resume that run.
- `untrusted_browser_origin` or invalid Host: use loopback URLs.
- Unknown build revision: set `FANTASY_FOOTBALL_BUILD_REVISION`; do not infer it
  from package version.
- Cancel is cooperative. An active batch may finish; accepted cancellation
  cannot later become successful completion.
- Expired/deleted results are not recoverable through the API. Snapshot data,
  research artifacts, and checkpoints remain in approved private paths.

Local V1 protections include loopback binding, Trusted Host/Origin checks,
single-owner SQLite lease, bounded queue/workers/storage/retention/pagination,
transactional terminal state, safe public errors, build provenance, and
temporary-index cleanup. This is not authentication, authorization, TLS,
sandboxing, or a public deployment design.

## Performance and M7 handoff

The authoritative measured evidence is `M6_3_BACKEND_VALIDATION.md`: 14 teams,
188 players, two process workers, responsive polling/querying, and explicit
parent/aggregate-child RSS. Exact Monte Carlo/V(R) evaluation dominates;
SQLite transfer/query overhead is secondary. RSS is sampled, not enforced, and
large exhaustive live-league behavior is unverified. M7 must preserve resource
and incomplete-result labels and must not imply convergence.

Deferred: empirical-evidence selection over HTTP, automated candidate lineup
explanations, live trajectories, public deployment, authentication, resumable
background search, trade acceptance, and waiver-success probabilities. None is
a foundational blocker for local Integrated War Room development.

M6.4 stops at the backend boundary. It contains no M7 component or styling.

## Verification evidence

The final focused API/lifecycle/backend/documentation gate passed 90 tests.
The complete credential-free repository suite passed 851 tests in 78.11
seconds. Windows multiprocessing/orchestration passed 35 tests and documentation
links/status passed 40 tests. Compilation, Ruff `F,E9`, dependency consistency,
and Git whitespace checks passed. The only warning is the existing upstream
Starlette AnyIO alias deprecation.
