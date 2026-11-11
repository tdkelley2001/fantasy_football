# LW2.3A performance and consolidation checkpoint

Current disposition: **ACCEPTED**. The checkpoint implemented at `d630887` was independently accepted after implementation, as confirmed in the R2.1 authorization. This is not a V1 release decision or approval to begin LW2.3B. The original report's measurements and delivery-time review statements are preserved below as evidence, not current pending-review claims.

Status at delivery: implemented for independent review. Governing contracts: `MASTER_SPEC.md` section 1.3, `LW2_PARTIAL_WEEK_CONTRACT.md` (LW2.2A through LW2.3A), and `MONTE_CARLO.md` reproducibility, precision and recovery contracts. Accepted execution reference: `86189da`.

## Scope and decision

Retain the accepted production implementation. No simulation, validation, indexing, hashing, model, fingerprint, worker or probability code changes are made by this checkpoint. The measurements do not establish a sustained partial-week slowdown at 1,000 paths. Removing repeated checks or caching prepared inputs would introduce a new validation lifetime for a small, workload-dependent potential gain. That change is not justified by these synthetic workloads and their observed noise.

Deliverables are the separate benchmark harness, inspectable JSON measurements, reference-versus-working-tree equivalence evidence, regression results and this consolidation review. This is not a promotion of live or conditional scoring capabilities.

## Methodology

`benchmarks/benchmark_partial_week.py` uses existing synthetic, hand-checkable fixtures and the accepted `ProvisionalNormalModel(2.0, 0.1)`, seed 12345, paths starting at zero, identical policies and snapshots for V1 and partial modes. Four-team workload: five players, 15 player-weeks, three scoring weeks. Fourteen-team workload: 14 players, 56 player-weeks, four postseason weeks with explicit byes. These are small roster/player pools, not representative full live ESPN snapshots. No network requests, credentials or private league data are used.

Each workload measures 100, 500 and 1,000 paths, sequentially and with two Windows spawn workers, with three repetitions per case (72 timed batches across the two workloads). Parallel task size is 25 paths; each measured parallel batch includes worker startup and shutdown. V1/partial ordering alternates by repetition. Initial two-path warmups are excluded. Wall timings exclude report hashing, profiling and memory sampling. Raw samples, ranges, medians, throughput and full batch hashes are retained, including outliers. There is no claim of statistical significance from three repeats.

`--reference 86189da` loads the three accepted partial/coordinator modules from local Git in both parent and spawned workers. It does not check out files or change production modules on disk. Reference-worker startup includes these local source loads; short-run parallel times are consequently not estimates of a prewarmed production pool. Both V1 and partial modes pay that same reference-loader cost. Other source modules and synthetic fixtures are unchanged from the accepted reference.

Diagnostics are separate runs. cProfile measures 100 sequential paths per mode; its inclusive function times overlap and must not be added. Its instrumentation inflates runtime, so those seconds are not interchangeable with uninstrumented wall seconds. `simulate_deterministic_season` includes first-week preparation/composition. Subtracting `_prepare_partial_week` inclusive time from it identifies the remaining ordinary coordinator work. Composition's self time is reported separately from its inclusive validation work. Memory is sampled every 10 ms with psutil, reporting absolute parent RSS and parent-plus-descendant RSS at 1,000 paths. RSS can double-count shared pages, misses short peaks, and reflects warmup/allocator retention; it is not USS, exact allocation, or an incremental partial-input cost.

Environment recorded in each JSON artifact: Python 3.12.10, Windows 11 build 26300, AMD64 Family 25 Model 97 Stepping 2 (AuthenticAMD), 16 logical CPUs. Background host activity and CPU scheduling/power state were not controlled. In particular, fourteen-team 500-path sequential V1 samples span 5.124–11.543 seconds; differences within such ranges cannot support a caching decision.

## Wall-clock results

Median wall time in seconds; rates are paths/second. Positive overhead means partial is slower. Before/after production code is identical: these are measurements of the retained accepted implementation, not an optimization speedup claim.

| Fixture | Paths | Workers | V1 seconds | Partial seconds | V1 rate | Partial rate | Partial overhead |
|---|---:|---:|---:|---:|---:|---:|---:|
| Four teams | 100 | 1 | 0.612 | 0.600 | 163.4 | 166.5 | -1.88% |
| Four teams | 100 | 2 | 1.365 | 1.366 | 73.2 | 73.2 | +0.06% |
| Four teams | 500 | 1 | 3.080 | 3.005 | 162.3 | 166.4 | -2.42% |
| Four teams | 500 | 2 | 2.646 | 2.656 | 189.0 | 188.2 | +0.38% |
| Four teams | 1,000 | 1 | 6.174 | 5.940 | 162.0 | 168.3 | -3.78% |
| Four teams | 1,000 | 2 | 4.216 | 4.124 | 237.2 | 242.5 | -2.17% |
| Fourteen teams | 100 | 1 | 1.774 | 1.675 | 56.4 | 59.7 | -5.60% |
| Fourteen teams | 100 | 2 | 1.985 | 2.214 | 50.4 | 45.2 | +11.56% |
| Fourteen teams | 500 | 1 | 8.910 | 9.244 | 56.1 | 54.1 | +3.74% |
| Fourteen teams | 500 | 2 | 5.710 | 5.711 | 87.6 | 87.5 | +0.02% |
| Fourteen teams | 1,000 | 1 | 18.009 | 17.017 | 55.5 | 58.8 | -5.51% |
| Fourteen teams | 1,000 | 2 | 10.237 | 10.179 | 97.7 | 98.2 | -0.56% |

The +11.56% short parallel case is retained rather than averaged away. It does not persist at 500/1,000 paths, and this experiment does not isolate its startup/scheduling/input-transfer components. Small parallel batches can cost more than sequential execution because startup dominates; the existing reusable executor remains the appropriate execution mechanism when startup needs amortizing. No new pool or scheduler is introduced.

## Profile and memory results

Separate instrumented 100-path runs, seconds. A dash denotes a function absent in V1. Inclusive measurements overlap; parent coordinator time already contains preparation/composition/validation/serialization work.

| Profile boundary | Four V1 | Four partial | Fourteen V1 | Fourteen partial |
|---|---:|---:|---:|---:|
| Actual canonical validation, inclusive | 0.1233 | 0.1242 | 0.2106 | 0.2112 |
| Partial structural validation, inclusive | — | 0.0720 | — | 0.1374 |
| Proposed lineup validation, inclusive | — | 0.0378 | — | 0.0727 |
| Composition, inclusive | — | 0.0506 | — | 0.0992 |
| Composition, self | — | 0.0058 | — | 0.0113 |
| Companion serialization, inclusive | — | 0.0829 | — | 0.1829 |
| Partial first-week preparation, inclusive | — | 0.1562 | — | 0.3292 |
| Season coordinator, inclusive | 1.3568 | 1.2242 | 4.2314 | 3.8081 |
| Coordinator excluding partial preparation (derived) | 1.3568 | 1.0680 | 4.2314 | 3.4789 |

Actual composition arithmetic is small. Repeated structural validation accounts for approximately 3–5% of profiled partial path time (including generation, outer canonical validation and pregame gating); eliminating half those passes would target roughly 1.5–2.5% before accounting for replacement preparation/guard costs. Static serialization reuse is another possible future improvement, not a measured optimization in this checkpoint. Full snapshot and roster scale should be profiled before introducing shared prepared state. No invented timing is assigned to individual indexing comprehensions; their costs remain in the corresponding function's self time.

Sampled peak RSS, MiB, at 1,000 paths:

| Fixture | Workers | V1 parent | Partial parent | V1 parent + children | Partial parent + children |
|---|---:|---:|---:|---:|---:|
| Four teams | 1 | 55.74 | 55.78 | 55.74 | 55.78 |
| Four teams | 2 | 55.81 | 55.80 | 129.13 | 130.71 |
| Fourteen teams | 1 | 60.76 | 60.94 | 60.76 | 60.94 |
| Fourteen teams | 2 | 60.91 | 60.91 | 135.50 | 137.01 |

The approximately 1.5 MiB parallel difference is an absolute sampled-process observation, not proof of a persistent allocation increase. There is no new cache or retained prepared object in either mode.

## Bottlenecks and consolidation review

- Canonical validation is already suppressed inside one path by the accepted identity-scoped `validated_snapshot` context. It is still performed once per path at the outer boundary, plus fingerprint work. In the four-team 100-path profile, actual `_validate_snapshot` calls number 101 for V1 and 103 for partial mode. This common cost is not a new partial-week regression.
- Partial structural validation executes 402 times per 100 paths, executable checks and lineup legality 201 times each. The pregame gate and the deterministic composer independently validate public inputs, and both executable and proposed-lineup checks revisit structural evidence. This is real redundant work, but removing it requires carefully preserving standalone entry-point guarantees. No bypass flag, unsafe global cache, or weakened validation is introduced.
- Canonical player/roster/projection indexes, draw-routing starter sets and composition setup are reconstructed per path. A prepared immutable object could share them, but must bind snapshot, full companion, lineup, permissions, cutoff and source timing, not merely source payload hashes. Profiling does not justify adding that abstraction here.
- Evidence serialization is repeated in deterministic partial provenance (101 calls including aggregation fingerprint work per 100 paths). The static companion could be prepared once, but the deterministic provenance also includes path-specific realized values and must remain byte-identical. Serialization is visible in the profile but does not produce a measured sustained net slowdown in these workloads.
- First-week partial execution skips projected optimization/transactions and instead preserves the supplied legal assignments. That offsets validation/composition cost. Future-week ordinary simulation remains the dominant work; this checkpoint does not change its mathematics or policies.
- Ruff finds no unused imports/helpers in the LW2 foundation, deterministic coordinator, Monte Carlo integration or diagnostic entry point. Existing modules already cover source serialization, legality and immutable snapshot contexts; a second preparation framework is unnecessary.
- Historical documentation described each package's delivery boundary, sometimes reading as a current prohibition on already-approved later packages. Documentation now identifies the accepted package chain and distinguishes historical scope from current capability. No inferred ESPN field or league setting is promoted.
- Core execution raises contextual validation errors and rejects contradictory evidence. Companion deserialization still has a minor error-taxonomy limitation: a checksum-valid malformed object can raise a raw `KeyError`/enum `ValueError` rather than `PartialWeekError`. It remains non-executable and does not bypass validation. Normalizing that parser taxonomy is a separate correctness cleanup, not a performance change in this checkpoint.
- Production settings remain league-derived. Team/player counts, weeks and seeds in the harness are explicitly synthetic workload parameters, not validation templates. Current-week transaction restrictions, first-round-history limits and unsupported conditional remainder semantics remain intact.

## Reproduction and artifacts

Run from the repository root using the existing test environment:

```powershell
.venv\Scripts\python.exe benchmarks/benchmark_partial_week.py --reference 86189da --diagnostics --output benchmarks/results/lw23a_baseline_four.json
.venv\Scripts\python.exe benchmarks/benchmark_partial_week.py --reference 86189da --workload fourteen_team --diagnostics --output benchmarks/results/lw23a_baseline_fourteen.json
.venv\Scripts\python.exe benchmarks/benchmark_partial_week.py --reference 86189da --verify-only --output benchmarks/results/lw23a_verify_four_team_reference.json
.venv\Scripts\python.exe benchmarks/benchmark_partial_week.py --verify-only --compare-report benchmarks/results/lw23a_verify_four_team_reference.json --output benchmarks/results/lw23a_verify_four_team_retained.json
.venv\Scripts\python.exe benchmarks/benchmark_partial_week.py --reference 86189da --workload fourteen_team --verify-only --output benchmarks/results/lw23a_verify_fourteen_team_reference.json
.venv\Scripts\python.exe benchmarks/benchmark_partial_week.py --workload fourteen_team --verify-only --compare-report benchmarks/results/lw23a_verify_fourteen_team_reference.json --output benchmarks/results/lw23a_verify_fourteen_team_retained.json
```

The harness validates positive path/repeat/worker counts and stops on invalid fixtures, reference load failures or failed equivalence assertions. It never substitutes data or continues after a failed run. Raw JSON is generated by the harness, not manually reconstructed from console timing.

Raw artifacts: [four-team measurements](../benchmarks/results/lw23a_baseline_four.json), [fourteen-team measurements](../benchmarks/results/lw23a_baseline_fourteen.json), [four-team reference details](../benchmarks/results/lw23a_verify_four_team_reference.json), [retained details](../benchmarks/results/lw23a_verify_four_team_retained.json), [fourteen-team reference details](../benchmarks/results/lw23a_verify_fourteen_team_reference.json), [retained details](../benchmarks/results/lw23a_verify_fourteen_team_retained.json).

## Exact equivalence and regression evidence

All 72 timed batch digests agree across repeats and worker counts for each workload/path-count/mode. Ten retained detailed paths per workload are compared against the accepted source oracle in both V1 and partial modes: 40 detailed season results, with exact matching hashes before/after retention. The harness also asserts V1/partial equality of complete draw summaries/digests, first-week frozen scores and regular matchup results, subsequent transitions, final regular standings, complete postseason state and team records. Reference and working-tree hashes of all three execution modules match, and `git diff --exit-code 86189da -- src` passes. There is no internal representation or fingerprint change to explain away.

Affected regressions: **374 passed**, one existing Starlette/AnyIO deprecation warning, in 27.01 seconds. Command:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_partial_monte_carlo.py tests/test_partial_season.py tests/test_partial_week.py tests/test_canonical_snapshot.py tests/test_weekly_engine.py tests/test_postseason.py tests/test_season_simulator.py tests/test_weekly_transactions.py tests/test_player_outcomes.py tests/test_scenario_evaluator.py tests/test_monte_carlo.py tests/test_monte_carlo_parallel.py tests/test_monte_carlo_execution.py tests/test_monte_carlo_precision.py tests/test_app_service.py -q
```

These include accepted V1 configuration/batch goldens, individual draw counting, alternate legal lineups with shared path-indexed draws, batch and precision aggregation, 1/2/3-worker equality, sequential/parallel checkpoint cancellation/resume and incompatible-evidence recovery rejection. No test or production module was changed. Ruff checks of the LW2 foundation/coordinators/diagnostic and benchmark, benchmark formatting/compilation, and `git diff --check` pass. There is no configured static type checker. The initial benchmark attempt encountered sandbox restrictions on Windows worker pipes; the authorized run completed without simulation failures.

## Remaining limits and LW2.3B readiness

The synthetic pools and short horizons do not establish production throughput or memory for 1,061-player snapshots, full rosters, many future weeks or transaction-heavy paths. Two workers do not characterize all hardware scaling. Profiling reports sequential attribution, not worker CPU attribution. RSS sampling is approximate, and the host is not isolated. More representative credential-free workload preparation should precede any run/worker-lifetime cache proposal.

This checkpoint is ready for independent review, not permission to begin LW2.3B. Accepted pregame execution and its existing conditional-equivalence contract remain available. Live in-game work still needs verified active-game score/projection/lock/cutoff semantics, an explicitly approved conditional method and separate milestone approval. No live ESPN evidence was collected. Performance/equivalence findings are **Verified by tests** and synthetic benchmarks; live semantics remain **Unverified**, and conditional live execution remains **Unsupported**.
