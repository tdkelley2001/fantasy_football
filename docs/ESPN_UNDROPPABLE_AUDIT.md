# ESPN Undroppable-Player Evidence Audit (M2.3a)

## Scope and conclusion

This bounded read-only follow-up ran on 18 October 2026 against the configured private 2026 league. The command was:

```powershell
python -m fantasy_football.undroppable_audit --first-simulation-week 8
```

It prints only season and aggregate coverage. It does not print player, team, manager, or league identities, raw payloads, or credentials.

The league-level setting and player-level raw field are available with complete live coverage. The raw field is sufficient to preserve an explicit Boolean separately from absence. ESPN's official support documentation establishes that enabled leagues prevent players on the Undroppable Players List from being dropped and that affected players display “Can't Drop.” However, this audit did not expose a private player identity to manually correlate one raw `false` value with that UI label. Accordingly:

- field existence, type, coverage, and cross-request consistency are **Verified live**;
- pure parser and contradiction behavior are **Verified by tests**;
- exact per-player raw-Boolean-to-UI correlation remains **Unverified**;
- `espn-api` support for the field is **Unsupported** because version 1.0.1 ignores it rather than mapping it.

Official references: [ESPN Undroppable Players List](https://support.espn.com/hc/en-us/articles/360000070692-Undroppable-Players-List) and [ESPN Drop a Player](https://support.espn.com/hc/en-us/articles/360000065371-Drop-a-Player).

## Sources and live coverage

| Concept | Raw source | Type / missingness | Library transformation | Repository transformation | Evidence |
|---|---|---|---|---|---|
| League enablement | league `mSettings`; `settings.rosterSettings.isUsingUndroppableList` | Boolean when present; absence remains unknown; other types fail | None | Preserve `true`, `false`, or missing separately | **Verified live** as `true` in both initial and reconciliation responses; owner independently confirmed enabled in UI |
| Current player designation | paginated `kona_player_info`; `players[].player.droppable` | Boolean when present; absence remains unknown | `espn-api` `Player` ignores the field | Count and reconcile raw values without inversion or default | **Verified live** for all 1,052 current records: 1,038 `true`, 14 `false`, 0 missing |
| Rostered-player designation | league `mRoster`; `teams[].roster.entries[].playerPoolEntry.player.droppable` | Same | Ignored | Reconcile with current pool by signed player ID | **Verified live** for all 235 rostered players: 221 `true`, 14 `false`, 0 missing |
| Future-view consistency | each future-week paginated `kona_player_info`; same path | Same | Ignored | Require identical player universe and reject contradictory known values | **Verified live** across all 11 requested future weeks |

Every raw `false` in the live current universe belonged to a rostered player at retrieval. That observation does not prove that only rostered players can receive the designation or that the list cannot change later. The player field is separate from the league enablement setting: ESPN returned both facts, and repository logic must retain both.

The setting's availability was checked in the initial and final league requests. The player universe was checked in the current pool, roster copy, and every future-week view. Missing values are never interpreted as `true` or `false`; known contradictions fail the audit. Multi-request agreement establishes coherent retrieval, not timeless immutability.

## Effective legality contract approved for M2.3b

The proposed normalized fields are:

- `LeagueRules.undroppable_list_enabled: bool | None`
- `LeagueRules.undroppable_list_source_id: str | None`
- `Player.is_undroppable: bool | None`
- `Player.undroppable_source_id: str | None`

Raw `player.droppable=true` maps to `is_undroppable=false`; raw `false` maps to `true`; absence maps to `None`. M2.3b must not make that mapping authoritative until the remaining per-player UI-correlation question is reviewed or explicitly approved. The raw Boolean and source reference must remain independently inspectable.

The effective rule is capability-specific:

| League setting | Player designation | Result under this rule |
|---|---|---|
| `false` | any value | This rule does not prohibit the drop |
| `true` | `true` | Drop prohibited |
| `true` | `false` | This rule permits consideration; every other roster/transaction restriction still applies |
| `true` | unknown | Automatic drop not authorized |
| unknown | any value | Automatic drop not authorized until applicability is established |

Player protection is current source state, not a historical or future guarantee. Refreshes may legitimately change it.

## Proposed canonical validation and versioning

M2.3a does not change canonical schema v2. M2.3b should introduce canonical schema v3 explicitly because adding required serialized fields changes deterministic JSON compatibility.

Proposed validation:

1. Values are exactly Boolean or null; numeric `0`/`1` are invalid.
2. A non-null value requires a valid retained `SourceReference`.
3. Missing raw fields remain null and never become droppable by default.
4. Current-player and roster copies with contradictory known values fail translation.
5. Complete known player coverage is required for authoritative automatic dropping when the list is enabled; otherwise the drop capability fails while unrelated snapshot uses may remain valid.
6. The effective rule above is derived, not serialized as a second potentially contradictory Boolean.
7. Other roster locks, game locks, ownership, capacity, and transaction rules remain independent legality checks.

SQLite schema v1 can continue storing versioned canonical JSON and raw captured responses; no relational player table is required. Existing schema-v2 documents and checksums remain byte-for-byte immutable. Do not rewrite them in place. Schema-v3 publication receives a new UUID. A version-aware reader may retain explicit schema-v2 read support for reproducibility, but M2.3 drop authorization must reject v2 snapshots with a precise missing-protection-evidence error. Re-fetching and publishing a v3 snapshot is the preferred operational path; retranslation of old raw evidence, if ever offered, must create a new snapshot and identify its source snapshot rather than masquerading as the old document.

Affected M2.3b components are `canonical/model.py`, validation, serialization, adapter translation, sanitized fixtures, quality reporting, snapshot-version checks, CLI presentation, and persistence round-trip tests. Database tables do not require an incompatible migration merely because the embedded canonical document version advances.

## Reproduction and limitations

Credential-free tests cover enabled, disabled, missing, malformed, protected, explicitly droppable, unknown, incomplete, and contradictory evidence. Fixture tests prove parser behavior only. The 18 October authenticated run establishes the live counts above.

## M2.3b follow-up — 18 October 2026

Official ESPN documentation was rechecked and confirms that players on the Undroppable Players List cannot be sent to waivers/free agency and display “Can't Drop.” The authenticated read-only source continues to provide complete raw Boolean coverage, but the available tooling does not expose the authenticated interactive player card/drop control. No individual private `droppable=false` and `droppable=true` records were correlated directly to those UI states.

Therefore the exact raw polarity mapping remains **Unverified**, not verified live. Schema v3 retains the proposed inversion and exact source provenance alongside an `unverified` `undroppable_player_mapping` interpretation. The M2.3b transaction gate refuses automatic drops in enabled-list leagues until that interpretation is explicitly approved or independently corroborated. Fixture tests using an `understood` interpretation verify legality behavior only; they are not live semantic evidence.

The remaining direct verification method is simple and bounded: locally identify one raw `droppable=false` and one raw `true` rostered player, then confirm “Can't Drop” versus an available Drop action in the ESPN interface without committing the identities.
