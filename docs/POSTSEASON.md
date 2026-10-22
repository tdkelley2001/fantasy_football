# Deterministic Postseason Engine

M2.4 implements a pure, immutable postseason state machine in
`fantasy_football.postseason`. It consumes a validated canonical snapshot and
the final modeled regular-season standings. It never uses the snapshot's
historical playoff-seed field as the simulated seed order.

## Supported championship contract

The reference implementation currently supports the verified six-team,
no-reseed championship: seeds 1 and 2 receive first-round byes, seed 3 plays
seed 6, and seed 4 plays seed 5. Semifinals are seed 1 against the 4/5 winner
and seed 2 against the 3/6 winner. The final round contains championship,
third-place, and fifth-place games and resolves places 1–6.

Round-to-matchup-period relationships and scoring weeks come from canonical
league rules. Multiweek games accumulate supplied weekly team scores with
`math.fsum`; no rounding or zero floor is applied. Exact ties advance the
higher original postseason seed only when the canonical rule is understood as
`higher_seed`. Unresolved seeding, unsupported bracket structures, missing
weekly scores, nonfinite scores, and unsupported tie rules fail explicitly.

Callers may supply already-computed weekly team totals with
`apply_postseason_team_scores()`, or use `score_frozen_postseason_week()` to
validate frozen M2.1 lineups against modeled roster state and sum externally
supplied realized player scores through the established M2.2 scoring rules.
Neither route generates outcomes, changes rosters, or mutates its inputs.

## ESPN consolation ladder

ESPN's official playoff rules establish that every non-championship qualifier
enters a head-to-head Consolation Ladder, winners move upward, losers move
downward, the upper and lower boundaries cannot be crossed, and every team
continues playing. First-round participants are paired by adjacent descending
seed; if the count is odd, the lowest seed receives the bye. Consequently the
current 14-team/six-qualifier shape initializes 7–8, 9–10, 11–12, and 13–14.
Championship and consolation membership never cross.

Original postseason seed and current ladder position are separate immutable
fields. Official prose does not uniquely determine every later-round pairing,
so the engine does not invent one. Without an explicit validated
`ConsolationLadderConfiguration`, initialization and first-round scoring remain
supported while `consolation_later_round_transition_mapping` stays unresolved.
An explicit configuration defines each winner/loser position transition and
the final placement mapping. The engine validates complete coverage, unique
positions, upper/lower bounds, continued participation, and period mappings
before advancing. Final placements are emitted only after every configured
relationship resolves.

## Determinism and limitations

All collections and results use stable identifiers and deterministic ordering.
The state records completed and in-progress weekly scoring, active consolation
positions, final placements, and unresolved capabilities. The engine is a
deterministic reference, not an ESPN bracket scraper, score generator, waiver
processor, or full-season coordinator. Arbitrary championship formats,
reseeding, and unconfigured later-round consolation mappings remain unsupported
rather than receiving fallback behavior.

The credential-free acceptance run contains 13 focused postseason tests and
394 passing repository tests. On the development Windows/Python 3.12
environment, 1,000 synthetic 14-team initializations took 6.67 seconds
(6.67 ms each) and peaked at 382.3 KiB of traced Python memory. This is a
synthetic deterministic benchmark, not a live ESPN workload.

