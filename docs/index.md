# War Room documentation

Choose a starting point by what you want to do. Existing references stay at their original paths; this index does not relocate documents or turn historical evidence into current implementation claims.

## Getting started

- [README](../README.md): product scope, prerequisites and Windows quick start.
- [Installation](getting-started/installation.md): software prerequisites and locked setup.
- [Configuration](getting-started/configuration.md): public/private ESPN profile, manual rules and browser/CLI path precedence.
- [First run](getting-started/first-run.md): launch, refresh/select a snapshot, baseline and action analysis.
- [Operations and troubleshooting](getting-started/operations.md): private persistence, safe shutdown/recovery and common problems.
- [Application user guide](LOCAL_V1_USER_GUIDE.md): analytical interpretation and workspace usage.
- [Original installation evidence](M8_1_LOCAL_INSTALLATION.md): retained implementation and acceptance history.
- [Contributor environment and checks](../CONTRIBUTING.md#development-environment-and-checks): locked toolchain, known Node-version mismatch and safe verification tiers.

Use these current guides when older handoff material gives a broader runtime range or historical setup commands. Launcher and Python CLI settings differ as explained in configuration. Installation/startup is credential-free; private-league retrieval needs paired local credentials. No guide authorizes public deployment or bypassing a safe scoring boundary.

## Using War Room

- [User guide](LOCAL_V1_USER_GUIDE.md): ordinary baseline, action-analysis, retained-history and recovery workflow.
- [League Overview reference](M7_2_LEAGUE_ANALYTICS.md): probabilities, sampling intervals, placements and incomplete results.
- [Opportunity Explorer reference](M7_3_OPPORTUNITY_EXPLORER.md): candidate exploration, coverage, rankings and paired impacts.
- [Trade Lab reference](M7_4_TRADE_LAB.md): multi-team drafting, protected pins, completion and comparison.
- [Simulation Center reference](M7_5_SIMULATION_CENTER.md): explicit run configuration, progress, cancellation and result navigation.
- [Background runs](APPLICATION_SERVICE.md#analysis-lifecycle), [snapshot storage/inspection](SNAPSHOT_STORAGE.md) and [runtime/recovery evidence](M8_3_RUNTIME_AND_RECOVERY.md): retained data and operational boundaries.

Workspace documents include dated delivery evidence as well as interface explanations. Their historical review statements are not the current capability authority; use the status summary below. The application never submits transactions or invents acceptance/waiver-success probabilities.

## Understanding the architecture

- [Architecture overview](architecture/overview.md): concise subsystem/source map and data flow for new developers.

- [Master specification, system architecture](MASTER_SPEC.md#2-system-architecture-and-execution-lifecycle): presentation → application → accepted engine → data/persistence boundaries.
- [Canonical records](CANONICAL_MODEL.md), [ESPN adapter](ESPN_CANONICAL_ADAPTER.md) and [immutable storage](SNAPSHOT_STORAGE.md): source provenance and snapshot identity.
- [Application API and execution](APPLICATION_SERVICE.md): one current contract for transport, refresh, analysis lifecycle, retained results and local ownership.
- [Deterministic season coordinator](SEASON_SIMULATOR.md), [postseason engine](POSTSEASON.md) and [Monte Carlo execution](MONTE_CARLO.md): simulation and reproducibility.
- [R1 audit, feature/source ownership map](R1_REPOSITORY_AUDIT.md): where major features are implemented, known coupling and the proposed later documentation migration.
- [UI principles](UI_DESIGN_VISION.md): approved source-backed visual, accessibility and interaction direction.

The engine owns league mechanics and numerical interpretation. The frontend presents validated results. A historical milestone name is not permission to copy rules into a new presentation layer.

## Developing and testing

- [Verification and documentation maintenance](development/verification.md): five tiers, change-based matrix, numerical standards, maintenance responsibilities and the proposed two-audit archive pilot.

- [Developer setup](getting-started/development.md): locked dependencies, backend/Vite terminals, synthetic fixtures and verification tiers.

- [CONTRIBUTING.md](../CONTRIBUTING.md): original-repository and fork branches, upstream sync, overlap coordination, PR review and verification.
- [AGENTS.md](../AGENTS.md): standing implementation, evidence, fail-closed and change-discipline rules.
- [Backlog maintenance](BACKLOG.md#maintaining-this-file): propose, claim, update and complete stable work items through ordinary PRs.
- [Release checklist](RELEASE_CHECKLIST.md): credential-free versus explicit Windows process/recovery checks and independent signoff.
- [API evolution and compatibility](APPLICATION_SERVICE.md#api-evolution): additive versus incompatible changes; current developer setup remains in the guide above.

The full release script builds artifacts and runs a networked dependency audit; it is not a read-only/offline check. Live ESPN requests, process recovery and private stores require explicit scope. Report actual checks/results, skipped checks and limitations. Do not infer a fresh-machine or live-data pass from fixture tests.

## Analytical and API references

- **Approved meaning:** [master specification](MASTER_SPEC.md); [league configuration and unsupported modes](LEAGUE_CONFIGURATION_AUDIT.md).
- **Data and permissions:** [canonical contract](CANONICAL_MODEL.md), [adapter](ESPN_CANONICAL_ADAPTER.md), [snapshot storage](SNAPSHOT_STORAGE.md), [missing-projection policy](MISSING_PROJECTION_POLICY.md), [live scoring evidence/boundaries](LIVE_WEEK_SCORING.md), [partial-week contracts](LW2_PARTIAL_WEEK_CONTRACT.md).
- **League mechanics:** [roster valuation](ROSTER_VALUATION.md), [weekly transactions](WEEKLY_TRANSACTIONS.md), [complete-cycle reference/oracle](TRANSACTION_CYCLE_REFERENCE.md), [postseason](POSTSEASON.md), [season coordinator](SEASON_SIMULATOR.md).
- **Outcomes and numerics:** [player outcome models](PLAYER_OUTCOME_MODEL.md), [Monte Carlo paths/precision/workers/recovery](MONTE_CARLO.md).
- **Scenarios and searches:** [manual scenarios](MANUAL_SCENARIOS.md), [trade enumeration/screening/evaluation](TRADE_CANDIDATES.md), [acquisitions](ACQUISITION_CANDIDATES.md), [trade chains](MULTI_TRADE_CHAINS.md), [unified actions](UNIFIED_ACTION_SEARCH.md), [search orchestration](SEARCH_ORCHESTRATION.md).
- **Application contracts:** [API and execution reference](APPLICATION_SERVICE.md), including compatibility, refresh, lifecycle, storage, leases, limits and recovery. A running local server exposes `/docs` and `/openapi.json` for exact public shape; approved requirements govern meaning.

These references contain implementation layers and historical amendments. The status summary identifies current supported subsets; an unverified source claim or future design paragraph is not an executable capability.

## Research and evidence

- [Historical research dataset](HISTORICAL_RESEARCH_DATASET.md), [outcome-distribution evaluation](OUTCOME_DISTRIBUTION_RESEARCH.md) and [research-plan example](examples/m32_historical_research_plan.json): temporal provenance, leakage safeguards and provisional calibration.
- [ESPN connectivity observations](ESPN_CONNECTIVITY.md), [future-data audit](ESPN_FUTURE_DATA_AUDIT.md), [historical projections](ESPN_HISTORICAL_PROJECTION_AUDIT.md), [league-rule audit](ESPN_LEAGUE_RULES_AUDIT.md) and [undroppable evidence](ESPN_UNDROPPABLE_AUDIT.md): dated findings with bounded verification.
- [Missing-projection evidence/policy](MISSING_PROJECTION_POLICY.md) and [LW1 live-source evidence](LIVE_WEEK_SCORING.md): missing-versus-zero and source-authority distinctions.
- [Accepted LW2.3A performance checkpoint](LW23A_PERFORMANCE_CHECKPOINT.md) and its [benchmark harness](../benchmarks/benchmark_partial_week.py): repeated synthetic measurements, exact-equivalence artifacts and the decision to retain production code.
- [R2.3 reconciliation inventory](R23_DOCUMENTATION_RECONCILIATION.md): bounded technical drift, source/test evidence and the R23-06 question subsequently resolved by accepted WR-022.

**Verified live**, **Verified by tests**, **Unverified** and **Unsupported** are different claims. Historical returned projections do not establish authenticated pregame vintages. Fixtures establish code behavior, not current ESPN availability or production-scale performance.

## Current status and outstanding work

The [revised R2.7 plan](development/documentation-consolidation.md), in existing [PR #121](https://github.com/tdkelley2001/fantasy_football/pull/121), proposes a conditional 17-document architecture: domain documents own current contracts, BACKLOG owns exact future requirements/approval/delivery, and Git/PRs own ordinary history. It replaces the initial 40-document proposal and proposes retiring MASTER_SPEC after reviewed requirement transfer, with no replacement master. R2.7 is independently accepted at `fd99424`; D1 now consolidates API/execution documentation and is In Review. Other packages/authority transfer remain separately gated; current authorities below still apply. The [R2.6 inventory](R26_DOCUMENTATION_MIGRATION_PLAN.md) is discovery evidence, not an active archive plan. Use BACKLOG for work status, not either plan as a second queue.

| Document | Authority |
|---|---|
| [README](../README.md) | Product entry point and quick start. |
| [CONTRIBUTING](../CONTRIBUTING.md) | Contributor/fork/branch workflow and review. |
| [BACKLOG](BACKLOG.md) | Outstanding work, stable IDs, approval/evidence gates and review disposition. |
| [Current status](status.md) | Current capabilities, limits and release disposition. |
| [MASTER_SPEC](MASTER_SPEC.md) | Approved analytical requirements and modeling contracts. |
| [Historical roadmap](ROADMAP.md) | Original milestone history, dependencies and preserved acceptance gates; not current priorities. |

R2.0, R2.1 and R2.2 are independently accepted; R2.0 is recorded at `3391552`, R2.1 in [PR #113](https://github.com/tdkelley2001/fantasy_football/pull/113), and R2.2 at `a7c0ff4` ([PR #115](https://github.com/tdkelley2001/fantasy_football/pull/115)). The LW2.3A performance checkpoint (`d630887`) is also independently accepted. These acceptances do not declare V1 released: **M8.4 remains pending independent release disposition**. R2.3 ([PR #116](https://github.com/tdkelley2001/fantasy_football/pull/116)) and [WR-022](MISSING_PROJECTION_ZERO_CORRECTION.md) are independently accepted through baseline `28bf605`. R2.4 is independently accepted at `05165a8` ([PR #118](https://github.com/tdkelley2001/fantasy_football/pull/118)); R2.5's pilot at `fd98551` ([PR #119](https://github.com/tdkelley2001/fantasy_football/pull/119)); R2.6's inventory at `886335f` ([PR #120](https://github.com/tdkelley2001/fantasy_football/pull/120)). R2.7 supersedes the archive strategy with a reduction review; implementation still needs separate approval. Applicable technical/release gates remain binding pending explicit reviewed disposition under WR-002.

## Historical development records

Historical records remain discoverable. R2.1 preserved their original locations; R2.5 relocates only the pre-M3/pre-M4 audits below, retaining both original paths and heading anchors as compatibility pages. Delivery-time test counts, review statements and capability boundaries must be read at their stated baseline, not as a second current-status tracker.

- [Original roadmap](ROADMAP.md) and delivery sections of [MASTER_SPEC](MASTER_SPEC.md): milestone sequence, decisions and acceptance gates.
- [M0 feasibility/handoff](M0_FEASIBILITY_AND_M1_HANDOFF.md) and [proposed M1 data dictionary](ESPN_DATA_DICTIONARY.md): design vocabulary and discovery context, not replacements for today's canonical classes.
- Repository audits: [archived pre-M3](archive/audits/PRE_M3_REPOSITORY_AUDIT.md), [archived pre-M4](archive/audits/PRE_M4_INTEGRATION_AUDIT.md), [post-M7](POST_M7_CONSOLIDATION_AUDIT.md) and [R1 inventory/migration map](R1_REPOSITORY_AUDIT.md). The original two pilot audit paths remain navigation pages; [R2.5](R25_ARCHIVE_PILOT.md) records that pilot.
- The five redundant application/backend reports were incorporated into [APPLICATION_SERVICE](APPLICATION_SERVICE.md) in D1. Their chronology and exact historical evidence remain in accepted Git history; [source/verification](APPLICATION_SERVICE.md#source-and-verification) links the useful measured baseline.
- UI evidence: [frontend foundation](M7_1_FRONTEND_FOUNDATION.md), [superseded visual exploration](M7_1_VISUAL_DIRECTION_REVIEW.md), [League Overview](M7_2_LEAGUE_ANALYTICS.md), [Explorer](M7_3_OPPORTUNITY_EXPLORER.md), [Trade Lab](M7_4_TRADE_LAB.md) and [Simulation Center](M7_5_SIMULATION_CENTER.md). Linked screenshots remain evidence, not fabricated analytics.
- Local operation/release evidence: [installation](M8_1_LOCAL_INSTALLATION.md), [authorized real-league validation](M8_2_REAL_LEAGUE_VALIDATION.md), [runtime/recovery](M8_3_RUNTIME_AND_RECOVERY.md) and [M8.4 release audit](M8_4_FINAL_RELEASE_AUDIT.md). The [release checklist](RELEASE_CHECKLIST.md) still needs explicit reviewer disposition.
- Live-week records: [LW1](LIVE_WEEK_SCORING.md), [LW2 foundations/integration](LW2_PARTIAL_WEEK_CONTRACT.md) and [accepted performance/consolidation checkpoint](LW23A_PERFORMANCE_CHECKPOINT.md).

For active work use the backlog, not a historical checklist. Preserve original evidence and resolve conflicting contract text explicitly before changing behavior.
