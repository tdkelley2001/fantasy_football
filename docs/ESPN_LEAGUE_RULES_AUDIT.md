# ESPN League Rules Audit (M0.4)

## Scope and evidence

This document records a read-only audit performed on 2026-10-16 against the configured private league's 2026 season and completed 2024 and 2025 seasons. The executable diagnostic is `python -m fantasy_football.league_rules_audit --expected-team-count 14 --expected-playoff-team-count 6 --historical-season 2024 --historical-season 2025`. It emits only sanitized aggregates; raw private responses, credentials, manager identities, player identities, and transaction details are not persisted.

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
| Matchup ties | `scoringSettings.matchupTieRule` | `NONE` | enum | No verified raw definition establishes the operational result of `NONE`. | Unverified | `standings.matchup_tie_rule` is blocking. |
| Championship qualification | `playoffTeamCount`, `matchupPeriodCount` | six qualifiers; regular season through week 14; playoffs start week 15 | integers | Direct settings. | Verified live | Yes. |
| Championship rounds | `playoffMatchupPeriodLengthByRound`, `matchupPeriods` | 1, 1, 2 weeks; final is weeks 17–18 | maps | Direct current settings. Historical 2024/2025 final rows corroborate two-week aggregate behavior. | Verified live | Yes. |
| Byes and reseeding | six-team bracket, `playoffReseed` | two byes; false | derived count / bool | Two historical bye rows in both completed seasons verify seeds 1–2 receive byes. Historical pairings were fixed rather than reseeded. | Verified live (historical) | Strong evidence, but current 14-team bracket rows have not materialized. |
| Playoff matchup tie | `playoffMatchupTieRule` | `NONE` | enum | ESPN's default is higher seed, but LM override is possible and the raw enum mapping is not established. | Unverified + [ESPN playoff tie guidance](https://support.espn.com/hc/en-us/articles/4669390376852-Playoff-Scoring-Tiebreakers) | `postseason.playoff_matchup_tie_rule` is blocking. |
| Placement games | historical `schedule` and final standings | championship, 3rd-place, and 5th-place rows observed | schedule relationships | Observed in both completed 12-team seasons. | Verified live (historical) | Yes for six-team championship component. |
| Consolation enabled | `consolationLadderDisabled` | false | bool | A consolation ladder is enabled. Current 14-team pairings are not yet in the schedule. | Verified live | Enablement only. |
| Consolation structure | historical schedule | completed six-team ladders in 2024/2025; current expected participants 8 | schedule relationships | Historical ladders were placement ladders, not safely reducible to conventional single elimination. They do not prove the new eight-team mapping. | Unverified for 2026 / Unsupported pre-postseason | Explicit ladder configuration or actual 2026 bracket evidence is blocking. |

## Roster reconciliation and operational constraints

The configured ordinary roster is nine starters plus seven bench places. Slot 21 adds one separate IR place, for a maximum of 17 only when IR is occupied. At retrieval, ten teams used IR, three 16-player teams had all 16 ordinary places and empty IR, and one 16-player team had 15 ordinary players plus an IR occupant. Thus no alternative reserve mechanism is needed to explain the M0.2 observation.

ESPN's current guidance permits OUT and IR players to enter IR and permits a player whose status later becomes questionable or doubtful to remain. A healthy player in IR can invalidate additions, and a claim can fail if roster capacity changes before processing ([ESPN waiver/IR behavior](https://support.espn.com/hc/en-us/articles/360060240712-How-does-the-Injured-Reserve-Injury-List-impact-Waivers)). The future engine must model this as transaction legality, not reinterpret IR as an eighth bench slot.

## Waiver, transaction, and standings conclusions

This league uses traditional waivers. `waiverOrderReset=true`, official ESPN documentation, and current ranks support weekly inverse-standings reset followed by move-to-last on a successful claim; free-agent pickups do not change priority. Exact ordering for multiple contingent claims from one manager and the raw processing-hour timezone remain unresolved. These actual rules apply to path-dependent essential acquisitions. They do not replace the master specification's separate deterministic pre-simulation roster-completion procedure or later actionable waiver recommendations.

The raw trade settings establish the deadline, 24-hour review duration, eight-vote threshold, and no trade-count limit. Two team trade counters were observed. The audit did not fetch pending offers, votes, or manager-level transaction details. Add/drop positional limits use the raw `positionLimits`; IR and total-capacity legality also apply.

The current league is H2H points with one division, and ESPN supplies W/L/T, PF, PA, and a complete 1–14 seed permutation. `TOTAL_POINTS_SCORED` directly verifies points for as the selected first seeding tiebreak. It does not establish every subsequent tiebreak. Regular matchup ties and playoff matchup ties remain unresolved because raw `NONE` has not been authoritatively mapped for this league.

## Championship and consolation evidence

Current settings verify six qualifiers, two first-round byes, no reseeding, rounds of one, one, and two weeks, and a weeks 17–18 final. Completed 2024 and 2025 seasons each had 12 teams but the same six-team championship settings. Both produced 19 postseason schedule rows across periods 15–17, two home-only bye rows, fixed bracket progression, championship/third/fifth placement games, and six two-week period-17 rows spanning weeks 17–18.

The current 14-team schedule has no postseason pairings yet. The remaining eight teams are therefore the expected consolation population, but their exact seed mapping, initial pairings, advancement, round lengths, and placement outputs are not verified. The completed historical seasons had only six non-playoff teams, so extrapolating their ladder would violate the no-fallback rule.

## Manual configuration gaps

These keys are proposals for later review, not a production schema or defaults:

| Proposed key | Allowed value | Why needed / verification | Blocks authoritative simulation? |
|---|---|---|---|
| `waivers.claim_processing_order` | Explicit ordered procedure for multiple claims and priority movement | Confirm in ESPN league UI/help or observe sanitized completed-claim sequences. ESPN state remains authoritative; conflict must fail. | Yes for path-dependent waivers |
| `waivers.process_timezone` | IANA timezone verified for raw hour 11 | Compare UI-displayed processing time and execution timestamps. | Only for time-of-day simulation |
| `transactions.trade_review_type` | `league_vote`, `commissioner`, or `none` | Confirm league settings UI; raw threshold alone is insufficient. | No unless trades are modeled |
| `standings.matchup_tie_rule` | Named verified rule | Confirm UI or observe an actual tied regular matchup. | Yes |
| `standings.secondary_seeding_tiebreaks` | Ordered verified list | Confirm LM playoff settings. | Yes when the first tiebreak remains tied |
| `postseason.playoff_matchup_tie_rule` | Named verified rule | Confirm UI or an actual tied playoff matchup. | Yes |
| `postseason.consolation_ladder` | Participants, seed mapping, pairings, round scoring periods, advancement, placement mapping | Export/inspect the 2026 bracket once available or supply league-approved rules. | Yes |

Later reconciliation must compare every manual value with retrievable ESPN evidence and fail on conflict. Absence never activates a guessed default.

## Tests and limitations

The diagnostic has credential-free positive, negative, and adversarial coverage for malformed/missing roster settings, over-capacity rosters, duplicate teams, unknown waiver enums, missing/duplicate priorities, invalid playoff counts and durations, duplicate seeds, missing consolation metadata, unknown historical team references, contradictory pairings, and absent historical postseason evidence. It reports unresolved states in the result rather than constructing rules.

M0.3's original completion remains 47 passing tests. The projection-UI and missing-policy follow-up raised the suite to 55. M0.4 adds finite-projection checks, explicit 32-NFL-team reconciliation, and league-rule tests; the final M0.4 suite count is recorded in the roadmap after verification. Missing raw projections continue to become effective zero only under `missing_projection_policy`; explicit zero and imputed zero remain distinct.

No current master-specification requirement was contradicted. The important refinement is that inverse standings is supported for the configured weekly reset, not a universal waiver assumption, and the eight-team consolation structure remains a blocking evidence gap.
