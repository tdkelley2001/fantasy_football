# Exhaustive Single-Trade Candidate Reference

M5.1 implements the candidate-universe stage required by `MASTER_SPEC.md`
Sections 9.2 and 12. It does not screen, value, rank, simulate, or predict
acceptance of trades.

## Public contract

`SingleTradeSearchConfiguration` requires a requesting team, one or more allowed
counterparties, an explicit finite player universe, and one or more positive
`TradeShape(outgoing_count, incoming_count)` records. Optional outgoing and
incoming player filters use `None` for “all correctly owned players in the
declared universe”; an empty tuple intentionally permits no players on that side.
Protected pins use the accepted M4 `ProtectedPlayerPin` semantics during
automatic scenario completion.

`enumerate_single_trade_candidates(snapshot, state, configuration)` validates
the canonical snapshot and complete evolving state, enumerates stable-ID player
combinations for every counterparty and shape, and passes each explicit exchange
through M4 `complete_manual_scenario()`. Its immutable result contains all
structurally feasible candidates and a reconciled coverage summary:

- declared universe, counterparty, and shape counts;
- exact raw combination count;
- feasible and infeasible counts;
- stable infeasibility-reason counts; and
- `complete=True`, which is set only after `raw = feasible + infeasible`.

`iter_single_trade_candidates(...)` is the bounded-memory interface. It yields
the same feasible candidates in counterparty, shape, outgoing-ID, incoming-ID
order but intentionally does not retain rejection counts. Exhaustion of the
iterator means complete feasible coverage of the validated universe; there is no
resource cap or hidden truncation in M5.1.

Each `SingleTradeCandidate` contains a SHA-256 identity, snapshot/schema and
baseline-state identities, requesting team and counterparty, exact shape and
player IDs, M4-compatible explicit changes, the complete M4 hypothetical result,
and execution caveats. Candidate identity represents the baseline plus exact
transaction and remains stable when the same transaction is selected through a
different enclosing filter. It is deliberately distinct from the completed-state
equivalence identity deferred to M5.3.

## Exhaustiveness and validation

For counterparty `p` and shape `(o, i)`, the raw finite count is:

`C(requester_pool, o) * C(counterparty_pool[p], i)`.

M5.1 sums that expression across all configured counterparties and unique
shapes. Combinations come from sorted stable IDs, never mapping/set iteration.
Duplicate teams, players, shapes, malformed counts, unknown IDs, wrong ownership,
players outside the declared universe, requester-as-counterparty, disabled
trades, a closed snapshot-time deadline, and a zero trade limit fail explicitly.
An omitted filter and an explicitly empty filter remain different configuration
identities and behaviors.

Structural feasibility is exactly the accepted M4 what-if contract: binding
ownership changes first, all necessary exact capacity drops, then deterministic
round-robin refill, followed by evolving-state validation. Asymmetric trades are
therefore retained when this approved completion succeeds. Slot eligibility,
position limits, reserve occupancy, roster capacity, pins, and ESPN undroppable
drop protection are not reimplemented here.

## Execution boundary

Every emitted candidate is labeled `structural_hypothetical_only`. This does not
assert that ESPN or a counterparty will execute it. Caveats identify unmodeled
manager acceptance, ESPN execution authorization, M4 completion assumptions,
review/veto outcomes where configured, and unresolved remaining trade-limit
usage. Undroppable protection governs automatic drops; it is not silently
reinterpreted as a verified prohibition on trading that player. M5.1 performs no
network request and never alters the snapshot or state.

## Verification and performance

Hand-checkable tests cover exact one-for-one counts, multiple counterparties,
one-for-two, two-for-one and two-for-two shapes, omitted/empty/restricted filters,
stable identities, reordered inputs, malformed and incorrectly owned inputs,
disabled/deadline/limit rules, protected and undroppable capacity corrections,
input immutability, and no network access. An independently written brute-force
test enumerates leaf combinations and invokes M4 only after constructing each
explicit transaction; its feasible signature set exactly matches production.

Run the synthetic benchmark with:

```powershell
python benchmarks/benchmark_trade_candidates.py
```

On 24 October 2026, its four-team/eight-player/four-shape universe contained 27
combinations. All 27 were feasible and completed in 0.225 seconds untraced
(about 120 combinations/second); a separate traced run peaked at 0.238 MiB.
This is a sanitized small-fixture measurement, not a live-league throughput
claim. Combination count grows multiplicatively, while M4 completion can itself
enumerate capacity-drop alternatives and repeatedly evaluate exact V(R). No
candidate pruning is introduced to hide that cost.

Acceptance evidence: **17 focused M5.1 tests**, **79 combined M2.3/M4/M5.1
contract tests**, and the complete **658-test credential-free suite** pass.
Python compilation, 28 documentation-link tests, Ruff `F,E9`, and Git whitespace
checks also pass.

## Deferred work

M5.3 adds completed-state equivalence identity. Monte Carlo evaluation, waivers,
trade chains, persistence, and CLI integration remain later milestones.

## Optional V(R) screening (M5.2)

`screen_trade_candidates(snapshot, baseline_state, candidate_enumeration,
configuration)` assesses every structurally feasible M5.1 candidate. It calls
the accepted `value_roster()` unchanged and records, for both participants, the
complete baseline result, the result from the actual M4-completed shared league
state, and `after.total_value - before.total_value`. Baseline values are cached
once per participating team. After-values are not computed from the exchanged
players alone; forced drops, automatic refills, all ownership changes, and the
changed shared replacement pool remain visible to V(R).

`TradeScreeningConfiguration()` disables screening by default and therefore
retains every assessed candidate, including negative deltas. When explicitly
enabled, callers may set an inclusive minimum requester delta, an inclusive
minimum counterparty delta, or the convenience nonnegative-counterparty option.
The convenience option conflicts with an explicit counterparty minimum rather
than silently overriding it. Thresholds are finite and compared without prior
rounding. No default positive-value rule, positional filter, top-N cutoff, or
acceptance probability exists.

Every `TradeScreeningOutcome` retains the original candidate, both exact V(R)
diagnostics, pass/fail state, structured failure reasons, screening identity,
the `m2.3c-unified-vr-v1` policy label, assumptions, and the candidate's existing
execution caveats. Screen failure never changes structural feasibility. The
result embeds the complete normalized pre-screen enumeration.

Coverage separately reports raw M5.1 combinations, structural feasibility and
infeasibility, assessed candidates, unique retained/excluded candidates, and
possibly overlapping per-reason exclusion counts. `reason_counts_overlap`
states when one candidate failed multiple criteria. M5.2 has no partial-result
or interruption contract: a malformed identity or incomplete/unsupported V(R)
raises an explicit error and returns no misleading `complete=True` result.

Tests independently recompute both participant deltas, exercise disabled,
requester-only, counterparty-only, convenience, and combined screens, verify
threshold equality and the next representable float, cover asymmetric and
multi-partner completion, prove baseline-cache behavior, and reject incomplete
valuation. The independent threshold oracle exactly matches retained candidate
IDs. **17 focused M5.2 tests**, **73 combined M2.3c/M4/M5 tests**, and the full
**675-test credential-free suite** pass. Compilation, Ruff `F,E9`, documentation
links, and whitespace checks pass.

The sanitized 27-candidate benchmark assessed every candidate in 0.170 seconds
untraced (about 159 candidates/second), retaining 11 under a nonnegative
counterparty-delta screen; a separate traced run peaked at 0.119 MiB. This small
fixture does not predict live-league performance. Exact V(R), not threshold
comparison, is the measured computational bottleneck.
