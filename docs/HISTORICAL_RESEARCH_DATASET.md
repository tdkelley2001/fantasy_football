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

`build_historical_research_dataset(samples, sources, validated_pregame_captures=())` accepts:

- explicitly selected `(season, scoring_week)` samples;
- complete immutable player-week input records derived from the existing raw
  M0.5 parser;
- separate projection, actual, and scoring source references;
- timezone-aware observation-period boundaries and retrieval times;
- canonical request-parameter JSON and SHA-256 raw-payload identities; and
- one scoring signature shared by every selected sample.

Sources declare a role, target season/week, source kind, and one of the standing
evidence classifications: `verified_live`, `verified_by_tests`, `unverified`, or
`unsupported`. These fields are descriptive caller declarations, not proof of
authenticity. Source IDs must be unique and every sample reference must match
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

- `authenticated_pregame`: an immutable capture authorized through the separate
  validated-manifest trust boundary described below;
- `historical_projection_pregame_provenance_unverified`: a currently returned
  historical ESPN projection; and
- `not_applicable`: missing or policy-imputed values that are not forecasts.

A historical ESPN response is never promoted by a suggestive raw timestamp,
same-session stability, a fixture, caller-selected retrieval time, caller
verification reference, or caller digest. An authenticated pair requires
both an authenticated raw projection and a post-period actual. Policy-imputed
zeros and missing projections are never eligible projection-error pairs.

## Authenticated-capture trust boundary

`validate_pregame_capture_manifest()` is the only supported constructor for a
`ValidatedPregameCapture`. It takes canonical manifest bytes, the exact captured
payload bytes, and an `independently_trusted_manifest_sha256` provisioned outside
the source record. It verifies the manifest identity, exact payload identity,
source ID, endpoint/view/parameters, target player-week boundary, timezone-aware
capture time, and strict capture-before-period ordering. The builder then binds
that validated result back to identical source metadata and sample boundary.

The validator also parses the exact payload bytes with the accepted
`parse_historical_player_page()` ESPN parser. Its immutable parsed player-week
records travel with the validated authorization. During dataset construction,
every record using that authenticated projection source must match a captured
player ID, season, week, raw projection, default position, and NFL team. Altered
projection values, invented players, cross-week records, and identity/context
mismatches fail rather than inheriting authentication from a matching source ID.
Actual scores remain reconciled through the separately identified post-period
actual source; a pregame capture does not authenticate later actual results.

The expected manifest digest is the external trust anchor; the code cannot prove
where a caller obtained it. Hashing an arbitrary manifest and passing that hash
back is structurally valid but does **not** create independent real-world
authentication. Operational authenticated calibration therefore additionally
requires an independently controlled manifest registry or review record. No
such live manifest was added in M3.1, and all existing historical ESPN pairs
remain unverified exploratory evidence. A capture lacking this authorization is
preserved rather than rejected, but it receives the unverified classification.

The validated manifest identity and non-sensitive authority/reference are stored
in schema-v2 research output. Raw payload bytes are checked at validation time
but are not copied into the research dataset.

## Output contract and reproducibility

`HistoricalResearchDataset` schema v2 contains sorted source records, validated
capture-manifest identities, sorted player-week
rows, selected sample identities, scoring signature, structured coverage, fixed
limitations, schema version 2, and a SHA-256 identity over the evidence-bearing
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
- Only captures bound to an independently provisioned manifest identity and
  exact payload can produce authenticated pairs; caller source metadata alone
  cannot, and capture completion must precede the period.
- Authenticated player-week values are reparsed from those exact payload bytes
  and reconciled field-for-field against research records; source-ID agreement
  alone grants no row-level status.
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

Twenty-two focused credential-free tests cover deterministic order, missing versus explicit and
imputed zeros, authenticated and unverified evidence, fabricated source metadata,
manifest and payload identity failures, altered projections, nonexistent
players, mismatched weeks, boundary mismatches, source
role/period/digest/parameters, early actual leakage,
duplicate and mismatched player-weeks, status/provenance contradictions,
nonmatching scoring rules, coverage reconciliation, and identity tampering.
The complete repository suite passed **534 tests in 12.97 seconds** on Python
3.12.10. No live ESPN retrieval was performed for M3.1; fixture verification
proves code behavior only.

M3.1 does not authenticate the existing historical ESPN projections, reconstruct
forecast vintages, establish historical universe completeness, or prove that
returned position/team/scoring context is point-in-time. It does not choose
training/holdout periods, fit distributions, or define model-promotion criteria;
those decisions remain M3.2 and later work.
