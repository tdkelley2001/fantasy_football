# M7.4 Trade Lab

Status: **IMPLEMENTED — REVIEW PENDING**.

Governing contracts: `MASTER_SPEC.md` M7.4, `ROADMAP.md` M7.4, API 1.0 `ManualScenarioRequest` / `ManualScenarioResult`, the accepted M4 [manual scenario evaluator](MANUAL_SCENARIOS.md), and the [visual-first design standard](UI_DESIGN_VISION.md).

## Interaction and contract mapping

The Trade Lab is keyed by canonical snapshot ID and SHA-256. A snapshot change remounts the workspace, aborts outstanding work, and clears draft selections, chronological steps, protected pins, errors, and results. Each roster panel is derived from canonical player, assignment, eligibility, injury, and team records. Slot labels come from canonical `lineup_slot_capacities`; the client does not maintain a universal ESPN position map.

Users select any number of players in each direction, add the exchange as a chronological draft step, and may reorder, edit, or remove steps. `draftStepsToRosterChanges()` independently validates chronological ownership and produces at most one aggregate `RosterChangeInput` per changed player from original to final owner. It rejects duplicate same-step players, same-team transfers, and ownership discontinuities. This is bookkeeping validation only—not roster legality or ESPN authorization.

Protected pins map exactly to API 1.0 `ProtectedPlayerInput`. They prevent the accepted completion engine from choosing that player for an automatic capacity drop; they are not ESPN locks and do not prove transaction authorization.

## Final state versus ordered sequence

The timeline preserves the user's ordered hypothesis and intermediate ownership for inspection. API 1.0 accepts aggregate final ownership, not an ordered transaction chain. The interface therefore labels every timeline step as an intermediate structural hypothesis and labels evaluation as **final-state evaluation**. It does not claim intermediate legality, counterparty acceptance, ESPN executability, waiver success, or transaction completion probability. No TypeScript transaction engine was introduced.

The intentional Evaluate action submits `POST /api/v1/runs/manual-scenario`, polls the typed background-run record, and retrieves the retained `ManualScenarioResult`. Every request includes visible and editable master seed, matched path count, confidence level, precision target, IR policy, waiver boundary, and provisional Normal parameters. The browser never launches work in response to selection alone. Unsupported, rejected, cancelled, failed, stale, or provenance-mismatched work is not displayed as successful.

## Visual representation decisions

- **Roster composition — paired roster surfaces.** Two canonical rosters flank a central exchange summary because ownership and direction are the primary construction relationships. Search and canonical slot-name filters remain direct controls.
- **Multi-step draft — ordered action flow.** A numbered timeline preserves chronology and intermediate dependencies more honestly than collapsing actions into a table.
- **League impacts — signed paired-interval plots.** Championship and playoff differences use a common zero reference, exact baseline/scenario probabilities, probability-point changes, and engine-supplied paired intervals. A visible difference is not described as statistically significant.
- **Roster completion — explicit consequence strip.** Forced drops and automatic additions are separated from user-selected actions and identified as engine completion behavior.
- **Lineup explanations — weekly before/after inspection.** Changed weeks lead with projected-point difference, then exact starter, bench, reserve, and vacancy sets. Aggregate records are never reinterpreted as player projection changes.

The experience is a football strategy workspace rather than a data-entry form. Visuals remain semantically grounded; exact text accompanies graphical marks. Desktop/laptop use a paired builder, while mobile stacks both rosters, the exchange, timeline, settings, and results. All player selection and timeline controls are native keyboard-operable buttons; no drag interaction is required. Dark/light themes and reduced-motion behavior inherit the accepted shell.

## Integrity, uncertainty, and limitations

Draft mutations abort in-flight work and mark any previous result stale. Submission, polling, and result retrieval validate the active revision, run type, run ID, snapshot ID, canonical SHA-256, and API version. The output identifies the provisional outcome model and distinguishes Monte Carlo paired-interval uncertainty from unquantified outcome-model uncertainty. Backend-returned assumptions remain visible.

M7.4 does not submit ESPN transactions, validate ordered chains, model trade acceptance, create acquisition success probabilities, add league rules, persist private roster payloads in browser storage, or provide M7.5's general run-management experience. Scenario comparison is deferred rather than mixing incompatible settings or provenance.

## Verification evidence

Focused tests cover exact draft aggregation, chronological ownership failures, one-for-one and uneven exchanges, multiple players, editing/reset, protected pins, explicit configuration, intentional background submission, paired all-team impacts, forced drops, automatic additions, weekly starter/bench/reserve/vacancy explanations, failed requests, snapshot isolation, late responses, fourteen-team variability, keyboard access, and automated accessibility checks. Sanitized screenshots under `images/m7-4/` cover empty, constructed, multi-step, evaluated, impact, lineup, error, dark/light, laptop, and mobile states. Fixtures demonstrate UI behavior and do not claim live ESPN evidence.
