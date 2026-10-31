# Post-M7 Integrated Application Consolidation Audit

Status: **COMPLETE AND ACCEPTED** (31 October 2026). M7.1–M7.5 are independently accepted; M8.1 follows separately.

## 1. Reviewed baseline and scope

The independent review started from accepted commit `0d20ab4243c848db2921f9d7154ea312bf3639af` on a dedicated `audit/post-m7-consolidation` branch. It covered the React/TypeScript application, API schema 1.0 Pydantic contracts and HTTP routes, local SQLite run/snapshot integration, accepted analytical boundaries, tests, dependency locks, documentation, and actual rendered screenshots. It did not add an analytical method, league rule, deployment mechanism, or M8 packaging behavior.

## 2. Interface inventory

The frontend consumes the loopback API through `frontend/src/lib/api.ts`:

- health and build provenance;
- snapshot listing and exact snapshot detail;
- baseline, manual-scenario, and action-search background submission;
- retained run listing, exact run status, progress, cancellation, deletion, and typed results;
- paged action candidates, exact candidate detail, and canonical completed-state detail.

`frontend/src/types/api.ts` was checked field-by-field against `src/fantasy_football/app/contracts.py`. The consumed DTOs agree on API version `1.0`, required fields, nullability, lifecycle enums, snapshot/run/candidate/state identities, retained-result availability, confidence intervals, coverage flags, and stop reasons. Baseline values remain decimal probabilities; paired scenario and action-search changes remain probability points. The frontend does not reinterpret a null probability or interval as zero.

The four implemented workspaces retain separate responsibilities:

- League Overview reads completed baseline results and observed snapshot facts.
- Opportunity Explorer reads retained action-search summaries, paged paths, and shared-state evaluations.
- Trade Lab constructs explicit final-state scenarios and submits manual evaluations.
- Simulation Center submits baseline/action-search work and monitors retained lifecycle evidence.

League Insights remains visibly non-operational.

## 3. Findings by severity

No P0 finding was identified. No known P1 finding remains open.

| Severity | Evidence and impact | Resolution and status | Verification |
| --- | --- | --- | --- |
| P1 | Trade Lab cancelled a superseded retained-result request but had no independent latest-request identity. A transport that resolved after abort could display an old run under a newer selection. | Added a monotonic retained-request token in addition to `AbortController`; only the current run/snapshot request may mutate result, error, status, or loading state. **Resolved.** | Deterministic late-response regression switches between two retained runs while the first ignores cancellation. |
| P2 | Context and navigation drawers focused their close buttons and handled Escape, but did not trap keyboard focus or make the analytical background inert. | Added modal semantics, focus wrapping, background `inert`, Escape closure, and focus restoration. The scrim is no longer a competing focus target. **Resolved.** | Keyboard regression plus axe checks; desktop/mobile captures remain visually unchanged. |
| P2 | The Trade Lab screenshot harness returned a static scenario ID after production began assigning a unique ID per submission. Provenance validation correctly rejected the stale fixture, so evaluated captures timed out. | The capture route now binds the sanitized result to the submitted scenario identity. Production validation was not weakened. **Resolved.** | All Trade Lab construction, evaluation, lineup, error, laptop, and mobile captures regenerated. |
| P2 | The deferred-workspace component still contained unreachable pre-M7 descriptions for Opportunity Explorer, Trade Lab, and Simulation Center. | Removed unreachable labels and retained only the intentional League Insights placeholder. **Resolved.** | Strict typecheck, component tests, and production build. |
| P3 | Formatting, short-identity, and humanized-label helpers repeat across workspaces; archived M7.1 prototype selectors also remain in the stylesheet. | **Deferred.** Their semantics are not all identical, they produce no demonstrated correctness or performance defect, and broad consolidation would create avoidable visual risk before M8. A later measured cleanup may remove only selectors proven unused. | Source inventory and production bundle review. |
| P3 | Full default Ruff selection reports legacy modernization/style findings, including import ordering and FastAPI dependency-default warnings. | **Deferred.** The established correctness gate (`F,E9`) passes; the broader set predates this checkpoint and includes framework idioms and accepted modules. It is recorded rather than silently represented as clean. | `ruff check src tests --select F,E9` passes; full-scope finding retained in this audit. |

## 4. Implemented corrections

Corrections are limited to drawer accessibility, retained Trade Lab request isolation, obsolete unreachable placeholder copy, visual-fixture scenario provenance, current M7 status documentation, and regressions for those contracts. Canonical snapshots, API schemas, simulation fingerprints, analytical algorithms, transaction logic, and database formats are unchanged.

## 5. Deferred improvements

- League Insights is still a future workspace; no placeholder number implies functionality.
- Real ESPN/private-league compatibility remains an M8.2 validation gate. Sanitized fixtures establish code behavior only.
- The application has no public hosting, authentication, or account system; the accepted architecture remains loopback-only.
- Search result pagination is server-side and bounded. The frontend was not changed to virtualize candidate rows because current API pages and measured rendered fixtures showed no bottleneck.
- Historical run listing is explicitly the newest bounded API page, not complete lifetime history.
- Browser request cancellation stops observation, not accepted backend work; the UI continues to disclose that boundary.

## 6. League-configuration and hardcoding audit

Production UI team, player, roster, schedule, postseason, and capability displays derive from `SnapshotSummary`; analytical behavior remains in the accepted Python engine. No production branch was found for a 10-, 12-, 14-, or 16-team league. The 8-team visual fixture and 14-team test/benchmark fixtures remain sanitized evidence, not validation templates.

Simulation Center presets are disclosed application runtime policies. Candidate, evaluation, wall-clock, worker, and path settings are explicit transport/search budgets rather than league rules. The provisional Normal defaults remain labeled provisional. Waiver boundary, IR policy, action families/orderings, lineup slots, postseason structure, and acquisition rules are submitted or canonical inputs; unsupported engine capabilities fail closed. Existing approved modeled policies remain documented in their engine-specific references.

## 7. Contract and analytical-integrity findings

The contract audit confirmed:

- `RunStatus` includes queued, running, cancellation requested, completed, cancelled, failed, and interrupted.
- Result availability is independent of terminal status; failed/cancelled/interrupted work is never rendered as successful.
- League-wide and metric precision remain distinct from execution completion.
- Candidate generation coverage, state-evaluation coverage, statistical precision, and ranking resolution remain separate.
- Standalone probabilities use decimal probability units and Wilson-style interval fields supplied by the engine.
- Manual/action impacts use signed probability points and paired intervals supplied by the engine.
- Transaction authorization, structural hypothetical status, acquisition condition, required assumptions, and shared completed-state identity remain independent.
- Snapshot ID plus canonical SHA-256 and run/candidate/state identities are validated before displaying retained analytics.

Frontend tests cover the probability-versus-probability-point labels and values. The backend service tests continue to compare result numbers directly with accepted engine outputs.

## 8. Cross-workspace workflow and lifecycle results

The accepted paths were exercised through component integration tests and rendered QA:

1. snapshot selection → retained baseline → League Overview team detail;
2. retained action search → server-paged candidates → selected path → shared completed-state impacts → bounded comparison;
3. chronological Trade Lab draft/edit/reorder → explicit settings → background evaluation → paired league/lineup consequences;
4. baseline/action configuration → submission protection → polling/progress → cooperative cancellation/history → exact result navigation.

Snapshot-keyed boundaries clear Trade Lab drafts; League Overview and Opportunity Explorer validate retained provenance; Simulation Center filters history to the active snapshot. Abort cleanup and latest-request guards cover snapshot, run, page, candidate, detail, state-detail, polling, and retained manual-result transitions. Tests include delayed and out-of-order responses. Expired, deleted, unavailable, incomplete, failed, cancelled, and interrupted results retain distinct presentation.

An integrated smoke used the real loopback FastAPI factory/server, an actual persisted sanitized SQLite canonical snapshot, Vite, and headless Edge. The browser resolved exact snapshot `00000000-0000-4000-8000-000000000001`, rendered it, and navigated to Simulation Center without ESPN/network retrieval. Evidence: [integrated real-API smoke](images/post-m7/integrated-real-api-smoke.png).

## 9. Visual and accessibility review

The accepted visual hierarchy remains coherent: probability dot/whisker plot, playoff bands, placement heatmap, action-impact bars, paired impact intervals, chronological transaction flow, lineup explanations, lifecycle timeline, and exact supporting values. Null and unavailable data retain explicit text. Sampling uncertainty is not described as outcome-model certainty.

Actual captures were regenerated from the application for dark/light, desktop/laptop/mobile, selected detail/comparison, evaluated Trade Lab, active/completed/cancellation/failure lifecycle, no-result, precision-limited, unavailable-interval, and invalid/error states. Principal evidence is under:

- `docs/images/m7-2/` — League Overview;
- `docs/images/m7-3/` — Opportunity Explorer;
- `docs/images/m7-4/` — Trade Lab;
- `docs/images/m7-5/` — Simulation Center;
- `docs/images/post-m7/` — real API/frontend smoke.

Visual inspection found no misleading completion mark on active runs, no zero mark for unavailable intervals, and no cross-workspace styling break. Keyboard access has visible focus, skip navigation, modal focus containment/restoration, non-color status labels, chart text equivalents, reduced-motion rules, and responsive mobile controls. Each workspace retains automated axe coverage; automated results supplement rather than replace keyboard and screenshot inspection.

## 10. Verification evidence

Environment: Windows, Python 3.12, Node 24, headless Microsoft Edge. The sandbox blocks Windows native module/process primitives, so native frontend build and multiprocessing verification were run with normal local process permissions.

- Credential-free Python baseline: **862 passed**, one upstream Starlette/AnyIO deprecation warning, 85.26 seconds.
- Frontend focused/full suite after corrections: **5 files, 84 tests passed**; jsdom reports its expected unimplemented canvas context while axe completes.
- Strict TypeScript: passed.
- Production Vite build: passed in 384 ms; JS 334.38 kB (97.96 kB gzip), CSS 86.43 kB (16.36 kB gzip).
- Python compilation: passed.
- Established Ruff correctness gate (`F,E9`): passed.
- `pip check`: no broken requirements.
- `npm audit` production and complete lockfile: zero reported vulnerabilities.
- Documentation links/status and whitespace checks are part of the final credential-free regression run.
- Visual capture scripts for M7.2–M7.5 completed after fixture correction.

- Final credential-free Python regression: **864 passed**, one upstream Starlette/AnyIO deprecation warning, 90.53 seconds.

## 11. Remaining limitations and risks

M8 must still prove clean installation/startup, a representative authorized real-league workflow, operational resource behavior, interruption/recovery from the packaged experience, localhost security assumptions, and final user documentation. The current screenshots and synthetic persisted smoke are not live ESPN evidence. Outcome-model calibration remains provisional as already disclosed. No UI estimates counterparty acceptance, ESPN execution probability, waiver success probability, or future injury events.

The most material performance risk for M8 remains exact action search and repeated V(R)/Monte Carlo work, not React rendering. Existing server-side pagination, background execution, bounded admission, and SQLite result indexing remain the correct controls. No unmeasured frontend optimization was introduced.

## 12. M8 readiness recommendation

**Recommendation: ready for independent checkpoint review, then M8 if accepted.** No known P0 or unresolved P1 integration defect remains. API/statistical semantics reconcile, principal workflows are coherent, configuration authority remains engine/canonical driven, accessibility defects found here are corrected, and verification is current. This document does not accept its own checkpoint and does not start M8.
