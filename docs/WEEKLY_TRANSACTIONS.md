# Weekly Essential Transactions (M2.3d)

Status: **implemented — review pending**. Governing requirements: `MASTER_SPEC.md` Sections 5 and 7 and the M2.3d gate.

## Contract

`execute_weekly_essential_transactions(snapshot, state, policy)` is a pure, deterministic one-window executor. It validates canonical schema v3 and the M2.3b evolving state, then returns `WeeklyTransactionResult` containing a new state, phase/pass counts, initial/frozen/final priorities, selected acquisitions, compact team decisions, rejection counts, assumptions, candidate-player count, correction states explored, attempted sequences, unique legal effects, V(R) evaluation count, and measured valuation time. Inputs are never modified and no ESPN request occurs.

`WeeklyTransactionPolicy.waiver_boundary` accepts only the typed `WaiverBoundaryPolicy` values `UNRESOLVED` and `MODELED_WEEKLY_V1`. The latter is the approved simulation boundary and is labeled `modeled_weekly_waiver_boundary_v1`; an arbitrary string cannot authorize processing. No live ESPN boundary provider is implemented. This boundary authorizes the modeled phase only: it neither clears a particular player nor releases a hold. There is no fallback for unknown ESPN clearance time. Materially incomplete M2.3c results cannot be compared as exact values.

## Qualification, ranking, and execution

Qualification uses M2.1 on owned players only. A team is eligible only with at least one mandatory positive-projection starter vacancy, and a plan qualifies only if its resulting owned roster strictly reduces that count. A stronger replacement for an already fillable slot is not essential.

For every phase-eligible unowned player, the engine enumerates configured legal destinations and every possible owned-player drop when needed. It performs a finite state search over M2.3b-authorized reactive IR corrections. Projection-mode recovered occupants and strict-mode occupants with validated current-week `INELIGIBLE` evidence are activation requirements; strict `ELIGIBLE` occupants remain legal, while missing/`UNKNOWN` evidence is unresolved. Placement is considered only for a verified `OUT`/`IR` ordinary occupant whose currently full slot is a legal destination for the specific acquisition candidate. This prevents unrelated IR reshuffling for V(R).

The search can combine multiple placements, required activations, activation-capacity drops, and the final add/drop. Each player can consume ordinary-to-IR or required IR-to-ordinary movement at most once, and drops are irreversible in the cycle, which proves finite termination without a depth cap. Search identity retains roster, ownership, availability, counts, evidence and transition-history flags that affect future legality. Effect-equivalent final states may be canonicalized deterministically; materially different availability or ledger effects are retained.

Diagnostics preserve three stages. `legally_executable_plans` counts attempted sequences whose primitives all succeed; `essential_qualified_plans` is the subset strictly reducing owned-lineup vacancies; `valuation_complete_plans` is the subset with comparable complete V(R). Counts are sequence counts. `unique_legal_resulting_states` separately counts deduplicated legal effects. Rejections distinguish unresolved authorization, protection, limits, capacity, availability, non-improving coverage, incomplete valuation, and structural ineligibility. Every qualifying result is valued with the same equal-weight remaining-season V(R). Maximum resulting V(R) wins; exact ties use acquired player, dropped players, IR movements, and destination slot IDs. No top-N or preferred-position pruning is used.

## Phase ordering

Waiver processing visits the dynamic priority order once per pass. Each team can succeed once in a pass, each successful claimant moves to last, and needs/options are recomputed after every mutation. Passes continue until a complete pass makes no acquisition.

Immediate free agents are then visited in reverse of the priority frozen at the start of the window. This approved V1 behavioral assumption is not an ESPN rule. The order remains fixed even if waiver claims changed dynamic priority, free-agent additions do not change priority, and repeated passes permit multiple essential fills.

The shared state updates ownership immediately. Dropped players remain held and prohibited from the same cycle; no release occurs without M2.3b validated authorization. Acquisition counters, position/roster capacities, undroppable protection, IR evidence, and transaction ledger remain authoritative in M2.3b.

## Termination and limitations

Every success strictly reduces the acting team's current-week vacancy count, removes an acquired player from the pool, and prevents dropped-player same-cycle return. A phase ends on a no-progress pass; there is no arbitrary iteration cap.

This is the approved sequential greedy manager policy, not M2.3e global complete-cycle lookahead and not reconstruction of real submitted ESPN claims. Exact ESPN waiver timing and future strict-mode IR evidence remain externally unresolved. The engine records those restrictions rather than authorizing them. Detailed rejected candidates are summarized by reason to keep diagnostics bounded.

## Test and performance evidence

All **362 credential-free repository tests pass**. Sanitized focused tests cover no-op staffed teams, genuine and ineligible vacancies, FLEX/overlapping-slot repeated passes, contested shared free agents, explicit add/drop holds, necessary IR placement, strict `ELIGIBLE`/`INELIGIBLE`/`UNKNOWN` evidence, finite acquisition limits, controlled waiver authorization, stage-count reconciliation, waiver priority movement, unresolved waiver boundaries, deterministic reordered inputs, no network, immutability, and M2.1/M2.3c compatibility.

On 20 October 2026, a synthetic 14-team, three-week fixture with 24 pool players, four simultaneous essential shortages, and overlapping starter eligibility counted 106 candidate-player visits and correction states, attempted 1,455 sequences, produced 823 unique legal effects, and performed 68 complete V(R) evaluations. Four acquisitions completed in two free-agent passes in **20.650 seconds**, of which **13.505 seconds** was inside V(R). A separate four-player `tracemalloc` run counted 26 candidate/correction visits, 355 attempted sequences, 203 unique legal effects and 18 valuations in **28.555 seconds**, with **11.315 seconds** in V(R) and **0.811 MiB** peak traced Python memory. These are synthetic measurements, not live ESPN evidence. Exact repeated V(R) evaluation remains expensive and combinatorial; no candidate coverage was silently discarded to meet a runtime target.
