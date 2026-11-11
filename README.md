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

Follow [OPERATIONS](docs/OPERATIONS.md) for the complete Windows installation, ESPN configuration, launch, first analysis, private-data management and safe shutdown procedure. It records the tested Python/Node environment, locked setup and unresolved WR-003 version-policy mismatch. Installation/startup needs no ESPN credentials; private refresh needs the complete authorized cookie pair.

The application serves its built frontend on loopback. Refresh the configured league explicitly, select a snapshot, then submit a bounded baseline or hypothetical analysis in Simulation Center. A manual start-week override cannot bypass evidence safety checks. Use the [application user guide](docs/LOCAL_V1_USER_GUIDE.md) for workspace details and interpretation.

Developers use [CONTRIBUTING](CONTRIBUTING.md#development-environment-and-checks) for the separate backend/Vite workflow and verification tiers. V1 release signoffs remain in [WR-021](docs/BACKLOG.md#wr-021-release-acceptance); historical implementation evidence remains in Git/PRs.

## Documentation and contribution

- [Documentation index](docs/index.md) — start here for guides, architecture, API/domain references, research and evidence.
- [Contributing](CONTRIBUTING.md) — feature branches in the original repository or retained fork, safe synchronization, reviewed PRs and checks.
- [Development backlog](docs/BACKLOG.md) — the authoritative list of outstanding work; a proposal is not implementation approval.
- [Current capabilities](docs/status.md) — what is supported today and what remains provisional or unavailable.
- [Master specification](docs/MASTER_SPEC.md) — approved analytical requirements, modeling contracts and architecture.
- [Architecture overview](docs/architecture/overview.md) — subsystem/source map, data flow and extension boundaries.
- [Application API and execution](docs/APPLICATION_SERVICE.md) — API 1.0, refresh, background lifecycle, retained results, ownership and local security.
- [Historical roadmap](docs/ROADMAP.md) — preserved milestones, dependencies and acceptance gates, not an active work queue.
- [Historical development records](docs/index.md#historical-development-records) — audits, source observations and visual/runtime evidence retained at their original paths.

Keep changes small and use a reviewed pull request into `tdkelley2001/fantasy_football:main`. The repository-native backlog is maintained through those PRs; no Issues/Projects workflow is required.
