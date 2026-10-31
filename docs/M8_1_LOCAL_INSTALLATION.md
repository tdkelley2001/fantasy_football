# M8.1 local installation and operation

Status: **IMPLEMENTED — REVIEW PENDING** (31 October 2026).

M8.1 supplies one loopback-only FastAPI/Uvicorn process for API 1.0 and the
compiled React application. It does not perform ESPN retrieval, real-league
validation, or final release acceptance.

## Setup

Windows PowerShell 5.1 or 7, 64-bit Python 3.12 with the `py` launcher, and
Node.js 20 or newer with npm are required. Administrator rights, permanent PATH
or execution-policy changes, and ESPN credentials are not required.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1
```

Setup creates `.venv`, installs `requirements.lock`, installs the local package
without resolving dependencies, runs `npm ci`, builds `frontend/dist`, creates
private writable directories, and verifies the application import and build.
Repeating setup does not delete SQLite data. `-VerifyOnly` runs post-install
checks without installing.

## Start and stop

```powershell
.\scripts\start-local.ps1
.\scripts\stop-local.ps1
```

Start resolves paths from the repository, uses `.venv`, starts one hidden
loopback process, waits for `/api/v1/health`, then opens
`http://127.0.0.1:8000/`. `-NoBrowser` suppresses browser launch. A browser
failure leaves the healthy service available at the printed URL.

Stop validates the launcher-owned PID and process start time, then writes a
run-specific cooperative shutdown request. Uvicorn completes its lifespan so
the background coordinator releases its SQLite lease. Active analyses do not
continue after process shutdown; durable metadata classifies interruption on
the next start. A timeout leaves the process untouched for diagnosis. No
unrelated port owner is terminated.

Launcher metadata lives at `outputs/runtime/war-room-server.json`; it contains
no credentials. Dead-PID metadata is removed as stale. A live unhealthy record
fails closed. A second start returns the healthy existing URL.

## Configuration and persistence

Parameters override environment variables, which override these defaults:

| Setting | Environment | Default |
| --- | --- | --- |
| port | `WAR_ROOM_PORT` | `8000` |
| snapshot database | `WAR_ROOM_DATABASE` | `outputs/fantasy_football.sqlite3` |
| frontend build | `WAR_ROOM_FRONTEND` | `frontend/dist` |
| logs | `WAR_ROOM_LOG_DIRECTORY` | `outputs/logs` |

```powershell
$env:WAR_ROOM_PORT = "8123"
$env:WAR_ROOM_DATABASE = "D:\Private Fantasy Data\league.sqlite3"
.\scripts\start-local.ps1
```

The accepted run database remains adjacent as `league.runs.sqlite3`. Existing
`BackgroundRunPolicy` limits are unchanged. Launcher settings are application
runtime configuration, not canonical league rules. Build provenance continues
through the accepted package and `FANTASY_FOOTBALL_BUILD_REVISION` contract.

The server has no public-bind option: it always uses `127.0.0.1`. Static routes
expose only `frontend/dist/index.html` and files under `frontend/dist/assets`.
Missing assets and invalid API routes return 404. Source, `.env`, databases,
configuration, and arbitrary filesystem paths are not exposed. Production
source maps are not enabled.

ESPN credentials remain optional for installation/startup and stay in ignored
local configuration for separate authorized retrieval. Launcher output and
logs never dump environment values or ESPN payloads.

## Troubleshooting and development

- Missing/incompatible Python or Node, incomplete assets, unwritable storage,
  occupied ports, and health failures terminate with actionable messages.
- On Windows, close any running Vite/frontend process before setup. `npm ci`
  intentionally fails if such a process locks a native dependency; close it
  and rerun rather than bypassing the lockfile workflow.
- Per-run stdout/stderr logs are under `outputs/logs`.
- Re-run setup after dependency or frontend changes; persisted data remains.
- Development may still run Vite with its accepted proxy. Ordinary use does
  not require Vite.
- M8.1 introduces no database migration.

Credential-free verification covers route isolation, missing assets/builds,
loopback binding, actual health, duplicate starts, port conflicts, cooperative
stop/restart, spaced paths, and persistence. Full Python and frontend suites,
production build, static checks, dependency consistency, documentation links,
and a production-origin browser smoke capture form the review evidence. The
[M8.1 production-local capture](images/m8-1/production-local-sanitized-1440x1000.png)
shows the actual FastAPI-served build connected to API 1.0, a selected persisted
sanitized snapshot, Simulation Center navigation, and the expected no-run state;
it contains no fabricated analytics.

M8.2 owns live ESPN workflow validation, M8.3 owns sustained resource and
recovery certification, and M8.4 owns final security and release acceptance.
