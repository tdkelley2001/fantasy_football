# Chronological empirical-residual comparison

Decision update, September 18, 2026: [V1 is frozen](V1_MODEL.md) as mean-centered
Method D with k=500 and no recency weighting. The additional calibration experiments
proposed below are deferred beyond V1; the measured limitations remain recorded.

This benchmark compares candidate uncertainty methods on the frozen strict
player-week sample. It does not alter the canonical dataset, admit excluded
categories, fit a point-prediction correction, or connect probabilities to the app.

## Results

Completed September 18, 2026. The fixed sample contains 54,564 rows; the first
12,952 (2018–2019) initialize training. There are 34,556 development holdout
observations and 7,056 final-season observations. The weekly check reuses those
7,056 final-season outcomes. Across five methods and both centering modes, the
artifacts contain 486,680 forecast evaluations, not that many independent games.
The [saved result snapshot](residual_validation_results.json) includes final-year
position diagnostics and the lower-tail audit.

**D is the strongest mean-preserving starting point by final-year CRPS, but its
tail coverage is inadequate. E does not earn inclusion at the tested decay rate.**
Keep the uncertainty-model decision separate from the decision to correct ESPN's
point expectation: raw residuals perform differently.

### Centered 2025 season holdout

Training uses 2018–2024 only. Coverage columns are percentages; CRPS is in points.

| Model | CRPS ↓ | 50% coverage | 80% coverage | 90% coverage | 95% coverage |
|---|---:|---:|---:|---:|---:|
| A Universal | 3.0926 | 49.99 | 80.48 | 90.63 | 95.17 |
| B Position | 3.0676 | 50.44 | 80.40 | 90.32 | 95.11 |
| C Projection-local | 2.9551 | 52.07 | 81.21 | 88.76 | 94.08 |
| D Position + projection-local | **2.9347** | 50.28 | 80.07 | 88.75 | 93.03 |
| E D + recency | 2.9369 | 48.97 | 78.87 | 87.66 | 91.85 |

Mean interval widths, in points:

| Model | 50% width | 80% width | 90% width | 95% width |
|---|---:|---:|---:|---:|
| A | 6.15 | 14.18 | 19.59 | 24.65 |
| B | 6.22 | 14.13 | 19.29 | 24.00 |
| C | 6.85 | 13.27 | 17.26 | 20.97 |
| D | 6.81 | 13.24 | 17.33 | 20.88 |
| E | 6.75 | 13.07 | 17.15 | 20.65 |

D reduces CRPS by about 5.1% relative to A and 0.7% relative to C. Its narrower
outer intervals are partly accompanied by undercoverage, so they cannot be called
uniformly better calibrated. E's mean effective sample size falls from D's 500 to
351 in the annual holdout, and its tail coverage worsens.

The same broad conclusion survives weekly updating:

| Model | 2020–2024 holdout CRPS | 2025 annual CRPS | 2025 weekly CRPS | Weekly 95% coverage |
|---|---:|---:|---:|---:|
| A | 3.1431 | 3.0926 | 3.0927 | 95.14% |
| B | 3.1201 | 3.0676 | 3.0673 | 95.08% |
| C | 3.0188 | 2.9551 | 2.9548 | 93.85% |
| D | 2.9960 | 2.9347 | 2.9351 | 92.79% |
| E | 2.9953 | 2.9369 | 2.9371 | 91.61% |

E's tiny development CRPS advantage reverses on the final season. This does not
prove every possible recency method is inferior; it does not justify adopting
the tested one. No half-life was tuned after observing the reversal.

### Raw residual sensitivity

Uncentered 2025 annual results retain each training pool's empirical mean and thus
implicitly shift ESPN's expected score:

| Model | CRPS ↓ | 50% coverage | 80% coverage | 90% coverage | 95% coverage |
|---|---:|---:|---:|---:|---:|
| A | 3.0916 | 50.10 | 80.47 | 90.60 | 95.15 |
| B | 3.0653 | 50.64 | 80.47 | 90.25 | 95.03 |
| C | 2.9046 | 50.35 | 83.62 | 91.52 | 95.41 |
| D | 2.8884 | 49.55 | 82.87 | 91.78 | 95.78 |
| E | 2.8869 | 49.18 | 82.44 | 91.58 | 95.65 |

Widths are identical between centered and raw variants of the same model because
centering translates the distribution. Raw E's small final CRPS advantage is
not evidence of a statistically meaningful improvement. Raw D/E improve the
outer coverage but overcover the 80% interval; neither makes calibration automatic.

### Where centered D fails

Final-year 95% coverage by position is QB 93.80%, RB 94.19%, WR **89.67%**,
TE 96.68%, K 93.32%, and D/ST 95.40%. The aggregate hides a substantial WR issue.

There are 322 observations below D's nominal 95% lower endpoint, versus about
176 expected at a 2.5% lower-tail rate. Of these misses, **216 are zero actuals**;
192 of those are WR observations. Additive mean-centering moves the empirical
zero-score mass along with the rest of the distribution. These findings make
zero-score mass and mean preservation a specific concern for the next experiment,
not merely a reason to widen every interval uniformly.

The next step should test a mean-preserving construction/calibration that handles
zero-score mass, using only earlier data within each evaluation fold. D is a
candidate for that work, not a finished calibrated Monte Carlo distribution.
Do not retune on the now-inspected 2025 outcomes and present the result as a fresh
independent holdout win.

## Protocol fixed before evaluation

- **Season holdouts:** train on 2018 through the preceding year, predict the entire
  held-out season without updating within that season. Evaluate 2020–2025.
- **Development summary:** pooled 2020–2024 season holdouts.
- **Final-season comparison:** 2025, trained only on 2018–2024.
- **Weekly sensitivity check:** predict each week of 2025 using only prior seasons
  and earlier 2025 weeks. Exclude the entire target week, including earlier games
  in that week. The annual and weekly 2025 results reuse outcomes and are not
  independent replications.
- No bandwidth, neighborhood size, decay rate, sample inclusion, or distribution
  form is selected using these results. This is a fixed-design benchmark, not a
  hyperparameter search or an externally preregistered experiment.
- A–D run first and their results are saved before E runs. E uses the same test
  observations and D's same selected neighbors; only their weights change.

| Candidate | Historical residual distribution |
|---|---|
| A | All earlier sample residuals, equal weights |
| B | Earlier residuals at the forecast player's position, equal weights |
| C | Nearest 500 earlier projections in fantasy-point units, across positions |
| D | Nearest 500 earlier projections within the player's position |
| E | D's 500 observations with exponential recency weighting |

Local methods use absolute distance in projected points, not fixed-width bins.
Ties resolve by projected points, season/week, then player ID, independently of
actual outcomes. No sparse-position fallback is used: insufficient support fails
explicitly. Every evaluated local pool has 500 observations. Distance can grow at
the projection extremes; 500 is a benchmark choice, not a validated optimum.

E uses weight `2 ** (-age / 36)`, with age measured by `season * 18 + week`.
This is a two-season scoring-index half-life, not 36 calendar weeks. It includes
an unused Week 18 slot for 2018–2020. Effective sample size is reported as
`1 / sum(normalized_weight ** 2)`. Recency does not change neighbor membership.

## Centering and scores

The primary forecast is ESPN projection plus a historical residual draw after
subtracting that pool's weighted mean. It preserves ESPN as the point expectation,
consistent with the roadmap. Each conditional pool is centered separately, using
training data only. Raw, uncentered forecasts are also scored and shown separately;
these implicitly add a learned conditional bias correction to ESPN.

Reported central intervals have nominal coverage 50%, 80%, 90%, and 95%.
Endpoints are inverse weighted empirical-CDF quantiles at the corresponding equal
tail probabilities. Coverage includes endpoints. Width is upper minus lower,
averaged across observations; adding the ESPN projection does not change width.
Lower- and upper-tail miss rates are included to expose directional asymmetry.
The report does not clip negative scores, trim residual tails, or add smoothing.

CRPS is computed exactly for each finite empirical distribution as
`E|X-y| - 0.5 E|X-X'|`, using normalized weights. This scores the actual empirical
forecast, rather than applying an ensemble-size “fair” correction. Lower is better;
units are fantasy points. The implementation uses sorted cumulative sums and is
tested against the direct weighted pairwise definition. See the
[scoringrules empirical-CRPS documentation](https://scoringrules.readthedocs.io/en/latest/crps_estimators.html).

Aggregates weight each held-out player-week equally. Detailed results are grouped
by season, week, position, projection band, and joint position/projection band.
Aggregate coverage alone can hide subgroup failures. Smaller interval width is
not a win when achieved through material undercoverage.

## Artifacts and reproduction

```powershell
.\venv\Scripts\python.exe -m research.validate_residuals
```

Inputs are `outputs/history/initial_sample.jsonl.gz` and its manifest. The sample
hash is verified before evaluation, and all rows must retain the original sample
membership. No ESPN requests or new dependencies are required.

Outputs under `outputs/residual_validation/`:

- `protocol.json`: settings, source hash, scoring version, implementation hash.
- `stage_abcd.json`, `stage_e.json`: fold audits and grouped results for each stage.
- `stage_abcd_predictions.jsonl.gz`, `stage_e_predictions.jsonl.gz`: per-observation
  interval endpoints (in residual points), coverage, widths, CRPS, pool sizes, and
  effective sample sizes. Add the recorded projection for score-space endpoints.
- `comparison.json`: combined detailed comparison.
- `comparison.html`: standalone tables for the primary and raw sensitivity runs.

The frozen canonical sample and its existing diagnostics are preserved.

## Interpretation limits

This establishes chronological separation of observations. It is not a verified
live as-of replay: archived forecast-generation timestamps and historical revisions
are unknown, and all observations are rescored under the captured current rules.
The sample conditions on known participation and excludes uncertain availability,
so these results do not calibrate injury/DNP risk or complete season probabilities.
Historical evidence quality also differs by year, particularly in 2018.

Player-weeks share players and games. Small CRPS differences should not be called
statistically decisive from row counts alone. Any later tuning needs training-only
or nested chronological selection and a fresh holdout; repeatedly optimizing on
2025 would turn it into another development set.
