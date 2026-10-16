# Development-only locality sensitivity

Decision update, September 18, 2026: [V1 is frozen](V1_MODEL.md) at k=500.
Record **500–750 as a demonstrated stable region**, without claiming an optimal k.
The experiment and its limitations below remain unchanged.

This controlled check varies only the neighborhood size in **method D**
(position plus projection-local empirical residuals): `k = 250, 500, 750, 1000`.
Its purpose is to assess whether the existing 500-neighbor choice sits in a stable
region, not to select the smallest observed CRPS mechanically.

## Result: a stable CRPS region, with some tail sensitivity

Completed September 18, 2026, on the same **34,556** development holdout rows for
every k. The k=500 run reproduces all prior method-D pooled development metrics
within 1e-10, in both centered and raw modes.

Primary mean-centered results:

| k | CRPS ↓ | 50% coverage | 80% coverage | 90% coverage | 95% coverage | Mean 95% width |
|---|---:|---:|---:|---:|---:|---:|
| 250 | 3.00410 | 52.76% | 81.40% | 89.70% | 93.71% | 21.118 |
| **500** | **2.99603** | **52.45%** | **81.71%** | **90.15%** | **94.80%** | **21.471** |
| 750 | 2.99402 | 52.44% | 81.86% | 90.55% | 95.20% | 21.578 |
| 1,000 | 2.99527 | 52.21% | 81.67% | 90.68% | 95.33% | 21.507 |

All widths and CRPS are fantasy points. The HTML/JSON report contains widths at
every requested level, not just 95%.

The CRPS difference between 500 and the best observed value (750) is **0.00201
points, about 0.067%**. Across 500–1,000, the entire CRPS range is only 0.00201.
There is no steep monotonic improvement as locality tightens. The smallest pool
is slightly worse than 500 in every held-out season and undercovers the outer
interval more substantially.

| Held-out season | k=250 CRPS | k=500 | k=750 | k=1,000 |
|---|---:|---:|---:|---:|
| 2020 | 3.04917 | 3.04229 | 3.04446 | 3.05337 |
| 2021 | 3.20046 | 3.18835 | 3.18570 | 3.18785 |
| 2022 | 2.94270 | 2.93511 | 2.93294 | 2.93139 |
| 2023 | 2.88424 | 2.87665 | 2.87332 | 2.87159 |
| 2024 | 2.95025 | 2.94394 | 2.93985 | 2.93838 |

**Keep k=500 as the working default.** The small pooled CRPS improvement at 750
does not justify changing it for this stability exercise. This is a practical
robustness assessment, not a claim of statistically proven equivalence or an
optimal k. No constant or production model was changed.

Tail calibration is less invariant than aggregate CRPS. In particular, centered
WR 95% coverage is **91.55%, 93.55%, 94.53%, 95.02%** across the four k values.
Kicker coverage remains around 93%, while TE coverage remains above 96%. Larger
pools do not solve every position's calibration issue uniformly. Record this as
evidence for the next calibration experiment, rather than freezing the entire V1
distribution based on the CRPS plateau alone.

Raw residual CRPS is also stable: **2.96945, 2.96852, 2.97217, 2.97577**. In that
secondary mode, 500 has the lowest pooled score. Raw distributions still imply
the point-expectation changes discussed in the original comparison; these scores
were not combined with centered scores to select k.

The [saved result snapshot](locality_sensitivity_results.json) includes fold
support, positions, season/position groups, projection bands, and local radii.
The mean farthest-neighbor distances are 0.54, 1.04, 1.50, and 2.04 projected points
for k=250, 500, 750, and 1,000 respectively.

## Design

- Annual expanding-window holdouts: **2020–2024 only**. Each fold trains on 2018
  through the preceding season and holds training fixed throughout the test year.
- **2025 and 2026 are excluded before training and evaluation folds are built.**
  The evaluator also rejects forecasts outside 2020–2024 and any training pool
  reaching the forecast week. The frozen source file contains 2025 records, but
  those records do not enter this experiment.
- Same canonical sample, scoring rules, positions, distance metric, deterministic
  tie handling, quantile definition, and CRPS implementation as the A–E benchmark.
- Primary results center each residual pool to preserve ESPN's mean. Raw results
  are a separate sensitivity check, not an alternative objective used to pick k.
- No recency weighting, sample expansion, bandwidth optimization, tail adjustment,
  or automatic change to the application's model.
- Every k uses the same held-out observations. Pools must contain at least 1,000
  eligible historical observations; there is no silent capping or fallback.

The 2020 kicker training pool has 1,003 observations (D/ST has 1,021). Consequently,
the largest neighborhood is nearly position-wide in that first fold. Later folds
have more data. This is a meaningful change in locality, not just a numerical k
change, so results include individual seasons, positions, season/position groups,
projection bands, and weeks. Mean distance to the most distant selected projection
is recorded as `mean_neighbor_radius`, in projected fantasy points.

## Reproduction and outputs

```powershell
.\venv\Scripts\python.exe -m research.check_locality
```

The script uses the frozen `outputs/history/initial_sample.jsonl.gz` and verifies
its hash against the existing dataset manifest. It writes only to
`outputs/locality_sensitivity/`:

- `protocol.json`: fixed grid, allowed/forbidden seasons, source/rule/code hashes.
- `results.json`: fold boundaries, support counts, and grouped metrics.
- `comparison.html`: coverage and interval widths at 50/80/90/95%, plus CRPS,
  for pooled development observations and each held-out season.

The original A–E comparison and 2025 scores remain unchanged. No 2026 data is
fetched or scored. **2026 is reserved for the eventual prospective check**, which
will need a frozen specification and timestamped forecasts collected before
outcomes; this retrospective sensitivity run does not itself collect those
future forecast snapshots.

Tests cover exclusion of future seasons, chronological training boundaries,
insufficient-support failures, and equivalence between the prefix of a larger
nearest-neighbor pool and independently selecting each smaller k, including ties.

## Interpretation boundaries

Coverage and CRPS remain conditional on the original known-participation sample.
This experiment changes neither unknown inactive status nor the existing
zero-score/centering issue. Stability of k cannot establish that the full V1
distribution is calibrated or ready for season probabilities. The previously
inspected 2025 results cannot be relabeled as an untouched test after making a
development-based choice.
