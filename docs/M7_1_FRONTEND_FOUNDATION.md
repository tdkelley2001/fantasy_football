# M7.1 frontend foundation

Status: **IMPLEMENTED — REVIEW PENDING (28 October 2026)**.

Visual review found the initial shell too dashboard-conventional. The follow-up preserves it as a comparison and adds three isolated prototypes documented in [M7.1 visual direction review](M7_1_VISUAL_DIRECTION_REVIEW.md). No direction has been selected.

## Contract and scope

M7.1 implements the Integrated War Room shell required by `MASTER_SPEC.md` M7.1. It presents API 1.0 data and does not calculate rules, projections, probabilities, legality, or rankings. Living League is the source-backed foundation view. Opportunity Explorer, Trade Lab, and Simulation Control are explicitly non-operational placeholders for later M7 packages.

The browser reads relative `/api/v1` URLs. Vite proxies `/api` to FastAPI at `http://127.0.0.1:8000`; Host/Origin protections are unchanged. Integrated contracts are health/build metadata, snapshot listing/detail, and background-run listing.

## Stack and structure

- React/React DOM 19.3.1; TypeScript 7.0.2 strict mode
- Vite 8.3.5 and React plugin 6.1.2; Tailwind CSS/Vite plugin 4.3.3
- Lucide React 1.63.0
- Vitest 5.0.5, Testing Library 16.3.3, jsdom 30.1.3, axe-core 4.14.0
- Playwright Core 1.64.1 with installed Microsoft Edge for visual QA only

`frontend/src/App.tsx` owns the small presentation state and shell; `types/api.ts` mirrors consumed API DTOs; `lib/api.ts` is the typed client; `styles.css` defines tokens, responsive layout, and surface patterns. No general state library or dashboard framework is used.

## Design and interaction

Dark mode is primary: deep graphite/navy foundations, layered cool surfaces, restrained teal accents, and warm focus points. Light mode has independently selected colors. CSS properties provide color, elevation, radius, focus, and motion tokens. A tactical field motif displays standings facts only and is labeled as not being a forecast.

The shell provides a rail, command bar, persistent snapshot selector, workspace, contextual source/build drawer, connection state, and active-run indicator. Phone widths use a keyboard-operable drawer and bottom navigation. Reduced-motion preferences collapse motion. Focus rings, skip navigation, landmarks, accessible names, live status, and non-hover controls are included.

Only `war-room-theme` and `war-room-snapshot` identifiers are stored locally. Payloads/results are not persisted. A missing saved snapshot falls back safely.

## Local startup

```powershell
python -m fantasy_football.app_cli serve --snapshot-db .local/snapshots.sqlite --run-db .local/runs.sqlite
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Validation commands are `npm run typecheck`, `npm test -- --run`, and `npm run build`.

## Honest states

Loading uses a labeled skeleton. Empty storage explains how data becomes available. Transport failure is a disconnected local engine; typed API errors retain backend messages. Run status reports active records or “No active runs.” Deferred destinations never show invented rankings or probabilities.

## Visual QA evidence

These are screenshots of the implemented React app using isolated `frontend/dev/fixture-server.mjs`, an unambiguously sanitized QA fixture. Default startup always uses FastAPI. Reproduce with `node dev/capture-visuals.mjs` while Vite and the fixture are running.

| Capture | Viewport / state |
|---|---|
| [Desktop dark](images/m7-1/desktop-dark-1440x1000.png) | 1440 × 1000, populated fixture |
| [Laptop dark](images/m7-1/laptop-dark-1280x800.png) | 1280 × 800, populated fixture |
| [Mobile dark](images/m7-1/mobile-dark-390x844.png) | 390 × 844, responsive navigation |
| [Desktop light](images/m7-1/desktop-light-1440x1000.png) | 1440 × 1000, light theme |
| [Empty store](images/m7-1/empty-1280x800.png) | 1280 × 800, empty response |
| [Disconnected](images/m7-1/disconnected-1280x800.png) | 1280 × 800, API unavailable |

This is a review checkpoint, not a design freeze. The original visual image was absent, so the implementation follows the accepted written vision.

## Verification and limitations

Tests cover initialization, detail rendering, active runs, keyboard navigation, theme persistence, empty/disconnected/error states, stale selection, responsive navigation semantics, and axe-core. The production bundle is approximately 241 kB JavaScript and 17 kB CSS before gzip (76 kB and 5 kB gzip).

M7.1 does not poll progress, submit/cancel work, render probabilities, inspect candidates, or construct scenarios. Those remain M7.2–M7.5. Automated accessibility checks do not replace independent keyboard, screen-reader, contrast, and usability review.
