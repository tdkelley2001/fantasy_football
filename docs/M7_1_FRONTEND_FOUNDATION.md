# M7.1 analytics-first frontend foundation

Status: **IMPLEMENTED — REVIEW PENDING (29 October 2026)**.

## Contract and scope

Under `MASTER_SPEC.md` M7.1, the frontend presents accepted API 1.0 fields and never calculates league rules, projections, probabilities, legality, or rankings. The active League Overview is an observed snapshot surface. Opportunity Explorer, Trade Lab, and Simulation Center remain honestly labeled, non-operational destinations for M7.3–M7.5; M7.2 supplies the later simulation-driven overview.

The browser reads relative `/api/v1` URLs. Vite proxies `/api` to the local FastAPI service. Integrated contracts are health/build metadata, snapshot listing/detail, and background-run listing. No backend or analytical contract changed.

## Stack and structure

- React/React DOM 19.3.1 and strict TypeScript 7.0.2
- Vite 8.3.5, Tailwind CSS/Vite 4.3.3, and Lucide React 1.63.0
- Vitest, Testing Library, jsdom, axe-core, and Playwright Core for verification

`App.tsx` owns shell and request state. `LeagueOverview.tsx` owns the source-backed reference composition. `types/api.ts` mirrors consumed DTOs, `lib/api.ts` is the typed client, and `styles.css` contains tokens and responsive presentation. The prior three-concept source remains isolated historical evidence and is not loaded by the active application.

## Selected design

The selected layout uses a compact league masthead, interactive horizontal observed-points comparison, contextual team focus, featured scheduled matchup, compact standings, configured postseason context, and evidence provenance footer. These are distinct visual forms rather than interchangeable cards. Team monograms and matchup treatments create football identity without unlicensed logos or player imagery.

Observed points and current standings are explicitly labeled as snapshot facts, not forecasts. Postseason qualification counts are configuration context; qualification probabilities are expressly deferred. Null and unresolved configuration values remain unresolved.

Dark mode uses deep neutral surfaces, restrained teal, and warm selection emphasis. Light mode has separate surface and contrast choices. Modern sans-serif typography, aligned numerals, minimal borders, and compact labels replace the superseded oversized-serif, neon, spatial War Room direction.

## Interaction and request correctness

The shell provides persistent snapshot selection, primary analytical navigation, local connection and active-run status, theme switching, responsive navigation, and a source/build drawer. The drawer receives focus on opening, closes with Escape, and restores focus to its trigger.

Each effect owns and aborts its request controller. Snapshot requests carry monotonically increasing versions; only the latest non-aborted request may commit data, loading state, or local selection. Rapid selection remains enabled while a prior detail request is pending. Retry replaces the active controller and disconnected state never preserves stale success as current data.

Only `war-room-theme` and `war-room-snapshot` identifiers are stored locally. Payloads and results are not persisted.

## Local startup

```powershell
python -m fantasy_football.app_cli serve --snapshot-db .local/snapshots.sqlite --run-db .local/runs.sqlite
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Validation commands are `npm run typecheck`, `npm test -- --run`, and `npm run build`.

## Visual QA evidence

All captures are from the actual React application using the sanitized `frontend/dev/fixture-server.mjs` data. Reproduce with `node dev/capture-visuals.mjs` while Vite and the fixture are running.

| Capture | Viewport / state |
|---|---|
| [Desktop dark](images/m7-1/analytics-desktop-dark-1440x1000.png) | 1440 × 1000, populated |
| [Desktop light](images/m7-1/analytics-desktop-light-1440x1000.png) | 1440 × 1000, populated |
| [Laptop](images/m7-1/analytics-laptop-dark-1280x800.png) | 1280 × 800, populated |
| [Mobile](images/m7-1/analytics-mobile-dark-390x844.png) | 390 × 844, responsive |
| [Selected team](images/m7-1/analytics-team-selected-1440x1000.png) | Sunday Union detail selected |
| [Empty store](images/m7-1/analytics-empty-1280x800.png) | no snapshots |
| [Disconnected](images/m7-1/analytics-disconnected-1280x800.png) | local API unavailable |

Review confirms editorial hierarchy, multiple meaningful visual forms, legible chart labels, football-specific identity, deliberate dark/light modes, and complete mobile content. The fixed mobile navigation intentionally remains visible; bottom content padding keeps the final controls reachable.

## Verification and limitations

Frontend tests cover source-backed rendering, rapid-request races, unmount cleanup, selection persistence, keyboard navigation, drawer focus, theme persistence, empty/disconnected/typed-error states, responsive navigation semantics, and axe-core. Player photos, NFL marks, and team logos are not used; any future imagery requires a licensed and provenance-documented source.

M7.1 does not poll run progress, render simulation probabilities, inspect candidates, submit work, or construct scenarios. Those capabilities remain gated to M7.2–M7.5. Automated accessibility checks supplement rather than replace independent keyboard, screen-reader, contrast, and usability review.
