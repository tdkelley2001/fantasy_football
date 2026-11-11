# Configure ESPN and local storage

Run from the repository root. Installation and startup need no league credentials; browser refresh needs a valid configured profile. War Room retrieves ESPN data **read-only** and never submits transactions.

## League profile

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edit the ignored `.env` locally. Do not paste its contents into logs, commits or review discussions.

| Key | Actual requirement |
|---|---|
| `ESPN_LEAGUE_ID` | Required positive integer; replace the example placeholder with your ESPN league ID. |
| `ESPN_SEASON` | Required positive integer identifying the intended season, not an inferred current year. Downstream validation can reject unsupported seasons/data. |
| `ESPN_S2`, `ESPN_SWID` | Leave both blank for public access. Private access requires both values from your authorized ESPN session. One without the other is invalid; expired credentials can still fail retrieval. |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`; defaults to `INFO`. |
| `SNAPSHOT_DB_PATH` | Python settings/CLI snapshot path; defaults to `outputs/fantasy_football.sqlite3`; an empty value is invalid. It does **not** configure launcher storage. |
| `FANTASY_FOOTBALL_RULE_CONFIG_PATH` | Optional browser-refresh manual-rule YAML path. See below. |

[load_settings](../../src/fantasy_football/config.py) reads `.env` from the working directory, then overlays the process environment, including empty values. The default `.env` must exist when settings are loaded. Starting the server can succeed without it, but refresh/profile loading fails closed. Restart after intentional configuration changes for a predictable workflow. An inherited process variable can override an edited `.env`; check variable names locally without sharing secret values.

## Launcher paths and precedence

The PowerShell launcher does **not** read `.env` for its own settings. Explicit parameters override **process-environment** variables, which override these defaults:

| Start parameter | Process variable | Default |
|---|---|---|
| `-Port` | `WAR_ROOM_PORT` | `8000` |
| `-Database` | `WAR_ROOM_DATABASE` | `outputs\fantasy_football.sqlite3` |
| `-Frontend` | `WAR_ROOM_FRONTEND` | `frontend\dist` |
| `-LogDirectory` | `WAR_ROOM_LOG_DIRECTORY` | `outputs\logs` |
| `-RuntimeDirectory` | `WAR_ROOM_RUNTIME_DIRECTORY` | `outputs\runtime` |

Relative launcher paths resolve from the repository, even when the script is invoked elsewhere; the child server also runs from the repository. `-PythonExecutable` defaults to `.venv\Scripts\python.exe`; `-NoBrowser` suppresses browser opening and `-ReadinessTimeoutSeconds` defaults to 30. Start refuses an occupied foreign port or an already running instance with different paths. Stop before changing paths.

For example, with a private writable directory you control:

```powershell
.\scripts\start-local.ps1 -Port 8123 -Database "D:\Private Fantasy Data\league.sqlite3" -NoBrowser
# Open http://127.0.0.1:8123/ yourself.
.\scripts\stop-local.ps1
```

`-RuntimeDirectory` must also be supplied to **stop** if customized, or set the same `WAR_ROOM_RUNTIME_DIRECTORY` in that shell. Port and database are recovered from authenticated runtime metadata, not stop parameters. Keep one distinct runtime directory per deliberately separate instance.

The Python server's `--database` default is a literal path, not `SNAPSHOT_DB_PATH`. The launcher passes its selected `-Database` as `--database`. In contrast, the publication/inspection CLIs use `--database` when supplied, otherwise settings' `SNAPSHOT_DB_PATH`. Relative Python database paths resolve from the working directory. If using both browser and CLI, explicitly point them to the same private file; changing `.env` alone does not move launcher data. The adjacent run store is derived with `Path(database).with_suffix('.runs.sqlite3')`: `league.sqlite3` becomes `league.runs.sqlite3`.

## Manual league rules

Some capabilities require independently supported rules that ESPN does not expose sufficiently. Consult the reported rule gap and [configuration audit](../LEAGUE_CONFIGURATION_AUDIT.md) / [adapter manual-config contract](../ESPN_CANONICAL_ADAPTER.md). Do not copy fixture league rules into your league or invent missing values.

For browser refresh, put an independently reviewed YAML file at an ignored path such as `config/league_rules.local.yaml`, set `FANTASY_FOOTBALL_RULE_CONFIG_PATH` to that path and restart. Relative rule paths resolve from the working directory used by settings (the repository under the launcher), **not** the `.env` file's parent. `GET /api/v1/refresh/profile` reports `manual_rule_configuration_available: true` only after the configured file parses and validates for the configured league/season. This is not proof that a rule was applied: inspect the published snapshot's rule provenance and capabilities.

The `espn_adapter` and `snapshot_store` CLIs take **`--manual-config` explicitly**. They do not substitute `FANTASY_FOOTBALL_RULE_CONFIG_PATH` for that argument. This difference is intentional documentation of current code, not a new precedence policy.

## Simulation start week

Browser refresh defaults to **automatic safe-week detection**; an optional explicit override is still checked against authoritative live scoring evidence. Completion is not inferred from kickoff timestamps or your computer's date. Unsupported current-period membership/carry or unresolved standings evidence fails closed. An override cannot turn a live or otherwise unsafe week into a valid V1 boundary.

The `python -m fantasy_football.espn_adapter` diagnostic and `python -m fantasy_football.snapshot_store` publication CLI each require `--first-simulation-week` explicitly. They still enforce safety. These commands retrieve live data; run them only with separately authorized scope. The adapter diagnostic validates in memory; the store command publishes atomically and verifies the committed snapshot. A post-commit verification failure means publication may already exist: do not assume every reported failure rolled back or delete a database to retry.

Invalid configuration can prevent refresh; structurally valid but unsupported league semantics can prevent specific analyses. Inspect errors and [current capabilities](../status.md); manual configuration cannot authorize unsupported modeling. Missing projections, confirmed zero scores and policy-imputed zeroes remain different. See [first run](first-run.md) and [safe operation](operations.md).

Source checks: [config.py](../../src/fantasy_football/config.py), [refresh.py](../../src/fantasy_football/app/refresh.py), [server.py](../../src/fantasy_football/app/server.py), [HTTP store wiring](../../src/fantasy_football/app/http.py), [adapter](../../src/fantasy_football/espn_adapter.py), [publication CLI](../../src/fantasy_football/snapshot_store.py) and [inspection CLI](../../src/fantasy_football/snapshot_cli.py). These checks do not establish new **Verified live** ESPN capabilities.
