# Search orchestration and performance (M5.8)

Status: **IMPLEMENTED — REVIEW PENDING**.

`fantasy_football.search_orchestration` is the action-family-neutral execution
layer over accepted M5.7 candidate generation and M5.4 statistics. It performs
no ESPN network calls and introduces no transaction, valuation, outcome, or
probability estimator.

## Public contract

`execute_search_orchestration(snapshot, baseline_state, configuration,
simulation, model, ...)` returns an immutable `SearchOrchestrationResult`.
Configuration independently contains the complete M5.7 candidate universe,
fixed or progressive evaluation, M5.4 sampling settings, execution resources,
optional preflight, and optional current-result exports. Omitted resource limits
mean unlimited; positive values are enforced; zero is invalid.

Convenience presets (`quick`, `balanced`, `high_precision`, `exhaustive`, and
`full_bounded`) are editable starting points. They do not change canonical
league rules or candidate-family eligibility. Effective configuration is
retained in every result.

## Reference and bounded modes

Sequential reference mode uses the accepted materialized M5.7 reference.
Bounded mode consumes the same lazy action stream through a producer/consumer
queue with configured backpressure. Candidate and wall-clock generation limits
stop at an explicit boundary and mark coverage incomplete; queue capacity never
discards a candidate. Stable candidate IDs and M5.3 state fingerprints make
queue scheduling invisible.

Progressive evaluation begins only after the eligible unique-state universe is
known. This preserves M5.4 equal initial exposure, the complete unordered-pair
multiplicity family, and order-neutral finalist selection. Numerical parallelism
uses the accepted M3.5 executor with configurable path-task granularity and a
bounded in-flight future count; M5.8 creates no nested process pool.

## Progressive statistics

`evaluate_progressive_state_groups()` exposes the accepted M5.4 method for
M5.7 completed-state groups. It retains matched paths/common random numbers, one
shared baseline, all-team paired precision, all-unordered-state-pair and
all-planned-look Bonferroni protection, minimum finalists, unequal-coverage
overlap comparisons, and separate precision, competitiveness, and ranking
resolution. Equivalent paths share one state evaluation and do not inflate the
multiplicity family. Fixed evaluation remains available through the accepted M4
comparison and makes no progressive ranking claim.

## Preflight, progress, and budgets

Optional preflight measures a bounded candidate prefix, one bounded scenario
Monte Carlo sample when a state exists, elapsed times, throughput, and traced
parent-process memory. It warns that branching survival and adaptive path needs
make extrapolation uncertain. No estimate exists when preflight is disabled.

Immutable progress snapshots distinguish validation, preflight, generation,
grouping, evaluation, refinement, and final aggregation. Candidate coverage,
statistical precision, ranking resolution, workers, elapsed time, and stop
reasons remain separate. The contract never fabricates a completion percentage.

## Results and exports

Candidate results retain path/order, state identity, execution and acquisition
statuses, action count, evaluation paths, requester championship delta,
competitiveness, precision, and caveats. Versioned JSON provides complete or
explicitly filtered current summaries plus compact all-team championship,
playoff, and placement probability changes for evaluated states; CSV provides
the candidate table.
Filters never rerun simulation, invent unsimulated values, or alter analytical
run identity. Exports are explicit and are not a historical run archive.

## Known limits

- Current active results remain in memory. Disk-backed identity/result indexing
  is required before claiming bounded memory for arbitrarily large universes.
- Progressive generation/evaluation overlap is intentionally disallowed because
  accepted M5.4 selection requires the complete eligible universe.
- Wall-clock enforcement stops generation safely; an active Monte Carlo batch
  is allowed to finish.
- M3.6 simulation checkpoints are not duplicated. Search-level durable recovery
  and long-lived run management remain outside this implementation.
- `transaction_authorized` is modeled, not guaranteed ESPN execution or
  counterparty acceptance.

These limits are reported rather than hidden behind pruning or statistical
claims.

## Synthetic benchmark

On 25 October 2026 under Python 3.12 on the development Windows host, a
sanitized four-team universe with five candidates/five unique states and one
path per state took 4.394 seconds in sequential-reference mode with 1.028 MiB
traced peak and 4.516 seconds through the bounded queue with 0.964 MiB traced
peak. The bounded mode was slightly slower at this size, as expected from queue
overhead. This synthetic benchmark is not a live ESPN league forecast and does
not measure child-process RSS.
