# Data: ESPN evidence, canonical snapshots and storage

This is the current data lifecycle reference. Governing requirements remain [MASTER_SPEC sections 2-4, live-week addendum and M0/M1](MASTER_SPEC.md) and applicable [ROADMAP gates](ROADMAP.md). [RESEARCH](RESEARCH.md) owns historical temporal trust/evaluation; [TRANSACTIONS](TRANSACTIONS.md) owns hypothetical state/legality; [SEASON_SIMULATOR](SEASON_SIMULATOR.md) owns scoring/brackets; [Partial Week](PARTIAL_WEEK.md) owns execution permission/composition. [APPLICATION_SERVICE](APPLICATION_SERVICE.md) owns HTTP refresh and separate job/result persistence. Operator commands/configuration precedence live in [OPERATIONS](OPERATIONS.md).

- [Retrieval and provenance](#retrieval-and-provenance)
- [Raw-to-canonical map](#raw-to-canonical-map)
- [Canonical validation and serialization](#canonical-validation-and-serialization)
- [Rules and manual authority](#rules-and-manual-authority)
- [Live and temporal evidence](#live-and-temporal-evidence)
- [Immutable storage](#immutable-storage)
- [Source observations and limitations](#source-observations-and-limitations)
- [M0 consumer dependency](#m0-consumer-dependency)
- [Source and verification](#source-and-verification)

## Retrieval and provenance

Public leagues use no cookie pair; private leagues require both authorized ESPN_S2 and ESPN_SWID. Installation/startup is credential-free; retrieval is read-only network work. Never log/store cookies, tokens or authentication headers as provenance. League/team/player identities, raw responses, databases, research and detailed reports remain private. An explicit expected team count is an identity check, not a league-size template.

[espn_adapter.py](../src/fantasy_football/espn_adapter.py) separates sequential `retrieve_bundle()` from pure `translate_bundle()` and validation/reporting. `fetch_and_translate()` composes them; storage allocates publication identity. `CapturedResponse`, `PlayerPage` and `EspnSourceBundle` preserve role, endpoint/view, sanitized material parameters, offset/limit/week, retrieval UTC, deterministic parsed-payload SHA-256 and library context. These are parsed JSON representations, not HTTP wire bytes. No snapshot UUID is assigned during retrieval.

| Request | Authority / limitation |
|---|---|
| `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}`, views mTeam,mRoster,mMatchup,mSettings,mStandings | Initial league/settings/roster/standings/schedule authority; final request reconciles mutable state. Raw mappings bypass convenience-object transformations. |
| Same league endpoint, `kona_player_info`, explicit scoringPeriodId and paginated x-fantasy-filter | Current week owns player identity/ownership/status. Each future week supplies matching projections, never future ownership. Status filters include FREEAGENT, ONTEAM and WAIVERS; no independently known player-universe total. |
| Season endpoint `.../seasons/{season}`, `proTeamSchedules_wl` | NFL IDs, byeWeek and per-week games/date/statsOfficial. Not a fantasy settlement source. |
| `https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard` | Current event status joined by exact ESPN game ID; season dates/seasontype/week are explicit. Does not grant lineup/transaction permissions. |
| Historical league view `kona_playercard` | Bounded current-response comparison only; not a replacement for week-specific future projections or an authenticated vintage archive. |

Every pool series starts at offset 0, advances by limit, rejects oversized/duplicate/overlapping pages and ends on a short page (including an empty terminal page after an exact multiple). Retrieval's bounded page safety limit fails rather than returning a truncated universe. Every future week must match the current universe; identity/eligibility/protection reconcile. Final league comparison requires unchanged ownership/slots, W/L/T, PF/PA, seeds and priority. This catches specified changes across the retrieval interval, not transactional ESPN isolation or every possible settings change. No timestamp can prove settlement.

Default retry policy allows at most two retries after the initial request for connection/timeouts and supported HTTP 5xx errors. Auth/invalid league, malformed data, identity/ownership contradiction, incomplete pagination and validation errors are not retried. Request-context errors identify role/week/page without credentials. The separate public scoreboard uses a bounded HTTP timeout; synchronous espn-api operations do not provide universal in-flight cancellation. Application bounded shutdown is a separate contract.

### Evidence vocabulary

**Verified live** means the field/relationship was observed in the identified authorized retrieval, not universally guaranteed. **Verified by tests** establishes parser/normalization behavior on synthetic/sanitized fixtures. **Unverified** needs evidence; **Unsupported** is unavailable/unsafe in the investigated source or consumer. Approved policy is not an ESPN evidence class. Rule interpretation statuses (`understood`, `unverified`, `unsupported`, `missing`) and research evidence enums serve different purposes; do not equate understood fixture configuration with live proof.

## Raw-to-canonical map

Paths below are relative to the league response unless another request is named. These are **implemented canonical names**, not the proposed M0 dictionary vocabulary. Raw field availability is bounded to the [observations below](#source-observations-and-limitations); normalization/validation is **Verified by tests**. Unknown semantics remain explicit. Captured raw source retains additional fields even when no canonical entity projects them.

### Identity, rosters and player weeks

| Raw source | Canonical destination / transformation and constraint |
|---|---|
| request league/season, response `id`, `seasonId`, `scoringPeriodId`; `settings.name`, `settings.size` | LeagueSnapshot league_id/season/name, live context, LeagueRules.team_count; configured/response identities and distinct team count reconcile. Display names are not identity. |
| `teams[].id`, `.name` (or abbrev), `.record.overall.wins/losses/ties/pointsFor/pointsAgainst` | FantasyTeam identity/display and explicit cumulative W/L/T/PF/PA; finite points, no missing-to-zero substitution. |
| `teams[].playoffSeed`, `.waiverRank`, `.divisionId` | standing/playoff_seed, nullable waiver_priority/division_id. Source seed is current fact, not simulated future seeding. Owner/member joins from the early library diagnostic are private contextual evidence, not a second canonical owner table. |
| `teams[].roster.entries[].playerId`, `.playerPoolEntry.id`, `.playerPoolEntry.player.id`, `.playerPoolEntry.onTeamId`, `.lineupSlotId` | RosterEntry(player_id,team_id,lineup_slot_id,raw_owner_team_id); reconcile containing team, signed IDs and raw owner with current player pool. One authoritative roster owner. |
| current `players[].id`, `.player.id`, wrapper `.status`, `.onTeamId` | Player.player_id/acquisition_status and reconciliation to RosterEntry. IDs signed/nonzero; ONTEAM needs owner, FREEAGENT/WAIVERS no owner. Unknown enum preserved without guessed permission. |
| `player.fullName`, `.defaultPositionId`, `.eligibleSlots`, `.proTeamId`, `.injuryStatus` | Player display_name, default_position_id, eligible_lineup_slot_ids, nfl_team_id, injury_status. Name/injury nullable; future views must agree on required identity/eligibility, not override current ownership. NFL team 0 is unassigned, never bye. |
| union of raw `eligibleSlots` | LineupSlotNamespace.observed_slot_ids exactly preserves the observed sorted namespace. Default-position IDs and lineup-slot IDs remain distinct. Observed-only slot 25 is not playable without configured capacity. |
| `player.droppable` in current pool/roster/future copies | Nullable inverse Player.is_undroppable with exact source ID; Boolean only, numeric 0/1 invalid. Cross-copy absence/known value reconcile. Proposed polarity is retained, while undroppable_player_mapping stays unverified pending individual UI correlation. |
| `player.stats[]`: matching seasonId/scoringPeriodId, statSourceId=1, statSplitTypeId=1, appliedTotal | PlayerWeek `(player_id,season,scoring_week)`, raw_projection, projection_class, effective_projection/source and source_id. Exactly matching weekly record; duplicates/malformed/nonfinite values fail. Period 0 totals/averages are not weeks. |
| same identity fields, statSourceId=0, weekly split 1, appliedTotal | PlayerScoringObservation.actual_points and confirmed/unavailable evidence, with source ID. Present actual zero remains confirmed zero; absence stays unavailable. Component stats presence is a diagnostic, not participation proof. |
| no accepted live remainder/lock field | remaining_projection=None and lineup_locked=None; full-game source-1 projection never becomes an in-game remainder. |

### Projection contract

Historical provenance: the 15 October 2026 M0.3 follow-up used current-week kona_player_info for the configured 2026 league, week 6: pages 250/250/250/250/52, 1,052 distinct IDs. Exactly one matching seasonId/scoringPeriodId, source 1/split 1 record with numeric appliedTotal established a raw projection. Absence of a matching record was classified as missing; a matching appliedTotal=0 was explicit zero. The library's defaulted appliedTotal could not preserve that distinction. Current wrapper status/onTeamId supplied ownership, proTeamId=0 meant no association, explicit byeWeek was cross-checked with proGamesByScoringPeriod; injuryStatus/injured/active were descriptive, not future-health permission. The sample had 657 present values (286 zeros, 371 positive), 395 missing and no observed negative projection. Of the missing records, 394 were unrostered (384 free agents, 10 waivers), one rostered; 297 lacked NFL association, 98 had one, and seven were on bye. All 395 exposed active=true; 54 were NFL-assigned, non-bye and ACTIVE. These overlapping dimensions are not additive absence explanations or universal rates. They establish why missing cannot mean a verified zero forecast/nonparticipation. [Original dated evidence](https://github.com/tdkelley2001/fantasy_football/blob/4eea42d829e066ad9816e77399f09b9e28163de8/docs/MISSING_PROJECTION_POLICY.md) retains detailed injury/ownership tables; citing it does not authenticate its bytes offline.

| Raw record | Classification | Effective value | Effective source | Ordinary projected-lineup available |
|---|---|---:|---|---|
| Missing matching record | missing | 0 | missing_projection_policy | No |
| Present exactly zero | explicit_zero | 0 | espn | No |
| Present positive | present | unchanged raw | espn | Yes |
| Present finite negative | present | unchanged raw | espn | No |

Availability is derived as `effective_projection > 0`. Values are finite, neither rounded nor clamped. The old M0 negative-value design question is resolved by the accepted canonical contract. This data rule does not floor realized scores. The [outcome-model owner](PLAYER_OUTCOME_MODEL.md) owns WR-022 deterministic missing draws/public policy identity; [generated missing-policy authority](PLAYER_OUTCOME_MODEL.md#missing-zero-and-present-projections) is checked by M0 contract 2. No position-average, injury-return or replacement projection fallback is permitted. Future weeks use currently returned ESPN projections without predicting revisions or applying horizon mean/variance factors.

### Roster, scoring and transaction settings

| Raw path under settings | Canonical destination / normalization |
|---|---|
| `rosterSettings.lineupSlotCounts` | Sorted LineupSlotRule IDs/capacities, including explicit zero. Raw 20 identifies BENCH, 21 RESERVE; other configured IDs are STARTER. Positive configured eligible capacity is required for occupancy; no universal slot-count template. |
| `rosterSettings.positionLimits` | PositionLimit in **default-position** namespace. -1 -> unlimited None; other negatives fail. Non-position key 0 must be zero and is omitted. |
| `rosterSettings.lineupLocktimeType`, `rosterLocktimeType`, `moveLimit` | Raw lock enums retained; -1 move sentinel -> None. INDIVIDUAL_GAME setting is not per-player verified lock state or future permission. |
| `rosterSettings.isUsingUndroppableList` | Nullable LeagueRules enablement/source. False differs from unknown; known player status still needs understood mapping when enabled. |
| `scoringSettings.scoringItems[].statId`, `.points`, `.pointsOverrides` | Sorted ScoringRule IDs, finite signed points and sorted finite override pairs; absent overrides normalize to empty tuple, raw absence remains in captured response. Research scoring signature separately hashes currently returned scoring context. |
| `acquisitionSettings.acquisitionType`, `isUsingAcquisitionBudget` | AcquisitionRules raw type/budget flag; traditional_waiver_priority understood only for WAIVERS_TRADITIONAL. FAAB/other valid types remain consumer-unsupported rather than relabeled. |
| `acquisitionLimit`, `matchupAcquisitionLimit` | Independent season/matchup limits; -1 -> None. Integral float matchup limit is normalized to integer; malformed/other negative values fail. Limits do not prove current usage counts. |
| `waiverHours`, `waiverProcessDays`, `waiverProcessHour`, `waiverOrderReset` | Delay, raw process-day list/hour and Boolean reset. Hour timezone, clearance and multiple-claim ordering remain unverified; team waiverRank is mutable state, not the reset rule. |
| `tradeSettings.max`, `deadlineDate`, `revisionHours`, `vetoVotesRequired` | TradeRules enabled (max!=0), limit (-1 -> None), epoch-ms UTC deadline, review duration and threshold. Threshold/delay do not identify review workflow or acceptance probability. |
| `scoringSettings.scoringType`, `scheduleSettings.playoffSeedingRule` | StandingsRules type/raw first tiebreak; TOTAL_POINTS_SCORED -> points_for interpretation. Secondary sequence remains unresolved. |
| `scoringSettings.matchupTieRule`, `playoffMatchupTieRule` | Raw NONE retained; owner-confirmed normalization allow_ties / higher_seed. Other values stay unverified/missing, not current-league defaults. |

### Calendar, brackets and NFL evidence

| Raw source | Canonical destination / normalization |
|---|---|
| `scheduleSettings.matchupPeriodCount`, `matchupPeriods` | Regular-end period ID and ordered period-to-scoring-week mapping. MatchupPeriod calendar phase regular/postseason is separate from bracket. Full source-backed matchup_period_configuration interpretation preserves earlier current-period weeks outside the simulation horizon. |
| `schedule[].id`, `.matchupPeriodId`, `.home.teamId`, `.away.teamId` | FantasyMatchup ID/period/sides. Ordinary regular rows need complete pairs. Adapter postseason rows classify two sides scheduled, one partial, none placeholder, bracket_type postseason_unresolved; no inferred future participants/bracket membership. Canonical format also supports explicit bye/known bracket records when evidenced. |
| `scheduleSettings.playoffTeamCount`, `playoffReseed`, `playoffMatchupPeriodLengthByRound` | ChampionshipRules qualifier count, reseed, ordered PostseasonRound references. 0 disables, 1 invalid, count cannot exceed teams. Durations must agree with period weeks; do not hardcode six qualifiers/two byes/two-week final. |
| `scheduleSettings.consolationLadderDisabled` | Explicit Boolean inverted; missing/null stays unknown. Participant count derives only when enablement known. Default adapter rounds empty; championship periods cannot silently supply consolation membership. |
| audited `consolation_structure` manual value | bounded_winner_up_loser_down_v1 plus nonempty unique integer round_matchup_period_ids, all canonical postseason IDs with strictly increasing scoring weeks. Raw evidence/manual digest/approval remain separate. |
| season `settings.proTeams[].id`, `.abbrev`, `.byeWeek` | NFLTeam ID/nullable abbreviation/bye. Ignore unassigned ID 0; enforce the separately verified supported NFL universe count 32, not a fantasy-league-size rule. |
| `.proGamesByScoringPeriod[week][]`: id, scoringPeriodId, homeProTeamId, awayProTeamId, date | NFLGame string ID/week/team references and optional epoch-ms UTC kickoff. Duplicate team-side copies agree exactly. At most one game per team/week; each required week has game or explicit bye, not both. |
| game status if supplied; otherwise scoreboard event id, status.type.name/completed/state; otherwise statsOfficial | Supported explicit status branch is Verified by tests. Actual schedule status field was absent live. Scoreboard exact-ID join supplies scheduled/in-progress/completed status with consistent pre/in/post and completed flags. statsOfficial=true supports completed; false alone -> unknown. Conflicts fail, unknown tokens are not guessed. |
| repository request capture | SourceReference fields source_id, HTTPS endpoint, view, parameters, retrieved_at_utc and payload_sha256. Retrieval interval bounds requests but is not an ESPN transaction timestamp. AdapterReport retains library context; no invented canonical field for an old proposed dictionary name. |

## Canonical validation and serialization

Current canonical schema **4**; supported document reads **2, 3, 4**; new publication requires **4**. SQLite snapshot schema **1** and partial companion artifact **1** are independently versioned. Schema v1 is rejected. [canonical/model.py](../src/fantasy_football/canonical/model.py) uses frozen slotted dataclasses/tuples, stable flat identities and joins. LeagueSnapshot holds rules, teams, players, PlayerWeek, RosterEntry, MatchupPeriod/FantasyMatchup, NFLTeam/NFLGame, sources/interpretations/gaps and nullable LiveScoringState. LeagueRules groups scoring/slots/position limits, acquisition/trade/standings/championship/consolation and protection.

Positive fantasy-team/period/matchup/NFL/source relationships and signed nonzero player IDs reconcile; source/request IDs are nonempty stable strings. RosterEntry is the sole owner relationship; Player does not duplicate owner state. Missing/unknown acquisition states do not imply free agency. EvolvingLeagueState/state_to_json is [transaction audit state](TRANSACTIONS.md), not canonical JSON.

`validate_snapshot()` is pure/deterministic/nonmutating. It rejects incompatible schema/horizon/identity, non-UTC or inconsistent retrieval/source times, duplicate IDs/ownership, invalid capacity/eligibility/position references, missing player-week horizon records, incorrect raw/class/effective/source relationships, nonfinite scoring/standings/overrides, overlapping/incomplete periods, regular pairing gaps, invalid postseason side/status/bracket relationships, NFL game/bye contradictions, source/rule/manual provenance conflicts and malformed rule gaps. Known teams are unique in a period; multiple bracket types can share a postseason calendar period. No silent correction/default/owner creation occurs.

`RuleInterpretation` uses understood/unverified/unsupported/missing. Understood requires normalized meaning; missing has no raw/normalized value. Immutable JsonArray retains order, JsonObject sorted unique keys; nested JSON scalars/arrays/objects round-trip, mutable containers/duplicate unordered keys/nonfinite values fail. `RuleGap` names a unique nonempty ID, reason, source, nonduplicated affected capabilities and manual eligibility. Unknown coherent rules can be published but `require_understood_rules()`/consumer checks block the dependent operation. Structural validity is not execution permission.

`generate_quality_report()` validates first, then reports identity/horizon/entity counts, roster ownership, required/observed player-weeks, overall and per-week/position/ownership projection coverage and rule/capability warnings. Percentages use player-week denominators; explicit zero, missing, negative and observed-only slots are data characteristics, not one warning per player. Coverage is computed, not caller asserted.

`snapshot_to_json()`/`snapshot_from_json()` use deterministic record/key ordering, indented newline-terminated UTF-8 JSON, UTC Z timestamps, explicit null/zero/signed values and no nonfinite numbers; decoding revalidates. v2 omits v3 protection keys; v3 requires them even when null. Pre-v4 omits live/status fields and decodes no live companion/unknown status. Earlier v4 missing optional full-period evidence stays readable but cannot authorize a safe V1 boundary. Reserializing old parsed records can materialize optional defaults; historical byte identity comes from stored original canonical_json, never a new serialization.

## Rules and manual authority

| Source/evidence | Consumer boundary (algorithms owned elsewhere) |
|---|---|
| Dynamic roster/scoring/eligibility/period records | No fantasy team/slot/bracket template; malformed structure rejects ingestion. |
| Traditional type, budget flag, limits/reset/priority | Only verified non-budget traditional execution is supported. FAAB/alternative formats, unknown resets/usage and timing remain gated. |
| Raw injury/IR/lock settings | OUT/IR placement and two modeled IR modes belong to Transactions; no current provider authenticates arbitrary future strict IR or real per-player lock permission. |
| Undroppable setting and nullable player Boolean | League false does not prohibit by this rule; true/protected prohibits; true/unknown or unknown enablement cannot authorize automatic drop. Even known unprotected needs understood polarity and all other legality checks. |
| Raw NONE ties and TOTAL_POINTS_SCORED | Owner UI confirmation on 18 October 2026 supports allow_ties/higher_seed and PF-first for equivalent records. Alternate/deeper rules remain unsupported, not guessed. |
| Championship/consolation metadata | Fixed no-reseed title graph, independent rounds and placement/odd-reentry limitations belong to Season. Explicit enablement is separate from mapping/movement. |
| Postseason acquisition permission | No universal verified ESPN field/provider. Named all-team V1 assumption or provenance-validated configuration belongs to Season/Transactions, not a source claim. |

`load_manual_rule_config()` allows only audited fillable gaps with exact league/season, rule_id/gap_id/config_key, approved_value, expected_raw_value, approval and HTTPS evidence_url. Validate identity, duplicates, finite structure and agreement with existing ESPN evidence; no manual override of known contradictory facts. File SHA-256 and evidence URL become separate source provenance; original raw interpretation remains. Profile availability is not proof a rule applied. Proposed keys in old M0 reports are not an accepted universal schema. Current browser/CLI rule-path precedence is in OPERATIONS.

M8.2's retained 2026 evidence had common periods 15/16/17 (weeks 15,16,17-18), championship durations, but no future postseason rows or separate consolation-period field. An audited manual mapping bound the retained periods; retranslation/publish appended a new UUID without another ESPN refresh or changing prior snapshots. These numbers are historical context, not defaults. The source observation is Verified live for the retained response; mapping is separately approved configuration. [M8.2 source record](M8_2_REAL_LEAGUE_VALIDATION.md) remains intact; DATA owns this current interpretation, not its old explicit-browser-week recipe or numerical optimization chronology.

## Live and temporal evidence

The authorized 11 November 2026 **unplayed** observation also found seven matchup rows and 233 roster entries; candidate lineupLocked/rosterLocked/tradeLocked fields were Boolean false in all 1,061 player-pool and 233 roster-entry copies. Fourteen matchup sides exposed totalPoints=0, totalProjectedPoints and equal totalProjectedPointsLive; pointsByScoringPeriod and rosterForCurrentScoringPeriod.appliedStatTotal/entries were structurally present. These are **Verified live** presence/type/pregame observations only: active-game lock permission, live-final-versus-remainder meaning, latency/corrections, bench inclusion and multiweek accumulation remain **Unverified**. No live translator promotes these candidate fields.

A scoring week is completed only when every relevant game is explicitly final; unplayed only when every game is explicitly scheduled/not started; mixed scheduled/in-progress/completed is partial; missing/postponed/canceled/unsupported evidence is unresolved. Kickoff/wall clock, actual-record presence/absence and scores (including zero) prove none of completion, participation or fantasy settlement.

Ordinary V1 authorizes only the **current** explicitly unplayed week at the start of its independently supported matchup period. Canonical validation compares stored live membership to full source-backed matchup_period_configuration, retaining preceding weeks even when the simulation horizon omits them. next_fully_unplayed_period is diagnostic, never permission to skip current unsettled work. Manual override obeys the same invariant. Final NFL games still do not establish cumulative fantasy standings cutoff or stat-finality; earlier v4 lacking authority remains readable with its supported boundary suppressed/rejected by consumers.

Player observations keep actual points/source separate from full-game projections; remaining_projection/lineup_locked remain unavailable in live translation. No source observation establishes in-progress remainder, lineup-lock permissions, verified carry, fantasy settlement or stat-correction finalization. [Partial Week](PARTIAL_WEEK.md#current-capability-map) owns detailed validated companion/execution/composition rules, including fixed actuals plus remaining contributions exactly once. DATA does not authorize automatic live translation or new distributions.

## Immutable storage

[SnapshotStore](../src/fantasy_football/snapshot_store.py) stores one authoritative exact canonical JSON BLOB, not competing relational teams/players/rules. SQLite schema **1** contains store_metadata, snapshots (UUID/identity/times/schema/checksum/length/source count), canonical_documents (one per UUID), raw_responses (one per source ID/publication with context, compression/representation/digest/length/payload). Every connection enables foreign keys; update/delete triggers protect published rows. WAL and synchronous=FULL use SQLite commit/crash semantics.

`publish()` prepares everything before BEGIN IMMEDIATE: candidate snapshot_id must be None, assign fresh UUID (or validate explicit lowercase unique UUID), validate/serialize identified snapshot, reconcile exact source IDs/digests/metadata, round-trip canonical bytes, encode parsed raw mappings as deterministic_json_utf8 and gzip level 9 with mtime=0, decompress/check equality. SHA-256 covers exact UTF-8 canonical bytes including UUID; source hash agrees with CapturedResponse/SourceReference. No HTTP call occurs inside the write transaction. Insert complete metadata/document/sources and commit together; any pre-commit exception rolls back only that attempt. Identical content refreshes receive distinct retained publications.

`publish_and_verify()` separately reloads/verifies the committed UUID. A post-commit failure reports the permanent ID and distinct nonzero status, never rollback/deletion/retry. Earlier snapshots are neither overwritten nor hidden. Existing v2/v3/v4 rows/IDs/bytes/digests/raw evidence remain unchanged; new publication is v4. No in-place migration, deduplication, delete/update or snapshot-retention API exists. Application terminal-run deletion is another store.

`load(..., verify_sources=True)`/`verify()` check schema, unique metadata/document, canonical length/hash/validation, UUID/league/season/schema/retrieval agreement, exact source set/count/context, supported encoding/compression, decompression, uncompressed length/hash/reference equality and valid JSON/sanitized metadata. Internal verify_sources=False omits raw decompression/checksum verification, not canonical/source-row consistency checks; it is not full source verification. LoadedSnapshot.canonical_json returns original verified stored bytes. Successful hash checking establishes stored integrity, not independently authentic ESPN semantics.

Routine load/verify are snapshot-specific, not database-wide PRAGMA integrity_check. `check_database_integrity()` explicitly runs integrity_check and foreign_key_check; `require_database_integrity()` raises on either defect. Unrelated database corruption is distinct from requested-snapshot failure. No silent repair is performed.

`list_snapshots()` reads compact metadata/horizon without reconstructing/decompressing every snapshot, newest publication time then UUID descending, with optional league/season filters. `newest_metadata()` is metadata only. `snapshot_cli.select_snapshot()` gives an explicit canonical UUID precedence; invalid/missing/corrupt explicit selection never falls back. Without it, require league+season and fully load newest matching snapshot. CLI list/inspect/verify are read-only; `verify --database-wide` adds explicit diagnostics. Summary uses quality reporting and retrieval-based age without an implicit staleness threshold. Explicit --detail exposes selected canonical records, never raw response bodies. Private database paths/defaults/backups belong to OPERATIONS.

## Source observations and limitations

These are bounded historical observations, not newly executed checks or universal ESPN contracts:

| Observation/context | Classification and lasting limitation |
|---|---|
| 15 October 2026, private current 2026 league, week 6-14 pages: same 1,052 IDs; future ownership differed for 28 players | Verified live identity/pagination/projection availability. No independent total; future ownership never current authority. Missing/zero/bye remain distinct. |
| 17 October adapter: 97 players exposed eligible slot 25 absent configured capacities | Verified live raw namespace hazard. v2 corrected preservation, not extra playable capacity. Current fixture edge cases are Verified by tests. |
| 18 October undroppable: all 1,052 current records and 235 roster copies Boolean; 14 raw false, agreement over 11 future weeks | Verified live existence/type/coherence. Per-player raw false/true versus Can't Drop/Drop UI remains Unverified; espn-api exposure Unsupported. Do not promote inversion to understood merely from counts. |
| 2024/2025 completed seasons inspected in October 2026 | Verified live historical championship pairings/byes, multiweek sums and final-rank relationships for those source contexts, not a universal consolation template. Official ESPN rules investigated 21 October support even-field ladder movement; odd reentry remains Unverified. |
| 11 November 2026 live diagnostic: 136 past statsOfficial=true, 14 current false, 122 future false; all current IDs joined STATUS_SCHEDULED/pre/not-completed | Verified live game fields/join in that context. False alone not unplayed; schedule status path absent. |
| Same diagnostic, prior configured period 9: 688 source-0/split-1 actuals, 358 explicit zeros; current period 10 no actuals, 686 projections | Verified live weekly actual/projection fields. No participation/lock/settlement/finality proof. |
| Historical source-1/source-0 records and current scoring settings | Verified live retrieval, pregame timing and point-in-time player/scoring context Unverified; forecast vintages/revision sequence/horizon labels Unsupported. Research owns temporal authentication. |

Investigated espn-api 1.0.1 rounded/defaulted weekly appliedTotal (collapsing missing/zero), misaligned sparse position_slot_counts by zipping labels/values, ignored droppable, and used lineup-slot labels for a different default-position namespace. Current adapter parses raw records instead. These are recorded library limitations, not fresh version-wide verification. Full original counts/methods remain in immutable accepted Git history; no credentials/private individual examples are reproduced here.

## M0 consumer dependency

`python -m fantasy_football.m0_verification` remains an offline historical evidence/diagnostic-availability verifier, never a current ESPN compatibility or release-readiness certificate. The original disposition is GO_WITH_EXPLICIT_UNRESOLVED_METADATA. Its static unresolved-rule list is historical (some cases are subsequently resolved); provisional M0/M1 permission never authorizes later unsupported capabilities. Current ESPN projections/no unapproved horizon adjustments and capability-specific evidence gates remain binding under the owning contracts.

Evidence-role contract **2** below is executable metadata. Each of seven roles binds required authoritative sections to inspectable implementation definitions and, for the six retired sources, an immutable accepted Git reference plus SHA-256 of the original Git blob bytes at that revision. The verifier checks the exact role set/mapping/identity and declared evidence limits against its accepted contract, unique nonempty section anchors (excluding fenced examples), and Python definitions/annotated canonical fields without importing or running the listed diagnostic implementations. Keep the JSON block within this section; ordering/whitespace of records is immaterial. Changes to role ownership/interfaces or historical identities require a reviewed contract update, not an arbitrary prose phrase match.

Local checks establish section structure, declared evidence limits and implementation-definition availability, not full natural-language correctness or ESPN semantics. Historical **identity/reference** is checked against the recorded pin; the old source bytes are **not inspected or authenticated offline**. No network, Git command, repository history or fallback is used. A shallow/source-only checkout can run with the installed Python source available. Original reports can be inspected separately through the immutable citations, but the verifier never claims to have fetched or authenticated them. The missing-policy role now binds current Outcome Model and DATA sections. Its original dated report is an [immutable historical citation](https://github.com/tdkelley2001/fantasy_football/blob/4eea42d829e066ad9816e77399f09b9e28163de8/docs/MISSING_PROJECTION_POLICY.md), not a locally authenticated artifact; the verifier neither fetches it nor claims its complete bytes were inspected offline.

`evidence_documents` retains its meaning: the local files checked by this run, now DATA, RESEARCH and PLAYER_OUTCOME_MODEL. It no longer lists retired files as though locally present. All other existing report fields/meanings, CLI flags --project-root/--check-config/--json, default offline behavior, optional settings validation and failure exit 2 remain. Additive evidence_role_contract_version/evidence_roles expose section/interface checks and distinguish historical_identity_verified from historical_content_verified=False and not_inspected_or_authenticated_offline. Historical evidence_state/m1_gate/unresolved_rules and live_verification_performed=False are preserved. Diagnostic module availability is checked; reproduction commands are listed, never executed. Config failures are sanitized; detailed local exception values are not echoed. No credentials are required by default.

Contract 2 changes only checked-local-document membership and the seventh role's section mappings from contract 1. The role count, other six complete records, seventh canonical interfaces/evidence limits, historical identity/content status, report field meanings and JSON object shape are preserved. The numeric register schema_version and report evidence_role_contract_version are now 2; version-1 registers are rejected rather than silently interpreted under changed ownership. Callers pinning the old membership/version must update their expectation; this is not a new public report schema or numerical/snapshot version.

```json m0-evidence
{
  "schema_version": 2,
  "roles": [
    {
      "role": "connectivity",
      "sections": [
        "docs/DATA.md#retrieval-and-provenance",
        "docs/DATA.md#source-observations-and-limitations"
      ],
      "interfaces": [
        "fantasy_football.espn_connectivity:audit_league",
        "fantasy_football.espn_connectivity:PlayerOwnership"
      ],
      "historical_reference": "https://github.com/tdkelley2001/fantasy_football/blob/efa2e0599b4085feef20782b71b3f0b4e1a259c5/docs/ESPN_CONNECTIVITY.md",
      "historical_sha256": "fce1f7e584368c04867f47763e7bd6bf8fd561c8d0e0ce9eccdb93065cd96834",
      "evidence_limits": {
        "access": "read_only",
        "ownership": "current_roster_reconciled",
        "library_findings": "sparse_slots_and_signed_player_ids"
      }
    },
    {
      "role": "future_data",
      "sections": [
        "docs/DATA.md#retrieval-and-provenance",
        "docs/DATA.md#projection-contract",
        "docs/DATA.md#calendar-brackets-and-nfl-evidence"
      ],
      "interfaces": [
        "fantasy_football.future_data_audit:retrieve_player_pool",
        "fantasy_football.future_data_audit:parse_player_cards",
        "fantasy_football.future_data_audit:parse_pro_team_byes"
      ],
      "historical_reference": "https://github.com/tdkelley2001/fantasy_football/blob/efa2e0599b4085feef20782b71b3f0b4e1a259c5/docs/ESPN_FUTURE_DATA_AUDIT.md",
      "historical_sha256": "d981a8558ad8f3e4bb9373104dd0bb5bbe3e787d3ea3409cac51f24551e84fae",
      "evidence_limits": {
        "pagination": "complete_or_fail",
        "ownership": "current_week_only",
        "weekly_projection_source_split": "1/1",
        "missing_and_explicit_zero": "distinct",
        "bye": "explicit_source_only",
        "horizon": "currently_returned_projections"
      }
    },
    {
      "role": "league_rules",
      "sections": [
        "docs/DATA.md#roster-scoring-and-transaction-settings",
        "docs/DATA.md#rules-and-manual-authority",
        "docs/DATA.md#live-and-temporal-evidence"
      ],
      "interfaces": [
        "fantasy_football.league_rules_audit:audit_schedule",
        "fantasy_football.espn_adapter:load_manual_rule_config"
      ],
      "historical_reference": "https://github.com/tdkelley2001/fantasy_football/blob/efa2e0599b4085feef20782b71b3f0b4e1a259c5/docs/ESPN_LEAGUE_RULES_AUDIT.md",
      "historical_sha256": "73e8ceb1f73e20be62c66f051c65358109f006517ce2c2d0de9dbead3ac4ddc3",
      "evidence_limits": {
        "rule_authority": "dynamic_source_or_audited_manual",
        "ties": "dated_ui_confirmation_not_universal",
        "bracket": "source_specific",
        "unresolved": "capability_specific_fail_closed"
      }
    },
    {
      "role": "historical_projections",
      "sections": [
        "docs/RESEARCH.md#evidence-and-hypotheses",
        "docs/RESEARCH.md#external-trust-and-exact-row-binding",
        "docs/RESEARCH.md#coverage-and-leakage",
        "docs/RESEARCH.md#metrics-and-promotion"
      ],
      "interfaces": [
        "fantasy_football.historical_projection_audit:parse_historical_player_page",
        "fantasy_football.historical_projection_audit:scoring_signature",
        "fantasy_football.historical_dataset:validate_pregame_capture_manifest"
      ],
      "historical_reference": "https://github.com/tdkelley2001/fantasy_football/blob/efa2e0599b4085feef20782b71b3f0b4e1a259c5/docs/ESPN_HISTORICAL_PROJECTION_AUDIT.md",
      "historical_sha256": "d05581849b97cf133c1a64ed20019d3fe01e77b02653ab96813710478509d15c",
      "evidence_limits": {
        "pregame_provenance": "Unverified",
        "forecast_vintages": "Unsupported",
        "capture_authentication": "independent_manifest_payload_and_row_binding",
        "scoring_sampling_revision": "limitations_retained",
        "promotion": "independent_review_required"
      }
    },
    {
      "role": "data_dictionary",
      "sections": [
        "docs/DATA.md#identity-rosters-and-player-weeks",
        "docs/DATA.md#canonical-validation-and-serialization"
      ],
      "interfaces": [
        "fantasy_football.canonical.model:SourceReference.payload_sha256",
        "fantasy_football.canonical.model:PlayerWeek.raw_projection",
        "fantasy_football.canonical.model:PlayerWeek.projection_class",
        "fantasy_football.canonical.validation:validate_snapshot",
        "fantasy_football.canonical.validation:require_understood_rules"
      ],
      "historical_reference": "https://github.com/tdkelley2001/fantasy_football/blob/efa2e0599b4085feef20782b71b3f0b4e1a259c5/docs/ESPN_DATA_DICTIONARY.md",
      "historical_sha256": "9e9e4ee895df6a73f37127a6b8513ea4a8cccb6eb9c89ea7e837cd731623a7f7",
      "evidence_limits": {
        "namespaces": "position_separate_from_lineup_slot",
        "vocabulary": "implemented_not_historical_proposal",
        "provenance": "source_identity_and_digest",
        "structural_validity": "not_capability_permission"
      }
    },
    {
      "role": "m0_handoff",
      "sections": [
        "docs/DATA.md#m0-consumer-dependency",
        "docs/DATA.md#projection-contract",
        "docs/RESEARCH.md#metrics-and-promotion"
      ],
      "interfaces": [
        "fantasy_football.m0_verification:build_report"
      ],
      "historical_reference": "https://github.com/tdkelley2001/fantasy_football/blob/efa2e0599b4085feef20782b71b3f0b4e1a259c5/docs/M0_FEASIBILITY_AND_M1_HANDOFF.md",
      "historical_sha256": "eb1d1e1ec2f186f11c7a674287253850868cf5be017a7dd777023066a1320cb2",
      "evidence_limits": {
        "disposition": "GO_WITH_EXPLICIT_UNRESOLVED_METADATA",
        "live_verification": false,
        "future_capabilities": "not_authorized_by_M0",
        "projection_basis": "current_no_unapproved_horizon_adjustment",
        "collection": "optional_not_prerequisite"
      }
    },
    {
      "role": "missing_projection_policy",
      "sections": [
        "docs/PLAYER_OUTCOME_MODEL.md#missing-zero-and-present-projections",
        "docs/PLAYER_OUTCOME_MODEL.md#identity-and-compatibility",
        "docs/DATA.md#projection-contract",
        "docs/DATA.md#identity-rosters-and-player-weeks"
      ],
      "interfaces": [
        "fantasy_football.canonical.model:ProjectionClass",
        "fantasy_football.canonical.model:ProjectionSource",
        "fantasy_football.canonical.model:PlayerWeek.effective_projection"
      ],
      "historical_reference": null,
      "historical_sha256": null,
      "evidence_limits": {
        "raw_missing": "null",
        "classification": "missing",
        "effective_zero_source": "missing_projection_policy",
        "explicit_zero_source": "espn",
        "modeled_missing_outcome": "deterministic_zero"
      }
    }
  ]
}
```

Connectivity preserves read-only identity/ownership and library sparse-slot/signed-ID findings; future-data covers pagination/current authority/raw weekly matching/missing-zero/bye coverage; league-rules preserves settings/ties/bracket/manual provenance and gaps. Historical-projections binds vintage/scoring/selection/revision limitations to RESEARCH; dictionary binds implemented namespaces/provenance and structural-versus-capability validation. Handoff preserves the original provisional disposition/no-horizon assumptions and ongoing gates; the seventh role preserves the current missing policy. The source observations retain their original dates/classifications, not a fresh live verification. [BACKLOG](BACKLOG.md#data-research-and-m0-migration-obligations) retains future evidence gates and the independent review requirement.

## Source and verification

Source: [adapter](../src/fantasy_football/espn_adapter.py), [canonical model](../src/fantasy_football/canonical/model.py), [validation](../src/fantasy_football/canonical/validation.py), [serialization](../src/fantasy_football/canonical/serialization.py), [quality](../src/fantasy_football/quality.py), [store](../src/fantasy_football/snapshot_store.py), [inspection](../src/fantasy_football/snapshot_cli.py), [live resolver](../src/fantasy_football/live_scoring.py), [M0 utility](../src/fantasy_football/m0_verification.py). Tests cover canonical/schema, adapter/pagination/manual/live, storage/CLI/integrity, quality, league discovery, historical parsing and M0. Use [CONTRIBUTING](../CONTRIBUTING.md#change-based-verification-matrix) for exact verification selection; PRs own actual commands/results. No D5 live retrieval or source-class promotion is claimed. D4 mechanics findings remain in Transactions/BACKLOG; no new assumption fills them here.
