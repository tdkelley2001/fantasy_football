# War Room documentation

Choose a starting point by what you want to do. Existing references stay at their original paths; this index does not relocate documents or turn historical evidence into current implementation claims.

## Getting started

- [README](../README.md): product scope, prerequisites and Windows quick start.
- [Application user guide](LOCAL_V1_USER_GUIDE.md): configure ESPN access, refresh/select a snapshot and run your first analysis.
- [Local installation reference](M8_1_LOCAL_INSTALLATION.md): launcher options, paths, startup/shutdown and troubleshooting.
- [Contributor environment and checks](../CONTRIBUTING.md#development-environment-and-checks): locked toolchain, known Node-version mismatch and safe verification tiers.

Start with the README/contributor prerequisites when older handoff material gives a broader runtime range. Launcher and Python CLI database settings differ; the contributor guide explains the current behavior. Fuller setup-guide consolidation is outstanding in the backlog. Installation/startup is credential-free; private-league retrieval needs paired local credentials. No guide authorizes public deployment or bypassing a safe scoring boundary.

## Using War Room

- [User guide](LOCAL_V1_USER_GUIDE.md): ordinary baseline, action-analysis, retained-history and recovery workflow.
- [League Overview reference](M7_2_LEAGUE_ANALYTICS.md): probabilities, sampling intervals, placements and incomplete results.
- [Opportunity Explorer reference](M7_3_OPPORTUNITY_EXPLORER.md): candidate exploration, coverage, rankings and paired impacts.
- [Trade Lab reference](M7_4_TRADE_LAB.md): multi-team drafting, protected pins, completion and comparison.
- [Simulation Center reference](M7_5_SIMULATION_CENTER.md): explicit run configuration, progress, cancellation and result navigation.
- [Background runs](RUN_MANAGEMENT.md), [snapshot storage/inspection](SNAPSHOT_STORAGE.md) and [runtime/recovery evidence](M8_3_RUNTIME_AND_RECOVERY.md): retained data and operational boundaries.

Workspace documents include dated delivery evidence as well as interface explanations. Their historical review statements are not the current capability authority; use the status summary below. The application never submits transactions or invents acceptance/waiver-success probabilities.

## Understanding the architecture

- [Master specification, system architecture](MASTER_SPEC.md#2-system-architecture-and-execution-lifecycle): presentation → application → accepted engine → data/persistence boundaries.
- [Canonical records](CANONICAL_MODEL.md), [ESPN adapter](ESPN_CANONICAL_ADAPTER.md) and [immutable storage](SNAPSHOT_STORAGE.md): source provenance and snapshot identity.
- [Application service/API](APPLICATION_SERVICE.md) and [background lifecycle](RUN_MANAGEMENT.md): transport, orchestration and retained results.
- [Deterministic season coordinator](SEASON_SIMULATOR.md), [postseason engine](POSTSEASON.md) and [Monte Carlo execution](MONTE_CARLO.md): simulation and reproducibility.
- [R1 audit, feature/source ownership map](R1_REPOSITORY_AUDIT.md): where major features are implemented, known coupling and the proposed later documentation migration.
- [UI principles](UI_DESIGN_VISION.md): approved source-backed visual, accessibility and interaction direction.

The engine owns league mechanics and numerical interpretation. The frontend presents validated results. A historical milestone name is not permission to copy rules into a new presentation layer.

## Developing and testing

- [CONTRIBUTING.md](../CONTRIBUTING.md): original-repository and fork branches, upstream sync, overlap coordination, PR review and verification.
- [AGENTS.md](../AGENTS.md): standing implementation, evidence, fail-closed and change-discipline rules.
- [Backlog maintenance](BACKLOG.md#maintaining-this-file): propose, claim, update and complete stable work items through ordinary PRs.
- [Release checklist](RELEASE_CHECKLIST.md): credential-free versus explicit Windows process/recovery checks and independent signoff.
- [Backend readiness handoff](BACKEND_READINESS.md): API compatibility/troubleshooting reference; its Python-only startup procedure is historical, so use the current quick start for built frontend requirements.

The full release script builds artifacts and runs a networked dependency audit; it is not a read-only/offline check. Live ESPN requests, process recovery and private stores require explicit scope. Report actual checks/results, skipped checks and limitations. Do not infer a fresh-machine or live-data pass from fixture tests.

## Analytical and API references

- **Approved meaning:** [master specification](MASTER_SPEC.md); [league configuration and unsupported modes](LEAGUE_CONFIGURATION_AUDIT.md).
- **Data and permissions:** [canonical contract](CANONICAL_MODEL.md), [adapter](ESPN_CANONICAL_ADAPTER.md), [snapshot storage](SNAPSHOT_STORAGE.md), [missing-projection policy](MISSING_PROJECTION_POLICY.md), [live scoring evidence/boundaries](LIVE_WEEK_SCORING.md), [partial-week contracts](LW2_PARTIAL_WEEK_CONTRACT.md).
- **League mechanics:** [roster valuation](ROSTER_VALUATION.md), [weekly transactions](WEEKLY_TRANSACTIONS.md), [complete-cycle reference/oracle](TRANSACTION_CYCLE_REFERENCE.md), [postseason](POSTSEASON.md), [season coordinator](SEASON_SIMULATOR.md).
- **Outcomes and numerics:** [player outcome models](PLAYER_OUTCOME_MODEL.md), [Monte Carlo paths/precision/workers/recovery](MONTE_CARLO.md).
- **Scenarios and searches:** [manual scenarios](MANUAL_SCENARIOS.md), [trade enumeration/screening/evaluation](TRADE_CANDIDATES.md), [acquisitions](ACQUISITION_CANDIDATES.md), [trade chains](MULTI_TRADE_CHAINS.md), [unified actions](UNIFIED_ACTION_SEARCH.md), [search orchestration](SEARCH_ORCHESTRATION.md).
- **Application contracts:** [service/HTTP reference](APPLICATION_SERVICE.md), [retained runs/results](RUN_MANAGEMENT.md), [API compatibility handoff](BACKEND_READINESS.md). A running local server exposes `/docs` and `/openapi.json` for actual public shape; approved requirements govern meaning.

These references contain implementation layers and historical amendments. The status summary identifies current supported subsets; an unverified source claim or future design paragraph is not an executable capability.

## Research and evidence

- [Historical research dataset](HISTORICAL_RESEARCH_DATASET.md), [outcome-distribution evaluation](OUTCOME_DISTRIBUTION_RESEARCH.md) and [research-plan example](examples/m32_historical_research_plan.json): temporal provenance, leakage safeguards and provisional calibration.
- [ESPN connectivity observations](ESPN_CONNECTIVITY.md), [future-data audit](ESPN_FUTURE_DATA_AUDIT.md), [historical projections](ESPN_HISTORICAL_PROJECTION_AUDIT.md), [league-rule audit](ESPN_LEAGUE_RULES_AUDIT.md) and [undroppable evidence](ESPN_UNDROPPABLE_AUDIT.md): dated findings with bounded verification.
- [Missing-projection evidence/policy](MISSING_PROJECTION_POLICY.md) and [LW1 live-source evidence](LIVE_WEEK_SCORING.md): missing-versus-zero and source-authority distinctions.
- [Accepted LW2.3A performance checkpoint](LW23A_PERFORMANCE_CHECKPOINT.md) and its [benchmark harness](../benchmarks/benchmark_partial_week.py): repeated synthetic measurements, exact-equivalence artifacts and the decision to retain production code.

**Verified live**, **Verified by tests**, **Unverified** and **Unsupported** are different claims. Historical returned projections do not establish authenticated pregame vintages. Fixtures establish code behavior, not current ESPN availability or production-scale performance.

## Current status and outstanding work

| Document | Authority |
|---|---|
| [README](../README.md) | Product entry point and quick start. |
| [CONTRIBUTING](../CONTRIBUTING.md) | Contributor/fork/branch workflow and review. |
| [BACKLOG](BACKLOG.md) | Outstanding work, stable IDs, approval/evidence gates and review disposition. |
| [Current status](status.md) | Current capabilities, limits and release disposition. |
| [MASTER_SPEC](MASTER_SPEC.md) | Approved analytical requirements and modeling contracts. |
| [Historical roadmap](ROADMAP.md) | Original milestone history, dependencies and preserved acceptance gates; not current priorities. |

R2.0 is independently accepted at `3391552`. The LW2.3A performance checkpoint (`d630887`) is also independently accepted. Neither acceptance declares V1 released: **M8.4 remains pending independent release disposition**. Future features and model/source changes still need applicable approvals. Historical gates remain binding until an approved replacement explicitly supersedes them; unresolved gate migration remains WR-002, not discarded.

## Historical development records

All records remain discoverable; none is deleted or moved in R2.1. Delivery-time test counts, review statements and capability boundaries must be read at their stated baseline, not as a second current-status tracker.

- [Original roadmap](ROADMAP.md) and delivery sections of [MASTER_SPEC](MASTER_SPEC.md): milestone sequence, decisions and acceptance gates.
- [M0 feasibility/handoff](M0_FEASIBILITY_AND_M1_HANDOFF.md) and [proposed M1 data dictionary](ESPN_DATA_DICTIONARY.md): design vocabulary and discovery context, not replacements for today's canonical classes.
- Repository audits: [pre-M3](PRE_M3_REPOSITORY_AUDIT.md), [pre-M4](PRE_M4_INTEGRATION_AUDIT.md), [post-M5](POST_M5_CONSOLIDATION_AUDIT.md), [pre-M7](PRE_M7_REPOSITORY_AUDIT.md), [post-M7](POST_M7_CONSOLIDATION_AUDIT.md) and [R1 inventory/migration map](R1_REPOSITORY_AUDIT.md).
- Backend evidence: [M6 validation](M6_3_BACKEND_VALIDATION.md) and [backend readiness](BACKEND_READINESS.md).
- UI evidence: [frontend foundation](M7_1_FRONTEND_FOUNDATION.md), [superseded visual exploration](M7_1_VISUAL_DIRECTION_REVIEW.md), [League Overview](M7_2_LEAGUE_ANALYTICS.md), [Explorer](M7_3_OPPORTUNITY_EXPLORER.md), [Trade Lab](M7_4_TRADE_LAB.md) and [Simulation Center](M7_5_SIMULATION_CENTER.md). Linked screenshots remain evidence, not fabricated analytics.
- Local operation/release evidence: [installation](M8_1_LOCAL_INSTALLATION.md), [authorized real-league validation](M8_2_REAL_LEAGUE_VALIDATION.md), [runtime/recovery](M8_3_RUNTIME_AND_RECOVERY.md) and [M8.4 release audit](M8_4_FINAL_RELEASE_AUDIT.md). The [release checklist](RELEASE_CHECKLIST.md) still needs explicit reviewer disposition.
- Live-week records: [LW1](LIVE_WEEK_SCORING.md), [LW2 foundations/integration](LW2_PARTIAL_WEEK_CONTRACT.md) and [accepted performance/consolidation checkpoint](LW23A_PERFORMANCE_CHECKPOINT.md).

For active work use the backlog, not a historical checklist. Preserve original evidence and resolve conflicting contract text explicitly before changing behavior.
