# First launch and analysis

Complete [installation](installation.md) and [configuration](configuration.md) first. These are source-checked procedures, not a claim of a new clean-machine or live-ESPN test.

## Launch

From the repository root:

```powershell
.\scripts\start-local.ps1
```

Wait for the healthy URL printed by the launcher, normally `http://127.0.0.1:8000/`. It serves the built React application and API together; ordinary use needs no Vite server. If the browser does not open, visit the printed URL. Do not expose the service through a public proxy or port forwarding. Use only a trusted local machine.

## Refresh and select a snapshot

1. Open the ESPN refresh control and confirm the configured league, season and public/private access mode. If the profile is unavailable, fix configuration before retrieval.
2. Use automatic safe-week detection by default. Supply an override only when independently supported; it cannot bypass safety validation.
3. Explicitly start the read-only refresh. It retrieves and validates source evidence before publication; it does not change your ESPN league.
4. Review the result, projection coverage, rule limitations and capability findings. A successful publication appends a new immutable snapshot and the UI selects it. Repeated refreshes do not overwrite prior snapshots.
5. Use the snapshot selector to switch to a retained snapshot deliberately. Confirm league, season, retrieval time and simulation horizon before analysis. A new empty store has no snapshot to simulate.

Closing the panel does not cancel server work. Use explicit cancellation when available; publication is an atomic, non-cancellable stage. A post-commit verification error may leave a published snapshot, identified by the result. Follow the error rather than assuming no write occurred.

If evidence cannot establish a safe V1 boundary, stop there. Do not replace missing values with zero, edit the database, choose a later week to evade an unresolved period, or treat opt-in partial-week engine support as an available browser forecast. See [live scoring boundaries](../LIVE_WEEK_SCORING.md) and [current status](../status.md).

## First baseline

Select the intended snapshot, open Simulation Center and choose a bounded Quick baseline. Inspect the effective request and submit. Quick/Balanced/Detailed/Custom describe explicit workloads, not guaranteed runtime or accuracy. Follow progress and inspect the retained result in League Overview: championship, playoff and placement estimates should be read together with sampling intervals, precision and coverage.

## First action analysis

From Simulation Center, configure an action search with explicit finite limits and submit it for the same snapshot. Inspect retained candidates in Opportunity Explorer, including the selected universe, evaluated coverage, stop reason and paired impacts. For a specific proposed exchange, use Trade Lab's explicit multi-team draft and protected pins, review completion/ownership explanations and submit it for comparison. See the [application user guide](../LOCAL_V1_USER_GUIDE.md) for interpretation and workspace details.

These are hypothetical analyses. War Room never submits ESPN trades/claims or estimates manager acceptance/waiver success. Matching draws reduce comparison noise; they do not remove model uncertainty. The projection/outcome model remains provisional. Sampling intervals measure Monte Carlo uncertainty, not model error. A capped, interrupted, cancelled or capability-incomplete result is incomplete; a top displayed candidate need not be the proven global best. A completed run can still miss its precision target.

## Retain and stop

Simulation Center rediscovers retained runs for the selected snapshot. Completed results survive normal restart. Cancellation is cooperative: a batch may finish, and completion may commit before cancellation. Work active at unexpected exit is reconciled as interrupted on restart, not automatically resumed.

```powershell
.\scripts\stop-local.ps1
```

Use the same custom runtime directory if applicable. Do not delete runtime metadata or kill an unverified PID. [Operations and troubleshooting](operations.md) explains authenticated recovery, persistence and privacy.

Source references: [refresh coordinator](../../src/fantasy_football/app/refresh.py), [refresh UI](../../frontend/src/LeagueRefresh.tsx), [application UI](../../frontend/src/App.tsx), [run lifecycle](../RUN_MANAGEMENT.md) and [Simulation Center contract](../M7_5_SIMULATION_CENTER.md). Fixture tests prove behavior; only separately identified live evidence establishes ESPN availability.
