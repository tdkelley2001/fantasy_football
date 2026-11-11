# Contributing to War Room

`tdkelley2001/fantasy_football` is the authoritative repository for accepted code and documentation. Both regular contributors use reviewed pull requests into its `main` branch, whether the work branch is in the original repository or the existing fork. Keep the fork; no migration, remote replacement or permission change is needed.

Start with the [development backlog](docs/BACKLOG.md), [current capabilities](docs/status.md), [approved analytical specification](docs/MASTER_SPEC.md) and [standing development rules](AGENTS.md). The [original roadmap](docs/ROADMAP.md) preserves historical milestones, dependencies and acceptance evidence; it is no longer a parallel work queue. Applicable acceptance gates remain binding until explicitly superseded by an approved contract.

## Agree the work first

Use a stable `WR-NNN` backlog ID in the branch/PR description. Propose new work or claim an existing item by editing [BACKLOG.md](docs/BACKLOG.md) through an ordinary PR. An owner is optional; agree assignments rather than assigning the other contributor without discussion. A listed proposal is not implementation approval. Record scope, dependencies, acceptance/verification and the governing specification before starting substantive work.

Coordinate overlapping files or interfaces in the backlog entry and PR discussion. Agree sequencing, keep changes small and bring relevant upstream changes into the branch before final review. Do not combine work packages merely because they touch nearby code. Each contributor, including coding agents, follows the same review and evidence rules.

## Branches and safe synchronization

The Git examples are instructions, not repository settings. Begin with `git status --short` and `git remote -v`; preserve any local work deliberately. Check which repository each remote names. Do not discard changes, reset main, force-push or rewrite another contributor's published commits. If a fast-forward fails, inspect divergence and coordinate instead of forcing it. “Already up to date” does not prove local main has no extra commits: inspect ahead/behind state and review the complete PR diff against authoritative main.

Use a short branch such as `docs/WR-002-current-guides` or `fix/WR-003-node-check`. Replace example names with the actual work ID and branch. Use a new branch for each independently reviewable change.

### Working in the original repository

Here `origin` must be `tdkelley2001/fantasy_football`:

```shell
git fetch origin
git switch main
git merge --ff-only origin/main
git switch -c docs/WR-002-current-guides
```

Update an existing work branch with `git fetch origin`, switch to that branch and `git merge origin/main`. Resolve conflicts with the affected contributor, run the relevant checks, then push **the work branch**, for example `git push -u origin docs/WR-002-current-guides`. Open a PR with base `tdkelley2001/fantasy_football:main`. Do not push changes directly to upstream main.

### Working in the existing fork

Here `origin` must be the contributor's fork. Inspect remotes first; only if `upstream` is absent, add it with:

```shell
git remote add upstream https://github.com/tdkelley2001/fantasy_football.git
```

Verify an existing upstream URL rather than replacing it. To sync the fork's clean main and start work:

```shell
git fetch upstream
git switch main
git merge --ff-only upstream/main
git push origin main
git switch -c docs/WR-002-current-guides
```

The main push above updates **the fork only**, not authoritative main. If fork/local main contains unrelated commits, preserve that work and agree a branch base containing only the intended contribution; do not reset or delete the fork. Update an existing work branch by fetching upstream and merging `upstream/main` into that branch. Then push the work branch to `origin` and open a PR whose **base repository is the original repository**, not the fork. Both contribution routes receive the same review and verification.

Merging upstream into a shared branch is the default; rebasing or rewriting published history requires explicit coordination and is not needed for this workflow. Review the PR's files and base/head repositories before requesting review.

## Development environment and checks

The supplied application launchers target Windows. Python 3.12 is required. Use the locked Python/frontend dependencies; do not update them as an incidental cleanup. The existing environment was checked with Node 24.19.0. The installer currently accepts a wider Node range than the full frontend test lockfile supports; [WR-003](docs/BACKLOG.md#work-items) tracks that confirmed mismatch. Check the locked toolchain requirements rather than interpreting “Node 20 or newer” as sufficient for all contributor tests.

For the supplied Windows setup, use `scripts/setup-local.ps1` as described in [local installation](docs/M8_1_LOCAL_INSTALLATION.md). It installs dependencies and builds assets. Installation and startup need no ESPN credentials. For authorized ESPN access, use ignored local configuration as described in the [user guide](docs/LOCAL_V1_USER_GUIDE.md); private credentials must be supplied as a complete pair. The launcher uses `WAR_ROOM_DATABASE`/`-Database`, while Python settings/CLIs use `SNAPSHOT_DB_PATH`; do not assume changing one changes the other. CLI manual rule files use `--manual-config`; browser refresh resolves the configured settings path. [WR-002](docs/BACKLOG.md#work-items) tracks the fuller guide consolidation.

Choose checks proportional to the change and report the actual results. Useful Windows commands are:

```powershell
# Documentation and repository privacy checks
.venv\Scripts\python.exe -m pytest tests/test_documentation_links.py tests/test_repository_security.py -q

# Credential-free Python tier; uses synthetic/temp data, excludes real process recovery tests
.venv\Scripts\python.exe -m pytest -m "not windows_process"

# Established narrow correctness gate, not a repository-wide style rewrite
.venv\Scripts\python.exe -m ruff check --select E9,F63,F7,F82 .
.venv\Scripts\python.exe -m pip check
git diff --check

# For frontend changes
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
```

The frontend typecheck/build commands can generate local build metadata/assets. The complete `scripts/verify-release.ps1` runs tests/builds and a **networked npm audit**; it is not a read-only/offline command. Its `-IncludeWindowsProcessTests` tier deliberately starts/stops disposable owned processes. Run process/recovery tests and live ESPN diagnostics only within an explicitly agreed scope; never point them at another contributor's private data or running service. Fresh-machine, live-access and visual verification must be reported separately from fixture tests. See [release checks](docs/RELEASE_CHECKLIST.md) and [R1 findings](docs/R1_REPOSITORY_AUDIT.md) for known tooling limits.

Preserve raw missing versus explicit zero, immutable snapshots, source evidence, compatibility and deterministic path identities. Analytical/legality changes need focused adversarial tests and applicable reference-oracle, worker/batch/resume and fingerprint/golden regressions. Do not delete older schemas, tests or evidence merely because they are old. Do not commit `.env`, tokens, private league reports, databases/sidecars or user results; use sanitized fixtures and ignored local output.

## Review and completion

In the PR description, give the backlog ID, objective/change, governing contract, acceptance criteria addressed, exact verification results and skipped checks with reasons. State compatibility/evidence risks and any remaining blockers. No issue/PR template, label system, Project board or new workflow configuration is required.

Request review from the other contributor or an agreed independent reviewer. Merge only after review, applicable gates and relevant verification are satisfied. A successful local check is not acceptance of a new modeling assumption or a declaration of release. Update current capability documentation when behavior actually changes; update the backlog in the same PR or a small follow-up PR when review disposition is known. Keep items In Review until accepted, then retain their IDs in the completed record with the actual PR/decision reference. See [backlog maintenance](docs/BACKLOG.md#maintaining-this-file).
