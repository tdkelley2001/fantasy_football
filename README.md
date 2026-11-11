# War Room

War Room is a local web application for ESPN fantasy football analysis. It preserves league snapshots, simulates league-wide season outcomes and compares roster changes by their effect on championship probability.

## What you can do

- Explore championship, playoff and placement estimates with Monte Carlo sampling intervals and explicit precision/completeness information.
- Compare multi-team trade scenarios and search selected trade, acquisition and combined-action universes using matched player-week draws.
- Inspect configured league rules, immutable source snapshots and retained analysis results through League Overview, Opportunity Explorer, Trade Lab and Simulation Center.

ESPN access is **read-only**: War Room **never submits real transactions** or predicts whether another manager will accept a trade or a waiver claim will succeed.

## Current scope and limitations

War Room is **not formally released**. The final M8.4 release decision remains pending. See [current capabilities](docs/status.md) for the supported, provisional, engine-only and deferred features.

The application is loopback-only and assumes a trusted local machine. Do not expose it through port forwarding or a public proxy. ESPN projections are inputs to provisional outcome models, not guarantees; sampling intervals do not measure model error. Missing projections, explicit zeros and unsupported league mechanics remain distinct and visible.

Ordinary V1 simulation requires a verified safe whole-week boundary. Opt-in partial-week foundations and fully unstarted Monte Carlo integration are engine-only; they do not enable automatic in-game forecasts, live-week lineup advice or current-week transaction recommendations. Source evidence and permissions fail closed when unverified.

## Requirements and quick start

The supplied launchers target Windows with PowerShell 5.1 or 7, 64-bit Python 3.12 with the `py` launcher, Git and Node.js/npm. Node 24.19.0 was verified in the existing contributor environment. The installer currently accepts a wider Node range than the complete locked test toolchain supports; see [contributor requirements](CONTRIBUTING.md#development-environment-and-checks) and WR-003 in the [backlog](docs/BACKLOG.md#work-items).

From a fresh checkout:

```powershell
git clone https://github.com/tdkelley2001/fantasy_football.git
cd fantasy_football
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edit the ignored `.env` with your `ESPN_LEAGUE_ID` and `ESPN_SEASON`. Public leagues need no cookies; private leagues require both `ESPN_S2` and `ESPN_SWID`. Never commit credentials, private reports, databases or user results. Installation and application startup themselves require no ESPN credentials.

```powershell
.\scripts\start-local.ps1
# Later, stop the launcher-owned application:
.\scripts\stop-local.ps1
```

Open `http://127.0.0.1:8000/`. The application serves the built frontend; no separate Vite server is needed for ordinary use. Refresh the configured league explicitly, select a snapshot, then submit a baseline or action analysis in Simulation Center. Automatic boundary detection can reject a live/unsettled week; a manual override cannot bypass that safety contract.

For configuration, snapshot selection, interpretation, cancellation and authenticated recovery, use the [application user guide](docs/LOCAL_V1_USER_GUIDE.md) and [installation reference](docs/M8_1_LOCAL_INSTALLATION.md). Launcher storage uses `WAR_ROOM_DATABASE`/`-Database`; Python settings/CLIs use `SNAPSHOT_DB_PATH`. The [contributor guide](CONTRIBUTING.md) records this distinction and the verification commands.

## Documentation and contribution

- [Documentation index](docs/index.md) — start here for guides, architecture, API/domain references, research and evidence.
- [Contributing](CONTRIBUTING.md) — feature branches in the original repository or retained fork, safe synchronization, reviewed PRs and checks.
- [Development backlog](docs/BACKLOG.md) — the authoritative list of outstanding work; a proposal is not implementation approval.
- [Current capabilities](docs/status.md) — what is supported today and what remains provisional or unavailable.
- [Master specification](docs/MASTER_SPEC.md) — approved analytical requirements, modeling contracts and architecture.
- [Historical roadmap](docs/ROADMAP.md) — preserved milestones, dependencies and acceptance gates, not an active work queue.
- [Historical development records](docs/index.md#historical-development-records) — audits, source observations and visual/runtime evidence retained at their original paths.

Keep changes small and use a reviewed pull request into `tdkelley2001/fantasy_football:main`. The repository-native backlog is maintained through those PRs; no Issues/Projects workflow is required.
