# Provisional Repeated Season Simulation and Probability Precision

M2.6 is implemented by `fantasy_football.monte_carlo`. It sequentially generates
path-indexed score scenarios and passes each one to the accepted, unchanged M2.5
`simulate_deterministic_season()` coordinator.

## Public contract

`MonteCarloConfig` validates the master seed, positive path count, first path
index, IR policy, weekly transaction policy, postseason participation policy,
optional consolation configuration, and complete-result requirement.

- `run_monte_carlo_path()` reconstructs one configured path and can optionally
  retain its detailed deterministic result.
- `run_monte_carlo_batch()` runs the explicit contiguous range sequentially and
  retains compact per-path summaries rather than full season states.
- `combine_monte_carlo_batches()` requires exact, duplicate-free coverage of the
  requested range and matching snapshot/model/seed identity before deterministic
  aggregation.

Every path starts from the same immutable snapshot. Ownership, transactions,
standings, and postseason state are independently recreated and never leak into
another path. Execution performs no ESPN request.

## Results and reconciliation

`MonteCarloBatchResult` records snapshot/league/season identity, model identity
and parameters, seed, exact path IDs, complete/incomplete/invalid counts,
projection-class coverage, assumptions, compact replay metadata, capability
diagnostics, and one aggregate for every configured team.

Every result also retains two SHA-256 identities. The simulation-configuration
fingerprint covers snapshot UUID, league/season/schema and order-independent
canonical-content digest; model ID and every parameter; IR, weekly transaction,
and postseason participation policies; complete optional consolation mapping
including source/approval provenance; complete-result policy; and named material
semantics versions. Path range and path count are deliberately excluded so valid
partitions share the fingerprint. The run identity adds the master seed. Current
M2.6 does not accept acquisition-count or IR-evidence overrides; those must be
added to this contract before such inputs can be supported.

Batch combination requires both identities to match the requested configuration
before inspecting results. Exact path coverage must then be contiguous,
duplicate-free, and complete. Thus batches with different transaction, IR,
participation, consolation, outcome-model, seed, snapshot identity, or snapshot
content cannot be combined, while disjoint ranges under one configuration can.

For a fully complete batch, team aggregates contain championships, playoff
qualifications, runner-up finishes, every placement count, and averages for
placement, regular rank, wins, and points for. Frequencies use all requested
paths. Reconciliation requires one champion and one owner of every placement per
path, the configured championship qualifier count, known team IDs, and complete
per-team placement distributions.

Reconciliation is first performed independently for every path. Each complete
path must contain exactly one record for every configured team, no unknown or
duplicate IDs, one champion, the exact `1..team_count` placement permutation,
the configured number of championship qualifiers, a qualified champion, and
finite structurally valid regular-season fields. An incomplete path retains the
same team-identity and numeric checks but may omit unresolved qualification or
placement values. Only after every path passes are league-wide totals reconciled.
Malformed paths never become capability-incomplete paths and cannot offset one
another through aggregate totals.

A capability-incomplete path is retained with its path ID and reason. If any
requested path is incomplete, unconditional championship and playoff frequencies
are `None`; observed complete counts are not renormalized. `require_complete=True`
instead fails on the first incomplete path. Domain-invalid paths fail immediately
with the path ID and are never silently replaced. Programming exceptions are not
swallowed.

## M3.4 probability precision contract

`fantasy_football.monte_carlo_precision` adds an immutable analysis and stopping
layer over the accepted M2.6 batches. `analyze_monte_carlo_precision()` analyzes
an already reconciled batch. `run_monte_carlo_to_precision()` executes contiguous
path-indexed chunks, combines them with `combine_monte_carlo_batches()`, and checks
precision only at the configured checkpoints. Its `MonteCarloConfig.path_count`
must equal the explicit maximum path count; path identities and the simulation
fingerprint otherwise retain the M2.6 contract.

`PrecisionConfiguration` requires a family confidence level, absolute target
half-width, minimum and maximum path counts, and positive evaluation interval.
At least the minimum is run before the first decision. Subsequent checks occur at
that interval and at the maximum. A result records every checkpoint and exactly
one stopping reason: `precision_reached`, `maximum_paths_reached`, or
`incomplete_capabilities`.

For every configured team, the analysis reports championship, playoff
qualification, and every exact final-placement probability. Counts remain the
authoritative M2.6 counts. With `T` teams the monitored family contains
`T * (T + 2)` binomial estimands: two outcomes and `T` placements for each team.
The number of planned looks is derived exactly from the minimum, maximum, and
evaluation interval. Each interval is a two-sided Wilson score interval using
Bonferroni allocation across every metric and every planned look:

`alpha_interval = (1 - family_confidence_level) / (monitored_metric_count * planned_look_count)`

The reported interval confidence is `1 - alpha_interval`; endpoint events retain
exact logical bounds of zero or one. Half-width is `(upper - lower) / 2`. This is
a conservative family-wise policy over league outcomes and the entire configured
sequential checking schedule; it does not require the league outcomes to be
independent. League-wide convergence requires every monitored
interval, for every team, to meet the configured half-width after the minimum
path count. A single converged manager or outcome cannot stop the run.

If any path is capability-incomplete, no unconditional probability or interval
is emitted for any team and no complete-only denominator is substituted. With
`require_complete=False`, the precision runner returns
`incomplete_capabilities`; with `require_complete=True`, the underlying accepted
M2.6 fail-fast behavior raises at the incomplete path. Invalid structural paths
continue to fail rather than becoming a stopping result.

The precision configuration and complete analysis each have deterministic
SHA-256 identities. Whole-range and partition-combined batches produce identical
estimates and identities.

## M3.5 bounded parallel execution

`fantasy_football.monte_carlo_parallel` preserves the sequential M2.6 runner as
the correctness reference and adds `run_monte_carlo_batch_parallel()`. Its
`ParallelExecutionConfiguration` requires positive worker and paths-per-task
limits plus an explicitly supported multiprocessing start method. The portable
default is `spawn`; one effective worker deliberately uses the exact sequential
implementation.

Workers receive the immutable snapshot, full run configuration, and outcome
model once through the process initializer. Tasks contain only bounded tuples of
path IDs, and workers return compact `MonteCarloPathSummary` tuples. The parent
sorts asynchronously completed results by path ID, requires exact unique
coverage, and delegates reconciliation to the same M2.6 aggregator. Inputs must
be process-serializable; unsupported inputs fail before workers launch. Worker
exceptions, invalid paths, and incomplete-capability behavior retain sequential
fail-closed semantics.

`ParallelMonteCarloExecutor` keeps one bounded pool alive across M3.4 precision
checkpoints, avoiding repeated serialization and startup for the same immutable
run. Each checkpoint still produces an ordinary `MonteCarloBatchResult` and is
combined through the accepted identity and coverage checks. Worker count, chunk
size, and completion order do not enter simulation fingerprints and cannot alter
path-indexed draws. Runtime diagnostics are observational and are not part of
deterministic result identity. Durable resume and distributed execution remain
out of scope.

## Evidence classification and limitations

All output probabilities remain provisional structural Monte Carlo results, not
fully calibrated forecasts. Wilson intervals quantify only finite path-sampling
uncertainty under the selected outcome model. They do not quantify model-family,
parameter, endpoint-revision, or calibration uncertainty. Player-weeks are conditionally
independent and future availability is governed only by the existing deterministic
engine and its explicit policies. The empirical model's historical pregame
provenance limitation remains explicit. Durable checkpoints, paired trade
scenarios, stochastic injuries, and correlations are deferred.

## Initial performance baseline

Benchmarks ran sequentially under Python 3.12 on the development workstation.
They are synthetic fixtures, not live-league forecasts:

| Workload | Paths | Uninstrumented runtime | Throughput | Traced peak memory |
|---|---:|---:|---:|---:|
| 4 teams, no essential acquisition | 100 | 1.444 s | 69.3 paths/s | 548 KiB |
| 14 teams, supported postseason | 20 | 1.064 s | 18.8 paths/s | 289 KiB |
| 4 teams, transaction-active pool | 20 | 0.499 s | 40.1 paths/s | 114 KiB |

`tracemalloc` increased runtimes to 33.523, 15.697, and 10.492 seconds
respectively and is reported only as memory instrumentation. Separately, 1,000
14-team score-universe generations took 0.282 seconds (0.282 ms/path), showing
that deterministic season mechanics—not key generation—dominate these fixtures.
Exact M2.3 valuation can be substantially more expensive in larger contested
transaction universes; no candidate truncation or legality shortcut was added.

The final identity/reconciliation benchmark combined two validated 50-path
partitions 1,000 times in 4.095 seconds, or 4.10 ms per 100-path combination on
the same workstation. This remains small beside complete path simulation.

M3.4's interval analysis of a reconciled synthetic four-team batch monitors 24
metrics. Repeating the analysis 1,000 times took 0.269 seconds, or about 269
microseconds per analysis. Retaining all 1,000 immutable results under
`tracemalloc` peaked at 7.82 MiB (1.446 seconds instrumented). This isolates
analysis overhead; it is not a live ESPN or complete-season throughput claim.

## M3.5 profiling and benchmark evidence

Before parallelization, `cProfile` on 20 synthetic four-team paths measured
0.965 seconds and about 3.41 million calls. Path execution accounted for 0.960
seconds cumulatively and the deterministic season coordinator for 0.957 seconds;
snapshot validation reached through lineup and transaction mechanics was the
dominant measured subcost. This supported independent path processes without
changing accepted mechanics.

Run the reproducible synthetic matrix with:

```powershell
python benchmarks/benchmark_monte_carlo_execution.py --path-multiplier 5
```

Uninstrumented Python 3.12 results used five paths per task:

| Workload | Paths | 1 worker | 2 workers | 4 workers |
|---|---:|---:|---:|---:|
| 4 teams, no essential acquisition | 200 | 65.37 paths/s | 93.56 paths/s | 75.56 paths/s |
| 4 teams, transaction-active | 100 | 31.16 paths/s | 50.64 paths/s | 38.47 paths/s |
| 14 teams, supported postseason | 100 | 14.28 paths/s | 25.94 paths/s | 28.90 paths/s |

Small 40/20/20-path runs show startup costs: one worker achieved
62.09/27.81/15.27 paths/s, two achieved 37.70/19.27/14.33, and four achieved
19.03/9.34/9.29. Parallel mode is configurable, never an automatic speedup.
On the 100-path 14-team fixture with two workers, chunks of 1, 5, and 20 achieved
17.39, 28.03, and 19.04 paths/s. The benchmark exposes workload, worker, chunk,
and path-multiplier controls.

Optional `--trace-parent-memory` reports only parent Python allocations and
explicitly makes its timings incomparable; it cannot measure aggregate child
resident memory. The small traced matrix observed parent peaks below 0.55 MiB,
but no total multiprocess memory claim is made without OS-level measurement.
These are sanitized synthetic fixtures, not live ESPN forecasts.

## M3.6 execution profiles and recovery

`fantasy_football.monte_carlo_execution` adds runtime policy without placing
execution choices in canonical league data. `QUICK_PROFILE` uses a 95% family
confidence level, 3-percentage-point target half-width, 100 minimum and 1,000
maximum paths, 100-path checks, two workers, and 25 paths per task.
`DETAILED_PROFILE` uses 95%, 1 percentage point, 1,000 minimum and 10,000
maximum paths, 500-path checks, four workers, and 50 paths per task. These are
editable convenience profiles, not league rules or different statistical
models. `SimulationExecutionProfile` supports fully explicit custom policies.

`execute_monte_carlo_profile()` reuses M3.4 analysis and M3.5 workers. After
each complete configured path range it reconciles the entire prefix, calculates
the simultaneous league-wide intervals, and emits a
`ProgressiveExecutionUpdate`. Intermediate updates carry `in_progress` and
`is_final=False`; they never imply convergence. Final reasons are precision,
maximum paths, incomplete capability, or explicit cancellation. The callback
runs only after reconciliation and any configured durable checkpoint write.

`MonteCarloCheckpointStore` writes deterministic JSON beneath an explicitly
approved local root (`outputs/` by default). It writes and flushes a temporary
file, calls `fsync`, and atomically replaces the prior checkpoint. The compact
document contains path summaries and precision history, not the canonical
snapshot, ESPN payloads, credentials, or research rows. Custom roots are an
explicit caller approval; normal private checkpoints remain beneath ignored
`outputs/` and must not be committed.

Recovery verifies the envelope SHA-256; schema; snapshot, league, and season;
simulation and seed-bearing run identities; model ID and complete parameters;
precision and execution-policy fingerprints; configured range; exact contiguous
path prefix; every path invariant; and every saved precision checkpoint against
a fresh calculation from its path evidence. Corruption, missing or overlapping
paths, incompatible seeds/models/policies/workers/chunks, and malformed history
fail before new paths run. A cancelled or externally interrupted run loses at
most the currently executing range; the preceding atomic checkpoint remains
recoverable. Resumed and uninterrupted runs retain identical final batches,
intervals, checkpoint histories, stopping decisions, and analysis identities.
M3.6 adds no cross-run completed-scenario cache or distributed recovery.

The reproducible recovery benchmark is:

```powershell
python benchmarks/benchmark_monte_carlo_recovery.py
```

On the development workstation, a synthetic 100-path/five-checkpoint sequential
run took 2.005 seconds without persistence and 2.400 seconds with persistence
(0.394 seconds measured overhead). Its final checkpoint was 72,558 bytes. Full
validation and recovery of all 100 paths took 0.029 seconds, executed zero new
paths, and reproduced the final precision result exactly. These measurements are
synthetic and filesystem-specific.
