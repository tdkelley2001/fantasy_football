# War Room

[Transactions](docs/TRANSACTIONS.md) owns evolving roster legality, essential acquisitions, V(R) and distinct correctness references.

War Room is a local web application for ESPN fantasy football managers who want to understand league-wide season outcomes and compare hypothetical roster changes. It preserves immutable league snapshots, simulates the remaining season and compares actions using matched player-week draws.

ESPN access is **read-only**. War Room **never submits real transactions**, predicts manager acceptance or estimates waiver-claim success.

## Current capabilities

| Availability | What you can use |
|---|---|
| Application | Explicit ESPN refresh/publication and snapshot selection; League Overview championship/playoff/placement estimates; Opportunity Explorer retained candidate exploration; Trade Lab final-state scenarios; Simulation Center bounded baseline/action execution, cancellation and retained history. |
| Accepted engine interfaces, not exposed in the browser/API | Validated partial-week evidence and deterministic fixed/remaining/carry composition; opt-in partial-season execution with verified standings cutoff/history; partial Monte Carlo for **fully unstarted** current players with approved matching full-game projections. Unresolved evidence and completed/in-progress/missing/ambiguous MC player states fail closed. Pregame equivalence requires matching starters/policies and no first-week acquisition changing ownership. Partial-season execution rejects current transactions/hypothetical initial rosters; later-round starts without reconstructible history and multiweek regular-period cases remain unsupported. |
| Provisional / evidence-limited | The application uses the provisional Normal outcome model; an empirical research path is engine-only. Sampling intervals quantify Monte Carlo uncertainty, not model error. Historical returned ESPN projections do not prove authenticated pregame vintages. Live observations are bounded to documented retrievals, not universal ESPN guarantees. |
| Unsupported / deferred | Automatic live-to-partial translation, conditional in-game distributions, current-week transaction/lineup advice, automatic injury forecasts, a joint-score model, Weekly Deep Dive, League Insights, application-level job resume, public hosting and accounts. A backlog proposal does not authorize implementation or new modeling assumptions. |

Ordinary V1 simulation requires a verified safe whole-week boundary. An explicit override or later unplayed games cannot bypass unresolved matchup-period membership, preceding contributions or standings evidence. NFL completion or score presence alone does not prove participation, fantasy settlement or stat-correction finality. Validated configuration determines league behavior; unknown rules and permissions fail closed.

Canonical snapshots preserve source provenance and historical schema reads without rewriting bytes/IDs. Read compatibility does not guarantee every consumer capability. Missing projections, explicit ESPN zeros and policy-imputed zeros remain distinct; the approved deterministic-zero correction preserves nonmissing draws while distinguishing numerical policy identity. See [data contracts](docs/DATA.md#canonical-validation-and-serialization) and [outcome models](docs/PLAYER_OUTCOME_MODEL.md).

## Limitations and release status

War Room is **not formally released**. Accepted engine/workspace implementation does not constitute release approval. **M8.4 release disposition remains pending**, including follow-up review and current clean-machine acceptance under [WR-021](docs/BACKLOG.md#wr-021-release-acceptance).

Exact valuation and action search can be expensive. A completed run can miss precision targets; incomplete paths/capabilities, candidate/evaluation coverage and unresolved rankings remain visible. A top displayed candidate need not be globally best or executable. Numerical checkpoint/resume exists; interrupted application jobs are classified, not automatically resumed. Active batches or synchronous ESPN calls can outlive cooperative shutdown waits; recovery requires authenticated launcher ownership.

The service binds to loopback on a trusted local machine. Host/Origin checks are not remote authentication or isolation from other local processes. Public proxies, port forwarding and untrusted shared-machine deployment are unsupported. Keep credentials, rule files, databases/sidecars, logs, research and user results private and out of Git.

## Start here

- [Install and operate](docs/OPERATIONS.md): Windows prerequisites, locked setup, public/private ESPN configuration, launch, first analysis, private storage and safe shutdown. Installation/startup needs no ESPN credentials. Tested versions and the unresolved Node-policy mismatch (WR-003) are recorded there.
- [Use the interface](docs/INTERFACE.md): workspace journeys, analytical presentation, provenance, accessibility and frontend contracts.
- [Contribute](CONTRIBUTING.md): original-repository/fork branches, safe synchronization, developer environment, verification tiers and independent PR review. [AGENTS](AGENTS.md) supplies standing development rules.
- [Development backlog](docs/BACKLOG.md): authoritative outstanding work and evidence/approval gates; a proposal is not implementation approval.

## Understand the system

- [Architecture map](docs/architecture/overview.md) and [application API/execution](docs/APPLICATION_SERVICE.md): source ownership, runtime boundaries and public contracts.
- [Data lifecycle](docs/DATA.md): ESPN sources, canonical structures/validation, league-rule evidence and immutable snapshot storage.
- [Season simulation](docs/SEASON_SIMULATOR.md), [outcome models](docs/PLAYER_OUTCOME_MODEL.md) and [Monte Carlo](docs/MONTE_CARLO.md): mechanics, provisional mathematics and reproducibility. [Partial-week contracts](docs/LW2_PARTIAL_WEEK_CONTRACT.md) define the separate evidence boundary.
- [Manual scenarios](docs/MANUAL_SCENARIOS.md) and [action search](docs/UNIFIED_ACTION_SEARCH.md): counterfactual completion, selected universes and paired comparison.
- [Research](docs/RESEARCH.md) and [live-source evidence](docs/DATA.md#live-and-temporal-evidence): temporal trust, evaluation/promotion gates and unresolved capabilities. Fixtures prove code behavior, not live ESPN semantics.
- [MASTER_SPEC](docs/MASTER_SPEC.md) remains authoritative for approved analytical requirements until a separately reviewed transfer. [ROADMAP](docs/ROADMAP.md) preserves historical milestones and applicable gates, not a second work queue. Ordinary history and retired reports remain in Git/PRs; retained evidence applies at its stated revision.
