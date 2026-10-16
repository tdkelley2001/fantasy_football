# Missing Projection Research and Approved V1 Policy

## Decision

For V1 modeling, a player-week with no valid ESPN weekly projection record receives an **effective projection of zero** and is unavailable for projected-lineup selection and stochastic scoring for that week.

This is an approved conservative modeling transformation, not a reinterpretation of ESPN's response. The canonical snapshot must retain the difference between a missing raw value and an explicit ESPN zero:

| Case | `raw_projection` | `projection_status` | `effective_projection` | `effective_projection_source` |
|---|---:|---|---:|---|
| ESPN positive | ESPN numeric value | `present` | same numeric value | `espn` |
| ESPN explicit zero | `0` | `explicit_zero` | `0` | `espn` |
| ESPN record absent | `null` | `missing` | `0` | `missing_projection_policy` |

No ingestion component may replace `null` with `0`, fabricate a raw record, or label an imputed value as ESPN-supplied. Reports and quality metrics must continue to count missing and explicit-zero records separately.

This policy is approved for the initial model. M0.5 historical evidence or later sensitivity analysis may justify a reviewed revision; it must not change silently.

## Raw classification methodology

The M0.3 follow-up examined the complete paginated week 6 player pool returned by `kona_player_info` for the configured 2026 league. Five offset pages contained 250, 250, 250, 250, and 52 records, for 1,052 distinct player IDs.

A valid raw weekly projection required exactly one `player.stats[]` entry with all of:

- `seasonId=2026`;
- `scoringPeriodId=6`;
- `statSourceId=1`;
- `statSplitTypeId=1`; and
- explicitly present numeric `appliedTotal`.

No matching entry was classified as missing. A matching entry with `appliedTotal=0` was classified as explicit zero. The audit did not use `espn-api`'s `Player` projection value because its `stats.get("appliedTotal", 0)` behavior collapses an absent value into zero.

Ownership came from the current-week wrapper `status` and `onTeamId`. NFL assignment came from raw `player.proTeamId`; `proTeamId=0` means that ESPN supplied no current NFL team association. Bye status came from explicit `settings.proTeams[].byeWeek` and was checked against `proGamesByScoringPeriod`. Injury evidence used the raw `injuryStatus`, `injured`, and `active` fields without inferring future health.

## Week 6 evidence

The 1,052 player-weeks contained 657 present projections and 395 missing projections. Of the present records, 286 were explicit zero and 371 were positive. No negative projection was observed.

### Missing records by current fantasy ownership

| ESPN pool status | Count |
|---|---:|
| `FREEAGENT` | 384 |
| `WAIVERS` | 10 |
| `ONTEAM` | 1 |
| Total unrostered | 394 |

### Missing records by raw injury status

| `injuryStatus` | Count |
|---|---:|
| `ACTIVE` | 314 |
| `QUESTIONABLE` | 40 |
| `INJURY_RESERVE` | 26 |
| `OUT` | 5 |
| Missing | 10 |

The separate raw `injured` boolean was true for 31 records and false for 364. The 31 true values comprised the 26 injury-reserve and 5 out records. All 395 records had `active=true`, demonstrating that ESPN's `active` boolean is not weekly game availability and cannot be used as a substitute for projection presence.

### NFL assignment and byes

| Condition | Count |
|---|---:|
| No NFL team association (`proTeamId=0`) | 297 |
| Assigned NFL team (`proTeamId!=0`) | 98 |
| Verified week 6 bye | 7 |

The 98 NFL-assigned missing records comprised 59 `ACTIVE`, 2 `QUESTIONABLE`, 26 `INJURY_RESERVE`, 5 `OUT`, and 6 missing injury statuses. Seven were on bye: five active, one on injury reserve, and one with missing injury status. Therefore 54 were NFL-assigned, non-bye, and marked `ACTIVE`. All 98 were fantasy-unrostered: 88 free agents and 10 waivers.

These dimensions overlap and must not be summed as mutually exclusive reasons. Free-agent status, injury status, NFL assignment, and bye status answer different questions.

## Rationale and limitations

The evidence supports zero as a conservative V1 effective value because 394 of 395 missing week 6 records were unrostered, 297 lacked an NFL team association, and many others were on IR, out, or on bye. It does not prove that missing semantically equals an ESPN projection of zero: one missing player was rostered, and 54 missing records were NFL-assigned, non-bye, and marked active.

The approved policy deliberately accepts the risk of assigning no modeled production to those exceptions. That risk must remain visible through missingness counts and can be evaluated during historical projection research and later sensitivity testing. No injury-return forecast, replacement projection, positional average, or other fallback is authorized.

## Implementation boundary

M0.3 records the decision and evidence only. M1 must implement the separate raw/status/effective/source fields in the canonical player-week contract and validate their relationships. M2 must consume `effective_projection` for lineup availability and simulation without mutating the raw snapshot evidence. No M1 or M2 implementation is introduced by this follow-up.
