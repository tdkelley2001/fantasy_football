# Fantasy Football Decision Engine

This repository is being reset for a clean-sheet rebuild of a league-wide decision engine for ESPN fantasy football. The intended system will estimate season-outcome distributions and compare roster actions by their effect on championship probability while honoring real league rules, uncertainty, and full-league consequences.

## Current status

M0 and M1 are **COMPLETE**. M2 is **IN PROGRESS**: M2.1, M2.2, and M2.3a are complete; the corrected M2.3b implementation is awaiting review. M2.3c and later work packages remain **NOT STARTED**. New snapshots use canonical schema v3, while historical schema-v2 snapshots remain immutable and readable. Immutable evolving roster/transaction legality exists, but transaction valuation, automatic selection, and weekly waiver-cycle processing do not. Simulator-specific rule gaps remain preserved without defaults.

## Authoritative documentation

- [Master specification](docs/MASTER_SPEC.md) — the complete approved model specification and governing requirements.
- [Development roadmap](docs/ROADMAP.md) — the M0-M7 milestone sequence, individual work packages, dependencies, gates, and current statuses.
- [M0.2 ESPN connectivity findings](docs/ESPN_CONNECTIVITY.md) — sanitized live-access evidence, field provenance, validation results, and deferred questions.
- [M0.3 future player-week findings](docs/ESPN_FUTURE_DATA_AUDIT.md) — projection, player-pool, bye, schedule, pagination, and provenance evidence.
- [Missing projection policy](docs/MISSING_PROJECTION_POLICY.md) — approved raw-versus-effective representation, week 6 evidence, methodology, and limitations.
- [M0.4 league-rules audit](docs/ESPN_LEAGUE_RULES_AUDIT.md) — roster/IR, waiver, trade, standings, championship, consolation, provenance, and explicit configuration gaps.
- [M0.5 historical projection audit](docs/ESPN_HISTORICAL_PROJECTION_AUDIT.md) — bounded historical coverage, projection/actual matching, as-of integrity, leakage risks, and M3 feasibility.
- [Undroppable-player evidence audit](docs/ESPN_UNDROPPABLE_AUDIT.md) — league and player field provenance, bounded live coverage, conservative legality semantics, and the proposed schema-v3 handoff.
- [ESPN data dictionary](docs/ESPN_DATA_DICTIONARY.md) — proposed M1 logical fields, raw paths, identifier namespaces, transformations, evidence, and validation tiers.
- [M0 feasibility and M1 handoff](docs/M0_FEASIBILITY_AND_M1_HANDOFF.md) — readiness matrix, rule-gap register, approved forecast/calibration policies, and the M1 recommendation.
- [Canonical model](docs/CANONICAL_MODEL.md) — schema-v3 entities, historical v2 compatibility, slot/protection provenance, evolving-state legality, validation, and serialization.
- [ESPN-to-canonical adapter](docs/ESPN_CANONICAL_ADAPTER.md) — M1.2 retrieval, translation, reconciliation, YAML rule-gap configuration, testing, and live acceptance evidence.
- [Snapshot storage](docs/SNAPSHOT_STORAGE.md) — M1.3 SQLite schema, canonical authority, source evidence, atomic publication, integrity checks, retention, and verification.
- [Agent instructions](AGENTS.md) — standing implementation and verification rules for future Codex work.

The master specification is authoritative. If another document or future implementation conflicts with it, stop and resolve the conflict explicitly rather than silently changing the model.

## Development setup

Python 3.12 is required. From a clean checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --requirement requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --editable .
.\.venv\Scripts\python.exe -m pytest
```

Copy `.env.example` to `.env` and replace its non-secret example values. Private-league credentials must be provided together as `ESPN_S2` and `ESPN_SWID`; configuration fails rather than accepting a partial pair. The `.env` file is ignored by Git.

Run the setup health check after configuration:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football
```

The health check validates configuration and logging only. It performs no ESPN or network access; connectivity begins in M0.2.

## Read-only ESPN connectivity diagnostic

M0.2 provides a read-only diagnostic for league identity, team and player ownership, standings, scoring, and eligible lineup slots:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.espn_connectivity --expected-team-count 14
```

The expected team count is deliberately explicit rather than a hidden league assumption. The command writes a human-readable report and fails on identity, count, ownership, eligibility, standings, scoring, or configured-slot inconsistencies. Add `--json` for the complete machine-readable report, including rostered player IDs. It does not submit transactions or modify ESPN data. Do not commit live reports because they contain league roster details.

M0.3 adds a sanitized aggregate audit of the complete paginated player pool, week-specific projections, byes, and remaining regular-season matchups:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.future_data_audit --expected-team-count 14
```

Add `--json` for aggregate coverage and retrieval context. The diagnostic remains read-only and preserves missing projections separately from explicit zeros.

For a manual ESPN UI comparison, print one named missing, explicit-zero, and positive example for the next fantasy week (or pass `--week` explicitly):

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.projection_ui_reconciliation
```

This output contains player names, player IDs, and fantasy team IDs. It is intended for local review only and must not be committed.

M0.4 adds a sanitized rules and postseason diagnostic. Historical seasons are explicit evidence inputs, not hidden defaults:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.league_rules_audit --expected-team-count 14 --historical-season 2024 --historical-season 2025
```

Add `--json` for the structured sanitized inventory. `--expected-team-count` is an optional identity check, not a supported-league template. Roster slots, playoff qualifiers, byes, round durations, and consolation settings are discovered dynamically. The command is read-only and reports unresolved rules rather than inventing them.

M0.5 adds a bounded historical projection/actual diagnostic. Historical season/week samples must be explicit:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.historical_projection_audit --sample 2024:1 --sample 2024:8 --sample 2024:14 --sample 2024:17 --sample 2025:1 --sample 2025:8 --sample 2025:14 --sample 2025:17
```

Add `--json` for the sanitized aggregate report. The command never imputes missing projections and never treats a returned historical projection as verified pregame merely because ESPN labels it projected. Live output should not be committed.

M0.6 provides a credential-free evidence manifest and reproduction guide. It lists existing diagnostics but deliberately does not execute live ESPN requests:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.m0_verification
.\.venv\Scripts\python.exe -m fantasy_football.m0_verification --check-config --json
```

`--check-config` validates local configuration only. The report always states whether live verification occurred, lists the credential requirements for each diagnostic, and preserves unresolved rules.

M2.3a adds a bounded, read-only undroppable-player evidence diagnostic. The first simulation week is explicit so the audit can reconcile the current player universe against every required future view:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.undroppable_audit --first-simulation-week 8
```

Add `--json` for the sanitized aggregate report. The command reports Boolean coverage only; it does not print player identities, league IDs, manager information, or raw payloads.

## M1.2 live validation

The read-only adapter requires an explicit first fully unplayed scoring week and emits only sanitized aggregate counts:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.espn_adapter --first-simulation-week 8 --expected-team-count 14
```

Schema v2 preserves observed eligibility categories independently of configured playable capacities. The command reports the observed namespace and deterministic canonical checksum.

## Immutable snapshot publication

`SNAPSHOT_DB_PATH` defaults to the ignored private local file `outputs/fantasy_football.sqlite3`. Set it in `.env` or pass `--database` explicitly. Publish one fully retrieved and reconciled snapshot with:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.snapshot_store `
  --first-simulation-week 8 `
  --expected-team-count 14
```

The command performs all ESPN requests before opening one SQLite write transaction, assigns a new UUID, atomically inserts the canonical document and all captured evidence, then reloads and verifies the committed snapshot. A pre-commit failure is reported separately from a post-commit verification failure; the latter prints the permanent committed snapshot ID and is never described as rolled back. Database, WAL, and SHM files are ignored and must remain private.

For programmatic inspection, call `generate_quality_report(snapshot)` from `fantasy_football.quality` on either an adapter candidate or `SnapshotStore.load(id).snapshot`. The immutable report calculates coverage from canonical records and keeps ordinary projection missingness in aggregate metrics. `SnapshotStore.check_database_integrity()` is the explicit database-wide SQLite diagnostic; ordinary snapshot loads perform complete requested-snapshot verification without scanning unrelated rows.

## Snapshot management

All snapshot-management commands are read-only and make no ESPN requests. The global `--database` option may be omitted to use `SNAPSHOT_DB_PATH` from the normal configuration.

List compact metadata newest first, optionally filtering by league and/or season:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.snapshot_cli --database outputs/fantasy_football.sqlite3 list
.\.venv\Scripts\python.exe -m fantasy_football.snapshot_cli --database outputs/fantasy_football.sqlite3 list --league-id 123 --season 2026 --json
```

Inspect an exact UUID, or select the newest snapshot for an explicit league and season:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.snapshot_cli --database outputs/fantasy_football.sqlite3 inspect --snapshot-id 00000000-0000-4000-8000-000000000001
.\.venv\Scripts\python.exe -m fantasy_football.snapshot_cli --database outputs/fantasy_football.sqlite3 inspect --league-id 123 --season 2026 --json
```

Summary inspection is sanitized and contains aggregates, projection coverage, rule limitations, age, horizon, source completeness, and integrity status. Private team/player/roster records and canonical source-request metadata require repeatable explicit detail flags: `--detail teams`, `rosters`, `players`, `projections`, `rules`, `matchups`, `nfl`, or `sources`; `--detail all` requests every supported detail. Raw captured ESPN response bodies are never printed.

Verify one exact or newest-selected snapshot, or explicitly scan the entire database:

```powershell
.\.venv\Scripts\python.exe -m fantasy_football.snapshot_cli --database outputs/fantasy_football.sqlite3 verify --snapshot-id 00000000-0000-4000-8000-000000000001
.\.venv\Scripts\python.exe -m fantasy_football.snapshot_cli --database outputs/fantasy_football.sqlite3 verify --league-id 123 --season 2026 --json
.\.venv\Scripts\python.exe -m fantasy_football.snapshot_cli --database outputs/fantasy_football.sqlite3 verify --database-wide
```

An explicit UUID takes precedence over league/season selectors and never falls back if missing or corrupt. Without a UUID, both league and season are required. Snapshot age is informational and is measured from retrieval completion; an old valid snapshot remains selectable for reproducibility.

## Projected-optimal lineup optimizer

M2.1 exposes `optimize_starting_lineup()` as a programmatic, credential-free reference optimizer. It accepts a validated canonical snapshot, fantasy team ID, scoring week, and optionally a complete validated alternate roster state for a future simulation path:

```python
from fantasy_football.lineup_optimizer import optimize_starting_lineup
from fantasy_football.snapshot_store import SnapshotStore

store = SnapshotStore("outputs/fantasy_football.sqlite3")
snapshot = store.load("00000000-0000-4000-8000-000000000001").snapshot

lineup = optimize_starting_lineup(snapshot, team_id=1, scoring_week=8)
print(lineup.total_projected_points, lineup.assignments, lineup.vacancies)
```

The exact dynamic program expands only ESPN-configured starter capacity, never observed-but-unconfigured eligibility categories. Bench players may start when eligible; reserve/IR occupants and players with nonpositive effective projections may not. Shortages return an explicit best partial lineup with zero-point vacancies. Results are deterministic under reordered inputs, and optimization never refreshes ESPN data or mutates the snapshot.

## Deterministic weekly matchups

M2.2 consumes frozen lineups and caller-supplied realized scores. It resolves only canonical regular-season matchups and returns copied cumulative standings; it does not fetch ESPN data, generate scores, or mutate the snapshot:

```python
from fantasy_football.weekly_engine import (
    RealizedPlayerScore,
    initialize_standings,
    resolve_regular_season_week,
)

standings = initialize_standings(snapshot)
lineups = tuple(optimize_starting_lineup(snapshot, team.team_id, 8) for team in snapshot.teams)
scores = tuple(
    RealizedPlayerScore(player_id, snapshot.season, 8, points)
    for player_id, points in supplied_realized_points.items()
)
transition = resolve_regular_season_week(snapshot, 8, standings, lineups, scores)
```

Assigned starters require finite realized scores; vacancies add zero and negative results remain negative. The current league's confirmed `NONE` rule permits regular-season ties. Ranking uses exact winning percentage and configured total PF for identical records, while unresolved deeper ties remain explicit instead of receiving arbitrary seeds.

M2.3a closes a defensive legality gap: a frozen starter is rejected while their entry in the supplied modeled roster still occupies a configured reserve/IR slot. An explicitly supplied alternate roster may start a formerly reserved player only after that modeled state places the player in an ordinary configured slot. The weekly engine never performs or authorizes IR activation itself.

## Immutable evolving roster state

M2.3b exposes pure transaction-legality primitives in `fantasy_football.evolving_state`. Start a path from a published schema-v3 snapshot and pass the resulting `state.roster_entries` to M2.1 and M2.2:

```python
from fantasy_football.evolving_state import IRPolicy, initialize_evolving_state

state = initialize_evolving_state(
    snapshot,
    scoring_week=snapshot.first_simulation_week,
    ir_policy=IRPolicy.PROJECTION_BASED,
)
lineup = optimize_starting_lineup(
    snapshot,
    team_id=1,
    scoring_week=state.scoring_week,
    roster_entries=state.roster_entries,
)
```

Available primitives cover explicit add, drop, compound replacement, IR placement/activation, waiver-priority transitions, semantically authorized hold release, and cycle advancement. Release authorization is player- and boundary-specific; strict IR evidence is player- and week-specific; and season and matchup-period acquisition limits are counted independently. Directly constructed eligibility claims are rejected: accepted determinations must cross the checksum- and contract-validating evidence boundary. Projection-based IR recovery is explicitly ledger-labeled as an approved simulation assumption, while controlled fixture evidence remains labeled `validated_fixture` rather than verified ESPN evidence. Matchup counters reset only when the canonical matchup period changes, not on every scoring week. These primitives validate legality but never choose a transaction. Raw live `player.droppable` polarity remains unverified against an individual ESPN UI control, so automatic drops from current live-adapter snapshots fail until that interpretation is reviewed or corroborated. Exact ESPN clearance timing and future strict-IR eligibility also remain unresolved because no live evidence provider exists for them. M2.3c valuation and M2.3d cycle orchestration are not implemented.

## Historical implementation

The legacy code is not a foundation for the rebuild. It may be inspected as historical reference, but reuse requires an explicit specification-based justification and independent tests. To inspect it without changing the current branch:

```shell
git show archive/legacy-pre-clean-sheet-2026-10-15:<path>
```

To work with the full archived tree, create a separate worktree or branch from that reference.
