# War Room Local V1 User Guide

War Room is a locally hosted fantasy-football analysis web application. It reads an ESPN league, preserves immutable local snapshots, simulates complete league outcomes, and compares explicit roster actions. It does not submit transactions to ESPN, predict whether another manager will accept a trade, or guarantee an outcome.

## Before you start

Use the current [installation](getting-started/installation.md), [configuration](getting-started/configuration.md), [first-run walkthrough](getting-started/first-run.md) and [operations/troubleshooting](getting-started/operations.md) guides. They are the single current path for prerequisites, public/private ESPN setup, launcher storage, refresh, snapshot selection and safe shutdown. Contributors use [developer setup](getting-started/development.md).

Launcher storage uses `WAR_ROOM_DATABASE`/`-Database`; `SNAPSHOT_DB_PATH` controls Python settings/CLI defaults and does not move launcher data. Browser refresh uses automatic safe-week detection by default; an optional override cannot bypass live-evidence validation. The adapter/publication CLIs require an explicit week and `--manual-config` for manual rules; browser rules instead resolve the settings path. See the configuration guide for exact precedence.

Installation/startup needs no ESPN credentials. Refresh requires the configured league/season and, for private access, a complete credential pair. Publication appends immutable snapshots; inspect capability findings before analysis. Never guess a rule or bypass an unresolved scoring boundary.

## Configure ESPN access

Follow [current configuration](getting-started/configuration.md#league-profile) for the public/private profile and [manual-rule guidance](getting-started/configuration.md#manual-league-rules). This heading is retained for existing bookmarks; setup instructions are maintained in the consolidated guide.

## Refresh and select a league snapshot

Follow [the first-run snapshot steps](getting-started/first-run.md#refresh-and-select-a-snapshot), including automatic boundary validation, immutable publication and explicit snapshot selection. This heading remains available for existing bookmarks.

## Run and interpret analyses

### League Overview and baseline

Select a snapshot, open Simulation Center, choose Quick, Balanced, Detailed, or Custom, inspect the effective request, and submit a baseline. These names describe relative bounded workloads, not promised runtime or precision. League Overview displays retained championship, playoff, and placement estimates with confidence intervals when available.

### Opportunity Explorer

Submit an action search from Simulation Center. Opportunity Explorer reads the retained result and exposes bounded pages of trade, acquisition, chain, and combined-action candidates. Candidate coverage, evaluated-state coverage, transaction caveats, statistical competitiveness, and ranking resolution are separate facts. A top displayed candidate is not necessarily a proven global best.

### Trade Lab

Build an explicit multi-team exchange, pin players that automatic completion must retain, review the chronological draft, and submit it. The engine validates final ownership, performs the approved deterministic capacity/drop/refill completion, and compares baseline and scenario paths with matched player-week draws. Structural hypothetical feasibility is not proof that ESPN would execute every intermediate step or that another manager would agree.

### Confidence and incomplete work

Probability estimates describe the accepted provisional outcome model. Confidence intervals measure Monte Carlo sampling uncertainty only; they do not measure model error. A completed run may still miss its precision target. An interrupted, cancelled, capability-incomplete, candidate-capped, evaluation-capped, or deadline-limited run must be read as incomplete and is never silently renormalized.

## History, cancellation, and restart

Simulation Center rediscovers retained runs for the selected snapshot. Requesting cancellation acknowledges intent first; the terminal state may be `cancelled`, or `completed` if completion committed first. Completed results remain available after a normal restart. Work active during an unexpected process exit is classified as interrupted on restart and is not automatically resumed.

If a run or ESPN request stalls, cooperative shutdown can exceed the launcher timeout because Python cannot safely force-stop an arbitrary running thread. Ordinary `stop-local.ps1` then performs authenticated process-tree recovery even when Uvicorn has already closed its listener. Completed results and databases remain intact; unfinished work is reconciled on restart. To inspect instead, use `stop-local.ps1 -PreserveOnTimeout`, then run ordinary `stop-local.ps1` when ready to recover. Never delete launcher metadata or kill a PID manually. If the launcher cannot authenticate ownership, it refuses termination; an operating-system restart is safer than guessing.

## Protect local data

- Keep `.env`, SQLite databases, WAL/SHM files, research rows, checkpoints, and live reports out of version control.
- The service binds only to loopback and validates Host and state-changing browser Origin headers, but it is not a multi-user authenticated service. Do not expose it through port forwarding or a public proxy.
- Use the application only on a trusted local machine. Other local processes can access loopback services under the V1 trust model.
- Back up private databases using normal SQLite-safe practices while the application is stopped.

## Known limitations

- Exact whole-league valuation and transaction search can be slow; meaningful precision can be expensive.
- The outcome distribution is provisional, and historical ESPN projection provenance is not authenticated pregame evidence.
- Missing projections, explicit ESPN zeroes, and approved policy-imputed zeroes remain distinct and can limit capabilities.
- Some ESPN rules, waiver timing, IR evidence, and postseason mappings remain unsupported or require explicit validated configuration.
- Baseline/manual cancellation is coarse; a running batch may finish after cancellation is requested.
- A stalled synchronous ESPN request can outlive the refresh coordinator's shutdown wait.
- Interrupted background runs are retained as interrupted but are not automatically resumed.
- Deployment is local-only; there are no accounts, public hosting, or remote authentication.
- War Room never executes real transactions and cannot promise trade acceptance or waiver success.
- League Insights and other post-V1 work remain deferred.

For installation failures, launcher ownership and database recovery, use [current operations](getting-started/operations.md). Original [installation evidence](M8_1_LOCAL_INSTALLATION.md), [runtime and recovery evidence](M8_3_RUNTIME_AND_RECOVERY.md), and [run management contracts](RUN_MANAGEMENT.md) remain available.
