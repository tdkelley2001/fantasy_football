# Provisional Repeated Season Simulation

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

For a fully complete batch, team aggregates contain championships, playoff
qualifications, runner-up finishes, every placement count, and averages for
placement, regular rank, wins, and points for. Frequencies use all requested
paths. Reconciliation requires one champion and one owner of every placement per
path, the configured championship qualifier count, known team IDs, and complete
per-team placement distributions.

A capability-incomplete path is retained with its path ID and reason. If any
requested path is incomplete, unconditional championship and playoff frequencies
are `None`; observed complete counts are not renormalized. `require_complete=True`
instead fails on the first incomplete path. Domain-invalid paths fail immediately
with the path ID and are never silently replaced. Programming exceptions are not
swallowed. M2.6 does not implement adaptive stopping or forecast intervals.

## Evidence classification and limitations

All output frequencies are provisional structural Monte Carlo results, not
calibrated forecasts. Fixed-run sampling variation is distinct from unmeasured
model-parameter and calibration uncertainty. Player-weeks are conditionally
independent and future availability is governed only by the existing deterministic
engine and its explicit policies. Parallel workers, checkpoints, paired trade
scenarios, stochastic injuries, correlations, and empirical fitting are deferred.

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
