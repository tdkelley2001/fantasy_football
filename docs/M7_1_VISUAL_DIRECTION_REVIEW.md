# M7.1 visual direction review

Status: **DESIGN EXPLORATION READY FOR INDEPENDENT REVIEW — NO DIRECTION SELECTED**.

This checkpoint implements three isolated Living League presentation prototypes under `MASTER_SPEC.md` M7.1. They reuse the accepted React shell, API 1.0 DTOs, tokens, sanitized fixture, and factual league fields. The current shell remains available for comparison. No backend, league-rule, probability, ranking, or transaction behavior changed.

## Review routes

- `/?concept=tactical` — Concept A: Tactical League Map
- `/?concept=landscape` — Concept B: Competitive Landscape
- `/?concept=table` — Concept C: Digital Strategy Table
- `/` — current shell comparison

The query selects presentation only and is not persisted. Team objects are keyboard-selectable and update factual context.

## Concepts

**A — Tactical League Map.** An ordinal league constellation makes teams the primary objects. Read order follows official standings and is explicitly labeled; distance, size, and position do not encode strength or probability. Selecting a club focuses its record, points, configured seed, and scheduled opponent. It offers the strongest direct team exploration and a useful future bridge to evidenced relationship overlays. Larger leagues require adaptive density, and future clustering must never be arbitrary.

**B — Competitive Landscape.** The configured championship qualifier count divides the official standing order into the configured field and teams outside it; scheduled matchups form a central spine. This is competition structure, not a probability model or invented tier. It has the clearest hierarchy, scales best across league sizes, and is easiest to audit. Its risk is drifting back toward conventional lists.

**C — Digital Strategy Table.** The football field is the primary interaction environment. Scheduled matchups occupy lanes; selectable club tokens summon factual intelligence at the table edge. Field placement is a layout convention with no quantitative meaning. This has the strongest football and future Strategy Canvas identity, but the highest density, scaling, and mobile risks.

## Comparison

| Criterion | A: Tactical map | B: Landscape | C: Strategy table |
|---|---|---|---|
| War Room fidelity | High | Medium-high | Highest |
| Structural distinctiveness | High | High | Highest |
| Information hierarchy | High | Highest | High |
| Team exploration | Highest | High | High |
| Matchup exploration | Medium | Highest | High |
| Contextual intelligence | High | Medium-high | Highest |
| Different league sizes | Medium-high | Highest | Medium |
| Opportunity/Trade Lab fit | High | Medium-high | Highest |
| Mobile usability | High | Highest | Medium |
| Accessibility | High | High | High, with spatial-order care |
| Implementation complexity | Medium | Low-medium | High |
| Clutter/implication risk | Medium | Low | High |

## Recommendation for review

Recommend **Concept C as the interaction-language north star, composed with Concept B’s competition hierarchy and Concept A’s selectable team-object pattern**. This is not a final selection. Independent review should test C at 10-, 12-, 14-, and 16-team sizes and determine whether its mobile form retains enough value.

## Actual application screenshots

All use the same sanitized eight-team fixture. Desktop is 1440 × 1000; mobile is 390 × 844. Selected captures choose the second available team object.

| Concept | Desktop default | Desktop selected | Mobile |
|---|---|---|---|
| A | [default](images/m7-1/review-tactical-desktop-default-1440x1000.png) | [selected](images/m7-1/review-tactical-desktop-selected-1440x1000.png) | [mobile](images/m7-1/review-tactical-mobile-390x844.png) |
| B | [default](images/m7-1/review-landscape-desktop-default-1440x1000.png) | [selected](images/m7-1/review-landscape-desktop-selected-1440x1000.png) | [mobile](images/m7-1/review-landscape-mobile-390x844.png) |
| C | [default](images/m7-1/review-table-desktop-default-1440x1000.png) | [selected](images/m7-1/review-table-desktop-selected-1440x1000.png) | [mobile](images/m7-1/review-table-mobile-390x844.png) |

## Technical follow-up

Initial loading now aborts through the React effect lifecycle, preventing an unmounted shell from completing its loading transition. Snapshot coverage labels now describe record counts (`Player records`, `Roster assignments`, `Capability records`, `Linked sources`) rather than interpreting capability strings as “supported rules.”

The exploration does not implement M7.2 data, probabilities, or analytical interactions. It does not finalize M7.1.
