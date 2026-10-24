# Manual Generalized Scenario Evaluation

M4 implements the `MASTER_SPEC.md` Section 8 counterfactual workflow. It creates
one structurally legal hypothetical starting state, then compares it with the
unchanged baseline over identical Monte Carlo path IDs and player-week random
outcomes. It does not claim that ESPN or another manager would authorize the
proposed transaction.

## Public contracts

`complete_manual_scenario(snapshot, baseline_state, scenario)` accepts a
validated canonical snapshot, a first-simulation-week `EvolvingLeagueState`, and
an immutable `ManualScenario`. Each `ExplicitRosterChange` identifies the exact
player, current owner (or `None` for an unrostered player), and destination owner
(or `None` for a release). Transfers can involve any number of teams. A player
may appear once. Source ownership, identifiers, protected pins, unique ownership,
slot eligibility, position limits, reserve occupancy, configured capacities,
and drop protection fail before a result is returned.

The immutable `CompletedManualScenario` includes the stable scenario digest,
complete resulting state, canonicalized explicit edits and pins, forced drops,
automatic additions, affected teams, V(R) decision values, pass numbers, and
assumption identifiers. The input snapshot and state are never modified. Pins
protect initial automatic completion only and are not persisted into later
modeled weekly manager behavior.

The comparison also returns one `TeamLineupExplanation` per configured team.
For every remaining scoring week it runs the accepted M2.1 exact optimizer over
both complete roster states and reports optimal starter IDs, projected bench
(ordinary-roster nonstarter) IDs, reserve/IR IDs, explicit vacancies, projected
lineup totals, and their difference. `changed_scoring_weeks` is a compact index
of any roster-set, starter-set, vacancy, or projection change. These are
projection-only explanations of the roster consequence; they are not realized
scores and do not reinterpret Monte Carlo outcomes.

`evaluate_manual_scenario(...)` completes the scenario, runs baseline and
hypothetical configurations, verifies exact path coverage and equal score-scenario
digests for every paired path, and returns standalone M3.4 probability analyses
plus paired championship, playoff, and every-placement differences for every
configured team. Sequential and bounded multiprocessing use the same API.

## Completion algorithm

1. Apply all binding ownership edits to a temporary ownership map. This phase may
   be underfilled or overfilled but never duplicate ownership.
2. Enumerate every legal set of required ordinary-roster capacity drops across
   overfull teams. Pinned, ESPN-protected, and protection-unknown players cannot
   be selected. Complete assignability is checked using configured slot and
   position capacities. The same M2.3c `value_roster()` selects the least-damaging
   result. With more than one overfull team, the exact objective is the tuple of
   their resulting V(R) values in frozen current waiver-priority order, followed
   by stable player IDs. This is deterministic priority ordering, not an ESPN
   simultaneous-drop rule.
3. Add every explicit and automatic release to the shared hypothetical completion
   pool. Current real waiver/hold status does not bar this one-time completion,
   as approved by Section 8.2; no live clearance timestamp is invented.
4. Visit teams in the frozen current ESPN waiver-priority order, at most once per
   pass. A team below configured ordinary capacity selects the legal player whose
   complete resulting state has maximum V(R), with player ID as the exact tie
   break. Repeat until every team is full or fail if no legal completion exists.
5. Restore untouched unowned players' original acquisition evidence. Players
   released by the scenario remain available under the explicit structural
   hypothetical assumption. Validate the final evolving state.

All necessary capacity drops occur before the first automatic addition. A player
dropped later in the all-drop stage can therefore refill an earlier vacancy. No
top-N pruning, independent positional score, nested Monte Carlo, speculative
injury, automatic trade search, or multi-step chain is used.

## Identity and paired statistics

`MonteCarloConfig.initial_evolving_state` is now part of the simulation
configuration fingerprint. The master seed remains in the run identity. Baseline
and scenario therefore have distinct simulation/run identities but generate the
same score scenario for a given model, master seed, path ID, player, and week.
Every paired path verifies the score-scenario SHA-256 before comparison.

For each binary outcome, M4 records per-path differences in `{-1, 0, 1}`, their
mean (scenario probability minus baseline probability), and improved/worsened/
unchanged counts. The interval separately bounds the paired improvement and
worsening probabilities with Wilson score intervals, then conservatively
differences those bounds. Bonferroni allocation covers both discordance directions
for the full family of `team_count * (team_count + 2)` championship, playoff, and
placement comparisons. This remains nondegenerate for zero-event and small-sample
cases. Bounds are clipped to the possible difference range and quantify Monte
Carlo sampling uncertainty only;
they do not quantify outcome-model calibration or parameter uncertainty. The
standalone M3.4 Wilson intervals remain separately available.

## Reproducible local command

The CLI reads an existing validated snapshot from the accepted SQLite store and
a strict JSON scenario. It performs no ESPN request. This example deliberately
selects the retained provisional Normal baseline and makes its dispersion inputs
explicit:

```powershell
python -m fantasy_football.scenario_evaluator `
  --database outputs/fantasy_football.sqlite3 `
  --snapshot-id <published-uuid> `
  --scenario outputs/private-scenario.json `
  --output outputs/private-scenario-result.json `
  --master-seed 20261023 --paths 1000 `
  --confidence-level 0.95 --target-half-width 0.02 `
  --normal-base-stddev 3.0 --normal-projection-scale 0.35 `
  --workers 2 --paths-per-task 25
```

Scenario input schema:

```json
{
  "scenario_id": "stable-user-label",
  "changes": [
    {"player_id": 101, "from_team_id": 1, "to_team_id": 2},
    {"player_id": 202, "from_team_id": 2, "to_team_id": 1}
  ],
  "protected_pins": [{"team_id": 2, "player_id": 101}]
}
```

Private inputs and results must remain under ignored local storage. The CLI
enforces output beneath `outputs/`. Its projection-based IR mode and provisional
Normal choice are explicit limitations; callers needing a validated strict-IR
state or the empirical research model use the programmatic API. Finite acquisition
limits whose historical counts are unavailable remain fail-closed during state
initialization.

## Verification and performance

Focused tests cover multi-team swaps, asymmetric capacity, protected pins,
undroppable players, shared-pool round-robin refill, invalid ownership, reordered
input, immutability, exact all-team reconciliation, zero-delta identity scenarios,
matched score digests, paired intervals, compact deterministic output, and
sequential/parallel equality. Separate fixtures prove both a trade that changes
the exact optimal starter and a bench-only trade that leaves the starter and
projected lineup points unchanged. The CLI gate publishes a sanitized canonical
snapshot through the real SQLite store, reads a strict scenario JSON file, runs
the actual entry point twice, and verifies byte-identical all-team output without
network access; invalid JSON and output outside `outputs/` fail explicitly.

## M4.3 requirement reconciliation

M4.3 does not introduce a duplicate utility. The accepted M2.3c
`value_roster()` contract already supplies the required remaining-week utility:
`test_equal_weight_multiweek_value_and_replacement_diagnostics` proves equal
week weighting and replacement diagnostics; the nonpositive-pool and
held/unresolved tests prove missing-access behavior; shared-pool, overlapping
eligibility, target-adverse, and exhaustive-oracle tests prove exact replacement
effects; add/drop tests prove one unified resulting-roster value; and the
representative-pool test records timing and no-network behavior. Known byes and
other unavailable weeks enter through the canonical week projection contract,
so a nonpositive or missing projection cannot start. Bench value arises only
when the exact weekly lineup selects that player or through the approved
replacement comparison. The implementation is exact rather than a new heuristic
"fast V(R)"; repeated exact V(R) remains the documented combinatorial performance
limit.

Acceptance evidence: **20 focused M4 tests** and the complete **640-test
credential-free repository suite** pass. Python compilation, documentation-link
validation, Ruff `F,E9`, and Git whitespace checks also pass.

Run the reproducible synthetic benchmark with:

```powershell
python benchmarks/benchmark_manual_scenario.py
```

On 23 October 2026, the four-team/100-matched-path fixture completed structural
scenario construction in 0.017 seconds and paired evaluation in 3.002 seconds
(33.306 paired paths/s). Completion-only traced Python memory peaked at 0.031
MiB. A deliberately traced whole paired run took about 99.9 seconds, demonstrating
that `tracemalloc` heavily distorts this workload; it is not used as the throughput
figure. These are synthetic test-fixture measurements, not live-league claims.
Exact capacity-drop combinations and repeated V(R) evaluations remain
combinatorial for large imbalanced scenarios.

## Boundaries

M4 does not search for trades or waivers, model acceptance, schedule future
actions, execute a real ESPN transaction, implement multi-step chains, alter the
M2.3 weekly manager policy, or build a dashboard. Explicit changes are binding
what-if inputs. Automated action search remains M5.
