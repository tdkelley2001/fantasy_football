# ESPN League Rules Audit (M0.4)

## Scope and evidence

This document records a read-only audit performed on 2026-10-16 against the configured private league's 2026 season and completed 2024 and 2025 seasons. The executable diagnostic is `python -m fantasy_football.league_rules_audit --expected-team-count 14 --historical-season 2024 --historical-season 2025`. The expected count is an optional identity check only. It emits only sanitized aggregates; raw private responses, credentials, manager identities, player identities, and transaction details are not persisted.

The access path is `espn-api` 1.0.1 for authentication and its `get_league()` read-only request to `lm-api-reads.fantasy.espn.com`, using the `mTeam`, `mRoster`, `mMatchup`, `mSettings`, and `mStandings` views. The rule values below are raw ESPN fields unless a transformation is stated. `espn-api` constructs convenient league objects, but the audit parses the raw response because several required settings are absent from or ambiguously transformed by the library.

Evidence labels retain their established meaning: **Verified live** was observed in the actual league response; **Verified by tests** means only the parser behavior is established; **Unverified** needs more evidence; **Unsupported** was not available from the investigated source.

## Rule inventory

| Rule / intended use | Raw endpoint field | Observed value (sanitized) | Type | Interpretation and transformation | Evidence | Sufficient? / manual input / impact |
|---|---|---:|---|---|---|---|
| Starting lineup | `settings.rosterSettings.lineupSlotCounts` | QB 1, RB 2, WR 2, TE 1, FLEX 1, D/ST 1, K 1 | map keyed by raw slot ID | Our code validates IDs 0,2,4,6,23,16,17 and sums nine starters. No library sparse-slot map is used. | Verified live | Yes for capacity; M1 must retain raw IDs. |
| Bench and IR | same, raw IDs 20 and 21 | BENCH 7; IR 1 | integer counts | Sixteen ordinary places plus one distinct IR place. IR is not treated as bench. | Verified live | Yes for capacity. |
| Current roster discrepancy | `teams[].roster.entries[].lineupSlotId` | total 16–17; ordinary 15–16; ten occupied IR slots; one ordinary vacancy | entry list / integer | Our code counts slot 21 separately. This fully explains M0.2's 16–17 range. | Verified live | Yes. |
| IR eligibility/status | `playerPoolEntry.player.eligibleSlots`, `injuryStatus` | IR occupants: 8 IR, 1 OUT, 1 QUESTIONABLE; all include slot 21 | array / enum | OUT or IR permits placement; ESPN support says a player later changed to questionable may remain there. Current state alone does not mean questionable players can initially enter IR. | Verified live + [ESPN IR guidance](https://support.espn.com/hc/en-us/articles/115003849911-Players-on-Injured-Reserve-IR) | Sufficient for current state; future legality must evaluate ESPN status transitions. |
| Position limits | `rosterSettings.positionLimits` | QB 4, RB 8, WR 8, TE 3, K 3, D/ST 3 | map keyed by default-position ID | Raw IDs are the default-position namespace, not lineup-slot IDs. `-1` means no configured cap for other IDs; no fallback is supplied. | Verified live | Yes after M1 preserves the namespaces. |
| Undroppable list | `rosterSettings.isUsingUndroppableList`; player-pool and roster `player.droppable` | enabled; complete Boolean player coverage | League Boolean and separate player Boolean; `espn-api` ignores the player field, so repository audit reads raw JSON | **Verified live** for paths/types/coverage; player-value-to-UI correlation **Unverified** | Schema-v3 proposal and exact counts are in `ESPN_UNDROPPABLE_AUDIT.md`; automatic drops require conservative unknown handling. |
| Locks and moves | `lineupLocktimeType`, `rosterLocktimeType`, `moveLimit` | `INDIVIDUAL_GAME`, `INDIVIDUAL_GAME`, `-1` | enums / integer | Per-player game locks; no configured move limit. | Verified live | Yes for exposed setting; postseason override not observed. |
| Waiver system | `acquisitionSettings.acquisitionType`, `isUsingAcquisitionBudget` | `WAIVERS_TRADITIONAL`, false | enum / bool | Standard priority waivers, not FAAB. Budget 100 and minimum bid 1 are inert in this mode and must not imply FAAB. | Verified live + [ESPN waiver overview](https://support.espn.com/hc/en-us/articles/360000041152-Waivers-Overview) | Yes for system selection. |
| Current waiver order | `teams[].waiverRank` | unique permutation 1–14 | integer | Mutable current priority state. Our code validates completeness and uniqueness. | Verified live | Yes for a snapshot; it is not a rule. |
| Waiver reset | `waiverOrderReset` | true | bool | Official guidance describes weekly inverse-standings reset versus persistent move-to-last. The raw Boolean plus current order supports weekly reset; successful claims still move a team last. | Verified live + [ESPN waiver-order guidance](https://support.espn.com/hc/en-us/articles/360000093771-Waiver-Order-Overview-and-Salary-Cap-Tiebreakers) | Mostly; precise multi-claim ordering remains manual/blocking. |
| Processing window | `waiverHours`, `waiverProcessDays`, `waiverProcessHour` | 24; Mon/Wed/Thu/Fri/Sat/Sun; raw hour 11 | integer / enum list | One-day waiver delay and configured processing days are direct. Raw hour timezone/encoding is not documented by the response. | Verified live; hour semantics Unverified | `waivers.process_timezone` requires UI/behavior verification before time-sensitive simulation. |
| Acquisition limits | `acquisitionLimit`, `matchupAcquisitionLimit` | -1, -1.0 | numeric sentinel | No configured season or matchup acquisition cap. | Verified live | Yes. |
| Free agent versus waiver | player-pool `status`; acquisition settings | `FREEAGENT` and `WAIVERS` both observed in M0.3 | enum | Status is mutable player state; standard-waiver behavior is documented by ESPN. | Verified live | Yes at snapshot time. Dropped-player reentry timing beyond 24 hours remains unverified. |
| Trade deadline/limit | `tradeSettings.deadlineDate`, `max` | 2026-12-02 17:00 UTC; -1 | epoch ms / integer | Our code converts epoch milliseconds to UTC; no trade limit. | Verified live + [ESPN deadline guidance](https://support.espn.com/hc/en-us/articles/360000097472-Trade-Deadline) | Yes. |
| Trade review/veto | `revisionHours`, `vetoVotesRequired` | 24 hours; 8 votes | integers | Direct thresholds; the response does not name league-vote versus LM review. Two trade-counter entries prove trades operate, not the review workflow. | Verified live; workflow Unverified | `transactions.trade_review_type` required if modeled; noncritical to season simulation unless trades are simulated. |
| Standings records | `teams[].record.overall` | 14 complete W/L/T, PF, PA records | numeric fields | Direct current records; missing and zero remain distinct. | Verified live | Yes. |
| Divisions | league settings / team division IDs | one division | integer relationship | No division-winner seeding effect exists in this league's current structure. | Verified live | Yes. |
| Seeding tiebreak | `scheduleSettings.playoffSeedingRule` | `TOTAL_POINTS_SCORED` | enum | Points for is the configured first seeding tiebreak. Four current equal-record groups provide observational consistency, not proof of every deeper tie step. ESPN notes LM leagues can customize the sequence. | Verified live + [ESPN tiebreak guidance](https://support.espn.com/hc/en-us/articles/4669389557140-Regular-Season-Tiebreakers) | First rule yes; deeper sequence requires UI/config verification. |
| Matchup ties | `scoringSettings.matchupTieRule` | `NONE` | enum | The raw API value was observed during M0.4. On 2026-10-18, the owner directly confirmed in the ESPN settings UI that `None` allows a tied final score and awards neither side a win or loss. | Verified live raw value + owner UI confirmation | Sufficient for `NONE`; alternate configured policies remain unsupported until their required score inputs and behavior are implemented. |
| Championship qualification | `playoffTeamCount`, `matchupPeriodCount` | six qualifiers; regular season through week 14; playoffs start week 15 | integers | Direct settings. | Verified live | Yes. |
| Championship rounds | `playoffMatchupPeriodLengthByRound`, `matchupPeriods` | 1, 1, 2 weeks; final is weeks 17–18 | maps | Direct current settings. Historical 2024/2025 final rows corroborate two-week aggregate behavior. | Verified live | Yes. |
| Byes and reseeding | six-team bracket, `playoffReseed` | two byes; false | derived count / bool | Two historical bye rows in both completed seasons verify seeds 1–2 receive byes. Historical pairings were fixed rather than reseeded. | Verified live (historical) | Strong evidence, but current 14-team bracket rows have not materialized. |
| Playoff matchup tie | `playoffMatchupTieRule` | `NONE` | enum | On 2026-10-18, the owner directly confirmed that ESPN advances the higher seed after a tied playoff matchup. A discretionary LM advancement override is possible but intentionally outside the model. | Verified live raw value + owner UI confirmation + [ESPN playoff tie guidance](https://support.espn.com/hc/en-us/articles/4669390376852-Playoff-Scoring-Tiebreakers) | Sufficient for future M2.4 tie advancement; not executed in M2.2. |
| Placement games | historical `schedule` and final standings | championship, 3rd-place, and 5th-place rows observed | schedule relationships | Observed in both completed 12-team seasons. | Verified live (historical) | Yes for six-team championship component. |
| Consolation enabled | `consolationLadderDisabled` | false | bool | A consolation ladder is enabled. | Verified live | Enablement plus the official rules below supports first-round construction. |
| Consolation structure | ESPN official playoff rules plus historical schedule | all non-qualifiers; adjacent-seed first round; lowest-seed bye when odd; winners move up and losers down without elimination | documented rules / schedule relationships | The general ladder and first round are official. The prose does not uniquely establish every later-round position transition. | Officially verified general behavior; later mapping unresolved | M2.4 supports initialization and requires explicit validated configuration for later transitions. |

## Roster reconciliation and operational constraints

The configured ordinary roster is nine starters plus seven bench places. Slot 21 adds one separate IR place, for a maximum of 17 only when IR is occupied. At retrieval, ten teams used IR, three 16-player teams had all 16 ordinary places and empty IR, and one 16-player team had 15 ordinary players plus an IR occupant. Thus no alternative reserve mechanism is needed to explain the M0.2 observation.

ESPN's current guidance permits OUT and IR players to enter IR and permits a player whose status later becomes questionable or doubtful to remain. A healthy player in IR can invalidate additions, and a claim can fail if roster capacity changes before processing ([ESPN waiver/IR behavior](https://support.espn.com/hc/en-us/articles/360060240712-How-does-the-Injured-Reserve-Injury-List-impact-Waivers)). The future engine must model this as transaction legality, not reinterpret IR as an eighth bench slot.

## Waiver, transaction, and standings conclusions

This league uses traditional waivers. `waiverOrderReset=true`, official ESPN documentation, and current ranks support weekly inverse-standings reset followed by move-to-last on a successful claim; free-agent pickups do not change priority. Exact ordering for multiple contingent claims from one manager and the raw processing-hour timezone remain unresolved. These actual rules apply to path-dependent essential acquisitions. They do not replace the master specification's separate deterministic pre-simulation roster-completion procedure or later actionable waiver recommendations.

The raw trade settings establish the deadline, 24-hour review duration, eight-vote threshold, and no trade-count limit. Two team trade counters were observed. The audit did not fetch pending offers, votes, or manager-level transaction details. Add/drop positional limits use the raw `positionLimits`; IR and total-capacity legality also apply.

The current league is H2H points with one division, and ESPN supplies W/L/T, PF, PA, and a complete 1–14 seed permutation. `TOTAL_POINTS_SCORED` directly verifies points for as the selected first seeding tiebreak. It does not establish every subsequent tiebreak. The 2026-10-18 owner UI review resolved the current league's regular and playoff tie meanings without changing the earlier raw-API evidence classification.

## Championship and consolation evidence

Current settings verify six qualifiers, two first-round byes, no reseeding, rounds of one, one, and two weeks, and a weeks 17–18 final. Completed 2024 and 2025 seasons each had 12 teams but the same six-team championship settings. Both produced 19 postseason schedule rows across periods 15–17, two home-only bye rows, fixed bracket progression, championship/third/fifth placement games, and six two-week period-17 rows spanning weeks 17–18.

On 21 October 2026, the official [ESPN Fantasy Football playoff rules](https://www.espn.co.uk/fantasy/football/ffl/story?page=fflrulesplayoffs) verified that all non-qualifiers enter the Consolation Ladder, first-round opponents are adjacent in descending seed order, the lowest seed receives a bye for an odd population, winners move up, losers move down, boundary teams cannot move beyond the ladder, and participants continue throughout the postseason. For the current 14-team/six-qualifier configuration this establishes 7–8, 9–10, 11–12, and 13–14 with no bye. It does not uniquely specify the complete later-round transition graph, so those transitions still require reproducible schedule evidence or approved explicit configuration.

## Manual configuration gaps

These keys are proposals for later review, not a production schema or defaults:

| Proposed key | Allowed value | Why needed / verification | Blocks authoritative simulation? |
|---|---|---|---|
| `waivers.claim_processing_order` | Explicit ordered procedure for multiple claims and priority movement | Confirm in ESPN league UI/help or observe sanitized completed-claim sequences. ESPN state remains authoritative; conflict must fail. | Yes for path-dependent waivers |
| `waivers.process_timezone` | IANA timezone verified for raw hour 11 | Compare UI-displayed processing time and execution timestamps. | Only for time-of-day simulation |
| `transactions.trade_review_type` | `league_vote`, `commissioner`, or `none` | Confirm league settings UI; raw threshold alone is insufficient. | No unless trades are modeled |
| `standings.secondary_seeding_tiebreaks` | Ordered verified list | Confirm LM playoff settings. | Yes when the first tiebreak remains tied |
| `postseason.consolation_ladder` | Participants, seed mapping, pairings, round scoring periods, advancement, placement mapping | Export/inspect the 2026 bracket once available or supply league-approved rules. | Yes |

Later reconciliation must compare every manual value with retrievable ESPN evidence and fail on conflict. Absence never activates a guessed default.

## Tests and limitations

The diagnostic has credential-free positive, negative, and adversarial coverage for malformed/missing roster settings, over-capacity rosters, duplicate teams, unknown waiver enums, missing/duplicate priorities, invalid playoff counts and durations, duplicate seeds, missing consolation metadata, unknown historical team references, contradictory pairings, and absent historical postseason evidence. It reports unresolved states in the result rather than constructing rules.

M0.3's original completion remains 47 passing tests. The projection-UI and missing-policy follow-up raised the suite to 55. M0.4 adds finite-projection checks, explicit 32-NFL-team reconciliation, and league-rule tests; the final M0.4 suite count is recorded in the roadmap after verification. Missing raw projections continue to become effective zero only under `missing_projection_policy`; explicit zero and imputed zero remain distinct.

No current master-specification requirement was contradicted. The important refinement is that inverse standings is supported for the configured weekly reset, not a universal waiver assumption, and the eight-team consolation structure remains a blocking evidence gap.

## 18 October 2026 owner UI confirmation follow-up

This follow-up records direct inspection of the ESPN league-settings interface by the project owner. It supplements—but does not retroactively relabel—the M0.4 raw-response and historical-bracket observations.

- The current regular-season `matchupTieRule=NONE` permits a tied game. Each club receives one tie and neither receives a win or loss. The UI also offered home team, most QB points, most WR points, most RB points, and most bench points. Those alternatives remain preserved configuration values, not implemented fallbacks.
- The current `playoffSeedingRule=TOTAL_POINTS_SCORED` establishes cumulative PF as the first tiebreaker for equivalent records. The UI alternatives were head-to-head record, intradivision record, total points for, and total points against. Secondary ranking behavior after the configured first rule remains unverified.
- A tied playoff matchup advances the higher-seeded team. Manual League Manager advancement changes are discretionary interventions and are outside the simulation model.

For new adapter translations, the repository preserves the raw `NONE` enum while normalizing the confirmed regular-season meaning to `allow_ties` and the confirmed playoff meaning to `higher_seed`. Other raw values remain unverified rather than being coerced to these current-league rules. Existing immutable snapshots retain the evidence state with which they were published.

## 18 October 2026 undroppable evidence follow-up

The owner confirmed in the league settings UI that **Observe ESPN's Undroppable Player List** is enabled. A new bounded authenticated diagnostic independently observed raw `settings.rosterSettings.isUsingUndroppableList=true` in both the initial and reconciliation league responses.

Raw `player.droppable` was present as a Boolean for all 1,052 current `kona_player_info` records and all 235 `mRoster` player copies. Current counts were 1,038 `true`, 14 `false`, and zero absent; rostered counts were 221, 14, and zero respectively. The identical universe and known values reconciled across 11 future-week `kona_player_info` views. The audit retains absence separately and fails on malformed types, incomplete page universes, or contradictory known values.

`espn-api` 1.0.1 does not expose or transform `player.droppable`; the repository parses raw JSON. ESPN support documentation establishes the operational Undroppable Players List and visible “Can't Drop” state, but this audit did not expose private player identities to compare a particular raw `false` record with the interface. Field availability and completeness are **Verified live**; that last per-player UI correlation remains **Unverified**. Full provenance, tests, effective-rule proposal, and schema-v3 handoff are documented in `ESPN_UNDROPPABLE_AUDIT.md`. No canonical schema migration was performed in M2.3a.

## Generalized discovery follow-up

The follow-up removed the current league's shape from structural validation. Retrieval still obtains raw ESPN responses; pure discovery functions now parse roster, acquisition, trade, scoring, schedule, and team state; a separate capability inventory classifies each area as `valid_and_understood`, `valid_but_unverified`, or `valid_but_unsupported`. Only malformed or contradictory source data raises `LeagueRulesAuditError`.

The diagnostic now derives all of the following from raw settings rather than expected constants:

- observed team count; an optional expected count remains an identity check only;
- every positive raw lineup-slot capacity, known label, unknown slot ID, starter/bench/IR capacity, current occupancy, and vacancies;
- waiver type and current priority completeness without requiring traditional waivers;
- scoring type and seeding-rule enums without requiring H2H points;
- playoff qualifier count, next-power-of-two bye count, round IDs and durations, scoring-week membership, and reseeding flag;
- consolation enablement when the field exists, while preserving a missing field as unverified.

Credential-free fixtures verify valid 8-, 10-, and 14-team configurations; differing starter and bench counts; multiple flex slots; zero, one, or two IR slots; four, six, and eight playoff qualifiers; alternate round durations; disabled consolation; and absent consolation metadata. An unfamiliar slot or enum remains in the report with unsupported/unverified status. Negative capacities, duplicate IDs, over-capacity rosters, incomplete priority permutations, overlapping scoring weeks, noncontiguous rounds, duration conflicts, bad seed permutations, duplicate historical appearances, invalid references, winner/score contradictions, and bad multiweek totals fail explicitly.

### Reproducible 2024 and 2025 bracket evidence

The strengthened historical parser uses raw team `playoffSeed` and `rankCalculatedFinal`, schedule `matchupPeriodId`, `winner`, side `teamId`, `totalPoints`, and `pointsByScoringPeriod`, plus configured matchup-period weeks. Repository code—not `espn-api` transformation—reconstructs the relationships below and validates IDs, unique appearances, winner membership, winner/aggregate consistency, and two-week sums.

Both completed seasons independently produced:

- championship entrants seeded 1–6;
- period 15 bye rows for seeds 1 and 2, plus 3–6 and 4–5 games;
- first-round winners seeded 3 and 4;
- period 16 pairings 1–4 and 2–3, with 5–6 in the fifth-place path;
- period 17 championship placement pairings whose calculated final ranks are 1–2, 3–4, and 5–6;
- twelve side-level checks proving each period-17 `totalPoints` equals the sum of weeks 17 and 18;
- `playoffReseed=false`, with observed pairings consistent with fixed bracket progression.

Winner and loser destinations are now recorded for every decided two-team row from periods 15 and 16. This supplies reproducible advancement and placement evidence rather than relying on row counts. The historical consolation evidence remains intentionally season-specific:

- 2024 pairings by period were 7–8, 9–10, 11–12; then 7–10, 8–11, 9–12; then 7–9, 8–12, 10–11.
- 2025 pairings by period were 7–8, 9–10, 11–12; then 7–11, 8–9, 10–12; then 7–8, 9–12, 10–11.

Those differing winner/loser paths and final-rank mappings verify the completed six-team consolation ladders. They still do not establish the current eight-team consolation structure. Current 2026 consolation participants, pairings, advancement, and placement mapping remain unverified until ESPN exposes the bracket or the league supplies approved rules.

This follow-up does not change the previously reported current-league values. It changes their architectural role: they are observed evidence and future configuration inputs, never universal validation templates.
