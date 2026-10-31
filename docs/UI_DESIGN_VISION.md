# UI design vision: premium football analytics

Status: **APPROVED M7 DESIGN NORTH STAR**. M7.1–M7.3 are **COMPLETE AND ACCEPTED** and M7.4 is **IMPLEMENTED — REVIEW PENDING**. The earlier Integrated War Room spatial exploration is preserved as [archived design evidence](M7_1_VISUAL_DIRECTION_REVIEW.md), but no longer defines the product architecture.

## Direction

The product is a premium football analytics platform combining professional quantitative research, modern sports editorial design, and interactive decision-support tools. “War Room” may remain as product identity; it does not mandate an immersive room, spatial league map, tactical field, or game-like navigation.

The active experience is visualization-first rather than table-first. Editorial composition establishes narrative and hierarchy, while compact tables provide precise supporting detail. Technical complexity is disclosed progressively. Every probability, interval, completeness marker, and coverage statement must retain its backend meaning and provenance.

## Principles

- Use meaningful analytical visualization before dense tabulation where the data supports it.
- Compose pages editorially instead of repeating a uniform card grid.
- Use football identity through team monograms, matchup treatments, restrained field or bracket motifs, and licensed assets only when provenance permits.
- Favor modern sans-serif typography, aligned numerals, compact labels, selective color, subtle separation, and purposeful whitespace.
- Make dense information understandable through hierarchy and progressive disclosure.
- Give probabilities, uncertainty, convergence, and incomplete coverage explicit visual treatment when those accepted backend results exist.
- Design dark and light modes independently for contrast and legibility.
- Keep keyboard, screen-reader, reduced-motion, mobile, and direct-control use first class.
- Never convert observed standings into forecasts, nulls into zeros, structural scenarios into authorized transactions, or partial results into converged conclusions.
- Keep the engine and versioned API as the only source of analytical interpretation.

Mandatory field-centric tactical surfaces, league constellations, spatial team maps, and the immersive War Room layout metaphor are retired. Football-field graphics remain available when they explain actual football structure rather than decorate empty space.

## Visual-first information design standard

Default to visual communication wherever it meaningfully improves understanding, comparison, exploration, or decision-making. This is an analytical selection rule, not a requirement to decorate every record.

For every major information component, the designer and implementer must:

1. Determine first whether a meaningful visual representation is possible.
2. Consider the relevant range of forms: charts, plots, heatmaps, distributions, brackets, diagrams, timelines, player or team imagery, and interactive graphical layouts.
3. Select the form whose visual encoding matches the underlying analytical relationship.
4. Verify that it preserves numerical accuracy, statistical uncertainty, accessibility, provenance, and interpretability.
5. Use it as the primary presentation when it communicates the result effectively.
6. Supply exact values, accessible alternatives, or supporting tables where they improve inspection and verification.
7. Use a table as the primary form only when a graphical form would be less clear, less precise, misleading, or unnecessarily complex.

Do not default to tables, cards, or grids merely because an API returns structured records. Equally, do not add decorative charts, arbitrary encodings, or football imagery that does not explain the data. Visual forms must earn their place by making a real relationship easier to perceive.

This standard governs the League Overview and every subsequent M7 workspace: Opportunity Explorer, Trade Lab, Simulation Center, and League Insights. Each work package must document the primary representation chosen for its major analytical components and why that representation fits the analytical meaning.

## Product structure

Compact horizontal global navigation exposes League Overview, Opportunity Explorer, Trade Lab, and Simulation Center; League Insights is visibly deferred. Narrow layouts use an accessible menu instead of compressing every destination. Contextual sidebars remain available for filters, team selection, and analytical detail, but are not permanent global navigation. M7.1 establishes the shell, M7.2 adds the retained-baseline League Overview, and later packages add their accepted analytical interactions without changing the visual integrity rules above.

The selected M7.1 implementation is a reference language, not a frozen component specification. New screens should extend its analytical labels, chart grammar, editorial spacing, identity treatments, provenance cues, and accessible interaction patterns in response to real data and workflows.
