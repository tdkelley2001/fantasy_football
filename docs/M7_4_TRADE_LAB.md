# M7.4 Trade Lab

Status: **IMPLEMENTED — REVIEW PENDING**.

Governing contracts: `MASTER_SPEC.md` M7.4, `ROADMAP.md` M7.4, API 1.0 `ManualScenarioRequest` / `ManualScenarioResult`, the accepted M4 [manual scenario evaluator](MANUAL_SCENARIOS.md), and the [visual-first design standard](UI_DESIGN_VISION.md).

## Interaction and contract mapping

The Trade Lab is keyed by canonical snapshot ID and SHA-256. A snapshot change remounts the workspace, aborts outstanding work, and clears draft selections, chronological steps, protected pins, errors, and results. Each roster panel is derived from canonical player, assignment, eligibility, injury, and team records. Slot labels come from canonical `lineup_slot_capacities`; the client does not maintain a universal ESPN position map.

Users select any number of players in each direction, add the exchange as a chronological draft step, and may reorder, edit, or remove steps. `replayDraft()` is the single authoritative frontend bookkeeping function for both displayed hypothetical ownership and aggregate request changes. It validates known players and teams, unique step identities, nonempty steps, duplicate same-step players, same-team transfers, and chronological source ownership, then produces at most one `RosterChangeInput` per changed player from original to final owner. It never silently skips a malformed transfer. This is bookkeeping validation only—not roster legality or ESPN authorization.

Editing retains the step's stable identity and exact sequence index. The roster builder replays only the prefix before that step so its original source players remain selectable. Saving validates the complete proposed sequence, including every later dependency, before replacing the step in place. Invalid edits, removals, and reorders leave the committed sequence untouched and show the replay error. Cancel discards only temporary editor selections. Independent steps may be reordered when the resulting full replay remains valid.

Protected pins map exactly to API 1.0 `ProtectedPlayerInput`. They prevent the accepted completion engine from choosing that player for an automatic capacity drop; they are not ESPN locks and do not prove transaction authorization.

## Final state versus ordered sequence

The timeline preserves the user's ordered hypothesis and intermediate ownership for inspection. API 1.0 accepts aggregate final ownership, not an ordered transaction chain. The interface therefore labels every timeline step as an intermediate structural hypothesis and labels evaluation as **final-state evaluation**. It does not claim intermediate legality, counterparty acceptance, ESPN executability, waiver success, or transaction completion probability. No TypeScript transaction engine was introduced.

The intentional Evaluate action submits `POST /api/v1/runs/manual-scenario`, polls the typed background-run record, and retrieves the retained `ManualScenarioResult`. Every request includes visible and editable master seed, matched path count, confidence level, precision target, IR policy, waiver boundary, and provisional Normal parameters. Before submission the client enforces the API 1.0 numerical domain: finite values; integral seed and path count; path bounds; open probability bounds; supported policy enums; nonnegative, nonzero Normal dispersion; and unique, known, rostered protected players synchronized to final ownership. These checks prevent malformed HTTP requests but do not recreate analytical validation.

The browser never launches work in response to player selection alone. Temporary player/team/filter/editor choices do not change the committed scenario revision and do not invalidate an existing result; the interface explicitly says they are absent from that completed analysis. Committing a step, pin, or evaluation setting marks prior output stale. Unsupported, rejected, cancelled, interrupted, failed, unavailable, stale, scenario-mismatched, or provenance-mismatched work is not displayed as successful.

## Visual representation decisions

- **Roster composition — paired roster surfaces.** Two canonical rosters flank a central exchange summary because ownership and direction are the primary construction relationships. Search and canonical slot-name filters remain direct controls.
- **Multi-step draft — ordered action flow.** A numbered timeline preserves chronology and intermediate dependencies more honestly than collapsing actions into a table.
- **League impacts — signed paired-interval plots.** Championship and playoff differences use a common zero reference, exact baseline/scenario probabilities, probability-point changes, and engine-supplied paired intervals. A visible difference is not described as statistically significant.
- **Roster completion — explicit consequence strip.** Forced drops and automatic additions are separated from user-selected actions and identified as engine completion behavior.
- **Lineup explanations — weekly before/after inspection.** Changed weeks lead with projected-point difference, then exact starter, bench, reserve, and vacancy sets. Aggregate records are never reinterpreted as player projection changes.

The experience is a football strategy workspace rather than a data-entry form. Visuals remain semantically grounded; exact text accompanies graphical marks. Desktop/laptop use a paired builder, while mobile stacks both rosters, the exchange, timeline, settings, and results. All player selection and timeline controls are native keyboard-operable buttons; no drag interaction is required. Dark/light themes and reduced-motion behavior inherit the accepted shell.

## Integrity, uncertainty, and limitations

Committed draft, protection, and settings mutations abort local request observation and mark any previous result stale. This does **not** claim to cancel an accepted backend job; a visible notice explains that the job may continue independently. Broad run management remains deferred to M7.5. Submission, polling, and result retrieval validate the active revision, terminal completion and result availability, run type, run ID, scenario ID, snapshot ID, canonical SHA-256, and API version. The output identifies the provisional outcome model and distinguishes Monte Carlo paired-interval uncertainty from unquantified outcome-model uncertainty. Backend-returned assumptions remain visible.

M7.4 does not submit ESPN transactions, validate ordered chains, model trade acceptance, create acquisition success probabilities, add league rules, persist private roster payloads in browser storage, or provide M7.5's general run-management experience. Scenario comparison is deferred rather than mixing incompatible settings or provenance.

## Verification evidence

Focused tests cover exact replay and aggregation; unknown players/teams, duplicates, and ownership discontinuities; one-for-one and uneven exchanges; stable first/middle edits; edit cancellation; valid and invalid reordering; dependent-step edit/removal rejection; temporary versus committed revisions; local observation versus backend cancellation; malformed numerical settings and pins; intentional background submission; paired all-team impacts; forced drops; automatic additions; weekly starter/bench/reserve/vacancy explanations; failed requests; snapshot isolation; late responses; fourteen-team variability; keyboard access; and automated accessibility checks. Sanitized screenshots under `images/m7-4/` cover empty, constructed, multi-step, edit, evaluated, impact, lineup, error, dark/light, laptop, and mobile states. Fixtures demonstrate UI behavior and do not claim live ESPN evidence.
