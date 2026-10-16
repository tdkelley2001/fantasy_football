# M0.2 ESPN Connectivity and League Inspection

Status: **COMPLETE** on 15 October 2026. This is a sanitized discovery record. It intentionally excludes credentials, raw cookies, league and team names, manager IDs, and player IDs.

## Scope and access method

The diagnostic uses `espn-api` 1.0.1 because it is a maintained Python client that exposes the league, team, roster, standings, and settings records needed by M0.2. Authentication uses the M0.1 configuration loader and passes `ESPN_S2` and `ESPN_SWID` only to the library request client. No authentication value is logged or included in a report.

The read-only league endpoint observed during live verification was:

```text
GET https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}
```

The request uses the `mTeam`, `mRoster`, `mMatchup`, `mSettings`, and `mStandings` views. `espn-api` also performs its normal read-only player and draft-detail requests while constructing a football `League`; M0.2 does not use those responses to implement projection, free-agent, draft, waiver, or postseason behavior.

## Field provenance

| Information | ESPN source field | Diagnostic representation | Classification |
|---|---|---|---|
| League identity | Configured ID and `League.league_id` | `league_id` | Verified direct value |
| Season | Configured season and `League.year` | `season` | Verified direct value |
| League name | `settings.name` | `league_name` | Verified direct value |
| Metadata team count | `settings.size` via `Settings.team_count` | `reported_team_count` | Verified direct value |
| Fetched teams | `teams[]` | `teams` | Verified direct records |
| Stable team ID | `teams[].id` via `Team.team_id` | `team_id` | Verified direct value |
| Team name | `teams[].name`, or ESPN location/nickname fields | `team_name` | Verified direct value |
| Manager identifier | Team owner references joined to `members[].id` by `espn-api` | `manager_ids` | Verified direct identifier; display names omitted |
| Standings and record | `teams[].playoffSeed` and `teams[].record.overall` | standing, W/L/T and PF | Verified direct values |
| Roster ownership | `teams[].roster.entries[]` and player `onTeamId` | team/player ownership records | Verified direct relationship |
| Stable player ID | Roster-entry player `id` | `player_id` | Verified direct value; negative IDs are valid for team defenses |
| Player eligibility | player `eligibleSlots` and `lineupSlotId` | eligible/current lineup slots | Verified direct values through `espn-api` mappings |
| Configured roster slots | `settings.rosterSettings.lineupSlotCounts` | `position_slot_counts` | Verified raw ESPN slot IDs mapped through `POSITION_MAP` |
| Scoring | `settings.scoringSettings.scoringItems` | `scoring_format` | Verified direct items through `espn-api` labels |
| Observed counts and uniqueness | The direct records above | observed team/player counts | Derived validation result |

## Live validation results

The configured 2026 target league passed the M0.2 gate:

- 14 teams expected explicitly by the diagnostic command.
- 14 teams reported by ESPN league metadata.
- 14 distinct team records fetched, with unique stable team IDs and standings positions.
- 233 distinct rostered player IDs, each observed on exactly one roster.
- Every rostered player's `onTeamId` agreed with the containing roster's team ID.
- Every rostered player exposed a current lineup slot and at least one eligible slot.
- 15 manager identifiers were available across 14 teams; no manager display names are retained in this document.
- Nine configured, nonzero roster-slot types were mapped from raw ESPN slot IDs.
- 39 scoring items were returned with IDs, labels, abbreviations, and numeric point values.
- Current team roster sizes ranged from 16 to 17 players.

The report requires `--expected-team-count 14`; the league size is not hidden in source logic. A mismatch among the explicit expectation, ESPN metadata, or fetched records is a blocking error.

## Validation and error behavior

The diagnostic fails explicitly for:

- authentication or authorization rejection;
- invalid league identity or season;
- connection and ESPN HTTP failures;
- malformed or unsupported response structures;
- missing required settings, scoring, roster, identity, standings, or eligibility fields;
- inconsistent team counts;
- duplicate team IDs or standings positions;
- duplicate player ownership or disagreement with `onTeamId`;
- configured lineup-slot IDs without a verified mapping.

Automated tests use in-memory sanitized objects and monkeypatched failures. They require no live credentials. The final clean-environment run passed 26 tests, including negative cases for authentication, connectivity, malformed responses, team-count mismatch, duplicate team IDs, duplicate ownership, ownership mismatch, missing eligibility, missing scoring, and unknown configured slot IDs.

## Missing or inaccessible information

No required M0.2 field was missing or inaccessible in the live run. This statement applies only to the bounded M0.2 scope; it is not evidence that later projection, waiver, schedule, tiebreak, or postseason fields are complete or correctly interpreted.

## Findings requiring further investigation

1. `espn-api` 1.0.1 derives `Settings.position_slot_counts` by zipping labels to the values of ESPN's sparse `lineupSlotCounts` map. The live response exposed an empty/misaligned label. The diagnostic therefore reads the raw slot-ID map, ignores only explicit zero-count slots, and fails if a configured nonzero slot lacks a known mapping. M1 must not use the defective derived dictionary.
2. ESPN uses negative stable IDs for team-defense players. Canonical identity validation must accept nonzero signed player IDs rather than requiring all player IDs to be positive.
3. Live roster sizes varied between 16 and 17. Whether these are ordinary vacancies, injury-reserve effects, or another roster-state detail must be established during the M0.3/M0.4 audits before defining canonical capacity rules.
4. Future player-week projections, the free-agent pool, bye and schedule semantics remain M0.3 work.
5. Standings tiebreak semantics, waiver behavior, and postseason/consolation structure remain M0.4 work.

## Usage

Human-readable inspection:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.espn_connectivity --expected-team-count 14
```

Complete JSON inspection, including rostered player IDs:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.espn_connectivity --expected-team-count 14 --json
```

Live reports contain current league details and must not be committed. The diagnostic performs only GET requests and does not submit ESPN transactions or mutate league state.
