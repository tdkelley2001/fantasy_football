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

## Canonical completed states and shared evaluation (M5.3)

M5.3 deliberately keeps three identities separate:

- The accepted M5.1 candidate ID identifies one proposed transaction path.
- `m5.3-completed-simulation-state-v1` identifies the normalized authoritative
  snapshot content and the complete M4-produced `EvolvingLeagueState`.
- `m5.3-shared-paired-evaluation-v1` identifies the baseline/completed state
  pair together with the accepted simulation fingerprints and run identities,
  master seed, exact path range, outcome-model evidence and parameters,
  transaction/postseason/IR policies, numerical semantics, and precision policy.

`completed_state_fingerprint()` uses the accepted order-normalized canonical
snapshot identity. The state portion contains all teams' ownership and slot
assignments, shared availability and holds, dynamic and frozen waiver orders,
week/cycle/matchup position, season and matchup acquisition counters, IR policy
and evidence, assumption IDs, and transaction ledger. Snapshot content supplies
standings, projections and evidence, schedules, eligibility, scoring, roster,
transaction, and postseason rules. No numeric rounding occurs. The ledger is
retained because its sequence base and records remain observable in later
transaction audit output. Candidate labels, explicit-trade descriptions,
search filters, and M4 explanation records are excluded from state identity;
they do not alter the completed state and remain on the candidate path.

`build_candidate_state_registry()` produces a deterministic many-to-one map.
Every `CandidateStatePath` retains its complete M5.2 outcome, which in turn
retains the M5.1 trade and M4 drops, refills, caveats, and diagnostics. State
groups and candidate IDs are canonically ordered. Recomputed hashes, mapping
reconciliation, snapshot provenance, and screening provenance are validated;
conflicts and collisions fail rather than overwrite records. By default only
screen-retained paths are eligible, while an explicit inspection mode can map
excluded paths without evaluating them as recommendations.

The registry also preserves the accepted M5.1/M5.2 baseline-state SHA-256.
Validation independently fingerprints each path's actual
`candidate.completed_scenario.state`; matching path/group labels alone cannot
authorize a candidate-to-state relationship. Candidate snapshot, schema,
baseline, screening, and path identities must all reconcile. Evaluation
recomputes the supplied baseline SHA from the accepted deterministic evolving-
state serialization and rejects a mismatch before invoking Monte Carlo.

`evaluate_trade_candidate_states()` invokes the accepted M4 paired statistical
engine once per unique completed state. All candidates in that group point to
the same immutable `ManualScenarioComparison` object, so probabilities, paired
deltas, path counts, confidence intervals, and all-team reconciliation are not
recomputed or copied into path-specific numerical results. The narrow
`evaluate_completed_manual_scenario()` boundary prevents rerunning M4 roster
completion; it does not change M3/M4 estimators. Worker count is intentionally
absent from the evaluation key because accepted sequential/parallel execution
is numerically identical. Its actual numerical configuration and path coverage
remain included.

Reuse is scoped to one explicit function call. There is no persistent or global
cache, and a projection/snapshot refresh, changed state, model, seed, path range,
policy, or precision configuration creates a different key. Future trade chains
and waiver sequences may use the same identity after they produce a complete
validated state, but their search and execution are not implemented here.

Focused tests construct distinct transaction records with identical completed
states, prove that both remain inspectable, count one actual paired call, and
verify the shared result object. Adversarial tests cover priority, availability,
counter/state, snapshot, model, seed, path-range and precision isolation;
reordered candidates; malformed maps and conflicting content; immutability; and
offline execution. The synthetic exhaustive benchmark has 27 genuine candidate
paths and 25 unique states: 25 paired evaluations execute and two are avoided.
It took 1.337 seconds untraced with 1.364 MiB traced peak memory on 24 October 2026.
This fixture demonstrates exact reuse, not realistic live-league throughput.
All **13 focused M5.3 tests**, **129 focused M3/M4/M5 integration tests**, and
the complete **688-test credential-free suite** pass; Ruff `F,E9`, compilation,
documentation-link, and whitespace checks also pass.

## Progressive paired trade search (M5.4)

`run_progressive_trade_search()` is the integrated, immutable orchestration
boundary. `ProgressiveTradeSearchConfiguration` keeps the accepted M5.1 finite
candidate universe, optional M5.2 screen, and M5.4 sampling policy separate.
The sampling policy validates confidence and paired half-width targets, equal
initial paths, refinement block size, maximum paths per state, minimum finalist
state count, and an optional unique-state initial-evaluation budget. The supplied
`MonteCarloConfig` continues to own seed, first path, league policies, outcome
model inputs, and exact numerical semantics.

The executor first exhausts and screens the full finite universe, then builds
the complete M5.3 registry before sampling. Canonical completed-state IDs—not
candidate arrival order—select states when an explicit budget is smaller than
the eligible universe. Every selected state receives the same initial path
indices. The result records unevaluated states and candidate paths with no
fabricated estimate or rank, sets candidate coverage incomplete, and uses the
`initial_state_budget_reached` stop reason. Such output is a valid partial
observation, not an exhaustive best-trade claim.

After the comparable initial stage, finalist selection retains at least the
configured number of highest requester championship-difference states. It also
retains every state whose direct matched-path championship difference relative
to the current leader has a Bonferroni-adjusted upper confidence bound of at
least zero. This compares paired candidate outcomes directly; it does not infer
competitiveness from overlap of independent marginal intervals. Because the
leader is selected from these same observations, the conservative V1 family is
all possible unordered eligible-state pairs across every planned initial and
refinement look, rather than only the comparisons made with the observed
leader. The underlying two-direction paired interval allocation remains part of
the accepted M4 estimator. This controls the declared finite comparison family;
it does not correct outcome-model error or establish power to resolve close
candidates.

Refinement keeps two separate sets: every state still statistically competitive
for the top rank, and the subset currently eligible for another sample block.
A competitive state that has met its individual all-team precision target stops
sampling but remains in every ranking reconsideration until a simultaneous
paired comparison defensibly excludes it. Competitiveness is recalculated after
every block over the full competitive set; eliminated states cannot re-enter.
When states have different accumulated coverage, their direct comparison uses
only the exact common path-index prefix. One baseline block is shared by the entire search; equivalent M5.3
states share scenario blocks and their immutable M4 comparison. Accepted batches
are combined only when their exact path coverage reconciles, so initial paths
are retained once and never resampled or double counted. A state is labeled
`precision_converged` only when every configured team's paired championship-
probability difference interval meets the requested half-width. Otherwise its
status distinguishes initial-only, selected, maximum-path, and not-evaluated
states. Full playoff and placement comparisons remain attached through the
accepted `ManualScenarioComparison` contract.

Candidate output is ranked by the requesting team's estimated championship-
probability difference, with stable candidate ID tie-breaking. Each row retains
partner, trade shape, M5.1 transaction metadata, M4 completion diagnostics,
M5.2 screening diagnostics, M5.3 state/evaluation identity, full all-team
statistics, and execution caveats. A state can satisfy all-team paired-
difference precision while remaining statistically competitive. A ranking is
resolved only when complete initial candidate coverage exists and exactly one
competitive state remains. Hitting a path or candidate budget with multiple
competitive states reports an unresolved ranking and never a confirmed global
best. Sorting or filtering this immutable dataset
does not trigger new sampling. Coverage independently reports raw combinations,
structural feasibility, screened paths, unique states, initial exposure,
refinement, convergence, baseline/scenario paths actually computed, deduplication
savings, incomplete states, the current competitive set, and ranking resolution.

An optional observer receives immutable `TradeSearchProgressSnapshot` values at
candidate-registry completion, during equal initial exposure, after finalist
selection and each refinement round, and at the final stop. A snapshot contains
only stable identifiers and current estimates; it never exposes mutable engine
inputs. Candidate coverage, all-team precision, and ranking resolution are
separate fields, and an intermediate snapshot is always provisional. The final
snapshot carries the same explicit stop reason as the returned result. This is
an in-process inspection interface, not a job store, queue, recovery mechanism,
or frontend.

The current implementation is a simple exact sequential orchestrator with the
accepted optional bounded process executor at each path block. It has no wall-
clock cutoff, persistent job, resume store, cloud queue, or UI. Candidate budget
and statistical precision remain independent. M5.5+ ranking extensions, waiver
searches, chains, combined searches, and M5.8 machine-specific preflight and
streaming work remain deferred.

The synthetic benchmark uses four teams, eight players, four trade shapes, and
two paths per state. It reports 27 raw/feasible/screen-retained candidates, 25
unique states, 25 initial and 25 refined states, two shared baseline paths, 50
scenario paths, two candidate evaluations avoided by deduplication, and zero
unevaluated states. Under Python allocation tracing the final follow-up took
54.945 seconds and peaked at 3.341 MiB on 24 October 2026; tracing dominates this small synthetic
measurement, so it is not a live-league throughput claim. The follow-up adds
adversarial coverage for data-selected leaders, all-pair/all-look multiplicity,
competitive unresolved rankings despite individual precision, unequal matched
path coverage, genuine statistical exclusion, and immutable coherent progress
snapshots. All **20 focused M5.4 tests** and the complete **708-test
credential-free suite** pass. Ruff `F,E9`, compilation,
documentation-link, and whitespace checks also pass.
