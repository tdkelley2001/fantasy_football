# M7.2 League Overview Analytics

Status: **IMPLEMENTED — REVIEW PENDING (29 October 2026)**.

Governing contracts: `MASTER_SPEC.md` M7.2, `ROADMAP.md` M7.2, the accepted M3.4 probability semantics, and M6 retained-run contracts.

## Contract

The input is an active canonical snapshot plus retained background-run metadata. A usable source must be a completed `baseline` run with an available result for that snapshot. The client selects the most recently finished usable run deterministically and permits explicit selection among other retained matching runs. It never launches analysis.

Before display, the client checks API schema version, selected run identity and type, run snapshot identity, result provenance snapshot identity, and canonical snapshot SHA-256. A mismatch is an unavailable result, not permission to combine records. Missing, deleted, expired, failed, cancelled, interrupted, queued, and running results remain distinct from completed evidence.

The read-only League Overview contains ranked championship probability points with engine-supplied simultaneous confidence intervals, a distinct playoff qualification band view, a final-placement heatmap with exact percentages and an accessible table, linked team context, and path/precision/stop/provenance/limitation disclosures.

Backend probabilities remain decimal values in `[0, 1]`; presentation converts them to percentages. A null estimate is **Unavailable**, never zero. The frontend performs no probability, interval, or placement inference.

## Incomplete and invalid states

Incomplete paths or capabilities produce a prominent warning that estimates are conditional on completed valid paths and are not unconditional league probabilities. With no usable completed baseline, observed standings remain visible and the page states whether matching work is active or ended unsuccessfully. It does not fabricate analytics or submit work.

## Accessibility, responsive behavior, and evidence

Every visual value is also text. Native buttons link team selection, focus remains visible, and the placement matrix has a semantic table disclosure. The matrix scrolls on narrow displays while probability and team detail layouts collapse to one column. Dark and light themes reuse M7.1 tokens.

The production build, strict TypeScript check, and 20 frontend tests pass. Tests cover retained selection, run switching, snapshot isolation, four- and fourteen-team configuration, confidence intervals, null estimates, exact placements, incomplete coverage, unavailable results, cancellation, accessibility, and no-result behavior. The sanitized eight-team visual fixture produces desktop dark/light, laptop, mobile, selected-team, and no-result captures under `docs/images/m7-2/`.

Limitations: M7.2 consumes retained results only. Run creation, live progress, scenarios, trades, and acquisitions remain later packages. Monte Carlo interval precision does not eliminate outcome-model uncertainty.
