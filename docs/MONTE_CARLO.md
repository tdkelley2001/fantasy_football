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
estimates and identities. M3.4 remains sequential; worker execution and durable
resume belong to M3.5 and M3.6.

## Evidence classification and limitations

All output probabilities remain provisional structural Monte Carlo results, not
fully calibrated forecasts. Wilson intervals quantify only finite path-sampling
uncertainty under the selected outcome model. They do not quantify model-family,
parameter, endpoint-revision, or calibration uncertainty. Player-weeks are conditionally
independent and future availability is governed only by the existing deterministic
engine and its explicit policies. The empirical model's historical pregame
provenance limitation remains explicit. Parallel workers, durable checkpoints,
paired trade scenarios, stochastic injuries, and correlations are deferred.

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
