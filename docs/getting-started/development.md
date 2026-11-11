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

From the repository root after dependencies are installed:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_documentation_links.py tests/test_contributor_documentation.py tests/test_repository_security.py -q -p no:cacheprovider
.venv\Scripts\python.exe -m pytest -m "not windows_process"
.venv\Scripts\python.exe -m ruff check --select E9,F63,F7,F82 .
.venv\Scripts\python.exe -m pip check
git diff --check
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
```

Choose the relevant tier for the changed area and report actual commands/results. The broad Python tier uses mocks, synthetic fixtures and temporary stores; it excludes marked real Windows process tests. It does not validate live ESPN. Frontend typecheck/build can generate local metadata/assets. Keep generated output out of the PR. Use the narrow Ruff gate above rather than imposing a repository-wide style rewrite.

The [release verification script](../../scripts/verify-release.ps1) additionally runs a **networked npm audit**. Its `-IncludeWindowsProcessTests` option intentionally controls disposable real processes. Live diagnostics/refresh, real-process shutdown/recovery and destructive database exercises require separately explicit scope. Historical browser captures may drive live refresh and assume a fixed Edge executable; do not run them as routine credential-free checks. `playwright-core` does not install a browser. See [release checks](../RELEASE_CHECKLIST.md).

## Safe synthetic work

Use the existing sanitized fixture modules [adapter_fixtures.py](../../tests/adapter_fixtures.py) and [canonical_fixtures.py](../../tests/canonical_fixtures.py) inside tests. For a concrete temporary-store/refresh exercise:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_snapshot_refresh.py -q -p no:cacheprovider
```

That module injects synthetic adapter/settings dependencies and uses pytest temporary paths; it does not require `.env`, live retrieval or your default database. Add focused tests following that pattern and inspect injected boundaries before extending them. Never label fixture probabilities or synthetic ESPN fields as **Verified live**. There is no installed persistent demo loader; a blank browser database is expected until an authorized real refresh or separately approved fixture workflow. Do not publish a fixture into a contributor's private store or copy private payloads into tests just to populate the UI.

## Troubleshooting and evidence

Use [operations](operations.md#common-failures) for Python/Node, port, ownership, path and configuration failures. For a dependency failure, verify interpreter/version and rerun locked setup; preserve the error instead of bypassing engines or updating locks. For missing snapshots, confirm the exact backend database before considering retrieval. API shape is exposed by local `/docs` and `/openapi.json`; credentials are unnecessary to inspect it.

Source checks: [setup script](../../scripts/setup-local.ps1), [server](../../src/fantasy_football/app/server.py), [frontend scripts](../../frontend/package.json), [Vite config](../../frontend/vite.config.ts), [pytest markers](../../pyproject.toml) and [synthetic refresh tests](../../tests/test_snapshot_refresh.py). R2.2 exercised only the checks recorded in the [backlog](../BACKLOG.md#r22-verification-for-review); installation, Vite, browser flow, full regression and fresh-machine procedures above were source-verified, not newly executed. No dependency, configuration or runtime behavior changes are part of this package.
