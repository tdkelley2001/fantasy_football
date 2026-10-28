# M6.3 backend integration, performance, and operational validation

Status: **IMPLEMENTED — REVIEW PENDING** (27 October 2026).

This audit implements the M6.3 gate in `MASTER_SPEC.md` Sections 8, 9, and 12.
It validates the accepted M0–M6.2 system; it does not add a model, transaction
rule, ranking, estimator, or frontend capability.

## Scope and architecture exercised

Tests traverse direct Python engines, `ApplicationService`, FastAPI, the
background coordinator, durable run SQLite, retained candidate/state queries,
and M5.8 temporary-index transfer. Baseline, identity manual scenarios,
standalone trades, immediate acquisitions, two-step trade chains, and combined
trade/chain/acquisition searches are included. Direct and background layers
reconcile engine/search identities, all-team probability structures, candidate
coverage, evaluation coverage, precision/ranking flags, stop reasons, candidate
IDs, completed-state IDs, and ordered action steps. Retained completed-state
detail now stores the accepted shared all-team paired evaluation once per state;
equivalent candidate paths do not imply independent Monte Carlo evidence.

Identical submissions preserve snapshot, model, seed/path, M3 engine, M5 state,
and analytical-equivalence identities while receiving distinct M6 execution and
presentation identities. Build revision remains `unknown` when neither an
explicit revision nor `FANTASY_FOOTBALL_BUILD_REVISION` is supplied; such a run
does not prove source-code byte equivalence.

## Configuration matrix

Credential-free tests cover supported four-team analytical fixtures, an
eight-team/four-qualifier postseason structure, and a sanitized 14-team/six-
qualifier complete-season fixture. Snapshot/league/season identity, configured
lineup slots and capacities, acquisition type, championship qualifier count,
postseason periods, and canonical source gaps pass through without fixed league
size branches. Existing canonical/adapter/postseason suites retain broader 8-,
10-, and 14-team configuration coverage. Unsupported settings continue to fail
in the canonical or engine layer rather than receiving an application fallback.

## Statistical and completion semantics

Public contracts keep candidate coverage, evaluation coverage, statistical
precision, ranking resolution, transaction authorization, conditional waiver
status, and evaluated path count separate. Null estimates remain null. Resource
limits produce valid partial results with their engine stop reason; they are not
infrastructure failures and are not labeled converged. Cancellation, process
interruption, storage failure, invalid request/configuration, missing/expired
run, and internal worker failure retain distinct durable/HTTP classifications.

## Targeted corrections found by validation

1. **SQLite handle lifecycle (high, fixed).** `sqlite3.Connection` context
   management commits or rolls back but does not close the object. Run-store
   methods now use an explicit close-owning context manager. A Windows regression
   deletes a just-used database immediately; the benchmark no longer leaves a
   locked temporary directory.
2. **Concurrent application startup (high, fixed).** Startup interruption
   recovery previously could mark another live process's work interrupted. A
   single-owner SQLite lease now rejects a second live application explicitly;
   a stale owner permits accurate restart recovery.
3. **Browser-origin/Host boundary (high, fixed).** Trusted-host validation
   allows only loopback names plus the test host. State-changing requests with a
   non-loopback `Origin` receive a typed 403. No permissive CORS headers are
   emitted. Requests without `Origin` remain available to local CLI/native
   clients.
4. **Storage overshoot (medium, fixed).** Run and candidate/state payload limits
   are checked inside the writing transaction using logical payload bytes, with
   a 4 KiB reserve for safe terminal metadata. An excessive write rolls back;
   the run fails safely and no candidate row commits. Physical SQLite page/WAL
   allocation is reported separately and can exceed logical payload by fixed
   database overhead.
5. **All-team shared evaluation delivery (medium, fixed).** Retained state detail
   now includes every available accepted all-team paired impact rather than only
   the requesting-team ranking field.

## Local security disposition

The server remains hard-bound to `127.0.0.1`; no public-host option exists.
Trusted Host mitigates DNS-rebinding Host spoofing, and the origin check blocks
hostile web pages from state-changing requests even when a simple browser POST
is possible. Query sorts/filters remain fixed allowlists with bound SQL values;
clients cannot supply storage paths. Public errors omit tracebacks, raw payloads,
credentials, and filesystem paths, while local logs retain worker tracebacks.

Residual V1 risks: there is no user authentication, TLS, or authorization if an
operator deliberately changes the binding outside the supported entry point;
loopback malware can access the service; and permitted localhost origins share
trust regardless of port. These are release/security review items for M6.4,
not evidence that the service is suitable for public exposure.

## Reproducible performance workflow

Run:

```powershell
python benchmarks/benchmark_app_backend.py --tier all
```

The 27 October 2026 development host was Windows 11 build 26300, Python 3.12.10,
AMD64 Family 25 Model 97, 16 logical cores, and 33,605,840,896 bytes RAM.
Dependencies were FastAPI 0.115.14, Starlette 0.46.2, Uvicorn 0.34.3, and
Pydantic 2.14.1. Runs used the provisional Normal model, seed 8128, one path,
one active application run, and at most two analytical workers. These are
synthetic sanitized measurements, not live ESPN forecasts.

| Tier | Structure/work | baseline | manual | combined search | submit | status p95 | health p95 | candidate page p95 | detail p95 | SQLite | traced Python peak | RSS before → after |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Small | 4 teams, 9 players, 44 combined paths, 5 retained runs | 0.275s | 0.645s | 6.107s | 10.6ms | 98.6ms | 181.1ms | 7.1ms | 5.1ms | 262,144 B | 2,497,455 B | 75,010,048 → 81,346,560 B |
| Representative | 14 teams/players, 3 retained runs | 0.658s | 1.861s | unavailable | 9.9ms | 267.7ms | 196.9ms | unavailable | unavailable | 303,104 B | 1,746,553 B | 81,956,864 → 82,821,120 B |
| Stress | small combined search plus 50 repeated runs/queries | 0.240s | 0.617s | 6.149s | 8.7ms | 142.1ms | 139.4ms | 7.5ms | 5.9ms | 815,104 B | 1,863,438 B | 82,989,056 → 83,066,880 B |

The 50-row target was approximated by the complete 44-row combined-action
fixture. Page/detail targets (500/250 ms), health target (250 ms), and nonblocking
submission passed. Representative status polling measured 267.7 ms, 17.7 ms
over the provisional 250 ms target. This is a **moderate M7 responsiveness risk**:
the small sample and `tracemalloc` instrumentation make it non-conclusive, but
the thread executor cannot guarantee GIL-independent responsiveness. M6.4 should
repeat without allocation tracing and evaluate process isolation before release.
No universal exhaustive-search completion budget is asserted.

RSS includes the parent process. Peak child-process count/RSS was unavailable in
this harness and is explicitly null; no claim about strict aggregate process
memory is made. The tested one-path workload did not activate a child pool.
Database growth was predictable across 5/3/50 retained runs, coordinator
references returned to zero, and isolated temporary stores deleted successfully.

## Worker/interruption evidence

Focused tests cover normal/quick completion, queued and active cancellation,
candidate-generation cooperative stopping through accepted M5.8 hooks,
cancellation at the atomic completion boundary, failure, shutdown cancellation,
stale restart classification, single-owner startup, queue/worker bounds,
temporary-index cleanup, and terminal bookkeeping release. Existing spawn-based
M3.5/M5.8 suites cover Windows worker equivalence and partition identity. Tests
do not claim automatic resume or force-kill safety.

## Remaining limitations and handoff

- Parent RSS and traced allocations are observed, but peak aggregate child RSS
  remains unavailable (**medium**, M6.4 performance validation).
- Representative polling narrowly missed the provisional target under tracing
  (**medium**, M6.4/M7 responsiveness decision).
- Baseline/manual cancellation remains coarse while inside an accepted engine
  call (**documented**, M6.4 UX wording; no unsafe termination).
- Single-owner local SQLite deliberately rejects concurrent application
  instances; this is not a distributed scheduler (**accepted V1 constraint**).
- Localhost-origin trust and lack of authentication prohibit public deployment
  (**high if exposed**, M6.4 release security checklist).

No finding requires changing an accepted fantasy-football or statistical
algorithm. M6.3 remains pending independent review; M6.4 and M7 are not started.

## Verification evidence

- Nine focused M6.3 tests (twelve parametrized cases) cover identity separation,
  Host/Origin security, distinct canonical league structures, transactional
  storage rollback, Windows handle release, live-instance exclusion, and direct/
  service/background/retained-result parity for acquisitions, chains, and
  combined searches.
- The combined M6.1–M6.3/documentation gate passed 86 tests in 7.82 seconds.
- The explicit Windows multiprocessing/M5.8 compatibility gate passed 35 tests
  in 14.15 seconds.
- All 847 credential-free repository tests passed in 64.41 seconds.
- Python compilation, Ruff `F,E9`, dependency consistency, documentation links,
  and Git whitespace checks passed. The sole warning is the existing upstream
  Starlette test-client AnyIO alias deprecation.
