# M6.3 backend integration, performance, and operational validation

Status: **IMPLEMENTED — REVIEW PENDING** (27 October 2026).

This audit implements the M6.3 gate in `MASTER_SPEC.md` Sections 8, 9, and 12.
It validates the accepted M0–M6.2 system and adds no model, transaction rule,
ranking method, estimator, or frontend capability.

## Integration and correctness

Tests traverse direct engines, `ApplicationService`, FastAPI, the background
coordinator, durable run SQLite, retained candidate/state queries, and M5.8
temporary-index transfer. They reconcile analytical identities, all-team
probabilities, coverage, precision/ranking flags, stop reasons, candidate IDs,
completed-state IDs, ordered actions, cancellation, and cleanup. Retained state
detail stores accepted all-team paired impacts once per completed state.

Identical submissions retain snapshot, model, seed/path, M3 engine, M5 state,
and analytical-equivalence identities while receiving distinct M6 execution
identities. An absent build revision remains `unknown`; it does not prove source
byte equivalence. League structure comes from canonical configuration and
unsupported settings still fail closed.

## Operational corrections retained from M6.3

- SQLite connections are explicitly closed, including on Windows.
- A live-instance SQLite lease prevents a second application from interrupting
  an active owner; stale ownership permits restart classification.
- Trusted-host and hostile-origin checks protect the loopback-only service.
- Logical payload limits are enforced transactionally with terminal-metadata
  reserve; failed writes leave no partial candidate row.
- Retained state detail preserves all-team paired evaluation results.
- Shared state evaluations are now serialized and written once per run rather
  than once per equivalent candidate path. Candidate links and IDs are unchanged.

The server remains hard-bound to `127.0.0.1`. It has no authentication or TLS
and is not supported for public exposure.

## Reproducible realistic-workload benchmark

Run `python benchmarks/benchmark_app_backend.py --tier all`.

The 27 October 2026 host was Windows 11 build 26300, Python 3.12.10, AMD64
Family 25 Model 97, 16 logical cores, and 33,605,840,896 bytes RAM. Dependencies
were FastAPI 0.115.14, Starlette 0.46.2, Uvicorn 0.34.3, and Pydantic 2.14.1.

The sanitized representative fixture has 14 teams, 12 ordinary roster players
per team, five starters (QB/RB/WR/TE/FLEX), seven bench places, 20 unrostered
players, 188 total players, four remaining scoring weeks, and the generic
six-qualifier postseason. These are benchmark inputs, never production rules.

Both search sizes used seed 8128, the provisional Normal model, two matched
paths per evaluated state, one active run, two process workers, one-path tasks,
an eight-item queue, and a 120-second deadline. The representative universe
generated two candidates/two states and evaluated both. The larger universe
generated 12 candidates/12 states and evaluated four under its declared limit.
Candidate coverage was exhaustive in both; the larger run stopped with
`evaluation_limit` and did not claim evaluation or statistical completeness.

| Search | Generation | MC evaluation | Transfer/persist | Total | States generated/evaluated | page p50/p95 | detail p50/p95 | health p50/p95 (n) | SQLite | parent peak RSS | child peak RSS/processes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Representative | 0.203s | 9.031s | 0.256s | 9.490s | 2/2 | 5.5/5.6ms | 4.6/17.0ms | 1.4/15.3ms (350) | 348,160 B | 85,610,496 B | 136,921,088 B / 2 |
| Larger | 0.812s | 14.953s | 0.340s | 16.105s | 12/4 | 3.5/5.2ms | 5.2/13.9ms | 1.4/14.8ms (564) | 569,344 B | 86,134,784 B | 136,921,088 B / 2 |

Allocation tracing was disabled during latency measurement. Separate one-path
traced baselines recorded 2,194,332 and 2,193,886 Python bytes; these are not
whole-process peaks. `psutil` sampled the parent and recursive children every
10ms (531 and 669 samples). Two children were observed and returned to zero
after shutdown; no persistent orphan remained. Aggregate child RSS is measured
evidence, not a platform-enforced limit.

Health and status polling continued during process computation and p95 stayed
under 250ms. Page/detail queries read retained SQLite rows and initiated no
Monte Carlo. The larger store grew about 229KB for six times as many links.
Transfer/persistence was 2.1% of total time; Monte Carlo evaluation dominated.

The representative workflow also reruns sequentially and compares its complete
`(candidate_id, completed_state_sha256)` set and coverage with the two-worker
result. Resource settings intentionally differ, so execution fingerprints are
not used as analytical-equivalence evidence. Existing path-indexed M3.5 tests
separately prove numerical worker-count equivalence.

These are synthetic sanitized measurements, not live ESPN forecasts or a claim
that an entire live-league exhaustive universe fits these budgets.

## Statistical and resource semantics

Candidate coverage, evaluation coverage, precision, ranking resolution,
transaction authorization, waiver condition, and path count remain separate.
Null estimates remain null. A resource-limited run returns valid partial data
with its stop reason and is never relabeled converged. Cancellation, process
interruption, storage failure, invalid configuration, missing/expired run, and
worker failure remain distinct durable and HTTP states.

Polling RSS can miss short-lived peaks and does not enforce a process-memory
ceiling. Exact V(R)/Monte Carlo evaluation dominates larger budgets; realistic
searches therefore remain explicitly resource-bounded without candidate
attractiveness pruning or heuristic substitution. Baseline/manual cancellation
is still coarse while inside an accepted engine call. The local SQLite service
remains single-owner rather than a distributed scheduler.

## Verification gate

Focused tests cover identity separation, Host/Origin security, distinct league
structures, transactional rollback, Windows handle release, live-instance
exclusion, realistic fixture dimensions, direct/service/background parity,
shared-state write deduplication, acquisitions, chains, and combined searches.
The complete credential-free suite, Windows spawn checks, Python compilation,
Ruff `F,E9`, dependency consistency, documentation links, and Git whitespace
are required before acceptance. The known Starlette AnyIO alias warning is
upstream and unchanged.

Final follow-up evidence: 49 focused M6.1–M6.3 tests passed; all 849
credential-free tests passed in 64.50 seconds; 39 documentation-link tests,
`pip check`, compilation, Ruff `F,E9`, and Git whitespace checks passed. The
only warning was the existing upstream Starlette AnyIO alias deprecation.

M6.3 remains **IMPLEMENTED — REVIEW PENDING**. M6.4 and M7 are not started.
