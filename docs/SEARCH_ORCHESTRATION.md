# Search orchestration and performance (M5.8)

Status: **COMPLETE AND ACCEPTED**.

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
queue with configured backpressure and writes accepted paths directly to a
temporary SQLite index in `index_page_size` batches. The index stores every
full candidate once, one canonical state payload per M5.3 fingerprint, and the
many-candidate-to-one-state links. `SearchResultIndex.iter_candidates()`,
`iter_candidate_results()`, `state_ids()`, and `get_state_group()` provide
deterministic paged access. Bounded `SearchOrchestrationResult.candidates` is
empty by design; `result.iter_candidates()` is the mode-neutral interface.
`result.close()` removes the database and sidecars. Context-manager use is also
supported, failed construction cleans up, and garbage collection is only a
final safety net. Temporary pickle payloads are process-created implementation
data, never a durable or caller-supplied interchange format.

Candidate and wall-clock generation limits stop at an explicit boundary and
mark coverage incomplete; queue capacity never discards a candidate. Stable
candidate IDs and M5.3 state fingerprints make queue scheduling invisible.

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
comparison and makes no progressive ranking claim. Both fixed and progressive
bounded evaluation load unique states from the index on demand; they do not
rebuild the full candidate tuple.

## Preflight, progress, and budgets

Optional preflight measures a bounded candidate prefix, one bounded scenario
Monte Carlo sample when a state exists, elapsed times, throughput, and traced
parent-process memory. It warns that branching survival and adaptive path needs
make extrapolation uncertain. No estimate exists when preflight is disabled.

Immutable progress snapshots distinguish validation, preflight, generation,
grouping, evaluation, refinement, and final aggregation. Candidate coverage,
evaluation coverage, statistical precision, ranking resolution, workers,
elapsed time, and stop reasons remain separate. One deadline applies to
preflight, sequential or bounded generation, fixed evaluation, and progressive
refinement. It is checked before requesting another candidate or Monte Carlo
batch. An active batch finishes safely; `wall_clock_overrun_seconds` reports the
nominal-budget overrun. Completed comparisons are retained, while skipped
states remain unevaluated and can never be labeled precise or ranking resolving.
An injectable stop signal provides deterministic validation with the same safe
boundaries. Unrelated exceptions still propagate. The contract never fabricates
a completion percentage.

## Results and exports

Candidate results retain path/order, state identity, execution and acquisition
statuses, action count, evaluation paths, requester championship delta,
competitiveness, precision, and caveats. Versioned JSON provides complete or
explicitly filtered current summaries plus compact all-team championship,
playoff, and placement probability changes for evaluated states; CSV provides
the candidate table. Candidate rows are streamed from the index rather than
materialized for export.
Filters never rerun simulation, invent unsimulated values, or alter analytical
run identity. Exports are explicit and are not a historical run archive.

## Known limits

- Compact per-state statistical comparisons remain in memory during M5.4
  finalist selection; full candidate paths and state payloads are disk-backed.
- Progressive generation/evaluation overlap is intentionally disallowed because
  accepted M5.4 selection requires the complete eligible universe.
- An active Monte Carlo batch cannot be preempted and can overrun the nominal
  wall-clock budget; the measured overrun is explicit.
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

The corrected index-growth benchmark used one sanitized candidate/state payload
with 100, 500, and 1,000 distinct path identities. SQLite files grew from
454,656 to 2,142,208 and 4,268,032 bytes, while traced Python peak allocation was
434,756, 711,243, and 697,851 bytes respectively. Runtime was 0.382, 2.034, and
3.966 seconds using deliberately conservative one-row commits; production uses
bounded batch commits. This demonstrates disk growth with path count without
linear retention of full Python candidate objects. It is synthetic, not a live
league workload, and excludes OS page cache and SQLite native allocation.
