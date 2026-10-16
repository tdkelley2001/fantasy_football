# ESPN Historical Projection Availability and As-Of Integrity Audit

## Executive summary

M0.5 is a bounded, read-only investigation of historical ESPN player-week projections and actual scores. On 16 October 2026, the diagnostic retrieved eight samples from the configured private league: weeks 1, 8, 14, and 17 in both 2024 and 2025. The 8,760 returned player-weeks contained 7,489 projection values, 5,214 actual values, and 5,000 matched projection/actual pairs.

The historical values are useful research evidence, but they are **not an authenticated pregame dataset**. No investigated weekly stat record contained a creation, update, revision, or original as-of timestamp. Same-session re-fetches were stable, and a bounded second ESPN view usually agreed with the first, but both checks establish only what ESPN returns now. They cannot establish what was visible before kickoff.

Accordingly, every returned projection is classified **historical projection, pregame provenance unverified**. There are zero verified-pregame observations. M3 must not use these values as its primary genuine-forecast calibration sample without independently timestamped corroboration. The strongest ESPN-only path is prospective snapshot capture, if separately approved, with immutable payload provenance and retrieval timestamps.

## Scope and method

The executable diagnostic is `python -m fantasy_football.historical_projection_audit`. Samples are explicit `--sample SEASON:WEEK` arguments; no current-season team count, roster, scoring, or player assumption is imposed on historical seasons. The audit:

- retrieves the entire paginated `FREEAGENT`, `ONTEAM`, and `WAIVERS` candidate universe for each sample;
- parses raw weekly records rather than `espn-api`'s rounded/defaulted player projection properties;
- matches projection and actual only on player ID, season, scoring period, weekly split, and source indicator;
- preserves missing, explicit zero, finite negative, and positive values separately;
- fingerprints each season's currently returned scoring settings;
- repeats the first page in the same session and compares exact parsed values;
- compares a bounded 25-player subset with a second ESPN view; and
- reports only aggregate, sanitized evidence. Live payloads and player names are not persisted.

This is not a warehouse, scheduled collector, scoring model, or proof that the endpoint returns every historically relevant NFL player.

## Samples and coverage

The league's raw `scheduleSettings.matchupPeriodCount` classified weeks 1, 8, and 14 as regular season and week 17 as postseason for these seasons.

| Season | Week | Phase | Player-weeks | Projection present | Missing projection | Explicit zero projection | Actual present | Matched pairs |
|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 2024 | 1 | Regular | 1,099 | 1,066 | 33 | 631 | 634 | 633 |
| 2024 | 8 | Regular | 1,099 | 1,082 | 17 | 663 | 689 | 688 |
| 2024 | 14 | Regular | 1,099 | 1,086 | 13 | 745 | 587 | 584 |
| 2024 | 17 | Postseason | 1,099 | 1,096 | 3 | 681 | 733 | 733 |
| 2025 | 1 | Regular | 1,091 | 1,043 | 48 | 592 | 638 | 628 |
| 2025 | 8 | Regular | 1,091 | 676 | 415 | 331 | 566 | 504 |
| 2025 | 14 | Regular | 1,091 | 709 | 382 | 340 | 624 | 563 |
| 2025 | 17 | Postseason | 1,091 | 731 | 360 | 311 | 743 | 667 |
| **Total** | | | **8,760** | **7,489** | **1,271** | **4,294** | **5,214** | **5,000** |

There were 2,190 unique player-season identities. Of the missing-projection records, 214 had a present actual. Actual stat breakdowns were present on 3,604 records. No sampled projection was negative, although the parser deliberately preserves any finite negative value. The returned universes covered QB, RB, WR, TE, K, and D/ST in every season; ESPN also returned a very small number of records with position IDs 9, 11, or 12, which remain raw unsupported categories rather than being relabeled.

Projection magnitudes across all samples were 396 high values (at least 15), 1,494 medium values (5 to under 15), 1,305 low positive values (under 5), 4,294 explicit zeros, and 1,271 missing values. These descriptive bins are audit summaries, not approved modeling thresholds.

The marked difference between 2024 projection coverage and later 2025 weeks is observed endpoint behavior, not evidence of a change at the original forecast date. It demonstrates material season/week selection effects that a calibration dataset would need to explain.

## Endpoints, views, and raw fields

Requests used the season-specific private-league endpoint:

`https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}`

| Purpose | View/parameter | Raw fields | Our transformation | Evidence |
|---|---|---|---|---|
| Complete bounded player pool | `view=kona_player_info`, `scoringPeriodId={week}`, paginated `x-fantasy-filter` | wrapper `id`; `player.id`, `defaultPositionId`, `proTeamId`, `stats` | Validate identity and page uniqueness; retain numeric IDs | Verified live |
| Weekly projection | player `stats[]` | `seasonId`, `scoringPeriodId`, `statSplitTypeId=1`, `statSourceId=1`, `appliedTotal` | Exact player-season-week match; nullable finite float; no imputation | Verified live field; pregame timing unverified |
| Weekly actual | player `stats[]` | same identity fields, `statSplitTypeId=1`, `statSourceId=0`, `appliedTotal`, `stats` | Exact match; nullable finite float; record whether component stats exist | Verified live |
| Cross-view check | `kona_playercard`, 25 selected IDs per season | same weekly records where returned | Compare exact projection/actual pairs for sampled weeks | Verified live current-response comparison only |
| Scoring context | league settings | `settings.scoringSettings.scoringItems[].statId`, `points`, `pointsOverrides` | Validate unique stat IDs and create a deterministic SHA-256 signature | Verified live current settings only |

Weekly records at `scoringPeriodId=0` are season-total or average records and are excluded. Treating them as player-week projections would be a structural error.

`espn-api` is used for authenticated request transport and endpoint construction. Its `Player` transformation is intentionally bypassed for this audit because it rounds `appliedTotal` and defaults absent weekly values to zero. Our code reads the raw response so missing and explicit zero remain distinct. The library and ESPN endpoints are unofficial interfaces; their meanings can change without a versioned public contract.

The returned `defaultPositionId` and `proTeamId` establish what the historical season endpoint returns now. No independent timestamp proves those wrapper attributes were the player's values as of the sampled week, so they must not be described as authenticated point-in-time roster metadata.

## Projection/actual matching and validation

A usable structural match requires one player wrapper, matching wrapper/player IDs, the requested season and week, weekly split type 1, exactly one source-1 projection record at most, and exactly one source-0 actual record at most. Unsupported sources, wrong associations, non-finite totals, duplicate records, duplicate paginated players, malformed component stats, and contradictory scoring definitions fail explicitly.

Missing projection means no matching source-1 weekly record. Explicit zero means a matching record exists and raw `appliedTotal` equals zero. The approved operational missing-projection policy is not applied here. In particular, none of the 1,271 missing values is converted into an ESPN forecast observation.

The 2024 and 2025 scoring fingerprints were identical at retrieval time, each based on 46 scoring items. This establishes equivalence of the settings currently returned for those season endpoints. It does not prove that the settings or applied totals were unchanged since the games occurred.

## Pregame/as-of provenance

### Classification

| Classification | Count/status | Basis |
|---|---|---|
| Verified pregame/as-of | 0 | No independently timestamped pregame artifact or raw revision timestamp was available |
| Historical projection, pregame provenance unverified | All 7,489 present projection records | ESPN labels/source structure distinguishes projection from actual, but original timing is absent |
| Potentially revised or hindsight-contaminated | Risk exists; no individual value proven revised | Historical scoring can be changed retroactively; endpoint has no projection revision history |
| Unavailable | 1,271 sampled player-weeks | No matching raw source-1 weekly record |

ESPN's public help defines `PROJ` as a projected total for a week, but does not describe an immutable historical projection archive. ESPN's weekly projection material also states projections update leading up to kickoff, confirming that a final displayed value can have multiple pregame vintages. Neither source identifies which vintage the historical API returns.

ESPN's scoring documentation states that league-manager scoring changes can update earlier results retroactively. That is direct evidence that currently returned historical applied totals are not necessarily immutable point-in-time artifacts. It establishes retrospective-risk for the scoring context and actual totals; it does not, by itself, prove a particular projection was recomputed.

Sources: [ESPN Fantasy Football Acronyms](https://support.espn.com/hc/en-us/articles/115003862972-Fantasy-Football-Acronyms), [ESPN Scoring Formats](https://support.espn.com/hc/en-us/articles/360003914032-Scoring-Formats), [ESPN Scoring Settings](https://support.espn.com/hc/en-us/articles/360000069512-Scoring-Settings), and [ESPN Week 13 Playbook (2024)](https://www.espn.com/fantasy/football/insider/story/_/id/42621105/nfl-fantasy-football-2024-ultimate-playbook-projections-win-probabilities-week-13-mike-clay).

## Revision and hindsight-leakage checks

All eight repeated first-page requests were byte-equivalent after parsing. In the second-view check, `kona_playercard` supplied 95 of 100 selected 2024 player-weeks and 91 of 100 selected 2025 player-weeks. It agreed exactly with `kona_player_info` for all returned projection/actual pairs. This is current-response consistency, not independent historical corroboration.

The audit also counted exact projection/actual equality. Every sample was below the deliberately broad 95% suspicious-tracking threshold and therefore reported no obvious exact-tracking signal. Many exact zeros are expected among nonparticipants, making raw equality an especially weak leakage detector. Passing this screen does not establish temporal validity or make the data leakage-free.

No projection appeared only because an actual was present according to any explicit timestamp—the endpoint supplies no timestamps with which to conduct that test. The audit prevents actual/source-0 records from entering projection/source-1 values and rejects season totals mistaken for weekly values.

## Missingness, zeros, and selection bias

The candidate universe is an ESPN-filtered response, not a census with an independently known denominator. A player can have no actual because they did not participate, because ESPN omitted a weekly record, or for another endpoint-specific reason; the audit does not infer participation from zero or missing values. A present actual-stat breakdown is stronger participation evidence but is not universally present.

Explicit-zero projections dominate this broad player universe and should not be assumed representative of positive-projection fantasy starters. Missingness varies sharply by season and week. The historical league endpoint may also reflect present-day historical indexing, and returned position/team fields lack their own as-of timestamps. These factors can bias position, magnitude, participation, and player-selection strata.

For later M3 work:

- nullable raw projections and explicit-zero status must be preserved;
- policy-imputed effective zeros are excluded from the primary genuine-forecast error sample;
- missing-projection records with actuals should be summarized separately;
- actuals may be researched independently, with current-scoring and revision limitations attached; and
- an endpoint response count must never be reported as the count of usable, authenticated calibration observations.

## Forecast horizon

The investigated responses expose at most one currently returned projection for a historical player-week. They contain no authenticated capture timestamp, lead-time label, or ordered revision sequence. The audit therefore cannot distinguish a projection captured immediately before kickoff from one captured one or several weeks earlier.

**Forecast-horizon-specific uncertainty is not identifiable from this historical source.** Horizon-dependent variance multipliers must be deferred unless prospective or independently archived snapshots provide genuine vintages. This does not block an initial V1 uncertainty model if M0.6 approves another defensible common residual-data strategy.

## M3 feasibility and alternatives

| Approach | Point-in-time reliability | Coverage/effort | Calibration use |
|---|---|---|---|
| Current historical ESPN projections | Unverified | Immediate broad historical coverage | Research/sensitivity only; not the primary genuine-pregame sample |
| Independently timestamped existing ESPN artifacts | Potentially strong if payload, identity, and capture time validate | Unknown and likely selective | Usable with provenance and selection-bias review |
| Prospective ESPN snapshots | Strong when captured before games with immutable raw provenance | Accumulates slowly; requires approved operations and retention | Recommended ESPN-only foundation for future calibration/held-out validation |
| Historical ESPN actuals alone | Timing of outcomes is clear, but current applied totals may be retroactively rescored | Broad in sampled endpoints | Outcome research only; cannot estimate forecast error without trustworthy forecasts |
| Third-party projections | Provider-dependent | Outside current policy | Not an automatic substitute and not implemented |

If prospective collection is approved later, each snapshot should preserve retrieval UTC time, endpoint/view/parameters, raw payload digest, league/scoring signature, target season/week, player identity, raw nullable projection, and source/split indicators. Collection frequency and horizon labels must be decided before data collection; reconstructing them afterward is not valid.

## Evidence classification and unresolved questions

**Verified live:** weekly source-1 and source-0 records, identity fields, finite `appliedTotal`, actual stat breakdown availability, pagination coverage, current scoring definitions, same-session stability, and cross-view current-value comparisons.

**Verified by automated tests:** positive matching; wrong player/season/week rejection; source confusion; missing, zero, and absent actual states; duplicate/contradictory records; pagination overlap; malformed values; scoring mismatch detection; suspicious exact-tracking classification; and the rule that fixture timestamps cannot promote evidence to verified pregame.

**Unverified:** original projection timing, historical accuracy of returned team/position wrapper fields, whether current historical scoring definitions match the game-date definitions, endpoint-universe completeness, and whether any individual value was retrospectively recomputed.

**Unsupported by investigated source:** historical projection revision sequences, authenticated as-of dates, one-week-ahead versus multiweek-ahead vintages, and forecast-horizon labels.

Questions carried to M0.6:

1. Is the lack of an authenticated historical pregame sample acceptable for V1, or must prospective collection delay empirical M3 calibration?
2. Are independently timestamped ESPN artifacts available outside this repository and capable of passing identity/scoring/provenance validation?
3. May unverified historical projections be used only for explicitly labeled sensitivity work, or should they be excluded entirely from model selection?
4. What minimum prospective sample, horizon cadence, and held-out period would justify M3 promotion?
5. How should M0.4's unresolved transaction, tie, and current consolation rules combine with this calibration limitation in the M1 go/no-go decision?

## Reproduction

With local credentials in ignored `.env` values:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.historical_projection_audit `
  --sample 2024:1 --sample 2024:8 --sample 2024:14 --sample 2024:17 `
  --sample 2025:1 --sample 2025:8 --sample 2025:14 --sample 2025:17
```

Add `--json` for the sanitized structured report. Do not commit live output: although this diagnostic omits names and manager data, the configured league ID and endpoint context remain private-league metadata.
