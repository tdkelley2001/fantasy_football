# Provisional Player Outcome Models

M2.6 introduces `PlayerOutcomeModel`, a deliberately small interface that turns
the canonical player-week universe into one immutable
`DeterministicScoreScenario`. It supplies scores only; M2.5 remains authoritative
for transactions, lineups, matchups, standings, and postseason progression.

## Preserved Normal baseline

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
replacement without coordinator changes.

## M3.3 projection-conditioned empirical model

`fit_projection_empirical_residual_model(dataset, report,
selection_reference=...)` constructs the approved, explicitly provisional
`ProjectionEmpiricalResidualModel`. It first verifies the deterministic M3.1
dataset and M3.2 report identities, requires the report to reference that exact
dataset, and requires its selected exploratory candidate to be
`projection_empirical_residual`. There is no alternative-family fallback.

Training rows are strictly earlier than the report's configured temporal
evaluation boundary. A row is usable only when it contains a raw ESPN projection
and actual, is not policy-imputed, and satisfies the report's evidence policy.
The accepted 2024/2025 evidence therefore enters as
`unverified_exploratory`, never authenticated pregame evidence. The fitted model
records the dataset SHA-256, report SHA-256, temporal boundary, projection-bin
edges, minimum group size, sparse-group policy, training count, exact fitted-row
SHA-256, fitted-atom SHA-256, selection reference, and draw contract in
`parameters`. All participate
in the M2.6 simulation fingerprint.

For a finite present ESPN projection, the model selects its configured
projection band. A band meeting `minimum_group_size` uses that band's empirical
observations. A sparse or absent band uses the explicitly recorded
`pooled_empirical` within-family policy; this is the same established M3.2
empirical fallback and is not a silent distribution substitution. Each nonzero
historical observation contributes `target projection + historical residual`.
Each historical actual of exactly zero contributes an exact zero atom. Sampling
uses the discrete empirical quantile without interpolation, rounding, flooring,
or conditional bias correction. Signed residuals and negative simulated scores
remain possible.

Canonical `MISSING` and `EXPLICIT_ZERO` projection classes remain unavailable
under the accepted lineup policy and receive deterministic zero outcome records
from this model. Their distinct raw projection class and effective source remain
unchanged in the snapshot and batch projection-class counts. Policy-imputed
historical zeros never enter fitted evidence.

## Matched empirical random keys

The empirical model hashes canonical JSON containing:

- key contract `fantasy-football-empirical-quantile-v1`;
- master seed and path index;
- stable player ID, season, and scoring week;
- independent draw dimension `outcome_quantile`; and
- complete model ID and parameters.

The digest maps to one open-interval uniform empirical quantile. Ownership,
roster position, transaction order, team-processing order, collection order,
batch boundaries, and worker assignment do not enter the key. The same
player/week/path therefore receives the same draw in baseline and hypothetical
scenarios even when ownership differs. Different players, weeks, paths,
evidence, or model configuration receive distinct deterministic keys.

## Benchmark and limitations

On Python 3.12.10, a synthetic accepted season-shaped fixture with 15
player-weeks generated 5,000 empirical scenarios in 0.784 seconds uninstrumented
(about 6,381 scenarios/second). A `tracemalloc` run took 5.348 seconds and
reported 7.42 MiB peak while retaining all 5,000 returned scenarios in the
benchmark list. This is a draw-only synthetic benchmark, not a live-league or
full-season throughput claim.

The empirical family is provisional because its historical projection timing
is unverified, its eight sampled weeks are sparse, endpoint revisions remain
possible, and its scoring context may not represent other leagues or seasons.
It adds no player effects, correlations, injury events, forecast-horizon curve,
or bias correction. The Normal model remains supported. M3.4–M3.5 own adaptive
precision and multiprocessing; M3.3 introduces neither.

Verification includes 52 focused M2.6/M3.3 tests for empirical atoms, exact
zero mass, sparse fallback, evidence/report validation, fingerprint changes,
matched ownership scenarios, random-key dimensions, reordered execution,
batch partition/combination equivalence, no-network behavior, and the unchanged
Normal baseline. The complete credential-free suite passes 573 tests in 14.20
seconds on Python 3.12.10.
