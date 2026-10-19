# Remaining-Season Roster Valuation V(R)

## Contract

M2.3c implements the deterministic reference valuation

`V_t(R_i, S_t) = sum(w=t..W, estimated_lineup_points(i, w, R_i, S_t))`.

Every remaining scoring week has weight one. The engine uses canonical effective ESPN projections, configured starter slots, raw eligibility, current modeled ownership/occupancy, and M2.3b acquisition availability. It does not use realized-score calibration, injury generation, Monte Carlo, a depth bonus, or a time/playoff multiplier.

The public interfaces are:

- `value_roster(snapshot, state, team_id, ...)` for an accepted evolving state;
- `value_hypothetical_roster(...)` for an explicitly supplied structurally legal roster and availability state, without claiming that ESPN would authorize the producing transaction sequence; and
- `compare_roster_values(baseline, scenario)` for unified delta V(R) and separate current-week vacancy improvement.

Results contain total value, weekly owned/replacement contributions, mandatory and remaining vacancies, owned and estimated replacement assignments, competing demands, opponent assignments, acquisition-state exclusions, access ranks, assumptions, and unresolved-input status. Inputs and ledgers are never mutated.

## Weekly algorithm

1. M2.1 computes every team's exact projected-optimal owned lineup. Reserve occupants remain excluded and nonpositive effective projections remain unavailable.
2. Only actual unrostered canonical players with positive week projections enter the candidate pool. `free_agent` is included under the snapshot-time marginal-access approximation. `waivers` is included only for the current state week when the caller explicitly selects `current_waiver`; teams ahead of the target use the actual current dynamic waiver queue. `hold`, `unresolved`, and rostered players are excluded.
3. Other teams contribute only demonstrated mandatory vacancies. A complete lineup creates no demand merely because an upgrade exists.
4. The exact opponent reference allocates the shared pool lexicographically: maximize opposing vacancies filled, maximize opposing projected improvement, minimize the target's best remaining attainable lineup, then use stable vacancy/player IDs. Each proposed per-team player set is reoptimized with M2.1's exact candidate assignment, so FLEX and overlapping eligibility can rearrange owned players legally.
5. The target receives its exact best lineup from its owned players and the remaining shared pool, with replacement count capped at the pre-replacement mandatory-vacancy count. A player can appear at most once per week across opponent and target assignments.
6. Weekly lineup values are summed without discounting.

This is an exact deterministic allocation for the explicitly selected snapshot-time player universe and modeled access state. It is not a forecast of actual manager claims.

## Provenance and assumptions

Verified ESPN facts are limited to canonical identities, configured slots, eligibility, ownership at retrieval, effective projections under the approved missing-projection policy, and preserved acquisition states. The following are approved V1 modeling assumptions:

- equal weighting of remaining weeks;
- present-information mandatory-demand forecasting only;
- all identifiable future opposing essential needs may be ahead of the target when future priority is unknown;
- current waiver priority is used only for an explicitly selected imminent waiver context; and
- weekly replacement opportunities are marginal access proxies, not persistent acquisitions.

The same replacement player may therefore be an estimated opportunity in several weeks. No speculative ownership or ledger entry is created. Free-agent future availability can change in reality; V(R) intentionally does not invent those transactions. Held and unresolved players remain excluded and visible in diagnostics. No numerical access discount or arbitrary probability is applied.

## Correctness and performance

M2.1's assignment objective and stable tie policy are reused through `optimize_candidate_lineup()`. Tests cover equal-week summation, nonpositive projections, explicit vacancies, shared scarcity, opponent-first allocation, no duplicate assignments, acquisition-state exclusions, current waiver context, actual and structural-hypothetical states, deterministic input reordering, seeded small-pool oracle comparisons, immutability, and no-network execution.

On 18 October 2026, the controlled benchmark with four teams, two competing mandatory vacancies, 120 positive shared-pool candidates, and three scoring weeks completed in **0.153 seconds** on the development environment. This is a bounded representative algorithm benchmark, not a claim about the private 14-team live snapshot. Runtime is sensitive to the number of simultaneous mandatory vacancies and exact-tie allocations; no player cutoff or approximate pruning is used.

The complete credential-free repository suite passes **337 tests**. M2.3d must still implement actual weekly transaction choice and execution; M2.3e must add complete-cycle lookahead and broader equivalence/performance validation.
