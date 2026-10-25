# Immediate multi-trade chains (M5.6)

Status: **IMPLEMENTED — REVIEW PENDING**.

`fantasy_football.trade_chains` is the deterministic reference for immediate
multi-trade what-if paths. It implements the policies approved in
`MASTER_SPEC.md` sections 7–8: finite exhaustive enumeration, chronological
shared ownership, immediate-predecessor dependency, vacancy chronology, and
completion only after the explicit chain.

## Public contract

`TradeChainSearchConfiguration` selects one requesting team, an explicit
tradeable-player universe, allowed counterparties, positive trade shapes,
minimum/maximum chain lengths, optional incoming/outgoing filters, protected
pins, and an optional materialization limit. IDs and configuration inputs are
normalized before hashing. The search derives league size, roster structure,
ownership, trade enablement, deadline, and player eligibility from the
canonical snapshot and evolving state.

`iter_multi_trade_chains(snapshot, state, configuration)` lazily emits feasible
`TradeChainCandidate` paths. `enumerate_multi_trade_chains(...)` materializes a
bounded inspection result with reconciled `TradeChainCoverage`. A configured
limit never masquerades as exhaustive coverage: `complete` becomes false and
the truncation stage and reason are recorded. Zero feasible paths are a valid,
complete result. Stable `TradeChainRejectionCode` values distinguish consecutive
partner, missing immediate dependency, invalid ownership transition, and final
completion failures; human-readable details remain separate diagnostics.

Every path has a stable ID scoped by snapshot, baseline-state identity,
normalized configuration, and ordered trades. Each completed candidate also
uses the accepted M5.3 canonical completed-state fingerprint. Distinct paths
are retained even when that final fingerprint is identical.

## Chronological rules

- Each trade updates both managers' ownership before the next trade is
  generated.
- Trade `n > 1` must send at least one player acquired by the requester in
  trade `n - 1`. Older acquisitions do not satisfy this dependency by
  themselves.
- Consecutive counterparties must differ. A prior counterparty may return
  after an intervening partner.
- Temporary ordinary-roster underfill or overfill is recorded, not repaired or
  used to prune the path. This is structural what-if support, not a claim that
  ESPN would execute the intermediate sequence.
- Protected pins cannot be transferred or automatically dropped.

## Vacancy ledger and completion

After each explicit trade, changes in each affected manager's ordinary-roster
vacancy are recorded with transaction index, creation/reduction count,
outstanding count, and chronological creation priority. Completion replays the
ledger and reconciles it to the actual final imbalance.

Completion occurs once and in this order:

1. enumerate and choose every required capacity drop using the accepted exact
   roster assignment and unified V(R) policy;
2. place all dropped players into the shared completion pool;
3. order managers by their earliest still-outstanding vacancy event;
4. fill all vacancies for one manager before proceeding to the next;
5. validate the complete evolving league state and compute its M5.3 identity.

This is intentionally not M4's round-robin refill policy. A later capacity drop
can therefore be selected by a manager with an earlier outstanding vacancy.
If the ledger cannot establish an unambiguous priority, completion fails rather
than inventing a tiebreaker.

## Evidence and limitations

The engine makes no ESPN calls and submits no transactions. Counterparty
acceptance, veto/review outcome, remaining trade-count authorization, and ESPN
acceptance of temporarily imbalanced intermediate rosters remain unresolved
execution caveats. The completion pool follows the already approved M4
structural what-if policy; it is not a statement about live waiver clearance.

M5.6 does not run Monte Carlo, search waiver moves, combine trade and waiver
universes, estimate acceptance, schedule future-week moves, or implement M5.7+
processing. Exact generation remains combinatorial by design; limits apply
only with explicit incomplete-coverage reporting.

## Synthetic benchmark

On 25 October 2026 under Python 3.12 on the development Windows host, the
six-player/four-team sanitized fixture produced all 16 two-step paths from 72
explored transitions in 0.733 seconds with 0.45 MiB peak traced memory. Its
three-step variant produced all 32 paths from 200 transitions in 1.353 seconds
with 0.50 MiB peak traced memory. These are synthetic reference-search figures,
not a live-league throughput claim; exact branching is combinatorial.
