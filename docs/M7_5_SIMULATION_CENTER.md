# M7.5 Simulation Center

Status: **IMPLEMENTED — REVIEW PENDING** (31 October 2026). Governing contracts: `MASTER_SPEC.md` M7.5, API schema 1.0, `RUN_MANAGEMENT.md`, and the visual-first standard in `UI_DESIGN_VISION.md`.

## Contract and output

The Simulation Center is an integrated Configure → Monitor → History surface. It submits accepted API 1.0 baseline and action-search requests, monitors retained run and progress records, and delegates completed-result rendering to League Overview, Opportunity Explorer, or Trade Lab. It does not implement analytical estimators, legality, roster completion, or candidate generation in TypeScript.

Quick, Balanced, and High Precision are transparent runtime presets. Selecting one writes visible path, confidence, precision, and checkpoint fields; all effective fields remain inspectable and editable. Action-search configuration exposes requesting team, families, orderings, counterparties, player restrictions, trade shape, chain/action bounds, fixed/progressive evaluation, sampling, candidate/evaluation limits, wall-clock budget, workers, and response rows. Backend validation and admission policy remain authoritative.

## Lifecycle semantics

- Submission requires deliberate action and is guarded against duplicate in-flight submission. Ambiguous transport failures are not retried.
- Active polling aborts on unmount, remains scoped to run/snapshot identity, and stops at terminal state.
- The UI shows actual stages, counters, coverage, precision, ranking resolution, elapsed time, and stop reason. It never derives an overall percentage or ETA. Baseline/manual work is explicitly described as coarse progress.
- Cancellation is cooperative. `cancel_requested` is distinct from `cancelled`, and completion can win the race before cancellation takes effect.
- Terminal deletion is explicit, confirms the run identity, and is visually separate from cancellation.

## History, navigation, identity, and export

History is snapshot-scoped and searchable/filterable. API 1.0 currently exposes a newest-first bounded list of at most 50 records and no request-body retrieval; the UI does not claim complete lifetime history or recreate historical configuration.

Completed baseline and action-search runs reopen in their established workspaces with an explicit preferred run ID. Snapshot mismatch is rejected by navigation and independently validated by each result viewer. Manual results reopen Trade Lab, but their historical draft is not reconstructed because the retained contract does not contain it.

Trade Lab submissions now receive unique user-facing scenario IDs (`trade-lab-<snapshot>-<uuid>`), distinct from run ID and engine scenario SHA-256. The current export is intentionally limited to retrieved run metadata JSON and labels its scope, timestamp units, snapshot, canonical identity, and run ID.

## Visual and accessibility decisions

- A lifecycle timeline communicates categorical state without inventing a gauge.
- Source-backed counters are primary; the coverage/precision matrix keeps independent completeness dimensions distinct.
- Exact retained records use a compact list because timestamps and identities require precise inspection.
- Status is never encoded by color alone. Keyboard controls, semantic labels, mobile reflow, and reduced-motion behavior use the shared shell.

## Verification and limitations

Focused tests cover DTO construction, presets, invalid settings/membership, deliberate submission, progress semantics, cancellation acknowledgement, filtering/navigation, bounded-history disclosure, and axe accessibility. Existing frontend suites cover stale responses, snapshot isolation, result provenance, responsive navigation, and analytical workspaces. Actual captures live under `docs/images/m7-5/`.

Known limitations: run history is bounded to 50 records; baseline/manual progress is coarse; expiration has no separate status enum; export covers metadata rather than full candidate/state universes; retained manual results cannot reconstruct historical transaction drafts.

M7.5 remains pending independent review. M8 has not started.
