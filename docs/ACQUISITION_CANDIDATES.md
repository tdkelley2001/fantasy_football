# Immediate Acquisition Candidate Reference

## Scope and contracts

M5.5 implements a deterministic reference over an explicitly declared finite
universe of standalone acquisitions. The governing contracts are Master
Specification Sections 7, 8, and 12 (M5.5). It does not rank candidates, run
Monte Carlo, submit ESPN transactions, combine trades and waivers, or model
manager claim behavior.

`ImmediateAcquisitionSearchConfiguration` identifies the requester, acquisition
players, optional drop-player filter, enabled add-only/drop-add action forms,
optional acquisition-status filter, and waiver-boundary policy. `None` means a
filter was omitted; an empty tuple is an explicit empty selection. Player,
team, ownership, rule-policy, and type errors fail before enumeration.

The finite leaf is `(acquired player, optional selected drop, ordinary
destination slot)`. Including the destination is necessary because configured
capacity and eligibility can make otherwise identical ownership requests
legally different. `enumerate_immediate_acquisition_candidates()` returns every
leaf and reconciled coverage; `iter_immediate_acquisition_candidates()` yields
the same stable stream without retaining coverage counters. No projection,
V(R), popularity, position preference, or candidate cap prunes the universe.

## Availability and authorization

The analyzer consumes the accepted M2.3b state and transaction primitives:

- `FREE_AGENT` can produce an `authorized_immediate` state only when the exact
  add or selected drop-then-add transition passes all ownership, capacity,
  eligibility, IR, protection, count, and reentry checks.
- `WAIVERS` is never called an immediate free-agent add. With the controlled
  `modeled_weekly_v1` boundary in a supported traditional non-budget league, it
  can produce a `conditional_waiver` successful-claim counterfactual. The state
  includes the accepted priority-to-last consequence, but the record explicitly
  says that claim submission, competing managers, and success are unresolved.
- An unresolved waiver boundary preserves a structurally legal waiver plan as
  unresolved and exposes no resulting state.
- `HOLD` and `UNRESOLVED` expose no resulting state and receive no invented
  release time or authorization.
- `ROSTERED` is prohibited as a standalone acquisition, including a player
  owned by another manager. It is never silently converted into a transfer.

Priority diagnostics report the requester position, higher-priority teams, the
current order, and the conditional post-success order when applicable. They do
not predict whether another manager claims the player and contain no fabricated
success probability.

Every successful candidate state is an immutable `EvolvingLeagueState`, so the
accepted M5.3 canonical state fingerprint can consume it directly. Candidate
identity separately binds snapshot/schema, baseline-state hash, normalized
search configuration, requester, player, selected drop, and destination. A
hypothetical conditional waiver state is not proof of real-world authorization.

## Coverage and limitations

Coverage reports declared and status-eligible acquisition counts, declared
drops, raw leaves, structural feasibility, each exclusive disposition, and
rejection reasons. Disposition counts reconcile exactly to raw leaves. Synthetic
tests establish code behavior only; ESPN waiver clearance timing and competing
claim behavior remain unsupported. FAAB and other waiver policies cannot use
the modeled traditional-waiver boundary.

M5.6+ transaction chains, combined trade/acquisition search, streaming,
statistical ranking, job orchestration, and UI remain deferred.

## Verification evidence

The focused suite has 18 tests covering the hand-counted exhaustive oracle,
add-only and replacement capacity, protected drops, free-agent and waiver
semantics, holds and unresolved status, existing ownership, priority,
traditional-waiver gating, omitted versus empty filters, reordered input,
immutability, and offline execution. The complete credential-free repository
suite has 727 passing tests.

The sanitized three-player/two-drop/two-destination benchmark enumerated all 18
leaves in 0.117 seconds with 0.047 MiB traced peak memory on 24 October 2026.
It found four structurally executable leaves: two authorized free-agent actions
and two conditional waiver scenarios. This is a small synthetic reference
measurement, not a live ESPN or full-league throughput claim.
