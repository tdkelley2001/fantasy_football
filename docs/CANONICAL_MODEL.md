# Canonical Snapshot Contract — Schema Version 1

## Scope

M1.1 defines the immutable ESPN-independent contract between future ingestion, persistence, and simulation. It does not fetch ESPN data, persist snapshots, allocate snapshot IDs, compile simulation arrays, or implement league behavior.

The implementation is in `src/fantasy_football/canonical/` and uses frozen, slotted Python dataclasses and tuples. Records are deliberately flat and joined by stable identifiers. `LeagueSnapshot` is the logical container, not an ESPN response mirror. The current serialized contract is schema version 2.

Schema v2 adds immutable `LineupSlotNamespace.observed_slot_ids`, derived from the exact union of raw player eligibility evidence. This namespace is distinct from `LeagueRules.lineup_slots`, which contains only ESPN-configured capacities. An observed but unconfigured category such as slot 25 remains preserved but is not a legal roster destination. Occupied slots must have positive configured capacity and appear in the player's raw eligibility. Schema-v1 JSON is intentionally incompatible and rejected because it cannot express this distinction.

## Entities and keys

| Entity | Identity / role |
|---|---|
| `LeagueSnapshot` | Schema version, optional externally allocated snapshot ID, league ID/name and season identity, retrieval interval, explicit simulation horizon, rules, records, provenance, gaps, and validation metadata |
| `LeagueRules` | League-agnostic grouping of scoring, roster, acquisition, trade, standings, championship, consolation, and interpreted raw rules |
| `FantasyTeam` | Positive fantasy-team ID plus present cumulative standings, optional seed/rank/waiver/division state |
| `Player` | Signed nonzero player ID, default-position ID, eligible raw lineup-slot IDs, current NFL team/injury/acquisition state |
| `RosterEntry` | The only authoritative ownership relationship: player ID → team ID and occupied lineup-slot ID |
| `PlayerWeek` | Composite key `(player_id, season, scoring_week)` and the raw/effective projection contract |
| `MatchupPeriod` | Positive matchup-period ID mapped to ordered scoring weeks and only a `regular` or `postseason` calendar phase |
| `FantasyMatchup` | Positive matchup ID, period ID, bracket classification, zero-to-two known sides, and explicit scheduled/bye/partial/placeholder state |
| `NFLTeam` | Positive NFL-team ID and optional bye week; player NFL-team ID zero is a separate unassigned sentinel |
| `NFLGame` | Source game ID, scoring week, two NFL-team IDs, and optional UTC kickoff |
| `SourceReference` | Stable request/reference ID, HTTPS endpoint, raw view, parameters, UTC retrieval time, optional SHA-256 payload digest |
| `RuleInterpretation` | Raw field/value, optional normalized meaning, evidence status, source, and optional audited manual configuration provenance; values may be JSON scalars or immutable structured JSON |
| `RuleGap` | Named unresolved gap, reason, affected future capabilities, source, and whether audited manual configuration is permitted |

Default-position IDs and lineup-slot IDs remain separate namespaces even where their integers happen to overlap. Player IDs may be negative; zero is invalid. NFL team ID zero is allowed only on `Player` as the unassigned sentinel and is never interpreted as a bye.

## Ownership and current state

`RosterEntry` is the single authoritative ownership table. `Player` contains current acquisition status but no owner. A player without a roster entry is unrostered, though their acquisition status may still be `WAIVERS`, unavailable, or another raw state rather than immediately free.

Recognized current ESPN states are reconciled with that table: `ONTEAM` requires a roster entry, while `FREEAGENT` and `WAIVERS` require no owner. Unknown acquisition enums are retained without guessed semantics and do not invalidate an otherwise coherent snapshot. A populated raw owner on a roster entry must agree with its authoritative team ID.

The snapshot begins from cumulative current standings and current rosters. It explicitly stores `first_simulation_week` and `final_simulation_week`; it does not derive the first safe week from the wall clock. Every included player must have exactly one `PlayerWeek` for every required week in that inclusive range. Completed historical weeks and transaction history are outside the operational snapshot contract.

## Projection contract

| Raw record | Classification | Effective value | Effective source | Projected-lineup available |
|---|---|---:|---|---|
| Missing | `missing` | `0` | `missing_projection_policy` | No |
| Present and exactly zero | `explicit_zero` | `0` | `espn` | No |
| Present and positive | `present` | exact raw value | `espn` | Yes |
| Present and negative | `present` | exact raw value | `espn` | No |

Availability is derived as `effective_projection > 0`; no redundant boolean is stored. Raw and effective values must be finite. Values are neither rounded nor clamped. This availability rule does not constrain future realized fantasy scores, which may be negative when the later outcome model permits them.

## Rule interpretation

Allowed evidence states are `understood`, `unverified`, `unsupported`, and `missing`. An understood record requires a normalized interpretation. A missing record cannot contain a raw or normalized value. Unverified and unsupported records preserve valid raw source data without inventing an operational meaning.

Manual configuration provenance is all-or-nothing: configuration key, approval reference, and audited gap ID must be present together, the gap must exist, and it must permit manual configuration. The canonical snapshot may contain unresolved rules. `require_understood_rules(snapshot, rule_ids)` is the deliberately small boundary a future simulator capability can invoke; it is not a capability-permission framework.

Rule values use ordinary JSON scalars when sufficient. Structured evidence uses frozen `JsonArray` and `JsonObject` records; arrays retain order (for example, ordered tiebreaks), while object keys use canonical increasing order. Nested strings, numbers, Booleans, nulls, arrays, and objects round-trip deterministically. Mutable containers, duplicate or unordered object keys, unsupported values, and nonfinite nested numbers fail validation. Illustrative fixture structures are test evidence only, not verified current-league rules.

## Matchup calendar and bracket entries

`MatchupPeriod` is a calendar relationship, not a bracket classification. It maps scoring weeks to either the regular season or postseason. Championship, consolation, placement, and unresolved bracket entries may coexist in one postseason period through each `FantasyMatchup.bracket_type`; round numbers remain on the corresponding championship or consolation rule records.

`FantasyMatchup.entry_status` distinguishes a scheduled two-team matchup, a one-team bye, a one-known-team partial future pairing, and a zero-known-team placeholder. Regular-season operational periods require complete scheduled pairings for every team. Postseason periods permit explicit partial and placeholder entries so the snapshot never fabricates future participants. Known teams remain unique within a period, and unknown IDs, self-pairings, mismatched status/participant counts, or bracketless postseason entries are contradictions.

## Validation boundary

`validate_snapshot` is pure, deterministic, and non-mutating. Snapshot-acceptance invariants include:

- supported schema version and coherent league/season/horizon identity;
- timezone-aware UTC retrieval ordering and source timestamps inside the retrieval interval;
- unique team, signed player, source, matchup, period, NFL-team, NFL-game, scoring-rule, slot, interpretation, and gap IDs;
- one authoritative owner per player and valid team/player/slot references;
- occupied slot and position counts within dynamically supplied capacities/limits;
- eligible-slot references in the lineup-slot namespace;
- complete player-week horizon coverage and exact raw/class/effective/source relationships;
- finite scoring, standings, projection, and override numerics;
- matchup periods that cover every required scoring week exactly once;
- complete ordinary regular-season pairing coverage, while allowing explicitly classified postseason byes, partial entries, and zero-participant placeholders;
- concurrent championship, consolation, and placement entries in the same postseason period without conflating the calendar with a bracket;
- dynamically configured postseason round references without assuming a league shape;
- valid NFL references, at most one game per team/week, and exactly one game-or-bye state per required week;
- source references for projection and rule evidence; and
- structurally coherent interpretation and manual-configuration records.

Failures identify the entity, identifier, field, and invariant. Validation never fills a value, changes an enum, assigns an owner, creates a matchup, or supplies a rule default.

An unresolved consolation ladder or tie rule is valid canonical metadata. It blocks only future behavior that explicitly requires the missing meaning. Invalid references, duplicate ownership, malformed projection provenance, and contradictory bye/game records invalidate the snapshot itself.

## Serialization

`snapshot_to_json` and `snapshot_from_json` implement schema version `1`:

- JSON is indented, human-readable, and ends with a newline;
- object keys and all identity-bearing record collections have deterministic ordering;
- timestamps serialize as ISO-8601 UTC strings ending in `Z`;
- null, explicit numeric zero, negative IDs, negative projections, raw enums, gaps, and evidence states round-trip unchanged;
- JSON nonfinite numbers are prohibited;
- deserialization reconstructs typed immutable records and performs full validation; and
- any schema version other than `1` fails explicitly.

This is an interchange contract only. SQLite tables, compressed raw payload storage, transactionality, publication, checksums of the entire canonical document, migrations, and snapshot-ID allocation remain M1.3.

## Representative fixture and tests

`tests/canonical_fixtures.py` defines a sanitized four-team snapshot with:

- owned and unrostered players;
- a signed negative D/ST ID;
- positive, explicit-zero, missing, and finite-negative projections over three future weeks;
- a regular matchup and a two-week championship period;
- two NFL byes and complete relevant NFL game coverage;
- concurrent championship/consolation entries, an unresolved placement placeholder, unsupported structured consolation evidence, ordered structured tiebreak evidence, and an unverified regular matchup tie rule; and
- request provenance and a raw payload digest placeholder.

An alternate fixture test removes IR and adds multiple flex slots, demonstrating that the validator does not impose the current league's roster template.

## Deferred work

M1.2 must map verified raw ESPN sources into these contracts and supply sanitized adapter fixtures. M1.3 must design SQLite storage, compressed raw payload retention, staged validation, immutable atomic publication, schema migrations, canonical checksums, and snapshot identity allocation. Neither work package is implemented here.

The exact production display-name privacy policy and which raw payload fragments remain queryable versus compressed are persistence/adapter design questions. They do not alter the current entity keys or validation contract.

M1.2 live translation identified one contract issue requiring review: ESPN player eligibility includes raw lineup-slot ID 25 even though the league's `lineupSlotCounts` mapping contains only IDs 0–24. Schema v1 currently has no separate lineup-slot namespace registry, so it cannot preserve the eligibility ID without either dropping evidence or inventing a configured capacity. The adapter fails explicitly. A separate immutable known/observed lineup-slot ID set is the recommended targeted amendment; it has not been implemented pending approval.
