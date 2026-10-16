# M0 Feasibility Decision and M1 Handoff

## Decision

**M0 recommendation: GO for M1 with explicit unresolved metadata.**

M0.1–M0.5 provide enough verified access, identity, rule discovery, projection, schedule, and provenance behavior to design and implement canonical immutable snapshots and a production adapter. This approval is limited to M1. It does not approve M2 rule choices, an M3 distribution, or any transaction simulation.

The absence of authenticated historical pregame forecasts is not a general development blocker. The user has approved provisional exploratory use of those pairs and provisional Monte Carlo probability estimates, provided outputs clearly identify provisional statistical calibration. Prospective collection is deferred and is not a V1 prerequisite.

## Readiness matrix

| Area | Classification | Evidence and M1 consequence |
|---|---|---|
| Current league/team/roster/standings availability | Ready now | Live M0.2 identity, ownership, standings, and scoring reconciliation succeeded |
| Future player pool, projections, NFL byes, fantasy schedule | Ready now | M0.3 validated pagination, current ownership, raw weekly projection records, 32-team bye data, and regular schedule |
| Dynamic roster/scoring/rule discovery | Ready now | M0.4 accepts multiple structurally valid configurations and preserves unknown enums |
| Identifier and cross-source reconciliation | Ready now | Signed player IDs, team references, ownership, weeks, sources, split types, and slot namespaces are documented and tested |
| Source provenance and retrieval context | Ready now for design | Required fields and evidence labels are known; raw digest/schema implementation belongs to M1 |
| M1 canonical entities | Ready now for M1.1 design | Entity/field vocabulary and invariants are documented, but no production schema exists yet |
| ESPN-to-canonical adapter | Ready now after M1.1 | Raw sources and known library defects are identified; implementation intentionally remains M1.2 |
| Immutable staged refresh | Ready now for design | Multi-request inconsistency risk is known; staging, validation, atomic publication, and persistence remain M1.3 |
| Snapshot validation | Ready now | Snapshot-acceptance versus capability-specific invariants are separated in the data dictionary |
| Unknown rule preservation | Ready with explicit unresolved metadata | M1 may store raw/unresolved rules without inventing simulator behavior |
| Championship simulation rules | Ready with limited unresolved metadata | Qualifiers, byes, reseeding, periods, and durations are supported; tie behavior must remain unresolved |
| Consolation simulation | Blocked for authoritative M2 full-placement behavior | Current eight-team ladder relationships are not verified; does not block M1 ingestion |
| Essential waiver simulation | Requires further design/evidence before M2.3 | Current priority/settings are available; exact multiple-claim and dropped-player behavior remain unresolved |
| Trade workflows | Requires further design before M4/M5 | Deadline/delay/vote threshold exist; review workflow is unverified and irrelevant to no-trade baseline |
| Historical calibration | Ready only as explicitly provisional research | Returned pairs have unverified pregame provenance; no model/distribution decision is made here |
| Forecast-horizon modeling | Deferred/unsupported | No historical vintages or lead-time metadata; no V1 mean/variance horizon adjustment |
| Scheduled prospective collection | Deferred by approved scope | Not a prerequisite for M1 or V1 |

## Approved post-M0.5 policies

### Current projections

For every future week, V1 uses ESPN's currently available player-specific weekly projection as its projected-point input. V1 does not forecast later changes to ESPN's projection. The assumed expected adjustment from future ESPN revisions is zero as an approved simplification, not an empirical random-walk finding. V1 applies no forecast-horizon mean adjustment or variance multiplier.

### Missing projections

Canonical design must retain four independent facts: nullable raw value, raw classification, effective projected points, and effective-value source.

| Raw observation | Raw class | Effective value | Effective source |
|---|---|---:|---|
| No matching ESPN projection record | `missing` | 0 | `missing_projection_policy` |
| Matching record with zero | `explicit_zero` | 0 | `espn` |
| Matching record with finite positive value | `present` | unchanged | `espn` |

Finite negative ESPN projections remain valid raw ESPN values and must not be rejected, relabeled missing, or silently coerced. The existing approved policy defines availability for positive and zero effective projections but does not explicitly define the effective-value/availability treatment of a negative ESPN projection. M1 must surface that narrow design question for approval before accepting such a player-week as simulation-ready. Historical policy-imputed zeros are never ESPN forecast observations and cannot enter a genuine-forecast error sample as zeros.

### Statistical maturity

Future output must distinguish:

1. **Structural/model correctness:** data and deterministic league mechanics satisfy validated contracts.
2. **Provisional statistical calibration:** a clearly labeled interim distribution uses approved but incompletely validated evidence.
3. **Empirically validated statistical calibration:** a later model has passed defined held-out/calibration evidence gates.

Historical source-1/source-0 pairs with unverified pregame provenance may support explicitly provisional exploratory calibration. The project may produce provisional Monte Carlo probabilities before that provenance is independently validated. M0.6 selects no distribution, grouping, fit, threshold, or promotion gate.

### League configuration

All structures are discovered dynamically. The current 14-team league, its roster slots, traditional waiver system, six-team championship, and round lengths are observations—not universal validators. Structurally valid unknown configurations are preserved as unsupported/unverified. Contradictory structures fail. Manual per-league values are allowed only for audited gaps, with source and timestamp, and must never silently override conflicting ESPN evidence.

## Rule-gap register

| Gap | ESPN established | Unknown / why it matters | Resolution and manual configuration | Dependency / severity |
|---|---|---|---|---|
| Current eight-team consolation ladder | Enabled; eight nonqualifiers implied; historical six-team ladders observed | Current participants, seed mapping, pairings, transitions, durations, placements | Inspect 2026 bracket when materialized or supply explicit approved ladder; conflict with ESPN fails | M1 stores gap; **blocks M2 authoritative all-team placement** |
| Multiple waiver claims | Traditional waivers, complete priority, weekly reset evidence | Claim ordering, contingencies, and priority movement across multiple claims | UI/help plus sanitized transaction sequence; explicit ordered config permissible | **Blocks M2.3/M5 waiver paths**, not M1 ingestion |
| Regular matchup tie | Raw `matchupTieRule=NONE` | Operational standings result | UI or observed tied matchup; named explicit config permissible | **Blocks M2.2 tied path only** |
| Playoff matchup tie | Raw `playoffMatchupTieRule=NONE`; official defaults exist but may be overridden | Advancement in exact tie | League UI or observed tie; named explicit config permissible | **Blocks M2.4 tied playoff path** |
| Secondary standings tiebreaks | First seeding rule is `TOTAL_POINTS_SCORED` | Order after equal record and equal PF | Export league playoff settings or observed resolved tie; ordered config permissible | Blocks only affected M2 seeding ties |
| Dropped-player waiver reentry | One-day waiver delay and player `WAIVERS` state observed | Exact reentry/lock behavior after a simulated drop | Official league-specific UI/help or timestamped transaction evidence; config permissible | **Blocks affected M2.3/M5 release/reacquisition paths** |
| Waiver processing time | Days, raw hour 11, and delay exposed | Hour encoding/timezone and boundary behavior | Compare UI time and actual processing timestamps; IANA timezone config permissible | Time-sensitive M2/M5 behavior; not basic weekly snapshot ingestion |
| Trade-review workflow | Deadline, 24-hour revision, eight-vote threshold | League vote versus commissioner/none and precise processing | League UI or transaction history; explicit enum config permissible | M4/M5 trades only; **not baseline/no-trade blocker** |
| Postseason transaction restrictions | General transaction settings available | Any playoff-specific override | League UI or observed behavior; scoped config if needed | M2/M5 postseason actions only |

No production default is approved for any gap.

## M1 validation handoff

Snapshot publication must require coherent league identity, complete distinct team IDs, unique ownership, dynamically valid capacity and references, valid scoring configuration, exact player-week/source/split identity, finite numerics, correct raw/effective projection provenance, complete NFL/bye and regular-season schedule relationships, and complete retrieval/source metadata.

Capability validators are separate. A snapshot may retain unknown consolation or transaction semantics and remain inspectable. It is not eligible for an authoritative simulator capability that depends on the missing rule. Each capability decision should name the exact blocking rule keys.

M1 design decisions still requiring deliberate architecture review are:

- concrete immutable entity boundaries, key types, and versioned serialization;
- raw payload retention/digest strategy and sanitized inspect output;
- staged refresh consistency-window policy and atomic publication mechanism;
- SQLite/Parquet division, migrations, retention, and snapshot identifiers;
- representation of evidence class, interpretation status, rule gaps, and explicit manual configuration;
- supported-versus-preserved enum policy in typed interfaces; and
- effective-projection and availability semantics for a finite negative raw ESPN projection; and
- capability-readiness metadata without importing M2 behavior into M1.

These are normal M1 design tasks, not M0 blockers.

## Reproducible verification

Credential-free manifest check:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.m0_verification
.\.venv\Scripts\python.exe -m fantasy_football.m0_verification --check-config --json
.\.venv\Scripts\python.exe -m pytest
```

The manifest verifies required evidence documents and diagnostic modules, lists unresolved rules and reproduction commands, and explicitly reports `live_verification_performed=false`. `--check-config` validates local configuration only; it performs no network request.

Live diagnostics require private credentials and are independently invoked:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.espn_connectivity --expected-team-count 14
.\.venv\Scripts\python.exe -m fantasy_football.future_data_audit --expected-team-count 14
.\.venv\Scripts\python.exe -m fantasy_football.league_rules_audit --expected-team-count 14 --historical-season 2024 --historical-season 2025
.\.venv\Scripts\python.exe -m fantasy_football.historical_projection_audit --sample 2024:1 --sample 2024:8 --sample 2024:14 --sample 2024:17 --sample 2025:1 --sample 2025:8 --sample 2025:14 --sample 2025:17
```

The explicit expected team count is an identity/reconciliation input for the configured league, never a universal supported structure. The extensive historical audit is not required for routine health checks. Live output remains local and uncommitted.

## Final gate

- **M0 discovery milestone:** complete, subject to review of this handoff.
- **M1:** recommended **GO WITH EXPLICIT UNRESOLVED METADATA**.
- **M2:** not generally approved; several capability-specific rules remain unresolved.
- **M3:** provisional research path approved, but empirical calibration remains unvalidated.
- **M4/M5:** transaction semantics remain future work.

No M1 implementation is included or authorized by this document.
