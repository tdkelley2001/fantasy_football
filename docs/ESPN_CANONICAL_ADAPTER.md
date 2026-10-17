# M1.2 ESPN-to-Canonical Adapter

## Status

M1.2 is **BLOCKED pending a targeted M1.1 contract decision**. The credential-free retrieval/translation implementation and tests are complete enough to expose the issue, but the live acceptance gate did not produce a valid canonical snapshot.

On 17 October 2026, a read-only live run used explicit `first_simulation_week=8` because scoring week 7 was already active. The adapter retrieved the current league, current player authority, future week pages, and NFL calendar sequentially. Translation stopped before producing a snapshot because 97 players exposed raw eligible lineup-slot ID `25`, while `settings.rosterSettings.lineupSlotCounts` defined only IDs `0–24`.

The current schema validates player eligibility against configured `LineupSlotRule` IDs. Dropping ID 25 would lose source evidence. Creating a zero-capacity rule would incorrectly claim that ESPN explicitly configured the absent ID. The adapter therefore fails with a contract-specific diagnostic, as required, and M1.2 is not marked complete.

## Responsibility boundaries

`fantasy_football.espn_adapter` separates:

1. Sequential authenticated retrieval into `CapturedResponse` and `EspnSourceBundle` records.
2. Network-independent translation through `translate_bundle`.
3. Existing canonical validation, deterministic serialization checking, sanitized reporting, and critical-state reconciliation.

`AdapterResult.raw_sources` retains in-memory raw mappings, request context, retrieval time, and SHA-256 digest for future M1.3 persistence. M1.2 does not write those payloads, allocate snapshot IDs, publish snapshots, or implement a database.

## Endpoints and source precedence

| Purpose | Endpoint/view | Authority and transformation |
|---|---|---|
| League settings, teams, rosters, standings, schedule | League endpoint with `mTeam,mRoster,mMatchup,mSettings,mStandings` | Initial current-state authority; parsed from raw JSON rather than library convenience objects |
| Current player ownership/status/identity | League endpoint, current `scoringPeriodId`, paginated `kona_player_info` | Current view is authoritative; reconciled exactly to roster entries |
| Future player-week projections | One paginated `kona_player_info` request series per required future week | Only matching season/week, `statSourceId=1`, `statSplitTypeId=1` records are projections; future wrapper ownership is ignored |
| NFL teams/games/byes | Season endpoint with `proTeamSchedules_wl` | Raw team IDs, `byeWeek`, game IDs, teams, scoring periods, and UTC kickoff times |
| Mutable-state reconciliation | A final league request | Ownership/slots, W/L/T, PF/PA, seeds, and waiver priority must exactly match the initial observation |

Every pool series must begin at offset zero, advance by the declared limit, contain no duplicate/overlapping IDs, and end with a short page. Every future week must return the same player universe as the current authoritative view. ESPN supplies no independent total count, so this is completeness against the verified pagination contract rather than an external universe.

## Projection translation

The adapter implements the approved canonical policy without using `espn-api`'s rounded/defaulted projection attribute:

- no matching weekly record → raw null, `missing`, effective zero, `missing_projection_policy`;
- matching finite zero → `explicit_zero`, effective zero, ESPN source;
- matching finite positive or negative value → `present`, unchanged effective value, ESPN source;
- malformed, duplicate, cross-week, wrong-split, or nonfinite matching records fail.

## Rule translation and manual configuration

Verified raw scoring, roster, acquisition, trade, standings, championship, and consolation fields translate into dynamic canonical rule records. Unknown or unresolved operational semantics remain `unverified`, `unsupported`, or `missing`; no waiver, tie, or consolation default is introduced.

Optional YAML configuration is restricted to audited gaps and requires:

- exact league ID and season;
- canonical rule ID and audited gap ID;
- configuration key;
- approved structured value;
- exact expected current ESPN raw value;
- approval reference; and
- HTTPS evidence URL.

The file SHA-256 and evidence URL become source provenance. A manual interpretation is stored separately from the original ESPN interpretation, so raw ESPN evidence retains its own source reference. Identity mismatch, unaudited gaps, duplicate rules, malformed/nonfinite values, or conflict with ESPN evidence fails. Store private league configuration under a name such as `config/league_rules.local.yaml`; `config/*.local.yaml` is ignored by Git.

Example structure (illustrative only, not an approved league rule):

```yaml
league_id: 123
season: 2026
rules:
  - rule_id: consolation_structure
    gap_id: consolation_ladder
    config_key: postseason.consolation_ladder
    expected_raw_value: false
    approved_value:
      rounds: []
    approval: review-reference
    evidence_url: https://example.invalid/league-rule-evidence
```

## Retrieval reliability

The adapter permits at most two retries after the initial request. It retries connection timeouts, connection failures, HTTP 5xx responses represented by the ESPN client, and request exceptions carrying 5xx responses. Authentication failures, invalid leagues, malformed payloads, identity conflicts, incomplete pagination, and canonical contradictions are not retried. Errors retain request role, scoring week, offset, and limit where applicable. Cookies are never placed in source metadata, logs, reports, or exceptions.

## Credential-free verification

Sanitized fixtures cover current ownership, three-page pagination, two future weeks, positive/zero/missing/negative projections, a negative D/ST ID, 32 NFL teams, games/byes, standings, waiver priority, postseason rule metadata, unresolved rules, approved YAML configuration, deterministic translation, and sanitized CLI output.

Adversarial tests cover incomplete and overlapping pages, inconsistent universes, ownership conflicts, invalid IDs, nonfinite/malformed projections, missing required settings, incomplete regular schedule, mutable-state changes, manual-config conflicts, and the unconfigured-eligible-slot contract blocker. The focused adapter/CLI suite passed 22 tests, and the complete credential-free repository suite passed 180 tests.

## Required M1.1 decision

The recommended correction is to distinguish the **known raw lineup-slot identifier namespace** from **configured lineup-slot capacities**. For example, `LeagueRules` could preserve a separate immutable set of observed/known lineup-slot IDs, while `LineupSlotRule` continues to mean an explicitly present ESPN capacity. Player eligibility would validate against the namespace set; roster occupancy would continue to require an explicitly configured positive-capacity slot.

No such amendment is implemented in M1.2. After review and approval, it requires a focused M1.1 schema/serialization/validation change, followed by another live M1.2 run. No evidence currently suggests an adapter mapping can solve the issue without losing or inventing data.

## Live workflow

```powershell
python -m fantasy_football.espn_adapter `
  --first-simulation-week 8 `
  --expected-team-count 14
```

The first week is an explicit operational decision and must be the first fully unplayed week. The command emits only sanitized aggregate output. `--manual-config` accepts an optional local YAML file; neither that file nor private raw responses should be committed.
