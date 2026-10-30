# M7.2 League Overview Analytics

Status: **COMPLETE AND ACCEPTED (29 October 2026)**.

Governing contracts: `MASTER_SPEC.md` M7.2, `ROADMAP.md` M7.2, the accepted M3.4 probability semantics, and M6 retained-run contracts.

## Contract

The input is an active canonical snapshot plus retained background-run metadata. A usable source must be a completed `baseline` run with an available result for that snapshot. The client selects the most recently finished usable run deterministically and permits explicit selection among other retained matching runs. It never launches analysis.

Before display, the client checks API schema version, selected run identity and type, run snapshot identity, result provenance snapshot identity, and canonical snapshot SHA-256. A mismatch is an unavailable result, not permission to combine records. Missing, deleted, expired, failed, cancelled, interrupted, queued, and running results remain distinct from completed evidence.

The read-only League Overview contains ranked championship probability points with engine-supplied simultaneous confidence intervals, a distinct playoff qualification band view, a final-placement heatmap with exact percentages and an accessible table, linked team context, and path/precision/stop/provenance/limitation disclosures.

Backend probabilities remain decimal values in `[0, 1]`; presentation converts them to percentages. A null estimate is **Unavailable**, never zero. The frontend performs no probability, interval, or placement inference.

## Visual representation decisions

M7.2 applies the [visual-first information design standard](UI_DESIGN_VISION.md) component by component:

- **Championship probability — ranked dot-and-whisker plot.** Position on a common 0–100% scale supports accurate league-wide comparison, while the horizontal whisker preserves the engine-supplied simultaneous confidence interval. Exact percentages remain adjacent to every mark.
- **Playoff qualification — ranked probability bands.** Filled bands make qualification likelihood and threshold separation quickly scannable while remaining visually distinct from the championship forecast. Exact percentages are embedded in each band.
- **Final placement — team-by-placement heatmap.** The two-dimensional matrix exposes distribution shape, concentration, and plausible finish ranges across the entire league without reducing each team to a single expected rank. Every cell contains its exact percentage, and a semantic table supplies an accessible alternative.
- **Selected-team context — focused detail panel.** A compact focal panel is appropriate for inspecting two exact forecast metrics, their intervals, and observed record context after graphical league comparison. It is supporting detail rather than the primary league-wide representation.
- **Run provenance and precision — progressive disclosure.** These exact categorical and identifier records do not gain clarity from an arbitrary chart, so a disclosure with aligned facts and definitions is the primary representation.
- **No-result and incomplete states — explicit status narrative plus observed standings.** No chart is drawn without valid analytical evidence. Incomplete coverage receives a prominent warning; a compact standings list is retained only as factual fallback context because inventing a graphical forecast would be misleading.

The run selector is a direct control rather than a visualization. It changes the complete retained evidence context and never blends values across runs.

## Precision and API contract semantics

A completed background execution is not automatically a statistically qualified forecast. The prominent qualification notice independently reports incomplete paths, incomplete analytical capabilities, failure to reach the league-wide precision target, and any team metric whose `precision_reached` value is false. Technical disclosure retains requested/completed/incomplete path counts and the stop reason. Confidence intervals describe Monte Carlo sampling uncertainty only; outcome-model evidence and calibration limitations remain separately labeled.

Both championship and playoff graphics consume only supplied API intervals. Playoff bands use bounded interval markers distinct from the championship dot-and-whisker grammar. When an estimate exists but its interval is null, the exact estimate remains visible with **Interval unavailable** and no artificial zero-width marker. Keyboard-accessible labels state the estimate, interval availability or endpoints, and metric precision status.

The frontend DTOs mirror API 1.0: `incomplete_capabilities` entries are `(capability, scoring_week)` pairs, baseline results retain `candidate_coverage_complete: null`, and provenance includes the complete `application_run` identity. The sanitized fixture follows this authoritative shape.

## Incomplete and invalid states

Incomplete paths or capabilities produce a prominent warning that estimates are conditional on completed valid paths and are not unconditional league probabilities. With no usable completed baseline, observed standings remain visible and the page states whether matching work is active or ended unsuccessfully. It does not fabricate analytics or submit work.

## Accessibility, responsive behavior, and evidence

Every visual value is also text. Native buttons link team selection, focus remains visible, and the placement matrix has a semantic table disclosure. The matrix scrolls on narrow displays while probability and team detail layouts collapse to one column. Dark and light themes reuse M7.1 tokens.

The production build, strict TypeScript check, and 24 frontend tests pass. Tests cover retained selection, rapid run switching, late cancelled responses, in-flight snapshot changes, four- and fourteen-team configuration, league-wide and metric precision, confidence intervals, missing intervals, null estimates, exact placements, incomplete capabilities, unavailable results, cancellation, accessibility, and no-result behavior. The sanitized eight-team visual fixture produces desktop dark/light, laptop, mobile, selected-team, no-result, precision-limited, and unavailable-interval captures under `docs/images/m7-2/`.

Limitations: M7.2 consumes retained results only. Run creation, live progress, scenarios, trades, and acquisitions remain later packages. Monte Carlo interval precision does not eliminate outcome-model uncertainty.
