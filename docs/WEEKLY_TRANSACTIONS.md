# Weekly Essential Transactions (M2.3d)

Status: **implemented — review pending**. Governing requirements: `MASTER_SPEC.md` Sections 5 and 7 and the M2.3d gate.

## Contract

`execute_weekly_essential_transactions(snapshot, state, policy)` is a pure, deterministic one-window executor. It validates canonical schema v3 and the M2.3b evolving state, then returns `WeeklyTransactionResult` containing a new state, phase/pass counts, initial/frozen/final priorities, selected acquisitions, compact team decisions, rejection counts, assumptions, candidate-plan coverage, V(R) evaluation count, and measured valuation time. Inputs are never modified and no ESPN request occurs.

`WeeklyTransactionPolicy` must explicitly say whether the modeled waiver-processing boundary is authorized. An authorized waiver phase also requires a named assumption/evidence identifier. There is no fallback for unknown real ESPN clearance time. Materially incomplete M2.3c results cannot be compared as exact values.

## Qualification, ranking, and execution

Qualification uses M2.1 on owned players only. A team is eligible only with at least one mandatory positive-projection starter vacancy, and a plan qualifies only if its resulting owned roster strictly reduces that count. A stronger replacement for an already fillable slot is not essential.

For every phase-eligible unowned player, the engine enumerates configured legal destinations and every possible owned-player drop when needed. It also enumerates only M2.3b-authorized reactive IR activation or placement corrections. Each sequence is applied through the immutable legality primitives; failed intermediate actions leave no state or ledger mutation. Every qualifying result is valued with the same equal-weight remaining-season V(R). Maximum resulting V(R) wins; exact ties use acquired player, dropped players, IR movements, and destination slot IDs. No top-N or preferred-position pruning is used.

## Phase ordering

Waiver processing visits the dynamic priority order once per pass. Each team can succeed once in a pass, each successful claimant moves to last, and needs/options are recomputed after every mutation. Passes continue until a complete pass makes no acquisition.

Immediate free agents are then visited in reverse of the priority frozen at the start of the window. This approved V1 behavioral assumption is not an ESPN rule. The order remains fixed even if waiver claims changed dynamic priority, free-agent additions do not change priority, and repeated passes permit multiple essential fills.

The shared state updates ownership immediately. Dropped players remain held and prohibited from the same cycle; no release occurs without M2.3b validated authorization. Acquisition counters, position/roster capacities, undroppable protection, IR evidence, and transaction ledger remain authoritative in M2.3b.

## Termination and limitations

Every success strictly reduces the acting team's current-week vacancy count, removes an acquired player from the pool, and prevents dropped-player same-cycle return. A phase ends on a no-progress pass; there is no arbitrary iteration cap.

This is the approved sequential greedy manager policy, not M2.3e global complete-cycle lookahead and not reconstruction of real submitted ESPN claims. Exact ESPN waiver timing and future strict-mode IR evidence remain externally unresolved. The engine records those restrictions rather than authorizing them. Detailed rejected candidates are summarized by reason to keep diagnostics bounded.

## Test and performance evidence

All **355 credential-free repository tests pass**. Sanitized focused tests cover no-op staffed teams, genuine and ineligible vacancies, FLEX/overlapping-slot repeated passes, contested shared free agents, explicit add/drop holds, finite acquisition limits, waiver priority movement, unresolved waiver boundaries, deterministic reordered inputs, no network, immutability, and M2.1/M2.3c compatibility.

On the development environment, a synthetic 14-team, three-week fixture with 24 pool candidates, four simultaneous essential shortages, and overlapping starter eligibility considered 1,455 plans and performed 68 complete V(R) evaluations in 20.282 seconds uninstrumented; four acquisitions completed in two free-agent passes. A separate four-candidate `tracemalloc` run considered 355 plans and 18 valuations in 33.660 seconds with 0.638 MiB peak traced Python memory. These are synthetic measurements, not live ESPN evidence. Exact repeated V(R) evaluation remains expensive and combinatorial; no candidate coverage was silently discarded to meet a runtime target.
