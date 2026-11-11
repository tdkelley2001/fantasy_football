# Developer setup and local verification

Follow [CONTRIBUTING](../../CONTRIBUTING.md) for branch/fork synchronization and reviewed PRs. The governing contracts remain [MASTER_SPEC sections 2–3](../MASTER_SPEC.md#2-system-architecture-and-execution-lifecycle): keep engine, presentation, network retrieval and immutable persistence boundaries separate. Use the [backlog](../BACKLOG.md), not historical milestones, to agree scope.

## Locked environment

Use Windows, PowerShell, Python 3.12 and **Node 24.19.0** for the full locked toolchain. The existing environment reports Python 3.12.10 and Node 24.19.0; the [R1 audit](../R1_REPOSITORY_AUDIT.md) records prior verification. WR-003 remains the broader installer version-policy mismatch. Do not regenerate locks, update versions or use `pip install -e ".[app,test]"` with fresh dependency resolution as an incidental setup fix.

The normal [installation command](installation.md#install-from-a-fresh-checkout) runs these dependency/build operations. For a contributor who needs to perform them explicitly, from the repository root:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.lock
.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-deps -e .
npm.cmd --prefix frontend ci --no-audit --no-fund
npm.cmd --prefix frontend run build
```

No activation script is required when using the explicit interpreter path. Installation needs network access unless dependencies are already cached; `--no-audit` does not make installation offline. Close your own Vite processes before `npm ci` on Windows. Setup/import/build success is not clean-machine, live-data or release acceptance.

## Backend and Vite

For ordinary built-frontend use, use [start/stop launchers](first-run.md). For interactive development, run the backend in a foreground terminal against a **separate private development path**:

```powershell
.venv\Scripts\python.exe -m fantasy_football.app.server --database outputs/dev/league.sqlite3 --port 8000
```

It serves `frontend/dist` by default, so build first. This command uses its explicit path, not `.env`'s `SNAPSHOT_DB_PATH`, and is not owned by the PowerShell launcher. Keep the terminal and stop it with Ctrl+C; do not point launcher-stop at this process. Cooperative shutdown can wait on running work. Avoid starting live refresh or long jobs merely to check a UI change.

In a second terminal:

```powershell
npm.cmd --prefix frontend run dev
```

Open the printed Vite loopback URL (normally `http://127.0.0.1:5173/`). [vite.config.ts](../../frontend/vite.config.ts) proxies relative `/api` requests to `http://127.0.0.1:8000` without changing Origin. For a deliberately different backend port, set `$env:VITE_API_TARGET = "http://127.0.0.1:8123"` in the Vite terminal before starting it and use `--port 8123` on the backend. Vite may choose another port if 5173 is occupied; use its printed URL. Do not widen Host/Origin guards or bind to a public interface. Stop Vite with Ctrl+C in its own terminal. Never mix foreground and launcher ownership assumptions.

## Credential-free checks

Use the consolidated [verification guide](../development/verification.md) for fast checks, targeted modules, broader Python/frontend regressions, the networked release gate and explicitly authorized integration tiers. Its [change matrix](../development/verification.md#change-based-verification-matrix) maps subsystem changes to compatibility, reference/golden, worker/batch, checkpoint/resume and privacy checks. Existing acceptance gates remain binding; report actual commands, results and exclusions.

Build/typecheck can generate assets/metadata. The full release script includes a **networked npm audit**. Live ESPN, actual browser/clean-machine integration and Windows process/recovery need explicit scope; never use another contributor's private data or terminate an unverified process. These warnings and exact commands are maintained in the verification guide rather than duplicated here.

## Safe synthetic work

Follow [credential-free synthetic verification](../development/verification.md#tier-3-credential-free-regression) using existing fixture modules and temporary stores. Never treat synthetic records/probabilities as live evidence, publish a fixture into a private store or run historical browser captures as ordinary tests. There is no installed persistent demo loader.

## Troubleshooting and evidence

Use [operations](operations.md#common-failures) for Python/Node, port, ownership, path and configuration failures. For a dependency failure, verify interpreter/version and rerun locked setup; preserve the error instead of bypassing engines or updating locks. For missing snapshots, confirm the exact backend database before considering retrieval. API shape is exposed by local `/docs` and `/openapi.json`; credentials are unnecessary to inspect it.

Source checks: [setup script](../../scripts/setup-local.ps1), [server](../../src/fantasy_football/app/server.py), [frontend scripts](../../frontend/package.json), [Vite config](../../frontend/vite.config.ts), [pytest markers](../../pyproject.toml) and [synthetic refresh tests](../../tests/test_snapshot_refresh.py). Historical R2.2 execution evidence remains in the [backlog](../BACKLOG.md#r22-verification-for-review). Use the [verification guide](../development/verification.md) for current check selection and side effects. Setup/Vite/browser/fresh-machine procedures were source-checked, not newly exercised by R2.4; no runtime or dependency change is part of this consolidation.
