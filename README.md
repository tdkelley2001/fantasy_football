# Fantasy Football Decision Engine

This repository is being reset for a clean-sheet rebuild of a league-wide decision engine for ESPN fantasy football. The intended system will estimate season-outcome distributions and compare roster actions by their effect on championship probability while honoring real league rules, uncertainty, and full-league consequences.

## Current status

M0, the ESPN data and feasibility audit, is in progress. M0.1 through M0.4 are **COMPLETE**; M0.5 and all later work packages remain **NOT STARTED**. The former application, research artifacts, and tests remain recoverable from the archival Git reference `archive/legacy-pre-clean-sheet-2026-10-15`.

## Authoritative documentation

- [Master specification](docs/MASTER_SPEC.md) — the complete approved model specification and governing requirements.
- [Development roadmap](docs/ROADMAP.md) — the M0-M7 milestone sequence, individual work packages, dependencies, gates, and current statuses.
- [M0.2 ESPN connectivity findings](docs/ESPN_CONNECTIVITY.md) — sanitized live-access evidence, field provenance, validation results, and deferred questions.
- [M0.3 future player-week findings](docs/ESPN_FUTURE_DATA_AUDIT.md) — projection, player-pool, bye, schedule, pagination, and provenance evidence.
- [Missing projection policy](docs/MISSING_PROJECTION_POLICY.md) — approved raw-versus-effective representation, week 6 evidence, methodology, and limitations.
- [M0.4 league-rules audit](docs/ESPN_LEAGUE_RULES_AUDIT.md) — roster/IR, waiver, trade, standings, championship, consolation, provenance, and explicit configuration gaps.
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
.\.venv\Scripts\python.exe -m fantasy_football.league_rules_audit --expected-team-count 14 --expected-playoff-team-count 6 --historical-season 2024 --historical-season 2025
```

Add `--json` for the structured sanitized inventory. The command is read-only and reports unresolved rules rather than inventing them.

## Upcoming work package

After M0.4 review, M0.5 is next: audit historical pregame projection availability, provenance, and calibration feasibility. M0.4's unresolved tie, multiple-waiver-claim, and eight-team consolation rules remain explicit inputs to the later M0.6 go/no-go decision.

## Historical implementation

The legacy code is not a foundation for the rebuild. It may be inspected as historical reference, but reuse requires an explicit specification-based justification and independent tests. To inspect it without changing the current branch:

```shell
git show archive/legacy-pre-clean-sheet-2026-10-15:<path>
```

To work with the full archived tree, create a separate worktree or branch from that reference.
