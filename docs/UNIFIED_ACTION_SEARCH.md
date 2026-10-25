# Unified immediate action search (M5.7)

Status: **IMPLEMENTED — REVIEW PENDING**.

`fantasy_football.unified_actions` composes the accepted M5.1, M5.5, and M5.6
references. It does not reimplement trade legality, acquisition authorization,
roster valuation, final-state identity, or Monte Carlo statistics.

## Supported finite grammar

The caller independently selects action families and exact orderings. V1
supports:

- standalone trade;
- standalone multi-trade chain;
- standalone immediate acquisition or drop-and-add;
- trade then acquisition;
- acquisition then trade;
- chain then acquisition; and
- two or more acquisitions up to the configured total-action limit.

An acquisition between dependent trade steps is intentionally unsupported.
It neither satisfies nor resets M5.6's rule that trade `n` must spend a player
acquired in trade `n - 1`. Future grammar extensions must preserve that fact
explicitly rather than inferring dependency from general ownership history.

Configuration separately specifies requester, allowed families/orderings,
counterparties, tradeable players, acquisition players, drop universe, trade
shapes, chain lengths, total actions, availability filter, waiver boundary,
protected players, optional requester-only V(R) screening, and an optional
materialization limit. Omitted drop/status filters retain M5.5 semantics;
explicitly empty tuples mean no selected drops/statuses. Configuration identity
normalizes all unordered inputs.

## Chronology and authorization

Each source action is generated against the preceding action's resulting
immutable state. Ownership, availability, acquisition counts, holds,
same-cycle restrictions, waiver priority, IR restrictions, and protection are
therefore revalidated at every acquisition or trade boundary. A player cannot
be reused by a former owner or acquired twice. Protected players are excluded
from explicit trade and drop choices.

M5.6 retains authority for trade-chain dependency, partner chronology,
pre-existing/trade-created vacancy events, temporary imbalance diagnostics,
all-drops-before-additions completion, and manager-first vacancy priority.
M5.5 retains authority for free-agent versus waiver/held/unresolved/rostered
status and typed legality failures.

Execution is represented by two independent stable fields. `execution_status`
is `transaction_authorized` or `structural_hypothetical`; `acquisition_status`
is `immediate_free_agent` or `conditional_waiver`. Therefore an over-capacity
intermediate sequence can never present an unqualified authorized status, and
both immediate and conditional acquisitions remain distinguishable within
either sequence class. A modeled conditional waiver records successful-claim
priority movement but never claims likely success or resolves higher-priority
manager behavior. Held,
unresolved, and unauthorized paths are counted as source rejections and never
materialized as executable candidates.

Trade→acquisition and chain→acquisition preserve the chronological incomplete
ownership and vacancy ledger. The explicit acquisition is authorized next,
before deterministic completion chooses any vacancy pickups, and completion is
then applied exactly once. Thus a two-for-one trade can be followed by the
selected add-only pickup without that vacancy first being consumed by an
automatic addition. Capacity drops required by the complete path still precede
all automatic additions. Acquisition→trade preserves acquisition counts and
availability in the trade baseline. This V1 sequencing is structural what-if
analysis; it does not authorize ESPN submissions.

Authorization of an acquisition from an incomplete trade path is deliberately
separate from final structural completion. A capacity-neutral authorization
view retains the requester's actual reserve occupants and the selected
player's real shared availability, counters, waiver order, hold/reentry state,
IR evidence, and destination eligibility. It contains no ordinary-roster proxy
drops. An explicit selected drop is checked independently for ownership and
protection before authorization. The accepted M5.6 completion subsequently
chooses every permanent capacity drop through V(R); the selected acquisition
is pinned against being discarded by that completion. If a trade leaves an
intermediate team over capacity, the candidate is marked
`structural_intermediate_only` and carries the caveat
`intermediate_capacity_is_structural_what_if_not_transaction_authorization`.
That label never claims the combined sequence is immediately ESPN-executable.
Free-agent authorization and conditional-waiver status describe only the
explicit acquisition boundary; neither upgrades a structural hypothetical
sequence to transaction-authorized.

## Identity, screening, and evaluation

Every candidate ID includes snapshot, complete baseline-state identity,
normalized unified configuration, ordering, and exact source action IDs and
players. Every final state uses the accepted M5.3
`completed_state_fingerprint`. Distinct paths remain separate; exact equivalent
states are grouped many-to-one and expose avoided-evaluation counts.

Optional combined screening compares the requester's complete final state with
the baseline using unified V(R). It is disableable and never screens an
intermediate action. Counterparty thresholds across multi-party paths are
currently unsupported and fail configuration validation rather than being
silently approximated.

`evaluate_unified_action_states` runs one fixed shared baseline batch, invokes the
accepted M4 paired comparison once per unique completed state, and links every
path to that result. It introduces
no estimator, confidence interval, random draw, or ranking rule. Progressive
sampling and multiplicity-aware finalist decisions are **not integrated by this
adapter**. Its immutable state groups are the narrow input boundary for later
M5.4 orchestration work reserved to M5.8. The fixed-batch result therefore makes
no ranking-resolution or precision-completeness claim. Conditional-waiver
caveats remain path-level metadata and must not be presented as actionable
certainty.

## Coverage and limitations

The lazy iterator consumes accepted lazy trade, chain, and acquisition sources
incrementally and can emit a prefix without constructing the remaining source universe.
The materialized interface reports generated/retained/screened paths,
authorized versus conditional paths, source rejection categories, unique final
states, reuse, and explicit truncation. A configured cap is rejected by the
iterator because only the materialized result can report incomplete coverage.
Candidate completeness and Monte Carlo precision are separate claims.

V1 does not support trade→acquisition→trade interleaving, acquisition insertion
inside a dependency chain, standalone drops without an addition, competing
manager claim simulation, waiver success probabilities, future-week streaming,
M5.8 scheduling/progressive orchestration, or GUI/background jobs. A requested
standalone chain or chain→acquisition length that exceeds the unified total
action limit is rejected explicitly rather than silently omitted.

## Synthetic benchmark

On 25 October 2026 under Python 3.12 on the development Windows host, the
sanitized four-team mixed trade→add, add→trade, and chain→add universe produced
20 retained paths and 20 final states, while recording 25 structurally
infeasible acquisition leaves, in 2.182 seconds with 0.661 MiB traced peak.
This is a small synthetic generation benchmark and includes no Monte Carlo.

The final incomplete-state authorization follow-up also measured an adversarial
over-capacity requester case (one-for-two trade followed by the selected
acquisition): three retained structural paths, two exact final states, 1.783
seconds, and 0.319 MiB traced peak. This is synthetic correctness/performance
evidence, not a live ESPN transaction benchmark.
