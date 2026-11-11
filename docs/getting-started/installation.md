# Install War Room

This is the current Windows installation path. War Room is local-only and is not formally released; M8.4 release disposition is still pending. Start from the authoritative repository's accepted `main`. Contributors should also follow [CONTRIBUTING](../../CONTRIBUTING.md) and the separate [developer setup](development.md).

## Prerequisites

- Windows with PowerShell 5.1 or 7, Git, and a writable private checkout.
- 64-bit Python 3.12 with the Windows `py` launcher. The inspected contributor environment uses Python 3.12.10.
- Node.js/npm. **Node 24.19.0** is the tested contributor version compatible with the full locked frontend toolchain. The setup script's broader acceptance check does not guarantee compatibility with all test dependencies. This remains [WR-003](../BACKLOG.md#work-items); do not upgrade dependencies or edit the lockfile to work around it.
- Network access to install locked dependencies and sufficient disk space for dependencies, builds and local databases. ESPN access is not required to install or start the application.

## Install from a fresh checkout

Run in PowerShell:

```powershell
git clone https://github.com/tdkelley2001/fantasy_football.git
cd fantasy_football
py -3.12 --version
node --version
npm.cmd --version
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1
```

The per-process execution-policy option does not change machine policy or require administrator access. Respect organizational policy if it prevents execution. Setup creates `.venv`, installs `requirements.lock`, installs the local package with `--no-deps`, uses `npm ci --no-audit --no-fund`, builds `frontend/dist`, creates `outputs/logs` and `outputs/runtime`, and checks the application import. Run commands from the repository root. Close your own Vite processes before rerunning setup because Windows can lock native frontend dependencies.

Setup can be repeated without deleting SQLite data; it reinstalls dependencies and rebuilds assets. Do not run it while another contributor is using this checkout. To check an already prepared environment without reinstalling:

```powershell
.\scripts\setup-local.ps1 -VerifyOnly
```

This still creates the output directories and checks imports/assets; it is not a clean-machine installation test. Optional setup parameters are `-PythonLauncher` and `-VirtualEnvironment`. A custom environment also needs the matching `-PythonExecutable` on start; the default launcher looks in `.venv`.

Next: [configure ESPN](configuration.md), then [launch and run your first analysis](first-run.md). For failures use [operations and troubleshooting](operations.md).

## Verification boundary

R2.2 commands were checked against [setup-local.ps1](../../scripts/setup-local.ps1), [start-local.ps1](../../scripts/start-local.ps1), the [Python metadata](../../pyproject.toml) and [frontend lockfile](../../frontend/package-lock.json). Node 24.19.0 and Python 3.12.10 were observed in the existing environment; all 98 frontend tests passed on that Node version. Prior environment evidence is recorded in the [R1 audit](../R1_REPOSITORY_AUDIT.md). This documentation package did **not** reinstall dependencies, exercise a clean machine, start/stop real application processes or retrieve live ESPN data. Actual R2.2 checks are recorded in the [backlog](../BACKLOG.md#r22-verification-for-review).
