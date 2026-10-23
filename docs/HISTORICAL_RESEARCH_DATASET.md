# Historical Projection Research Dataset

## Status and scope

M3.1 implements an immutable, deterministic research dataset contract in
`fantasy_football.historical_dataset`. It transforms explicitly selected,
already retrieved historical player-week evidence. It does not make network
requests, write to the canonical SQLite snapshot store, fit an error model, or
replace the provisional M2.6 outcome model.

The governing requirements are `MASTER_SPEC.md` sections 3.1, 7, 12.1A M3.1,
and the historical evidence boundary recorded in
`ESPN_HISTORICAL_PROJECTION_AUDIT.md`.

## Input contract

`build_historical_research_dataset(samples, sources)` accepts:

- explicitly selected `(season, scoring_week)` samples;
- complete immutable player-week input records derived from the existing raw
  M0.5 parser;
- separate projection, actual, and scoring source references;
- timezone-aware observation-period boundaries and retrieval times;
- canonical request-parameter JSON and SHA-256 raw-payload identities; and
- one scoring signature shared by every selected sample.

Sources declare a role, target season/week, source kind, and one of the standing
evidence classifications: `verified_live`, `verified_by_tests`, `unverified`, or
`unsupported`. Source IDs must be unique and every sample reference must match
the source role and target period. Actual evidence must have been retrieved no
earlier than the end of the observation period. Player IDs, season/week
associations, duplicate player-weeks, finite values, raw status labels, temporal
provenance labels, and scoring consistency fail fast when contradictory.

The builder accepts no implicit season, league size, roster, position, or scoring
default. Position and NFL-team identifiers remain raw numeric evidence.

## Projection classification

Value origin and temporal provenance are deliberately separate.

`ProjectionValueKind` distinguishes:

- `espn_value`: a finite, nonzero raw ESPN source-1 weekly value;
- `espn_explicit_zero`: a present raw ESPN source-1 zero;
- `missing`: no raw projection value; and
- `model_policy_imputed_zero`: an explicit research annotation attached only to
  a missing raw value. The raw value remains null.

`ProjectionTemporalProvenance` distinguishes:

- `authenticated_pregame`: an immutable capture classified `verified_live`,
  carrying a verification reference, completed before the observation period;
- `historical_projection_pregame_provenance_unverified`: a currently returned
  historical ESPN projection; and
- `not_applicable`: missing or policy-imputed values that are not forecasts.

A historical ESPN response is never promoted by a suggestive raw timestamp,
same-session stability, a fixture, or caller-selected retrieval time. A
sanitized fixture cannot claim `verified_live`. An authenticated pair requires
both an authenticated raw projection and a post-period actual. Policy-imputed
zeros and missing projections are never eligible projection-error pairs.

## Output contract and reproducibility

`HistoricalResearchDataset` contains sorted source records, sorted player-week
rows, selected sample identities, scoring signature, structured coverage, fixed
limitations, schema version 1, and a SHA-256 identity over the evidence-bearing
core. `historical_research_dataset_to_json()` emits deterministic UTF-8 JSON and
rejects an inconsistent dataset identity.

Reordering input samples, sources, or player records does not change output.
The dataset remains outside `LeagueSnapshot`, evolving simulation state, and
SQLite schema v1. Generated research JSON may contain private league/player
identifiers and endpoint context; it belongs only in ignored local output and
must not be committed.

## Coverage reporting

Coverage is calculated from rows rather than caller aggregates. Every report
contains reconciled counts for:

- overall data;
- each season;
- each season/week;
- each raw default-position ID; and
- descriptive projection levels: missing, model-policy-imputed zero, explicit
  ESPN zero, finite negative, positive under 5, 5 to under 15, and at least 15.

Each cell reports rows, raw projections, actuals, raw pairs, authenticated pairs,
unverified exploratory pairs, missing projections, explicit zeros, and policy
imputations. A policy-imputed row remains included in the raw-missing count, so
the imputation count is a disclosed subset rather than a replacement for missing
evidence. The magnitude bands reproduce M0.5 descriptive reporting and are
not model strata or approved calibration thresholds.

The accepted M0.5 live audit recorded 8,760 player-weeks, 7,489 present raw
projections, 5,214 actuals, and 5,000 structurally matched raw pairs across the
explicit 2024/2025 weeks 1, 8, 14, and 17. All 5,000 pairs remain eligible only
for explicitly provisional, unverified exploration; **zero are authenticated
pregame calibration pairs**. The per-week and projection-level counts are in
`ESPN_HISTORICAL_PROJECTION_AUDIT.md`. That historical run did not persist its
row-level output, so a future authorized rerun is required to materialize a
dataset and its exact position-level table. Tests use sanitized evidence only
and do not claim new live verification.

## Leakage safeguards

- Source 0 actuals and source 1 projections remain separate values and source
  references.
- Actual component-breakdown presence and raw as-of-like metadata presence are
  preserved as evidence flags; neither flag authenticates projection timing.
- A player-week must match its selected season and scoring period exactly.
- Duplicate records and cross-sample collisions fail.
- An actual captured before the observation period ends fails.
- Only independently classified immutable pregame captures can produce
  authenticated pairs, and their retrieval must precede the period.
- Historical endpoint values remain unverified regardless of raw as-of-like
  fields.
- Missing values stay missing; a separate policy-imputation field cannot replace
  or overwrite raw ESPN evidence.
- Different scoring signatures cannot be pooled into one dataset.

These safeguards establish evidence integrity, not freedom from selection bias,
endpoint revision, or scoring-history revision.

## Programmatic example

```python
from fantasy_football.historical_dataset import (
    HistoricalResearchInputRecord,
    HistoricalResearchSample,
    HistoricalResearchSource,
    build_historical_research_dataset,
    historical_research_dataset_to_json,
)

# Construct sources and samples from an explicitly authorized retrieval. Raw
# HistoricalPlayerWeek records come from parse_historical_player_page().
dataset = build_historical_research_dataset(samples, sources)
payload = historical_research_dataset_to_json(dataset)
```

The caller controls any local write and must use an ignored private output path.

## Tests and limitations

Seventeen focused credential-free tests cover deterministic order, missing versus explicit and
imputed zeros, authenticated and unverified evidence, fixture/non-pregame
promotion attempts, source role/period/digest/parameters, early actual leakage,
duplicate and mismatched player-weeks, status/provenance contradictions,
nonmatching scoring rules, coverage reconciliation, and identity tampering.
The complete repository suite passed **529 tests in 17.40 seconds** on Python
3.12.10. No live ESPN retrieval was performed for M3.1; fixture verification
proves code behavior only.

M3.1 does not authenticate the existing historical ESPN projections, reconstruct
forecast vintages, establish historical universe completeness, or prove that
returned position/team/scoring context is point-in-time. It does not choose
training/holdout periods, fit distributions, or define model-promotion criteria;
those decisions remain M3.2 and later work.
