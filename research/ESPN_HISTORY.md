# ESPN historical data audit

Verified September 17, 2026 (ET; request timestamps are UTC). This is an
availability audit, not a finished training dataset or Monte Carlo implementation.
The subsequent [canonical dataset and diagnostics](HISTORY_DATASET.md) implement
the next dataset milestone; the findings below preserve the original audit.
Findings come from read-only requests against the configured league and ESPN's
league-independent player endpoints. Availability is observed, not a guarantee
that an undocumented endpoint will retain the same behavior.

## Main finding

ESPN supplies archived weekly **projected and actual raw statistics for
2018–2025**, including QB, RB, WR, TE, K, and D/ST. These can be scored under the
current league rules to form player-week projection errors. The configured
league's own history only reaches 2024; that does not limit the player archive.

After quarantining three conflicting player-week actual records, the audit found
101,903 projection/actual pairs, including 58,268 with positive projected points.
These are candidate observations, not 58,268 independent, fully cleaned training
examples. Repeated players and shared games create dependence.

The largest provenance limitation: ESPN exposes archived week-specific forecasts,
but the tested records do not establish **when those forecasts were generated**.
We cannot call them verified kickoff snapshots, nor reconstruct what a Week 12
projection looked like back in Week 3.

## What is available

| Data | Verified access | Appropriate use / limitation |
|---|---|---|
| Weekly player actuals and projections | Global player archive, every season 2018–2025 | Core residual dataset; historical global rows require scoring raw components |
| League-scored weekly points | Configured league in 2024–2025; weeks 1, 8, 18 checked | Validation against `appliedTotal`; uses that season's rules |
| Raw passing, rushing, receiving, kicking and defensive scoring components | Actual and projected stat dictionaries | Rescore both sides under one scoring version; not a play-by-play feed |
| Player identity and eligibility | Player ID, name, default position, eligible slots | Keep IDs and season-specific metadata; hybrid positions need explicit mapping |
| Historical NFL team | Weekly stat record's `proTeamId` | Prefer this over the player's top-level team for historical joins |
| NFL schedule and opponents | Season schedule view checked for 2018, 2024, 2025 | Game IDs, teams, dates, scoring periods; join to distinguish games and byes |
| League rules, teams, schedule and results | Configured league's 2024, 2025, 2026 responses | League replay and validation; historical rules/team counts differ |
| Weekly fantasy rosters and lineup slots | Historical `mRoster` and scoreboard samples | Ownership and starter/bench/IR history; not intraday lineup revision history |
| Drafts | 192 picks in both 2024 and 2025; 224 in 2026 | Historical roster construction and later behavior research |
| Waiver/free-agent/roster transactions | `mTransactions2`, historical weeks 1, 8, 18 | Rows include type/status and some dates/bid fields; field presence varies |
| Accepted trades | Historical transaction row confirmed | Exchanged-player items may be empty; complete trade reconstruction not established |
| Recent activity feed | Current season works; 2024–2025 returned 404 | A failed communication feed does not mean transaction history is absent |
| Injury/ownership metadata | Fields exist in player responses | No verified weekly as-of injury, ownership-percentage, or depth-chart archive |
| Forecast revision history | Not verified | Retrieval timestamp must not be presented as forecast-generation timestamp |

The own-league settings response lists previous seasons 2024 and 2025. Earlier
requests for this league returned 404, including legacy history requests. That
does not prove that other older leagues are inaccessible. Likewise, a player
directory can exist without weekly stats: tested 2016 and 2017 full player pools
had no weekly rows. **2018 is the earliest verified usable season**, not a claim
that every conceivable pre-2018 ESPN route has been exhausted.

## Measured coverage

The pool filter includes the six normal fantasy positions and a few players with
hybrid default positions who are eligible for those slots. No top-owned-player
limit was applied to the global request. These counts describe returned data;
they do not independently prove ESPN has every historical NFL appearance.

| Season | Scoring weeks represented | Paired player-weeks | Pairs with projection > 0 |
|---|---|---:|---:|
| 2018 | 1–17 | 15,832 | 7,424 |
| 2019 | 1–17 | 12,412 | 7,370 |
| 2020 | 1–17 | 12,723 | 7,430 |
| 2021 | 1–18 | 14,271 | 7,711 |
| 2022 | 1–18 | 12,396 | 7,205 |
| 2023 | 1–18 | 11,887 | 6,834 |
| 2024 | 1–18 | 11,735 | 7,133 |
| 2025 | 1–18 | 10,647 | 7,161 |
| **Total** | | **101,903** | **58,268** |

“Projection > 0” uses the current 2026 scoring rules. It is a useful coverage
diagnostic, not the finalized inclusion rule: legitimate zero and negative
projections, especially D/ST, need intentional treatment. Do not add the many
zero-projection inactive records indiscriminately to an error distribution.

Current 2026 responses include future forecasts and in-progress actuals. They are
excluded from this completed-season table. Any later ingestion of 2026 must
establish completed games/weeks before calculating errors.

Per-position and per-week counts, historical/current scoring items, validation
results, and sanitized quality examples are in
[espn_history_findings.json](espn_history_findings.json).

## Reproducible access pattern

Base URL: `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl`

The most useful verified request is:

```text
GET /seasons/{year}/players?view=kona_player_info
X-Fantasy-Filter: {
  "filterSlotIds": {"value": [0, 2, 4, 6, 16, 17]},
  "filterStatsForSourceIds": {"value": [0, 1]},
  "filterStatsForSplitTypeIds": {"value": [1]}
}
```

This global route uses a **flat filter** and returned the season's weekly records
in one response. By contrast, the league route wraps player filters in
`{"players": {...}}`. The research reused the configured authenticated session;
anonymous access was not separately tested. League-independent does not imply
that this audit proved authentication is unnecessary.

For the configured league, use:

```text
GET /seasons/{year}/segments/0/leagues/{league_id}
    ?view=kona_player_info&scoringPeriodId={week}
X-Fantasy-Filter: {"players": {"limit": 2000}}
```

Other verified views on the league route: `mSettings`, `mRoster`,
`mDraftDetail`, `mTransactions2`, and combined `mMatchupScore`/`mScoreboard`.
Scoreboard requests also used a schedule filter for `matchupPeriodId`; matchup
periods and scoring weeks must not be conflated for multi-week playoffs.
NFL schedules use `/seasons/{year}?view=proTeamSchedules_wl`.

Player stat selection must require the requested `seasonId`, a positive
`scoringPeriodId`, `statSplitTypeId = 1`, and `statSourceId = 0` (actual) or `1`
(projection). Pair on season, player ID, and scoring week after resolving
duplicates. Season totals and rest-of-season splits are not weekly forecasts.
Require raw `stats` to be a dictionary; do not interpret nested stat objects as
players simply because they also contain `id`, `proTeamId`, and `stats`.

The endpoint semantics are also reflected in the maintained
[espn-api request implementation](https://github.com/cwendt94/espn-api/blob/master/espn_api/requests/espn_requests.py)
and [player parser](https://github.com/cwendt94/espn-api/blob/master/espn_api/football/player.py).
These are implementation references, not an official ESPN API contract. Wrapper
year restrictions are not sufficient evidence of server-side availability.

## Scoring: normalize before calculating errors

Historical global rows provide raw stat components but generally no league
`appliedTotal`. For this league's additive rules, score each component using its
configured points and default-position override, then sum:

```text
projection = score(projected_components, current_rules)
actual     = score(actual_components, current_rules)
residual   = actual - projection
```

I checked **9,715 values across 2024 and 2025, weeks 1, 8, and 18**, rescoring raw
global data under each historical season's rules and comparing with ESPN's
league-scored actuals/projections. There were **zero mismatches above 0.000001
points**; the largest floating-point difference was approximately 0.000000005.
A handful of league zero-score rows had no matching global record and were
reported separately, not counted as successful comparisons.

Current D/ST rules differ substantially from 2024–2025. For example, the
shutout override changed from 5 to 10 points, and the old yards-allowed tiers
were removed. Mixing old league-scored residuals with current projections would
mix scoring systems. Rescore both projected and actual historical components
under today's rules and record a scoring-rules hash/version.

Projected defensive scoring buckets can contain fractional values. Preserve
them; do not round them or substitute a bucket derived from expected points or
yards allowed. The audit helper validates this league's additive rules, not
every custom scoring format supported by ESPN.

Example from the configured league: Josh Allen's 2025 Week 1 archived projection
was 20.83 points and actual was 38.76, an error of approximately +17.93. One such
row is an observation; the model needs a distribution of comparable observations.

## Data quality and provenance boundaries

1. **Missing is not zero.** A missing actual can represent a bye, a cancelled
   game, an unavailable record, or another issue. An explicit empty/zero stat
   record is a different case. Even positive projections sometimes lack actuals.
2. **Cancelled games need explicit treatment.** Fifteen of the 17 positive
   projection records lacking actuals in 2022 were Bills/Bengals Week 17 players.
   That game was cancelled; those are not ordinary scoring misses. See the
   [Bills' official 2022 schedule](https://www.buffalobills.com/schedule/2022/).
3. **Duplicate keys can disagree.** In 2020, three actual player-week keys had
   conflicting team/game records. One had scores of 1.5 versus 0. The coverage
   helper quarantines conflicting keys instead of allowing response order to
   choose the result. Identical duplicates collapse to one row.
4. **Historical player pools matter.** Selecting today's rosters or only highly
   owned players creates survivorship/selection bias. Preserve season pools,
   eligibility, and provenance; investigate position and coverage shifts.
5. **Historical team joins matter.** Prefer the weekly stat's team, particularly
   for traded players. The [box-player implementation](https://github.com/cwendt94/espn-api/blob/master/espn_api/football/box_player.py)
   also distinguishes weekly and top-level team identity.
6. **A current field is not a historical snapshot.** Do not use injury status,
   percent owned, or a present-day team assignment as if known before an old game.
7. **No verified forecast vintage.** Store retrieval time separately from unknown
   forecast time. Archived forecasts support an archived-game-week error model;
   they do not establish exact pre-kickoff or several-weeks-ahead calibration.
8. **Completion flags need validation.** The 2018 schedule returned
   `statsOfficial = false` on historical games. That field alone is not a reliable
   universal completion filter. Resolve completion with schedule/game evidence.

## League replay and transaction findings

Historical rosters genuinely change: Week 1 versus Week 8 membership differences
were 116 in 2024 and 119 in 2025. Week 1 `mRoster` membership matched the historical
scoreboard roster in both years, including starter/bench/IR slots. A requested
future week's roster in the current season is not a prediction of future ownership.

The league had 12 teams in 2024/2025 and has 14 in 2026. Historical team totals are
useful for replay checks, but should not substitute for player-level uncertainty
in trade evaluation or be compared without accounting for changed rules/rosters.

`mTransactions2` returned the following scoring-period-specific row counts:

| Year | Week 1 | Week 8 | Week 18 |
|---|---:|---:|---:|
| 2024 | 209 | 14 | 24 |
| 2025 | 200 | 35 | 9 |

Week 1 includes 192 draft rows in each season, so these are not all waiver moves.
Later samples include waiver, free-agent, and roster activity. The accepted trade
in the 2025 Week 1 response had an empty `items` list. The
[espn-api transaction implementation](https://github.com/cwendt94/espn-api/blob/master/espn_api/football/league.py)
documents this limitation and attempts player-card recovery; recovery and
complete season-wide transaction coverage were not verified here. Bid-field
presence does not establish access to every unsuccessful claim or private offer.

## Next milestone

Build a validated player-week dataset before implementing probability outputs:

- Preserve raw actual/projected components, source identifiers, season/week/player,
  historical team, position/eligibility, retrieval time, and scoring version.
- Produce normalized projection, actual, and residual plus explicit missing,
  cancelled, bye, duplicate, and inclusion/exclusion diagnostics.
- Reconcile sample values to ESPN and audit distributions by position, year,
  and projection level. Choose inclusion policies before interpreting counts.
- Compare residual pools using chronological holdouts. More years available does
  not automatically mean all years should receive equal weight.
- Start timestamped forward-projection snapshots for future forecast-horizon
  research. Historical snapshot timing cannot be recovered by labeling it now.

Then calibrate uncertainty around ESPN expectations and connect seeded simulation
to the deterministic season engine. Shared-game correlations, injuries/availability,
and longer-horizon changes require modeling decisions; the archive is evidence
for those decisions, not a ready-made complete probability model.

## Reproduce the audit

Run `python -m research.espn_history_probe --phase coverage` using the repository's
configured environment. Other phases are `discovery`, `deeper`, `context`,
`quality`, and `transactions`. The probe makes read-only requests and stores
sanitized summaries under ignored `outputs/espn_history_probe/`; it does not
persist credentials, raw league responses, or member profiles. The checked-in
findings file freezes this audit's counts; reruns may change as ESPN changes.

Extraction tests: `python -m unittest discover -s tests -p test_espn_history_probe.py -v`.
The research probe is separate from app ingestion and does not change app behavior.
