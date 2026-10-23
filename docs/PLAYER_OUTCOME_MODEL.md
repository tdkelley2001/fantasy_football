# Provisional Player Outcome Model

M2.6 introduces `PlayerOutcomeModel`, a deliberately small interface that turns
the canonical player-week universe into one immutable
`DeterministicScoreScenario`. It supplies scores only; M2.5 remains authoritative
for transactions, lineups, matchups, standings, and postseason progression.

## Implemented provisional model

`ProvisionalNormalModel(base_stddev, projection_scale)` uses independent draws:

`score = effective_projection + sigma * Z`

`sigma = base_stddev + projection_scale * abs(effective_projection)`

where `Z` is standard normal. Both dispersion values are mandatory, explicit,
finite, nonnegative inputs and at least one must be positive. They are
illustrative assumptions, not ESPN-derived or empirically calibrated estimates.
Scores are not floored, so finite negative and zero outcomes remain possible.
There are no position multipliers, bias correction, injury events, correlations,
or shared game shocks.

The canonical raw projection, projection class, effective projection, and source
are never modified. Missing-policy zero and explicit ESPN zero both have mean
zero under this provisional family, but remain distinct canonical evidence and
are counted separately in batch metadata. A present finite negative effective
projection retains that signed mean.

## Stable random keys

Each player-week draw hashes the following canonical JSON tuple with SHA-256:

- key-contract name `fantasy-football-player-week-draw-v1`;
- caller master seed and nonnegative path index;
- player ID, season, and scoring week;
- model ID and complete ordered parameters.

Two counter-separated SHA-256 digests produce open-interval uniforms, which are
converted with the Box-Muller transform. No Python `hash()`, batch RNG, shared
mutable generator, or input sequence position participates. Consequently a path
can be reconstructed alone, batches may be reordered or partitioned, and adding
an unrelated player cannot perturb existing player-week draws.

The model generates every canonical in-horizon player-week, including currently
unrostered and reserve players. This ensures that a later legally acquired
starter already has a path-defined outcome. It does not resample after observing
lineups or transactions.

## Replacement boundary

Alternative models implement the same `model_id`, `parameters`, and
`generate_scenario()` contract. Controlled prescribed-score fixtures demonstrate
replacement without coordinator changes. M3 may replace the provisional family
only after separate empirical calibration and provenance review.
