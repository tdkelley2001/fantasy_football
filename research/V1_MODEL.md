# Frozen V1 residual model

**Status: frozen September 18, 2026, by explicit product decision. Further tuning
is closed for V1.** This is the authoritative marginal-model specification.
The season simulator is now implemented in `fantasy_projection/monte_carlo.py`
and exposed through the app's Simulation view; see the repository README for
lineup selection, dependence, bye handling, reproducibility, and supported rules.
The machine-readable counterpart is [v1_model_spec.json](v1_model_spec.json).

## Distribution

Use **Method D**, with **k = 500** and **no recency weighting**.

For a player at position `p` with ESPN projection `mu`:

1. Take historical observations at the same position from the canonical initial
   modeling sample, scored under the same league rules as the target projection.
2. Select the **500 nearest historical projections**, using absolute distance in
   fantasy points. Resolve ties by historical projection, season, week, then player
   ID, matching the evaluated implementation. Each observation receives equal weight.
3. Compute each historical residual `r_i = actual_i - projection_i` and the selected
   pool's arithmetic mean `r_bar`.
4. Set `epsilon_i = r_i - r_bar`. Sample one of the 500 centered residuals uniformly,
   with replacement across repeated Monte Carlo draws.
5. Return `simulated_score = mu + epsilon_i`.

Thus `E[epsilon] = 0` and `E[simulated_score] = mu`, up to floating-point precision.
These are distribution expectations; a finite Monte Carlo run need not have an
exactly zero sample-average residual.

No raw-pool bias correction, recency weighting, residual trimming, smoothing,
post-draw clipping/flooring, or zero-mass adjustment is part of V1. Those changes
would alter the frozen distribution, and clipping can break the mean constraint.
Do not silently shrink k or substitute another position/universal pool if there
are fewer than 500 eligible observations; report unsupported coverage explicitly.

## Training data and scope

Retain the existing `completed-positive-played-v1` sample contract. Preserve zero
and negative actual results, while requiring a valid positive historical projection,
valid unambiguous actual, recorded participation, and a completed game. Previously
excluded categories are not reintroduced by this freeze.

The initial frozen training snapshot is the existing 2018–2025 sample (54,564 rows),
identified by its hash in the machine-readable specification. Using 2025 as past
training for future forecasts is distinct from using 2025 to choose k; the k
sensitivity used only 2020–2024 development folds. Retrospective evaluations must
continue to train strictly before their held-out season/week.

Training data updates must carry explicit dataset/scoring provenance. Current
scores and historical residuals must use compatible scoring rules. The initial
snapshot is rescored under the captured 2026 rules; changing those rules requires
rebuilding/versioning the scored dataset, not silently mixing point systems.

This defines the marginal player-score distribution. Cross-player/week dependence,
seed management, shared draws between roster scenarios, bye handling, and unresolved
availability/projection coverage belong to the next season-engine implementation.
The freeze does not silently assign independence or invent injury probabilities.

## Evidence supporting the fixed neighborhood

**500–750 is a demonstrated stable region**, not evidence that 500 is optimal.
The controlled 2020–2024 development check produced centered CRPS of:

| k | CRPS |
|---|---:|
| 250 | 3.00410 |
| **500** | **2.99603** |
| 750 | 2.99402 |
| 1,000 | 2.99527 |

The 500-to-750 difference is about 0.067%. We retain 500 without searching for
small further gains. The broader tested 500–1,000 range was also stable in pooled
CRPS, while tail coverage varied more, especially for WRs. See the
[development-only sensitivity methodology](LOCALITY_SENSITIVITY.md) and
[chronological A–E comparison](RESIDUAL_VALIDATION.md).

## Recorded limitations and prospective validation

The freeze accepts the measured limitations; it does not claim exact calibration.
Centered D's previously observed 2025 95% interval coverage was 93.03% overall and
89.67% for WRs. Mean-centering moves the empirical zero-score mass. The canonical
sample also conditions on observed participation, and archived forecast-generation
timestamps are unknown. These findings remain visible in model documentation and
must not be described as resolved by freezing the specification.

**2026 is the eventual truly prospective check.** A prospective evaluation must
use forecasts and a frozen model/data specification saved before the evaluated
outcomes. Outcomes already observed before that freeze are not prospective.
No 2026 outcomes were used to choose this specification, and timestamped future
forecast collection remains work to implement. Any later tuning is a new version,
not an unrecorded alteration of V1.

The implemented season engine uses this exact distribution with independent
player-week residuals, expected-score lineup selection, confirmed-bye zeroes,
and reproducible shared draws across roster alternatives. None of these changes
retunes the frozen residual distribution. The shared transaction backend and
move-screen simulation integration follow in the roadmap.
