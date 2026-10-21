# Complete-Cycle Transaction Reference (M2.3e)

Status: **implemented — review pending**. Governing requirements: `MASTER_SPEC.md` Sections 5 and 7 and the M2.3e gate.

## Interfaces and boundaries

`enumerate_feasible_cycles(snapshot, state, policy)` is the exact small-universe counterfactual reference. Its node contains the complete immutable evolving state, phase, pass, current manager order and position, managers processed in the pass, and whether the pass made progress. At every turn it branches over an explicit pass and every M2.3b-authorized essential plan. It updates shared ownership, holds, acquisition counts, ledger, and dynamic waiver priority immediately. Waivers use dynamic-priority passes; free agents use reverse frozen initial priority. The result reports decision nodes, legal acquisition branches, pass branches, complete paths, distinct terminal effects, V(R) calls and time, cache statistics, and an explicit completeness flag.

`execute_sequential_policy_reference(snapshot, state, policy)` independently implements the mandatory-action V1 policy. It uses its own correction and plan enumeration rather than the M2.3d executor: at each turn it chooses the legal coverage-improving result with maximum unified V(R), then applies the stable transaction key. `validate_operational_policy_equivalence()` compares its exact terminal state effects, ledger, and phase-pass counts with the operational M2.3d path. This validates the optimized operational executor; it does not give managers counterfactual hindsight.

`compare_sequential_to_feasible()` confirms that the sequential history belongs to the feasible set and reports each team's attainable V(R) range across complete paths. These per-team extrema can belong to different paths and therefore are not claimed to be jointly attainable. No league-wide, max-min, target-manager, or championship objective is selected.

## Exact enumeration and termination

The feasible reference intentionally does not reuse production correction-graph pruning or deduplication. It uses accepted M2.3b primitives and independently enumerates supported IR placements, required activations, required drops, and final acquisitions. Passing is one branch per manager turn, but a no-progress pass ends the phase; it cannot recur indefinitely. A successful essential acquisition strictly reduces the acting team's current-week vacancy count, removes an available player from the shared pool, increments the applicable acquisition counters, and makes any dropped player unavailable for the current cycle. The finite player universe, finite acquisition limits, irreversible same-cycle holds, one success per team per pass, and phase-ending no-progress pass provide termination without an action-depth cap.

All returned paths are complete. The API currently has no resource-budget mode: if execution is interrupted, it returns no result rather than a misleading partial result marked exhaustive. Exhaustiveness is only claimed for the supplied small universe. The exact tree is exponential and is not intended for full live-league enumeration.

## Correctness evidence

All **371 credential-free repository tests pass**. Sanitized tests cover contested shared ownership, explicit passing, dynamic waiver movement, repeated waiver/free-agent passes, reverse frozen free-agent order through operational equivalence, no duplicate ownership, same-cycle state effects, cache-on/off equality, input reordering, unsupported waiver boundaries, input immutability, and no ESPN calls. The comparison checks roster/IR occupancy, availability and holds, acquisition counters, dynamic and frozen priorities, deterministic ledger, terminal vacancies, and complete per-team V(R).

On 20 October 2026, the exact one-player/four-manager contested fixture produced 47 decision nodes, 6 legal acquisition branches, 7 complete paths and 7 distinct terminal effects. It made 6 V(R) evaluations; under `tracemalloc` it completed in 5.515 seconds with 0.279 MiB peak traced Python memory (uninstrumented pytest execution of the focused module was 1.78 seconds). A separate two-player contested fixture produced 33 paths and 209 nodes in 1.238 seconds. These are synthetic correctness workloads, not live ESPN evidence.

The independent sequential reference on the accepted synthetic 14-team, 24-player, three-week fixture made 68 complete V(R) evaluations, selected four acquisitions in two free-agent passes, and completed in 18.019 seconds, including 13.727 seconds inside V(R). The operational executor's previously recorded equivalent workload was 16.155 seconds. Exact V(R), not manager-loop bookkeeping, remains the dominant cost.

## Limitations

Exact ESPN waiver-clearance timing and future strict-mode IR evidence remain unresolved. The typed modeled weekly boundary authorizes only the approved simulation phase and never clears held players. Unknown evidence remains unavailable. The exhaustive reference has deliberately combinatorial scaling and is suitable only for declared small universes; realistic leagues use the equivalence-tested sequential executor. Caches are keyed by the full immutable state, team, and phase, so ownership, availability, evidence, counters, and priority changes cannot reuse stale plan results. No candidate truncation, top-N filtering, stochastic approximation, or speculative transaction is used.
