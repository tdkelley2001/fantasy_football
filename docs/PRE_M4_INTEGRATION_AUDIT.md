# Pre-M4 Integration and Consolidation Audit

Reviewed baseline: `87cdbbb` (23 October 2026). This audit verifies the
accepted M0–M3.6 foundation and does not implement M4. Its governing contracts
are `MASTER_SPEC.md` Sections 5, 7, 8, 10, and 12 and the standing rules in
`AGENTS.md`.

## Outcome

The integrated foundation remains suitable for M4 after one narrow correctness
fix. A reusable multiprocessing executor previously checked the seed-independent
simulation-configuration fingerprint but not the seed-bearing run identity when
accepting another batch. Its workers retain the seed used at pool initialization,
so a caller could submit a different-seed batch whose aggregate claimed the new
identity while draws came from the old seed. `ParallelMonteCarloExecutor` now
requires both identities to match before dispatch. An adversarial regression
proves rejection before worker execution.

No other blocking consistency, league-hardcoding, private-data, checkpoint, or
reconciliation defect was established. M4 remains unstarted. This consolidation
was subsequently accepted before M4 began.

## End-to-end contract review

| Boundary | Authority and consistency finding |
|---|---|
| Canonical evidence | Schema-v3 immutable snapshots remain the only league authority; historical v2 reads do not acquire v3 transaction authority. Source references and raw/normalized distinctions remain intact. |
| Rosters and lineups | Evolving state is separate from snapshot evidence. M2.1 consumes complete modeled roster entries, exact configured slots, and excludes IR occupants. |
| Transactions and valuation | M2.3b owns legality; M2.3c values complete legal hypothetical states without mutating them; M2.3d executes essential-only plans; M2.3e retains independent small-case references. Their apparent overlap is intentional oracle separation. |
| Weekly and postseason mechanics | M2.2 scores frozen assignments. M2.4 derives supported graphs and periods from canonical/configured rules and fails closed for unsupported structures. M2.5 carries one shared immutable path state. |
| Outcome evidence | M3.1/M3.2 research remains outside production snapshot state. M3.3 preserves model/evidence identity and matched player-week keys; the empirical model remains provisional because historical pregame timing is unverified. |
| Aggregation and precision | M2.6 reconciles exact path IDs and counts. M3.4 applies simultaneous Wilson intervals to every configured team and required outcome metric without renormalizing incomplete paths. |
| Parallel and recovery | M3.5 now checks seed-independent configuration and seed-bearing run identities for reusable workers. M3.6 additionally validates model parameters/evidence, precision policy, execution policy, exact prefix coverage, path summaries, and recomputed precision history. |

Sequential, parallel, differently partitioned, and resumed execution all converge
through the same `MonteCarloPathSummary` and batch reconciliation contracts.
Tests compare actual path summaries and complete aggregates, not merely totals.

## League configuration review

The production search found no fantasy-league-size branches for 10, 12, 14, or
16 teams and no hardcoded six-qualifier/eight-consolation production template.
Configured team, slot, scoring, acquisition, period, qualifier, and bracket data
remain canonical inputs. ESPN slot IDs and the 32-NFL-team check are documented
source-namespace/domain invariants, not fantasy-league defaults. Traditional
waiver execution, modeled weekly processing, reverse frozen-priority free-agent
ordering, projection-based IR recovery, and all-team postseason participation
remain explicit supported policies rather than universal ESPN claims. FAAB,
unknown clearance timing, unresolved strict-IR evidence, and unsupported bracket
structures remain capability-specific fail-closed cases.

## Identity matrix

- `simulation_configuration_fingerprint`: canonical content, model identity and
  parameters, simulation policies and semantics; deliberately excludes seed and
  path range so compatible partitions can combine.
- `monte_carlo_run_identity`: simulation fingerprint plus master seed.
- path identity: run identity plus exact path index, with scenario/evidence
  digests checked during aggregation.
- precision identity: confidence, target half-width, minimum/maximum counts and
  evaluation interval.
- execution identity: profile plus precision identity and parallel worker/chunk/
  start-method configuration.
- recovery identity: all of the above plus snapshot/league/season, model evidence,
  configured starting index, maximum coverage, checksum, exact prefix, and
  recomputed checkpoint history.

The fixed reusable-worker boundary is the only place this review found a missing
identity dimension.

## Storage and confidentiality

`.env`, `outputs/`, SQLite files and sidecars, bytecode, environments, coverage,
and build artifacts are ignored. The tracked-file audit found only `.env.example`
among credential-pattern paths and no tracked private research/checkpoint JSON or
database. Historical materialization refuses output outside an explicitly
ignored private root. Checkpoints default beneath ignored `outputs/`, contain
compact path summaries rather than source snapshots/research rows/credentials,
and use checksum validation plus flushed atomic replacement. Custom checkpoint
roots remain an explicit caller responsibility.

## Dead code and duplication

Static correctness checks found two no-effect production remnants and four
test/fixture remnants; they were removed. No production module was shown to be
obsolete. The exhaustive allocation, correction, transaction-cycle, and
sequential-policy references are deliberately independent correctness oracles.

`run_monte_carlo_to_precision()` and `execute_monte_carlo_profile()` retain
similar checkpoint loops. They serve different public contracts (one-shot
precision versus progressive durable execution), are tested against identical
results, and are not refactored here because extracting a shared framework would
add risk without a demonstrated correctness benefit.

## Performance findings for M4

Existing representative measurements show exact transaction search/V(R) is the
largest state-dependent cost (the 14-team essential-transaction fixture spent
12.266 of 16.155 seconds in V(R)). M3.5 profiling of 20 synthetic full-season
paths measured 0.965 seconds and identified repeated canonical validation through
lineup/transaction calls as the dominant deterministic subcost. The documented
14-team workload reached 28.90 paths/s at four workers, while small jobs often
became slower from startup overhead. Recovery validation for 100 paths took
0.029 seconds and checkpoint persistence added 0.394 seconds in its synthetic
measurement.

These are likely M4 hot spots because paired scenarios repeat invariant snapshot
validation and exact valuations. They are performance opportunities, not current
correctness defects. Before changing them, M4 should profile representative
paired scenarios and prove any validated-context cache key covers snapshot,
ownership, availability, team, week, evidence, and policy. No candidate pruning,
mechanics approximation, or speculative cache was introduced here. Aggregate
child-process resident memory remains unmeasured; existing `tracemalloc` numbers
cover parent Python allocations only.

## Documentation and status findings

M3.6 is now recorded as accepted, matching the supplied review status. The
master specification, roadmap, README, Monte Carlo contract, league-configuration
audit, and this report agree that M4 is not started. Historic benchmark/test
counts remain dated evidence and are not rewritten as current measurements.

## Remaining limitations and recommendation

The material known limits are evidence/model limits rather than consolidation
defects: historical ESPN projections lack authenticated pregame timing; the
empirical distribution is provisional; future waiver clearance and strict-IR
facts are unresolved; some league transaction/bracket modes remain unsupported;
and exact transaction searches are combinatorial.

Final disposition: **ACCEPTED**. M4 began only after that review, from the
existing public scenario, run-identity, and matched-draw contracts.

## Verification evidence

- Focused Monte Carlo identity, precision, parallel, recovery, and documentation
  regression: **103 passed**.
- Complete credential-free repository suite: **619 passed in 43.82 seconds**.
- Python 3.12 bytecode compilation: passed.
- Ruff correctness profile (`F,E9`) over `src` and `tests`: passed.
- Git whitespace validation and tracked-private-artifact scan: passed; the only
  tracked environment-pattern file is the intentionally sanitized `.env.example`.
