# Background run management and retained results (M6.2)

Status: **IMPLEMENTED — REVIEW PENDING**.

This implements `MASTER_SPEC.md` Sections 8, 9, and 12 and the M6.2 roadmap
gate. It changes application execution only. Accepted engines remain
authoritative for candidates, legality, simulation, statistics, precision,
ranking, and analytical stop reasons.

## Components and ownership

- `BackgroundRunCoordinator` validates/admit work, enforces queue and
  concurrency limits, owns cancellation signals, and schedules local workers.
- `ApplicationService` remains the adapter into baseline, manual-scenario, and
  M5.8 analysis. M5.8 progress and cooperative-stop hooks are reused.
- `BackgroundRunStore` durably owns SQLite lifecycle metadata, progress, safe
  terminal diagnostics, result summaries, candidates, actions, and state links.
- FastAPI supplies typed submission, polling, cancellation, result, query,
  detail, and deletion routes. Polling is deliberate; there is no WebSocket.

The coordinator uses a bounded `ThreadPoolExecutor` so HTTP never runs analysis
inline. Threads provide scheduling isolation and responsive polling, not
forceful CPU cancellation. M5.8 may use its accepted bounded process executor,
constrained by per-run and aggregate nested-worker policy. Defaults are one
active run, eight queued, two analytical workers total, a 3,600-second search
deadline, 1,000 evaluated states, 10,000 paths per state, 1 GB retained data,
100 terminal runs, and 24-hour retention. These are application policies, not
league rules.

## Lifecycle and cancellation

```text
queued -> running -> completed
queued -> cancelled
running -> cancel_requested -> cancelled
running -> failed
queued|running|cancel_requested -> interrupted (startup recovery)
```

Terminal states never reactivate. Cancellation is idempotent. Queued
cancellation prevents worker entry. M5.8 observes cancellation at accepted safe
boundaries. Baseline/manual cancellation is coarse: an active engine call may
finish, its result is discarded, and the run becomes `cancelled`. No thread or
child is killed at an unsafe boundary. An analytical budget stop is a completed
result with disclosed incomplete coverage/precision, not infrastructure
failure. Worker exceptions become `failed` with a safe public message and a
local traceback. Prior-process active records become `interrupted` at startup;
M6.2 does not claim resume and does not change M3.6 checkpoints.

## Progress

Action search persists exact M5.8 stage, explored/retained candidates, unique
states, evaluated states, simulation paths, coverage, precision, ranking,
elapsed time, and stop reason. No percentage is invented. Baseline/manual work
exposes coarse queued, preparing, and terminal stages because those engines do
not expose fine callbacks. A deadline may overrun while an active batch finishes
safely; M5.8's measured overrun remains in the result.

## Persistence and queries

The private local SQLite store uses WAL, foreign keys, and `synchronous=FULL`.
It records immutable request JSON/SHA-256, snapshot/build provenance, lifecycle
timestamps, expiration, progress, stop/error data, and results. Clients cannot
supply paths.

M5.8 temporary indexes remain worker-owned. Before close, every candidate
summary, ordered action, candidate/state link, and shared evaluation field is
copied into application storage in row writes. Queries therefore never rerun
Monte Carlo. Cancellation/failure metadata remains inspectable, but partial
candidate rows are discarded rather than presented as completed results.
Deletion and retention purge cascade through candidate/team rows.

Candidate filters and sorts are allowlisted and applied globally before limit
and offset. Sorts are identity, evaluated paths, and requester championship
improvement; null improvements sort last and candidate ID is the stable final
tie-break. Filters cover ordering, involved team, authorization, acquisition
condition, and evaluated state. Candidate details preserve ordered actions;
state details expose all paths sharing one evaluation identity.

## HTTP routes

HTTP 202 submission:

- `POST /api/v1/runs/baseline`
- `POST /api/v1/runs/manual-scenario`
- `POST /api/v1/runs/action-search`

Polling and ownership:

- `GET /api/v1/runs` and `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/progress`
- `POST /api/v1/runs/{run_id}/cancel`
- `GET /api/v1/runs/{run_id}/result`
- `GET /api/v1/runs/{run_id}/candidates`
- `GET /api/v1/runs/{run_id}/candidates/{candidate_id}`
- `GET /api/v1/runs/{run_id}/states/{state_id}`
- `DELETE /api/v1/runs/{run_id}` for terminal runs

Synchronous M6.1 routes remain small-run diagnostics. Background policy is
independently bounded; it is not an unlimited bypass.

## M6.3 concerns

V1 remains loopback-only without multi-user authorization. Schemas/query
allowlists prevent arbitrary SQL and paths, errors omit tracebacks and paths,
and queue/storage/retention are bounded. M6.3 must further verify browser-origin
protections, realistic memory/disk behavior, active multiprocessing shutdown,
Windows spawn behavior, and policy sizing. This is a local metadata store, not
a distributed queue; restart classifies rather than resumes abandoned work.

## Verification evidence

- Eleven focused background tests cover baseline/manual/action-search engine
  parity, queued and running cancellation, idempotency, queue/worker limits,
  restart interruption, safe worker failure, retained candidate/state detail,
  involved-team filtering, global sort-before-page behavior, deletion cascade,
  HTTP 202 submission/polling, and immutable deterministic results. They passed
  in 1.99 seconds on the development Windows host; the tiny one-path action
  search took 0.23 seconds and is a contract fixture, not a production benchmark.
- The combined M6.1/M6.2/documentation focused gate passed 71 tests.
- All 832 credential-free repository tests passed in 75.11 seconds.
- Python compilation, Ruff `F,E9`, dependency consistency, documentation links,
  and Git whitespace checks passed. The only warning is the existing upstream
  Starlette test-client AnyIO alias deprecation.
