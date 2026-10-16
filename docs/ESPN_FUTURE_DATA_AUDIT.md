# M0.3 ESPN Future Player-Week Data Audit

## Scope and evidence classification

This document records the read-only M0.3 audit of the configured 2026 ESPN league. The final live run occurred on 15 October 2026 (America/New_York), while ESPN reported fantasy week 6. No raw authentication values, manager identities, player names, or roster lists are retained here.

Evidence labels have exact meanings:

- **Verified live** — observed against the configured league and validated by the M0.3 diagnostic.
- **Verified by tests** — demonstrated only with sanitized or synthetic credential-free inputs.
- **Unverified** — not established by the available live evidence.
- **Unsupported** — confirmed unavailable or unsafe through the investigated source or library transformation.

Run `python -m fantasy_football.future_data_audit --expected-team-count 14`. JSON output contains sanitized aggregates and retrieval timestamps, not a production snapshot.

## Live retrieval context

The audit used `espn-api` 1.0.1 for authenticated, read-only HTTP requests and parsed relevant raw mappings itself. UTC start/end timestamps bound every request group because ESPN does not provide transactional consistency across requests.

| Purpose | ESPN endpoint/view | Requests | Live result |
|---|---|---:|---|
| League, current rosters, fantasy schedule | League endpoint; `mTeam`, `mRoster`, `mMatchup`, `mSettings`, `mStandings` | 2 | Week 6, 14 teams, regular season through week 14 |
| Player universe and weekly projections | League endpoint; `kona_player_info`, one `scoringPeriodId` per week | 45 | Five pages for each week 6–14: 250, 250, 250, 250, 52 |
| NFL schedule and byes | Season endpoint; `proTeamSchedules_wl` | 1 | 32 NFL teams with explicit `byeWeek` values |

League endpoint: `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}`.

Season endpoint: `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}`.

## Live findings

### Player universe and ownership

The current-week player pool contained 1,052 unique IDs:

| Current status | Players |
|---|---:|
| `ONTEAM` | 233 |
| `FREEAGENT` | 786 |
| `WAIVERS` | 33 |
| Unrostered total | 819 |

Each week 6–14 returned the same 1,052 player IDs and terminated with a page shorter than the 250-record limit. No page or cross-page duplicate occurred. ESPN exposes no independent total count, so completeness is verified against the observed pagination contract, not against an external list of every conceivable NFL player.

The 233 current-week `ONTEAM` IDs and `onTeamId` values reconciled exactly with M0.2 rosters. Current `FREEAGENT` and `WAIVERS` entries had `onTeamId=0`. Twenty-eight players had a different status or owner in at least one future scoring-period view. Future-view values are not treated as current ownership; week 6 is authoritative for this audit.

Stable signed player IDs remain valid. Raw `player.id`, `defaultPositionId`, `eligibleSlots`, `proTeamId`, `injuryStatus`, wrapper `status`, and wrapper `onTeamId` were checked. Current injury-status counts were 795 active, 100 questionable, 87 injury reserve, 20 out, 7 doubtful, 1 day-to-day, and 42 missing. These are observed fields, not a future injury model.

### Weekly projections

The correct source was week-specific `kona_player_info`. A weekly projection is a raw `player.stats[]` entry whose `seasonId` matches the configured season, `scoringPeriodId` matches the requested week, `statSourceId=1`, `statSplitTypeId=1`, and `appliedTotal` is explicitly present and numeric.

Absence of that entry is **missing**. Presence with `appliedTotal=0` is an **explicit zero**. No substitution occurs.

Across 1,052 players and weeks 6–14, 9,468 player-weeks were examined: 5,913 had a projection, 3,555 were missing, and 2,488 present values were explicit zero. No negative was observed live; negative numeric projections remain supported and are verified by tests.

| Week | Present | Missing | Explicit zero | Negative |
|---:|---:|---:|---:|---:|
| 6 | 657 | 395 | 286 | 0 |
| 7 | 657 | 395 | 293 | 0 |
| 8 | 657 | 395 | 287 | 0 |
| 9 | 657 | 395 | 254 | 0 |
| 10 | 657 | 395 | 283 | 0 |
| 11 | 657 | 395 | 308 | 0 |
| 12 | 657 | 395 | 231 | 0 |
| 13 | 657 | 395 | 288 | 0 |
| 14 | 657 | 395 | 258 | 0 |

| Current status | Player-weeks | Present | Missing | Explicit zero |
|---|---:|---:|---:|---:|
| `ONTEAM` | 2,097 | 2,088 | 9 | 332 |
| `FREEAGENT` | 7,074 | 3,618 | 3,456 | 2,075 |
| `WAIVERS` | 297 | 207 | 90 | 81 |

`kona_playercard` was also investigated. Its top-scoring-period filter returned season totals and actual weekly records but not the required future weekly projections. Multiple week-specific `kona_player_info` requests are required.

### Bye weeks and availability

`proTeamSchedules_wl` exposes raw `settings.proTeams[].byeWeek`. The audit validated all 32 nonzero NFL team IDs and required the bye week not to contain a nonempty `proGamesByScoringPeriod` entry.

There were 662 player-bye-week combinations in weeks 6–14: 573 had an explicit zero projection and 89 were missing. Therefore bye, explicit zero, and missing remain separate canonical facts. The audit does not infer injuries, returns, or other availability reasons.

### Remaining fantasy schedule

Raw `schedule[]` supplies `id`, `matchupPeriodId`, `home.teamId`, and `away.teamId`. Weeks 6–14 contained 63 regular-season matchups: seven per week, with all 14 team IDs appearing exactly once each week. Home/away metadata is available. Playoff and consolation interpretation was excluded.

## Field provenance

| Value | Raw ESPN source | `espn-api` transformation | Repository transformation | Classification / limitation |
|---|---|---|---|---|
| Player identity | `players[].id`, `players[].player.id` | `Player.playerId` | Requires matching nonzero signed IDs | **Verified live** |
| Current ownership | wrapper `status`, `onTeamId` at current week | Exposes string/ID | Reconciles `ONTEAM` to M0.2; zero owner for unrostered | **Verified live**; future views are not current ownership |
| Position | `player.defaultPositionId` | Maps ID to label | Preserves validated raw ID | **Verified live** |
| Eligibility | `player.eligibleSlots[]` | Maps through `POSITION_MAP` | Preserves validated raw IDs | **Verified live**; unsupported IDs fail |
| Weekly projection | `player.stats[]` fields above | Rounds and uses `stats.get('appliedTotal', 0)` | Preserves raw numeric value; absent entry stays `None` | **Verified live**; library object is unsafe for missing/zero evidence |
| Injury/status | `player.injuryStatus`, wrapper `status` | Convenience attributes | Counts raw values; no future inference | **Verified live** |
| NFL bye | `settings.proTeams[].byeWeek` | Convenience schedule omits this distinction in places | Preserves week and checks game absence | **Verified live** |
| NFL schedule | `proGamesByScoringPeriod` | Opponent/date mapping | Used to validate bye | **Verified live** |
| Fantasy matchup | `schedule[]` week/home/away fields | Builds team-object schedules | Validates seven disjoint matchups/week | **Verified live** |
| Universe size | Paginated `players[]` | Loops until short page | Adds duplicate checks and repeats by week | **Verified live** against pagination; independent total is **Unsupported** |

## Automated verification

Credential-free tests cover missing/zero/negative values, wrong player-week associations, duplicate and omitted records, conflicting ownership, repeated pagination IDs, malformed structures, bye conflicts, and incomplete schedules. Passing fixtures establish code behavior only, not live ESPN behavior.

Final result: 47 tests passed under Python 3.12 and pytest 8.4.2.

## Gate result and follow-on concerns

M0.3 is **COMPLETE**. Live evidence covers future projections, current ownership reconciliation, paginated unrostered players, explicit byes, and the remaining regular-season schedule. Credential-free validation passed, and no private payload was committed.

Unresolved limitations:

- ESPN provides no independent player-pool total.
- ESPN gives no authoritative reason for every missing or zero projection.
- Multi-request results are not transactionally consistent; M1 needs an immutable staged-refresh boundary and retrieval metadata.
- M1 must preserve raw projection precision and keep missing, zero, and bye distinct.
- M0.4 must determine waiver, tiebreak, playoff, and consolation rules.
- M0.5 must establish historical as-of projection availability; M0.3 proves only current live access.

The previously unresolved downstream treatment of missing projections was subsequently approved as a conservative V1 policy: preserve the raw value as missing, derive an effective projection of zero with source `missing_projection_policy`, and keep it distinct from an ESPN-supplied zero. See [Missing Projection Research and Approved V1 Policy](MISSING_PROJECTION_POLICY.md) for the aggregate week 6 audit, methodology, rationale, exceptions, and implementation boundary.

## UI-reconciliation follow-up

On 16 October 2026, a separate read-only console diagnostic selected named week 7 examples for manual comparison in ESPN. Names, IDs, and fantasy ownership were printed locally and were not committed.

The follow-up reproduced the M0.3 week 7 totals exactly: 395 missing, 293 explicit zero, 364 positive, and no negative projections. The 657 present records equal the documented 293 zero plus 364 positive records. Exactly one missing record was currently rostered, so the diagnostic selected it as requested. No discrepancy with M0.3 classification was found.

The follow-up also confirmed that raw `defaultPositionId` uses a different ID namespace from lineup-slot IDs. Its console formatter therefore uses an explicit fail-fast default-position mapping rather than `espn-api`'s `POSITION_MAP`, which maps lineup slots. Manual confirmation of what ESPN's interface displays remains a user review step; the diagnostic does not treat UI text as API evidence until compared.

After the follow-up implementation, the complete credential-free repository suite contained 55 passing tests.
