# Fantasy Football Decision Engine

This repository is being reset for a clean-sheet rebuild of a league-wide decision engine for ESPN fantasy football. The intended system will estimate season-outcome distributions and compare roster actions by their effect on championship probability while honoring real league rules, uncertainty, and full-league consequences.

## Current status

M0 is **COMPLETE**. M1 is in progress: M1.1's schema-v2 canonical contracts, M1.2's live-accepted ESPN adapter, and M1.3's immutable SQLite snapshot persistence are complete. M1.4 and later work packages remain **NOT STARTED**. Simulator-specific rule gaps remain preserved without defaults. The former application, research artifacts, and tests remain recoverable from the archival Git reference `archive/legacy-pre-clean-sheet-2026-10-15`.

## Authoritative documentation

- [Master specification](docs/MASTER_SPEC.md) — the complete approved model specification and governing requirements.
- [Development roadmap](docs/ROADMAP.md) — the M0-M7 milestone sequence, individual work packages, dependencies, gates, and current statuses.
- [M0.2 ESPN connectivity findings](docs/ESPN_CONNECTIVITY.md) — sanitized live-access evidence, field provenance, validation results, and deferred questions.
- [M0.3 future player-week findings](docs/ESPN_FUTURE_DATA_AUDIT.md) — projection, player-pool, bye, schedule, pagination, and provenance evidence.
- [Missing projection policy](docs/MISSING_PROJECTION_POLICY.md) — approved raw-versus-effective representation, week 6 evidence, methodology, and limitations.
- [M0.4 league-rules audit](docs/ESPN_LEAGUE_RULES_AUDIT.md) — roster/IR, waiver, trade, standings, championship, consolation, provenance, and explicit configuration gaps.
- [M0.5 historical projection audit](docs/ESPN_HISTORICAL_PROJECTION_AUDIT.md) — bounded historical coverage, projection/actual matching, as-of integrity, leakage risks, and M3 feasibility.
- [ESPN data dictionary](docs/ESPN_DATA_DICTIONARY.md) — proposed M1 logical fields, raw paths, identifier namespaces, transformations, evidence, and validation tiers.
- [M0 feasibility and M1 handoff](docs/M0_FEASIBILITY_AND_M1_HANDOFF.md) — readiness matrix, rule-gap register, approved forecast/calibration policies, and the M1 recommendation.
- [Canonical model](docs/CANONICAL_MODEL.md) — M1.1 schema-v2 entities, slot namespaces, identifiers, ownership and projection contracts, validation boundary, serialization, and deferred work.
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

The command performs all ESPN requests before opening one SQLite write transaction, assigns a new UUID, atomically inserts the canonical document and all captured evidence, then reloads and verifies the committed snapshot. Database, WAL, and SHM files are ignored and must remain private. This is the minimal M1.3 publication workflow, not the M1.5 snapshot-management interface.

## Historical implementation

The legacy code is not a foundation for the rebuild. It may be inspected as historical reference, but reuse requires an explicit specification-based justification and independent tests. To inspect it without changing the current branch:

```shell
git show archive/legacy-pre-clean-sheet-2026-10-15:<path>
```

To work with the full archived tree, create a separate worktree or branch from that reference.
