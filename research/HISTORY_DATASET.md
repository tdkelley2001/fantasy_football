# Canonical player-week dataset and initial diagnostics

Built from the 2018–2025 archives on September 17, 2026 (ET). The initial sample
and diagnostics are implemented; model calibration and Monte Carlo are not.

## Artifacts and reproduction

```powershell
.\venv\Scripts\python.exe -m research.build_history
```

This writes to `outputs/history/`, which is ignored by Git:

| Artifact | Contents |
|---|---|
| `player_weeks.jsonl.gz` | Canonical dataset, including every excluded row and raw candidate stat records |
| `initial_sample.jsonl.gz` | Initial modeling sample with classifications, scores, and provenance |
| `sources/*.json.gz` | Frozen player/stat, game schedule/status, and scoring sources |
| `diagnostics.json` | Counts, overlapping exclusion reasons, moments, quantiles, and histograms |
| `diagnostics.html` | Standalone visual report with empirical residual intervals and exact tables |
| `manifest.json` | Source/artifact hashes, implementation hashes, scoring version, counts, retrieval times |

Rerunning reuses frozen sources, including the scoring snapshot. To capture newly
changed league rules or ESPN data, choose a new output directory:

```powershell
.\venv\Scripts\python.exe -m research.build_history --output outputs/history-new-snapshot
```

The default build covers all eight seasons. `--start` and `--end` can narrow that
range. A complete manifest is written only after successful construction and
diagnostics; its hashes identify the matching artifacts. Compressed-file hashes
can change between builds; the canonical uncompressed-content hash establishes
logical reproducibility. The checked-in [diagnostic snapshot](history_diagnostics.json)
records the results below without adding the full source archive to the repository.

No new dependency is required. The reusable classification/scoring functions live
in `fantasy_projection/history.py`; network and artifact generation are in
`research/build_history.py`. The app's deterministic engine is unchanged.

## Canonical universe and classification

The canonical key is `(season, week, player_id)`. There are **366,612 rows**: every
player returned in the six-position fantasy pool crossed with every regular-season
week (17 weeks through 2020; 18 thereafter). This includes unattached/retired player
identities that ESPN retains. It does not assert that all these identities were
active NFL roster members, and its absent-stat count is not an estimate of ESPN
data loss. Players missing entirely from ESPN's returned pool cannot be reconstructed.

Each row retains independent dimensions instead of one overloaded usable flag:

| Field | Meaning |
|---|---|
| `projection_status`, `actual_status` | `valid`, `missing`, `invalid`, or `conflicting` stat record |
| `projection_points`, `actual_points` | Scores recomputed using the current scoring snapshot; missing/ambiguous is null |
| `zero_projection`, `zero_actual` | Explicit booleans for valid values; null when value cannot be established |
| `game_status` | `completed`, `bye`, `inferred_bye`, `cancelled`, `not_completed`, `conflicting`, or `unknown` |
| `historical_team_id`, `team_evidence` | Weekly actual/projection evidence, D/ST identity, bracketed inference, or unknown |
| `team_conflict` | Actual and projected records name different known NFL teams |
| `participation_status` | `played`, `did_not_play`, `conflicting`, or `unknown` |
| `participation_evidence` | Actual games-played field, recorded activity, completed D/ST game, or none |
| `inactive_status` | Currently unknown: no verified game-day inactive-list source is available in these inputs |
| `raw_actual_records`, `raw_projection_records` | Every weekly candidate, including duplicates/conflicts |
| `quality_flags` | Overlapping descriptive flags; independent of sample selection |
| `initial_sample`, `sample_exclusions` | Separate versioned selection policy and all failed conditions |

An explicit GP of zero would establish did-not-play, **not official inactive**.
This snapshot contains no explicit zero-GP records. Empty stat lines and missing
actual records therefore remain participation-unknown. All official inactive
designations remain unknown; none are manufactured from current injury status.
Separating this field makes the limitation visible but does not mean historical
inactive lists have been recovered.

Actual stat `210` is games played, as labeled in the
[ESPN API stat mapping](https://github.com/cwendt94/espn-api/blob/master/espn_api/football/constant.py).
When absent, positive/negative nonzero recorded activity in specific actual
attempt/target/reception/kicking/tackle/return counters establishes participation.
An empty record alone does not. The 2018 archive particularly needs this evidence
path. A completed D/ST team game with a valid nonempty actual establishes a team
appearance. These evidence categories are stored separately for later sensitivity
analysis; they are not assumed equivalent to audited snap counts.

## Schedule reconciliation and conflicts

Game status comes from ESPN's site scoreboard, filtered to the NFL season and
regular-season type, spanning two calendar years. The game IDs are reconciled
against the fantasy schedule. Missing scoreboard events are fetched individually
from the ESPN game-summary endpoint, whose explicit status is retained. The build
requires all 32 teams and the expected 16/17 scheduled games per team, counting
cancelled games as scheduled, before classifying absent team-weeks as byes.

This caught the **2022 Bills–Bengals cancellation**: the calendar scoreboard omitted
game `401437947`, while the fantasy schedule retained it. Its individual summary
explicitly reports `STATUS_CANCELED`. No hardcoded player cancellation list or
missing-equals-bye substitution is used.

For players without direct weekly team evidence, agreement between observed teams
before and after the gap permits a marked inference. It does not prove uninterrupted
team membership. Inferred byes are therefore separate, and inferred-team rows are
excluded from the initial sample. Top-level current player teams are not projected
backward, except for the stable identity of a D/ST team unit.

Exact duplicate records collapse for scoring while remaining in the raw candidates.
Differing candidates remain conflicting even if they happen to score the same.
No response-order winner is chosen. The build retained three conflicting actual
keys and flagged 109 rows with differing actual/projection NFL teams.

## Scoring and strict initial sample

Both sides are scored using the captured **2026 league scoring rules**, including
position-specific overrides and fractional projected D/ST bucket components.
The rules are content-hashed. Nonfinite values, reverse scoring, or ambiguous
records are not silently approximated. The scorer currently supports additive
per-stat rules; the prior audit validated this league's conversion against ESPN
in 9,715 comparisons. Historical `appliedTotal` is not used as the training target.

Policy `completed-positive-played-v1` requires all of:

1. A normal, explicitly completed regular-season game.
2. Direct weekly NFL-team evidence (or a D/ST team identity), without disagreement.
3. Recorded participation, without participation/game contradiction.
4. One unambiguous valid projected stat record, rescored to **strictly positive** points.
5. One unambiguous valid actual stat record; **zero and negative actuals are allowed**.
6. A mapped QB/RB/WR/TE/K/DST position.

No minimum actual score, residual trimming, or winsorization is applied. A player
injured during a completed game remains included when appearance evidence exists;
we do not filter poor outcomes on hindsight. The selection does condition on
participation and excludes uncertain availability, so it is not yet the complete
pre-game uncertainty distribution needed by a season simulator.

## Classification counts

| Dimension | Count |
|---|---:|
| Canonical rows | 366,612 |
| Valid projection records | 146,050 |
| Valid actual records | 106,514 |
| Explicit zero projections | 87,670 |
| Explicit zero actual scores | 56,100 |
| Completed game joined | 107,205 |
| Directly supported byes | 1,240 |
| Inferred byes | 5,090 |
| Cancelled-game rows | 44 |
| Unknown game context | 253,033 |
| Recorded participation | 64,752 |
| Unknown participation | 301,860 |
| Conflicting actual keys | 3 |
| Initial sample | **54,564** |

These dimensions overlap and must not be summed. For example a row can have a
cancelled game, positive projection, and missing actual simultaneously. Missing
source values are kept as missing even when a bye/cancellation explains them.
All 312,048 excluded rows remain in the canonical dataset.

## Initial distribution diagnostics

The sample contains 54,564 observations across 1,559 distinct player/team-unit IDs.
Error is actual minus projection; these descriptive diagnostics do not fit,
recenter, or calibrate a simulation distribution.

| Metric | Points |
|---|---:|
| Mean error | -0.076 |
| Median error | -0.721 |
| Standard deviation | 5.917 |
| Mean absolute error | 4.315 |
| RMSE | 5.918 |
| P01 / P99 | -12.648 / +18.119 |
| P05 / P95 | -8.589 / +10.930 |

Skewness is +0.878 and excess kurtosis is +2.378. The positive tail is longer,
and a small average error does not mean symmetric or narrow uncertainty.
Zero actuals make up 16.92% of the sample; negative actuals make up 1.88%.

| Position | N | Mean error | SD | MAE |
|---|---:|---:|---:|---:|
| QB | 4,707 | -0.184 | 7.416 | 5.765 |
| RB | 12,354 | -0.186 | 5.926 | 4.234 |
| WR | 19,036 | -0.131 | 6.146 | 4.476 |
| TE | 10,031 | +0.117 | 4.803 | 3.372 |
| K | 4,217 | +0.157 | 4.463 | 3.548 |
| D/ST | 4,219 | -0.077 | 6.579 | 5.217 |

Spread also increases with projection level: pooled SD is **3.66** for projections
below 5 points, **5.76** for 5–10, **7.45** for 10–15, **8.33** for 15–20, and
**8.93** for 20+. Position mix also changes across these bands; the JSON includes
joint position/projection-band diagnostics so a pooled trend need not be mistaken
for a within-position effect.

Season mean errors range from +0.227 in 2018 to -0.305 in 2025. Coverage and
participation evidence differ by season, especially 2018. These observations
justify testing position/projection-level conditioning and time-aware validation;
they do not establish which model will calibrate best out of sample. Observations
share players, teams, and games, so the report does not attach independent-sample
confidence intervals to these summaries.

## Review performed after the initial diagnostics

Of the 58,268 positive-projection pairs in the availability audit, 3,704 remain
outside the strict sample. Their overlapping reasons are 3,637 unknown-participation
rows, 36 team disagreements, 55 unmapped-position rows, and 12 cancelled-game rows.
This review did not run a second residual distribution on exclusions or change
the initial policy.

Of those 3,637 unknown-participation pairs, 3,634 have zero actual scores. We should
not merge them into the distribution until appearance/inactive evidence separates
real zero-score games from absent participation. Their season counts are strongly
uneven, so simply pooling them would also change historical weighting.

Three nonzero cases are promising for a later participation-rule expansion:

| Player-week | Recorded evidence outside the initial activity whitelist | Current-rule actual |
|---|---|---:|
| Ty Montgomery, 2018 Week 11 | Rushing yards without an attempts/GP field | 0.5 |
| Jason Croom, 2018 Week 10 | Fumble recovery touchdown | 6.0 |
| Adam Shaheen, 2018 Week 11 | Receiving two-point conversion | 2.0 |

These records support revisiting the activity whitelist rather than admitting
the entire unknown-participation category. Keep the initial sample frozen and
test/version any expansion before comparing its diagnostics. Team-disagreement
records similarly deserve targeted historical-team/forecast-timing resolution;
they are not automatically invalid forever. Hybrid positions need an explicit
position-conditioning policy. Nonpositive projections need their own intended
modeling population, especially D/ST.

No excluded category has been reincorporated. Official inactive-list enrichment
and unresolved historical-team evidence remain future work. Byes and cancellations
are schedule events rather than ordinary low-score residuals. Forecast-generation
timestamps remain unknown; future timestamped snapshots are a separate requirement.

Only after that review and chronological calibration should these distributions
drive playoff/title probabilities in the app.
