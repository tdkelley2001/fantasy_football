# Fantasy Football Decision Engine

This repository is being reset for a clean-sheet rebuild of a league-wide decision engine for ESPN fantasy football. The intended system will estimate season-outcome distributions and compare roster actions by their effect on championship probability while honoring real league rules, uncertainty, and full-league consequences.

## Current status

Repository transition only. No new engine implementation has begun, and every M0-M7 work package is **NOT STARTED**. The former application, research artifacts, and tests remain recoverable from the archival Git reference `archive/legacy-pre-clean-sheet-2026-10-15`.

Do not begin M0.1 until this transition is reviewed and approved.

## Authoritative documentation

- [Master specification](docs/MASTER_SPEC.md) — the complete approved model specification and governing requirements.
- [Development roadmap](docs/ROADMAP.md) — the M0-M7 milestone sequence, individual work packages, dependencies, gates, and current statuses.
- [Agent instructions](AGENTS.md) — standing implementation and verification rules for future Codex work.

The master specification is authoritative. If another document or future implementation conflicts with it, stop and resolve the conflict explicitly rather than silently changing the model.

## Upcoming milestone

After transition approval, M0 is the next milestone: the ESPN data and feasibility audit. Its first work package is M0.1, repository and development-environment setup. This transition deliberately does not perform that work.

## Historical implementation

The legacy code is not a foundation for the rebuild. It may be inspected as historical reference, but reuse requires an explicit specification-based justification and independent tests. To inspect it without changing the current branch:

```shell
git show archive/legacy-pre-clean-sheet-2026-10-15:<path>
```

To work with the full archived tree, create a separate worktree or branch from that reference.
