# Consolidated ESPN Data Dictionary for the M1 Handoff

## Status and interpretation

This document consolidates M0.1–M0.5 evidence into proposed logical fields for M1 design. Names below are **design vocabulary**, not finalized Python classes, database columns, or a production canonical schema. M1.1 must define those artifacts separately.

Evidence labels retain their established meanings: **Verified live**, **Verified by tests**, **Unverified**, and **Unsupported**. Approved policy is not ESPN evidence. Presence codes are **R** required for the applicable record, **O** optional, and **C** conditional. Validation tiers are **S** snapshot acceptance, **C** capability-specific, and **W** diagnostic warning.

Primary raw endpoints are:

- League: `.../games/ffl/seasons/{season}/segments/0/leagues/{league_id}` with `mTeam`, `mRoster`, `mMatchup`, `mSettings`, `mStandings`, or `kona_player_info`.
- Season: `.../games/ffl/seasons/{season}` with `proTeamSchedules_wl`.
- Historical player-card comparison: the league endpoint with `kona_playercard`.

Every M1 source record should carry endpoint, view, request parameters, retrieval start/end UTC, configured league/season, and raw-source version/digest information sufficient to identify which request produced it.

## League identity and configuration

| Proposed logical field | Raw path / type / namespace | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `league_id` | request path and league object; integer, fantasy-league namespace | R; never null | Preserve configured/raw ID; **Verified live** | S: configured, response, and snapshot identities agree; snapshot join key |
| `season` | request path and league object `year`; integer season | R; never null | Preserve; **Verified live** | S: request and response agree; snapshot partition |
| `league_name` | `settings.name`; string | R for inspected source | Trim only; **Verified live** | S: nonempty; display metadata, potentially private |
| `current_scoring_period` | league current scoring period / `scoringPeriodId`; integer fantasy week | R for current refresh | Preserve; **Verified live** | S: positive and consistent with requested future range; refresh boundary |
| `team_count` | `settings.size`; integer | R | Preserve and reconcile to distinct `teams[]`; **Verified live** | S: metadata equals fetched count; no universal expected count |
| `regular_season_end` | `settings.scheduleSettings.matchupPeriodCount`; integer matchup period | R when H2H schedule is used | Preserve; **Verified live** | C: positive and consistent with matchup-period maps; season phase |

## Rules, roster configuration, and scoring

| Proposed logical field | Raw path / type / namespace | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `lineup_slot_capacity[slot_id]` | `settings.rosterSettings.lineupSlotCounts`; map string/int slot ID → integer | R; explicit zero is a configured zero | Convert keys to raw integer IDs; **Verified live** | S: unique IDs and nonnegative counts; roster capacity |
| `position_limit[position_id]` | `rosterSettings.positionLimits`; map default-position ID → integer/sentinel | C; `-1` is an explicit ESPN sentinel | Preserve raw IDs/sentinel; **Verified live** | C: namespace must not be confused with lineup slots; roster legality |
| `lineup_lock_type` | `rosterSettings.lineupLocktimeType`; enum string | C | Preserve raw and interpret only known value; **Verified live** | C: unknown enum retained unsupported; lineup legality |
| `roster_lock_type` | `rosterSettings.rosterLocktimeType`; enum string | C | Same; **Verified live** | C: transaction timing |
| `move_limit` | `rosterSettings.moveLimit`; integer/sentinel | C | Preserve `-1` meaning observed no limit; **Verified live** | C: validate recognized sentinel; transaction legality |
| `scoring_item.stat_id` | `settings.scoringSettings.scoringItems[].statId`; integer ESPN scoring-stat namespace | R | Preserve; **Verified live** | S: unique within scoring configuration; scoring identity |
| `scoring_item.points` | same item `.points`; finite number | R | Preserve precision; **Verified live** | S: finite, including valid zero/negative; score calculation |
| `scoring_item.overrides` | same item `.pointsOverrides`; mapping | O; absence differs from empty mapping | Preserve raw until M1 interpretation; **Verified live historical/current** | C/W: schema validation and raw retention; scoring reconstruction |
| `scoring_configuration_signature` | derived from ordered raw scoring items | R provenance field | Deterministic digest; **Verified by tests**, used live in M0.5 | S: projection/actual records tied to scoring context |

## Fantasy teams and standings

| Proposed logical field | Raw path / type / namespace | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `fantasy_team_id` | `teams[].id`; positive integer fantasy-team namespace | R | Preserve; **Verified live** | S: unique and referenced by roster/schedule/waiver rows |
| `team_name` | team name/location/nickname fields | R for UI/display | `espn-api` composes display name; **Verified live** | W/S for nonempty display; not an identity key |
| `manager_ids` | team owner refs joined to `members[].id` | O; may contain multiple | Library join; preserve IDs, omit from public reports; **Verified live** | W: privacy-sensitive and not simulator identity |
| `standing` / `playoff_seed` | `teams[].playoffSeed`; integer | R in observed league | Preserve raw role naming until M1 resolves semantics; **Verified live** | S: current ranks form unique permutation where ESPN supplies one |
| `wins`, `losses`, `ties` | `teams[].record.overall` numeric fields | R for settled standings | Preserve explicit zeros; **Verified live** | S: finite/nonnegative and complete; initial season state |
| `points_for`, `points_against` | `teams[].record.overall.pointsFor/pointsAgainst`; number | R | Preserve finite values including possible negative; **Verified live** | S: missing distinct from zero; standings/tiebreak state |
| `division_id` | team division reference / league divisions | C; no division is not an error | Preserve raw relationship; **Verified live** | C: references configured division when present; seeding rules |

## Current rosters and slot occupancy

| Proposed logical field | Raw path / type / namespace | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `roster_team_id` | containing `teams[].id` and player `onTeamId`; fantasy-team ID | R for rostered entry | Reconcile both sources; **Verified live** | S: exact agreement and known team |
| `rostered_player_id` | `teams[].roster.entries[].playerPoolEntry.player.id`; signed integer player namespace | R | Preserve nonzero signed ID; **Verified live** | S: globally unique owner; negative D/ST IDs valid |
| `occupied_lineup_slot_id` | roster entry `.lineupSlotId`; integer lineup-slot namespace | R | Preserve raw ID; **Verified live** | S: configured/recognized or explicitly unsupported; occupancy counts within capacity |
| `roster_entry_status` | player pool entry status/injury fields | O/C | Preserve raw enum; **Verified live** | C: reserve legality; no inferred injury-return behavior |
| `ordinary_occupancy` / `reserve_occupancy` | derived from raw entry slots and configured capacities | R validation result | Count separately; **Verified live/current league** | S: no capacity overflow; IR is never silently bench |

## Players and positional eligibility

| Proposed logical field | Raw path / type / namespace | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `player_id` | wrapper `players[].id`, `player.id`, roster player ID; signed integer | R | Require wrapper equality; **Verified live** | S: nonzero; global player join key; negative D/ST IDs valid |
| `default_position_id` | `player.defaultPositionId`; integer default-position namespace | R | Preserve and separately map known IDs; **Verified live** | S/C: never decode with lineup-slot mapping; player grouping |
| `eligible_slot_ids` | `player.eligibleSlots[]`; integer lineup-slot namespace | R for lineup candidates | Deduplicate/preserve raw; **Verified live** | S: nonempty for rostered players and included in the observed eligibility namespace; an unconfigured observed ID is preserved but is not playable |
| `observed_lineup_slot_ids` | union of raw `player.eligibleSlots[]` across the retrieved player universe | R derived evidence | Preserve sorted immutable identifiers without adding absent capacity records; **Verified live + tests** | S: exactly reconciles player eligibility; distinct from configured `lineupSlotCounts`; source for schema-v2 namespace |
| `nfl_team_id` | `player.proTeamId`; integer NFL-team namespace; zero can mean none | R for player-pool entry | Preserve; **Verified live** | S/C: nonzero must reference NFL universe; zero is not a bye |
| `injury_status` | `player.injuryStatus`; enum/string | O; absent remains absent | Preserve raw; **Verified live** | W/C: availability evidence only; no future injury model |

## Ownership and free-agent/waiver state

| Proposed logical field | Raw path / type / namespace | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `pool_status` | `players[].status`; enum `ONTEAM`, `FREEAGENT`, `WAIVERS`, or unknown | R in player-pool view | Preserve raw; interpret known values; **Verified live** | S: unknown enum retained and capability flagged; acquisition state |
| `owner_team_id` | `players[].onTeamId`; fantasy-team ID, zero unrostered | R | Preserve zero versus team reference; **Verified live** | S: `ONTEAM` reconciles roster; unrostered known statuses require zero |
| `ownership_as_of_week` | request `scoringPeriodId` plus retrieval time | R provenance | Current week is ownership authority; **Verified live** | S: future-view ownership must not overwrite current ownership |
| `player_pool_page_context` | `x-fantasy-filter` offset/limit/status list | R provenance | Record every page and termination; **Verified live** | S: no duplicate pages/IDs and terminal short page; independent total unsupported |

## Player-week projections

| Proposed logical field | Raw path / type / namespace | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `projection_season`, `projection_week` | `player.stats[].seasonId/scoringPeriodId`; integer | R for matching stat | Exact request association; **Verified live** | S: player-season-week composite key |
| `raw_projection` | matching stat `.appliedTotal`; finite number | O/nullable; absent matching record means missing | Raw parse; bypass library rounding/default; **Verified live** | S: `NaN`/infinity invalid; finite negatives preserved; ESPN mean input |
| `projection_status` | derived from record presence/value | R enum `missing`, `explicit_zero`, `present` | Repository classification; **Verified live + tests** | S: consistent with raw nullable value |
| `effective_projection` | approved policy derived value | R for V1-ready future input | Missing→0; zero→0; positive unchanged; finite-negative treatment requires explicit M1 review | S: approved portions are policy, **not ESPN evidence**; never silently coerce a raw negative |
| `effective_projection_source` | derived enum `espn` or `missing_projection_policy` | R | Based on raw presence, never magnitude alone | S: missing must use policy source; present values use ESPN source |
| `projection_stat_source_id` | matching stat `.statSourceId`; integer source namespace | R for present ESPN projection | Require `1`; **Verified live** | S: source 0 must never be projection |
| `projection_split_type_id` | matching stat `.statSplitTypeId`; integer split namespace | R for present weekly record | Require `1`; **Verified live** | S: scoring period 0 totals/averages excluded |

Approved V1 uses the currently available ESPN player-specific projection for every future week. It does not forecast later ESPN revisions, applies no horizon mean or variance adjustment, and treats the expected future revision adjustment as zero solely as an approved simplification.

## NFL teams, games, and byes

| Proposed logical field | Raw path / type / namespace | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `nfl_team_id` | season `settings.proTeams[].id`; positive integer | R for active NFL teams | Preserve; **Verified live** | S: unique; observed universe reconciles to separately verified expected count 32 |
| `bye_week` | `settings.proTeams[].byeWeek`; integer scoring week | R in investigated source | Preserve explicit value; **Verified live** | S: bye week must not contain a nonempty game record |
| `nfl_games_by_week` | `proGamesByScoringPeriod`; mapping week→games | C | Preserve raw references/timing; **Verified live for bye reconciliation** | S/C: valid team references and no contradictory bye game |

## Fantasy regular-season schedule

| Proposed logical field | Raw path / type / namespace | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `matchup_id` | `schedule[].id`; positive integer matchup-row namespace | R | Preserve; **Verified live** | S: unique |
| `matchup_period_id` | `schedule[].matchupPeriodId`; fantasy matchup-period integer | R | Preserve; **Verified live** | S: mapped to scoring periods and regular/postseason phase |
| `home_team_id`, `away_team_id` | `schedule[].home.teamId/away.teamId`; fantasy-team IDs | R for ordinary regular matchup | Preserve; **Verified live** | S: distinct valid teams; each team exactly once per regular week |
| `matchup_scoring_periods` | `scheduleSettings.matchupPeriods`; map period→week list | R for multiweek interpretation | Normalize keys only; **Verified live** | C: positive ordered weeks without conflicting round duration |

## Waiver priority and transactions

| Proposed logical field | Raw path / type / namespace | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `acquisition_type_raw` | `settings.acquisitionSettings.acquisitionType`; enum string | R | Preserve and interpret only known enums; **Verified live** | C: unknown structurally valid enum is unsupported, not invalid |
| `uses_acquisition_budget` | `.isUsingAcquisitionBudget`; bool | R | Preserve; **Verified live** | C: reconcile budget fields and acquisition type |
| `waiver_rank` | `teams[].waiverRank`; integer mutable state | C when priority waivers apply | Preserve; **Verified live** | C: if present, complete unique 1..team-count permutation |
| `waiver_order_reset` | acquisition `.waiverOrderReset`; bool | C | Preserve; weekly-reset interpretation supported by external guidance | C: exact multiple-claim behavior remains unresolved |
| `waiver_hours`, `process_days`, `process_hour_raw` | acquisition settings fields; integer/list/integer | C | Preserve; **Verified live** | C/W: days/hours structurally validate; hour timezone unverified |
| `acquisition_limits` | `acquisitionLimit`, `matchupAcquisitionLimit`; numeric/sentinel | C | Preserve recognized sentinel; **Verified live** | C: transaction legality |
| `trade_deadline_utc` | `tradeSettings.deadlineDate`; epoch milliseconds | C | Convert to UTC while retaining raw; **Verified live** | C: finite valid epoch; trade legality |
| `trade_limit`, `review_hours`, `veto_votes_required` | `tradeSettings.max/revisionHours/vetoVotesRequired`; integers | C | Preserve; **Verified live** | C: review workflow remains unverified; M4/M5 trades |

## Championship and consolation metadata

| Proposed logical field | Raw path / type / namespace | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `playoff_qualifier_count` | `scheduleSettings.playoffTeamCount`; integer | R | Preserve; **Verified live** | C: 0 allowed, 1 invalid, cannot exceed teams |
| `playoff_round_lengths` | `.playoffMatchupPeriodLengthByRound`; map round→weeks | C if playoffs enabled | Normalize integer keys; **Verified live** | C: contiguous rounds and consistent matchup periods |
| `playoff_reseed` | `.playoffReseed`; bool | C | Preserve; **Verified live** | C: bracket behavior |
| `first_round_bye_count` | derived from qualifier count and bracket power of two | C | Structural derivation; **Verified by tests and historical evidence** | C: does not hardcode current league |
| `playoff_seeding_rule_raw` | `.playoffSeedingRule`; enum | C | Preserve and interpret known value; **Verified live** | C: secondary tiebreaks unresolved |
| `matchup_tie_rule_raw` | `scoringSettings.matchupTieRule`; enum | C | Preserve `NONE`; semantics **Unverified** | C: blocks tied regular matchup progression, not M1 ingestion |
| `playoff_tie_rule_raw` | `.playoffMatchupTieRule`; enum | C | Preserve raw; semantics **Unverified** | C: blocks tied playoff advancement |
| `consolation_enabled` | `.consolationLadderDisabled`; bool/null | C | Invert only explicit bool; **Verified live** | C: null remains unknown |
| `consolation_structure` | current/historical `schedule[]` relationships | C | Reconstruct only observed pairings/transitions | **Unverified** for current eight-team ladder; preserve gap metadata |

## Historical projection/actual research records

| Proposed logical field | Raw path / type / namespace | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `historical_projection` | weekly source-1/split-1 `.appliedTotal`; finite number | O/nullable | Same raw matching as future projections; **Verified live field** | Research validation: never apply effective-zero policy to raw history |
| `historical_actual` | weekly source-0/split-1 `.appliedTotal`; finite number | O/nullable | Exact player-season-week match; **Verified live** | Research only; scoring revisions may be retrospective |
| `actual_stat_components_present` | source-0 `.stats`; mapping | O | Boolean coverage flag plus raw research data if approved | W: participation evidence, not universal |
| `temporal_provenance_class` | no raw as-of field exists | R derived evidence label | `historical_projection_pregame_provenance_unverified` | Must never be promoted without independent timestamped evidence |
| `forecast_horizon` | no verified field | nullable/unsupported | None | Unsupported; no V1 horizon adjustment |

Historical unverified pairs may be used only for explicitly provisional exploratory calibration. Outputs must distinguish structural correctness, provisional statistical calibration, and empirically validated calibration. No distribution family or promotion threshold is selected by M0.6.

## Retrieval and source provenance

| Proposed logical field | Source/type | Presence and missingness | Transformation and evidence | Validation tier / limitation / use |
|---|---|---|---|---|
| `retrieval_started_at_utc`, `retrieval_finished_at_utc` | repository request boundary; UTC timestamp | R for multi-request refresh | Record, never infer ESPN transaction time | S: ordered finite timestamps; consistency window |
| `endpoint`, `view`, `parameters`, `page_offset_limit` | request context | R per source batch | Sanitize credentials; preserve material filters | S: reproducibility and truncation detection |
| `source_library_version` | installed `espn-api` version | R | Record exact version | S/W: transformation provenance |
| `raw_payload_digest` | future M1 digest of staged raw bytes | R in immutable snapshot design | Deterministic cryptographic digest | S: integrity; not yet implemented |
| `evidence_classification` | M0/M1 metadata enum | R for uncertain fields/rules | One of established four labels | S: test evidence never upgraded to live |
| `interpretation_status` | derived capability enum | R for raw rules | valid-and-understood, valid-but-unsupported/unverified, invalid/contradictory | C: invalid blocks publication; unsupported can be preserved |
| `manual_configuration_source` | future explicit league config | C | ESPN first; config fills absence only; conflicts fail | C: permitted only for audited gaps with provenance |

## Known `espn-api` transformations and namespace hazards

1. `espn-api` player projections round `appliedTotal` and use `stats.get("appliedTotal", 0)`, collapsing missing and explicit zero. M1 must parse the raw weekly stat record.
2. Its derived sparse `position_slot_counts` can misalign ESPN slot IDs and labels. M1 must use raw `lineupSlotCounts` keys with validated mappings.
3. `defaultPositionId` is a player-position namespace; `lineupSlotId` and `eligibleSlots` are lineup-slot namespaces. They are never interchangeable.
4. ESPN player IDs are signed and nonzero; negative D/ST identifiers are valid.
5. `statSourceId=1` is projection and `0` is actual in the verified weekly structure. `statSplitTypeId=1` is the weekly split; `scoringPeriodId=0` season totals/averages must not be joined as weeks.
6. Unknown ESPN enum values remain raw and capability-limiting. M0 evidence does not justify a complete universal enum table.

## M1 validation inventory

| Invariant | Tier | Required behavior |
|---|---|---|
| League/season identity, nonempty settings, distinct team IDs, metadata/fetched count reconciliation | S | Reject staged snapshot on mismatch |
| Unique signed nonzero player IDs and at most one current owner | S | Reject duplicate/conflicting ownership |
| Roster slot occupancy within dynamically discovered capacities; reserve distinct from bench | S | Reject overflow/unknown contradictory references |
| Player eligibility references valid raw lineup slots | S/C | Accept snapshot data; block lineup capability if required semantics unsupported |
| Unique scoring stat IDs and finite points/overrides with scoring signature | S | Reject malformed configuration |
| Player-season-week/source/split identity and finite raw values | S | Reject cross-week/source confusion and non-finite values |
| Raw/status/effective/source projection relationship | S | Enforce missing→policy zero, explicit zero→ESPN zero, positive present→unchanged ESPN value; reject/unresolved until negative-effective semantics are approved |
| NFL team universe, IDs, games, and bye consistency | S | Reject duplicates, omissions against verified expected universe, and bye/game conflict |
| Complete regular-season matchup references and one appearance/team/week | S | Reject incomplete or duplicate schedule |
| Paginated pool termination, unique IDs, request context, multi-request timing | S/W | Reject detected truncation/overlap; warn on wide consistency window |
| Waiver priority permutation when priority state is required/present | C | Block waiver simulation on incomplete/conflicting order, not generic snapshot storage |
| Transaction enums/limits and verified workflow | C | Preserve unknown settings; block only the dependent M4/M5 behavior |
| Playoff seeds, qualifier count, periods, round durations, references | C | Required before authoritative championship simulation |
| Consolation participants, transitions, and full placement coverage | C | Preserve unresolved metadata in M1; block authoritative full-placement simulation |
| Refresh timestamps, request provenance, library/code/schema versions, raw digest | S | Reject untraceable publication |
| Historical scoring signature and temporal evidence class | Research/C | Never combine mismatched scoring silently or label unverified data as pregame |
| Unknown valid rule versus invalid contradictory structure | S/C | Preserve the former explicitly; reject the latter |

An unresolved capability-specific rule is not automatically a malformed snapshot. M1 may store it with explicit status, source, severity, and dependent capabilities. Simulation code must then refuse the affected authoritative behavior rather than substitute a familiar rule.
