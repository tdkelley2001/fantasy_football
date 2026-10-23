# Empirical Player Outcome Distribution Research

## Status and evidence conclusion

M3.2 is **IMPLEMENTED — REVIEW PENDING**. The deterministic research framework
is implemented in `fantasy_football.outcome_distribution_research`; it does not
replace or configure the provisional M2.6 draw model.

A bounded authenticated retrieval on 23 October 2026 materialized private
row-level data through the M3.1 schema-v2 contract and evaluated it locally.
No private rows or raw responses are committed. The historical endpoint does
not establish when its projections were originally available, so all results
remain **unverified exploratory evidence** and make no calibrated model-selection
claim. They compare the implemented candidates but do not promote an official
distribution into M3.3.

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
shrinkage strength. For empirical and Normal candidates, groups below
`minimum_group_size` retain the established pooled-only fallback. Hybrid
semantics differ deliberately: an empty local group uses pooled-only fallback,
while every nonempty group retains local evidence and shrinks it toward the
pooled distribution. A nonempty group below the threshold is reported through
`sparse_partially_pooled_rows`; `fallback_rows` means that pooled-only behavior
was actually executed. Groups exactly at or above the threshold are ordinary
partial-pooling rows and increment neither diagnostic. Negative predicted
outcomes are retained; no floor or rounding is applied.

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
- evaluation, pooled-only fallback, and sparse-partial-pooling counts.

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

That command reports coverage only. The accepted materialization path is:

```powershell
python -m fantasy_football.historical_research_workflow `
  --plan docs/examples/m32_historical_research_plan.json `
  --output-dir outputs/m32-evidence-local
```

The plan explicitly selects every season/week and observation boundary; it has
no league-specific season defaults. The workflow reuses the M0.5 paginated
parser, captures exact request filters and canonical response payloads, records
UTC retrieval times and scoring signatures, builds M3.1, then runs M3.2. It
refuses output outside a new or empty child of ignored `outputs/`. The private
directory contains the deterministic dataset and report, raw player/scoring
responses, and a retrieval manifest containing the selected plan and its SHA-256.
Observation windows describe the selected scoring periods; they do not prove
pregame capture timing. Credentials, cookies, raw responses, and player-level
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

Calling the evaluator with `dataset=None` still returns an explicit
insufficiency report rather than fabricated scores.

## Exploratory evidence run

The private 23 October run selected weeks 1, 8, 14, and 17 from 2024 for
training and the same weeks from 2025 for evaluation. It produced dataset
identity `7fe2626f...ddd26f5`, 8,760 player-week rows, 7,489 raw projections,
5,214 actuals, 4,294 explicit ESPN projection zeros, 1,271 missing projections,
and 5,000 matched pairs. The temporal split contained 2,638 training pairs and
2,362 evaluation pairs. Authenticated-pregame pair count was zero.

Held-out results, ordered by mean CRPS, were:

| Candidate | CRPS | log score | bias | RMSE | zero Brier | 50/80/90% coverage |
|---|---:|---:|---:|---:|---:|---:|
| projection empirical | 2.0294 | 2.1688 | -0.1317 | 4.6834 | 0.1473 | .616/.845/.930 |
| projection Normal | 2.0544 | 2.2266 | -0.1317 | 4.6834 | 0.1473 | .629/.882/.938 |
| joint hybrid partial pooling | 2.1036 | 2.2066 | -0.9975 | 4.8326 | 0.1539 | .710/.883/.946 |
| joint empirical | 2.2173 | 2.2332 | -0.9390 | 5.1206 | 0.1659 | .650/.851/.922 |
| joint Normal | 2.2371 | 2.2757 | -0.9390 | 5.1206 | 0.1659 | .659/.884/.937 |
| position empirical | 2.5569 | 2.4344 | -1.8846 | 5.5755 | 0.2357 | .707/.892/.947 |
| pooled empirical | 2.5675 | 2.4693 | -1.9551 | 5.5104 | 0.2493 | .713/.891/.941 |
| position Normal | 2.5800 | 2.4714 | -1.8846 | 5.5755 | 0.2357 | .733/.915/.950 |
| pooled Normal | 2.5967 | 2.5019 | -1.9551 | 5.5104 | 0.2493 | .746/.910/.950 |

The joint hybrid used sparse local evidence for 359 evaluation rows and pooled
only for 2 empty-group rows. The empirical projection-band candidate is the
exploratory winner; `recommended_candidate_id` remains null.

## Limitations

- The 5,000 observed pairs have unverified pregame provenance. Their private
  row-level artifact is reproducible locally but intentionally uncommitted.
- Forecast lead-time conditioning is unsupported because authenticated vintages
  do not exist in current evidence.
- Current historical scoring and player-context fields may not reconstruct the
  exact point-in-time configuration.
- The endpoint can revise historical projections after games; present-day
  retrieval consistency cannot remove hindsight or revision risk.
- The selected eight weeks are small and seasonally sparse, and therefore may
  not represent other seasons, weeks, positions, or scoring environments.
- Synthetic tests validate calculations and safeguards; the private run is
  exploratory evidence, not authenticated forecast calibration.
- Model-family promotion, M2.6 replacement, sampling performance optimization,
  and correlations are outside M3.2.

## Verification

Sixty-five focused credential-free tests across M0.5/M3.1/M3.2 cover private
materialization and confidentiality plus absent-data insufficiency, strict
temporal separation, authenticated-only filtering, unverified exploratory
classification, all candidate families and conditioning levels, sparse-group
fallbacks, zero/tail/interval/PIT diagnostics, deterministic identity and input
ordering, a hand-calculated perfect-forecast CRPS reference, invalid
configuration, and the no-network boundary. Synthetic
fixtures include zero and negative outcomes and multiple positions and
projection levels; they prove implementation behavior, not ESPN calibration.
Dedicated hybrid tests cover empty groups, nonempty groups below the threshold,
groups exactly at the threshold, groups above it, actual local-evidence use, and
unchanged empirical/Normal fallback behavior. Exact final counts are recorded in
the M3.2 roadmap gate evidence. The complete credential-free repository suite
passed **561 tests in 12.98 seconds** on Python 3.12.10.

