# Operate and troubleshoot War Room

Use [configuration](configuration.md) for precedence and path selection, [first run](first-run.md) for the normal workflow and [developer setup](development.md) for tests. This guide describes current source behavior; historical process/recovery evidence remains in [M8.3](../M8_3_RUNTIME_AND_RECOVERY.md).

## Know where data lives

| Default path | Purpose |
|---|---|
| `outputs/fantasy_football.sqlite3` | Immutable canonical snapshots and captured source evidence. Launcher `-Database`/`WAR_ROOM_DATABASE` selects it. |
| `outputs/fantasy_football.runs.sqlite3` | Adjacent durable run requests, lifecycle, results and lease state. Derived from the chosen snapshot path, not independently selected by the launcher. |
| `outputs/logs/war-room-<run-id>.stdout.log` and `.stderr.log` | Per-launch server output/error logs. |
| `outputs/runtime/war-room-server.json` | Launcher ownership/command/health identity and configured paths. |
| `outputs/runtime/war-room-shutdown.txt` | Run-specific cooperative shutdown control. |
| `frontend/dist` | Generated application build, not private analytical persistence. |

The SQLite databases can also have WAL/SHM sidecars. Browser snapshot selection is stored in localStorage; clearing browser storage does not delete server snapshots/results. Refresh appends snapshots; selecting another snapshot does not mutate the previous one. Run retention is governed separately by application policy, not a promise that every old result is kept forever.

Keep `.env`, rule files, databases/sidecars, private reports, research rows, checkpoints, logs and runtime data private and out of Git. Default output directories are ignored; custom paths need equivalent protection. Review staged filenames before committing; redact evidence before sharing. Back up both databases using SQLite-safe practices while the application is stopped. Do not edit snapshots, delete a live lease or copy an actively written SQLite file as a recovery shortcut.

## Shutdown and recovery

Use `.\scripts\stop-local.ps1`, with matching `-RuntimeDirectory` if customized. It authenticates the recorded process (PID, creation time, interpreter and exact command identity), and listener/health identity while available, then requests graceful shutdown. If the default 20-second timeout expires, ordinary stop performs authenticated recovery of only the verified launcher-owned process tree. It preserves the databases and completed results; unfinished durable runs are reconciled on restart.

For diagnosis, `.\scripts\stop-local.ps1 -PreserveOnTimeout` leaves the authenticated process alive on timeout. Rerun ordinary stop when ready to recover. Start can recognize an already healthy owned instance; if its listener has closed while the process is still alive it directs you to stop/recovery. A foreign port owner or unverifiable process fails closed. Never delete metadata to bypass checks, manually kill a guessed PID or terminate another contributor's service. If ownership cannot be established, retain evidence and seek diagnosis; an OS restart is safer than guessing a process identity.

## Common failures

| Symptom | Next step |
|---|---|
| Python missing/wrong version | Install 64-bit Python 3.12 with `py`; verify `py -3.12 --version`, then rerun setup. |
| npm engine/import/test failure | Check `node --version`; use the tested Node 24.19.0 for the full lockfile. WR-003 remains open. Do not loosen lockfiles or use forced installs. |
| Windows npm native-file lock | Close your own Vite/test processes normally, then rerun setup. Do not kill unknown processes. |
| Missing `.venv` or frontend assets | Run setup from the checkout; `-VerifyOnly` checks but does not install/build. A custom venv requires matching `-PythonExecutable`. |
| Port occupied | Use `-Port` or `WAR_ROOM_PORT` for an available loopback port, or stop the verified owned instance. No foreign process should be terminated. |
| Readiness timeout | Read the printed per-launch stdout/stderr logs locally. Use launcher recovery if its authenticated process is still alive; do not blindly delete metadata. |
| Refresh profile unavailable | Ensure `.env` exists, IDs are positive integers, credentials form a complete pair, inherited settings are intended and manual YAML matches league/season. Secrets are deliberately absent from the profile/error response. |
| Access denied or expired session | Recheck authorized league visibility and paired credentials locally. Never share cookies or run live diagnostics as routine tests. |
| Unsupported boundary/rule/capability | Read the reported gap and configuration/source contracts. Do not infer completion from time or invent a rule. A published snapshot can still lack a capability required for analysis. |
| Empty selector / `snapshot_not_found` | Check launcher database path and league/season. An empty store needs an authorized refresh or isolated synthetic test; `.env`'s CLI path may point elsewhere. |
| Unwritable path / `background_store_in_use` | Choose a private writable location; stop the other verified instance using that run store. Never delete a live lease. |
| `resource_exhausted` / slow analysis | Inspect concurrency, storage and resource budgets; reduce explicitly selected work where appropriate. A page-size limit does not bound computation. Report capped work as incomplete. |
| Stalled cancellation / `interrupted` | Cancellation is cooperative and synchronous retrieval can stall. Use authenticated stop/recovery; restart retains completed results but does not resume background work automatically. |
| Invalid Host / untrusted Origin | Use the printed loopback URL or documented Vite proxy. Do not widen network security checks. |

The service has no user accounts or remote authentication. Loopback/Host/Origin protections do not isolate it from other local processes on the trusted machine. Public hosting, port forwarding and untrusted shared-machine use are unsupported.

## Remaining onboarding limits

WR-003's installer/locked-toolchain version-policy mismatch remains unresolved. Fresh-machine acceptance remains separately gated in WR-021. New installations have no bundled persistent demo snapshot; credential-free tests provide temporary synthetic stores, not an automatic browser demo. Live safe-week evidence, unsupported league mechanics and projection gaps can block a first real analysis even when installation succeeds. See [status](../status.md) and [backlog](../BACKLOG.md); R2.2 does not remove those blockers or promote provisional models.

Source checks: [start](../../scripts/start-local.ps1), [stop](../../scripts/stop-local.ps1), [ownership helpers](../../scripts/local-runtime.ps1), [HTTP persistence wiring](../../src/fantasy_football/app/http.py), [snapshot store](../../src/fantasy_football/snapshot_store.py), [run management](../RUN_MANAGEMENT.md). No real-process or destructive database test was executed for R2.2.
