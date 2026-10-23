# Empirical Player Outcome Distribution Research

## Status and evidence conclusion

M3.2 is **IMPLEMENTED — REVIEW PENDING**. The deterministic research framework
is implemented in `fantasy_football.outcome_distribution_research`; it does not
replace or configure the provisional M2.6 draw model.

No row-level M3.1 dataset is committed or available in this development
environment. The earlier authenticated ESPN audit retained aggregate counts but
not private row-level output. Consequently this milestone makes **no empirical
model-selection claim**. The current evidence conclusion is insufficient: the
repository can reproduce a comparison once an explicitly authorized M3.1
schema-v2 artifact is supplied, but it cannot recreate results from aggregates.

## Input and temporal contract

`research_outcome_distributions(dataset, configuration, candidates)` accepts an
identity-verified M3.1 `HistoricalResearchDataset`. The explicit
`TemporalSplit(evaluation_start_season, evaluation_start_week)` assigns every
earlier player-week to training and every player-week at or after the boundary
to evaluation. Random player-week splits are not supported.

Only rows with both a raw ESPN projection and an actual score are usable.
Missing projections and policy-imputed zeros are excluded. Explicit ESPN zeros,
finite negative projections, zero actuals, and negative actuals remain distinct.
`EvidencePolicy.AUTHENTICATED_ONLY` includes only manifest/payload-bound M3.1
observations. `INCLUDE_UNVERIFIED_EXPLORATORY` also permits the M0.5 historical
records, but its results can never produce a calibrated-model recommendation.

Projection-band edges, minimum group/training/evaluation sizes, hybrid
shrinkage strength, density bandwidth floor, and Normal quadrature size are
explicit research configuration. They are not league settings or hidden model
defaults. Coverage is reported separately for training/evaluation, evidence
class, season/week, raw position ID, and configured projection band.

## Candidate comparison

The default comparison contains nine candidates:

- empirical residual forecasts conditioned on pooled, position, projection
  band, and position × projection band evidence;
- zero-mass plus Normal-residual forecasts under those same four conditioning
  structures; and
- a position × projection empirical hybrid partially pooled toward the overall
  empirical residual distribution.

An empirical observation with an actual zero contributes to the modeled zero
mass. Other empirical outcomes translate their observed residual to the target
projection. The Normal candidate estimates a zero mass and a signed nonzero
residual distribution, represented by deterministic quantile quadrature. The
hybrid combines local and pooled empirical support with the configured
shrinkage strength. Sparse conditioned groups fall back to pooled evidence and
report every affected evaluation row. Negative predicted outcomes are retained;
no floor or rounding is applied.

This is group-level research only. It introduces no player-specific parameters,
correlations, injury process, league-size assumption, or forecast-horizon curve.

## Held-out diagnostics

Each candidate reports:

- mean CRPS, the primary proper-score ordering metric;
- kernel negative log score with an explicit bandwidth floor;
- forecast-mean bias and RMSE;
- relative-error count and mean where the ESPN projection is nonzero;
- zero-outcome Brier score;
- 50%, 80%, and 90% interval coverage and mean width;
- lower-10% and upper-90% exceedance rates;
- a ten-bin deterministic mid-PIT histogram; and
- evaluation and sparse-group fallback counts.

The exploratory winner is ordered by held-out mean CRPS, then held-out negative
log score, then stable candidate ID. Under authenticated-only evidence meeting
the explicit minimum sample counts, that candidate becomes a research
recommendation pending independent review. Unverified evidence may identify an
exploratory winner but cannot authorize promotion. M3.3 remains responsible for
any separately approved implementation in the official simulator.

## Reproducible data pathway

The authorized ESPN diagnostic remains read-only:

```powershell
python -m fantasy_football.historical_projection_audit `
  --sample 2024:1 --sample 2024:8 --sample 2024:14 --sample 2024:17 `
  --sample 2025:1 --sample 2025:8 --sample 2025:14 --sample 2025:17 --json
```

That command reports coverage only; it does not persist private player rows and
must not be misrepresented as an M3.1 artifact. An authorized materialization
workflow must retain the exact response bytes and retrieval context, construct
M3.1 sources/samples through `build_historical_research_dataset()`, and—only for
true pregame captures—supply a separately trusted manifest validated by
`validate_pregame_capture_manifest()`. Generated JSON belongs in an ignored
private path. Credentials, cookies, raw private payloads, and player-level
research output must not be committed.

Once an in-memory schema-v2 dataset is available:

```python
from fantasy_football.outcome_distribution_research import (
    EvidencePolicy,
    ResearchConfiguration,
    TemporalSplit,
    research_outcome_distributions,
)

configuration = ResearchConfiguration(
    evidence_policy=EvidencePolicy.INCLUDE_UNVERIFIED_EXPLORATORY,
    temporal_split=TemporalSplit(2025, 1),
    projection_bin_edges=(5.0, 15.0),
    minimum_group_size=100,
    minimum_training_rows=1000,
    minimum_evaluation_rows=500,
    hybrid_shrinkage_strength=100.0,
    density_bandwidth_floor=0.25,
)
report = research_outcome_distributions(dataset, configuration)
```

The numbers above are an illustrative caller-selected research configuration,
not approved production parameters.

Calling the evaluator with `dataset=None` deterministically returns an explicit
insufficiency report rather than fabricated scores.

## Limitations

- The 5,000 previously observed historical projection/actual pairs have
  unverified pregame provenance and were not retained row by row.
- Forecast lead-time conditioning is unsupported because authenticated vintages
  do not exist in current evidence.
- Current historical scoring and player-context fields may not reconstruct the
  exact point-in-time configuration.
- Synthetic tests validate calculations and safeguards, not empirical ESPN fit.
- Model-family promotion, M2.6 replacement, sampling performance optimization,
  and correlations are outside M3.2.

## Verification

Fifteen focused credential-free tests cover absent-data insufficiency, strict
temporal separation, authenticated-only filtering, unverified exploratory
classification, all candidate families and conditioning levels, sparse-group
fallbacks, zero/tail/interval/PIT diagnostics, deterministic identity and input
ordering, a hand-calculated perfect-forecast CRPS reference, invalid
configuration, and the no-network boundary. Synthetic
fixtures include zero and negative outcomes and multiple positions and
projection levels; they prove implementation behavior, not ESPN calibration.
The complete credential-free repository suite passed **550 tests in 14.03
seconds** on Python 3.12.10.

