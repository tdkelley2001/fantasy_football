"""M5.6 exhaustive immediate multi-trade-chain reference.

The search deliberately keeps path history.  Ownership is changed after each
trade, while roster capacity is repaired once, after the explicit chain.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
import hashlib
import itertools
import json
from typing import Iterator

from fantasy_football.canonical.model import LeagueSnapshot, RosterEntry, SlotKind
from fantasy_football.canonical.validation import validate_snapshot
from fantasy_football.evolving_state import EvolvingLeagueState, state_to_json, validate_evolving_state
from fantasy_football.roster_value import value_roster
from fantasy_football.scenario_evaluator import (
    CompletedManualScenario,
    ExplicitRosterChange,
    ProtectedPlayerPin,
    ScenarioRosterAction,
    _automatic_drop_allowed,
    _build_roster,
    _ordinary_capacity,
    _ordinary_count,
    _state_with_roster,
)
from fantasy_football.trade_candidates import TradeShape
from fantasy_football.trade_evaluation import completed_state_fingerprint


class TradeChainError(ValueError):
    """Raised when a chain universe or completion is invalid or unsupported."""


class TradeChainRejectionCode(StrEnum):
    CONSECUTIVE_COUNTERPARTY = "consecutive_counterparty"
    IMMEDIATE_DEPENDENCY_MISSING = "immediate_dependency_missing"
    OWNERSHIP_TRANSITION_INVALID = "ownership_transition_invalid"
    FINAL_COMPLETION_INFEASIBLE = "final_completion_infeasible"


class VacancyEventOrigin(StrEnum):
    PRE_EXISTING = "pre_existing"
    TRADE = "trade"


@dataclass(frozen=True, slots=True)
class TradeChainSearchConfiguration:
    requesting_team_id: int
    counterparty_team_ids: tuple[int, ...]
    player_universe_ids: tuple[int, ...]
    trade_shapes: tuple[TradeShape, ...]
    minimum_chain_length: int = 2
    maximum_chain_length: int = 2
    allowed_outgoing_player_ids: tuple[int, ...] | None = None
    allowed_incoming_player_ids: tuple[int, ...] | None = None
    protected_pins: tuple[ProtectedPlayerPin, ...] = ()
    maximum_completed_paths: int | None = None


@dataclass(frozen=True, slots=True)
class ChainTrade:
    transaction_index: int
    counterparty_team_id: int
    outgoing_player_ids: tuple[int, ...]
    incoming_player_ids: tuple[int, ...]
    dependency_player_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class VacancyEvent:
    transaction_index: int | None
    team_id: int
    created_places: int
    reduced_places: int
    outstanding_places: int
    chronological_priority: int | None
    origin: VacancyEventOrigin


@dataclass(frozen=True, slots=True)
class IntermediateCapacity:
    transaction_index: int
    team_id: int
    ordinary_player_count: int
    configured_capacity: int


@dataclass(frozen=True, slots=True)
class TradeChainCandidate:
    chain_id: str
    snapshot_id: str
    source_schema_version: int
    baseline_state_sha256: str
    search_configuration_sha256: str
    requesting_team_id: int
    trades: tuple[ChainTrade, ...]
    vacancy_events: tuple[VacancyEvent, ...]
    intermediate_capacity: tuple[IntermediateCapacity, ...]
    completed_scenario: CompletedManualScenario
    completed_state_sha256: str
    execution_caveats: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TradeChainCoverage:
    transition_count: int
    rejected_transition_count: int
    raw_complete_path_count: int
    completed_feasible_chain_count: int
    infeasible_final_completion_count: int
    rejection_code_counts: tuple[tuple[TradeChainRejectionCode, int], ...]
    rejection_reason_counts: tuple[tuple[str, int], ...]
    complete: bool
    truncation_stage: str | None
    truncation_reason: str | None


@dataclass(frozen=True, slots=True)
class TradeChainEnumeration:
    search_configuration_sha256: str
    baseline_state_sha256: str
    candidates: tuple[TradeChainCandidate, ...]
    coverage: TradeChainCoverage


@dataclass(frozen=True, slots=True)
class _Validated:
    configuration_sha256: str
    baseline_sha256: str
    requester: int
    counterparties: tuple[int, ...]
    universe: tuple[int, ...]
    shapes: tuple[TradeShape, ...]
    outgoing_filter: frozenset[int] | None
    incoming_filter: frozenset[int] | None
    pins: tuple[ProtectedPlayerPin, ...]
    minimum: int
    maximum: int
    limit: int | None


@dataclass(slots=True)
class _Counters:
    transitions: int = 0
    rejected: int = 0
    raw_paths: int = 0
    infeasible: int = 0
    reasons: Counter[str] | None = None
    codes: Counter[TradeChainRejectionCode] | None = None

    def __post_init__(self) -> None:
        self.reasons = Counter()
        self.codes = Counter()


def _fail(message: str) -> None:
    raise TradeChainError(message)


def _stable_ids(values: tuple[int, ...], label: str, *, empty: bool = False) -> tuple[int, ...]:
    if not isinstance(values, tuple):
        _fail(f"{label} must be a tuple")
    if any(isinstance(item, bool) or not isinstance(item, int) or item == 0 for item in values):
        _fail(f"{label} must contain nonzero integer IDs")
    if len(values) != len(set(values)):
        _fail(f"{label} contains duplicate IDs")
    if not empty and not values:
        _fail(f"{label} must be nonempty")
    return tuple(sorted(values))


def _sha(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _validate(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    configuration: TradeChainSearchConfiguration,
) -> _Validated:
    validate_snapshot(snapshot)
    validate_evolving_state(state, snapshot)
    if not isinstance(configuration, TradeChainSearchConfiguration):
        _fail("configuration must be TradeChainSearchConfiguration")
    if snapshot.snapshot_id is None:
        _fail("chain enumeration requires an identified canonical snapshot")
    team_ids = {item.team_id for item in snapshot.teams}
    player_ids = {item.player_id for item in snapshot.players}
    requester = configuration.requesting_team_id
    if requester not in team_ids or isinstance(requester, bool):
        _fail(f"requesting team {requester!r} is unknown")
    partners = _stable_ids(configuration.counterparty_team_ids, "counterparty_team_ids")
    if requester in partners or set(partners) - team_ids:
        _fail("counterparty_team_ids contain the requester or unknown teams")
    universe = _stable_ids(configuration.player_universe_ids, "player_universe_ids")
    if set(universe) - player_ids:
        _fail("player_universe_ids contain unknown players")
    owners = {item.player_id: item.team_id for item in state.roster_entries}
    if any(owners.get(player_id) not in {requester, *partners} for player_id in universe):
        _fail("every tradeable player must be owned by the requester or an allowed counterparty")
    if not isinstance(configuration.trade_shapes, tuple) or not configuration.trade_shapes:
        _fail("trade_shapes must be a nonempty tuple")
    for shape in configuration.trade_shapes:
        if not isinstance(shape, TradeShape) or shape.outgoing_count <= 0 or shape.incoming_count <= 0:
            _fail("trade shapes require positive outgoing and incoming counts")
    shapes = tuple(sorted(configuration.trade_shapes))
    if len(shapes) != len(set(shapes)):
        _fail("trade_shapes contains duplicates")
    for label, number in (("minimum_chain_length", configuration.minimum_chain_length), ("maximum_chain_length", configuration.maximum_chain_length)):
        if isinstance(number, bool) or not isinstance(number, int) or number < 2:
            _fail(f"{label} must be an integer of at least two")
    if configuration.minimum_chain_length > configuration.maximum_chain_length:
        _fail("minimum_chain_length cannot exceed maximum_chain_length")
    limit = configuration.maximum_completed_paths
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0):
        _fail("maximum_completed_paths must be a positive integer or null")
    outgoing = None if configuration.allowed_outgoing_player_ids is None else frozenset(
        _stable_ids(configuration.allowed_outgoing_player_ids, "allowed_outgoing_player_ids", empty=True)
    )
    incoming = None if configuration.allowed_incoming_player_ids is None else frozenset(
        _stable_ids(configuration.allowed_incoming_player_ids, "allowed_incoming_player_ids", empty=True)
    )
    if (outgoing is not None and not outgoing.issubset(universe)) or (incoming is not None and not incoming.issubset(universe)):
        _fail("player filters must be subsets of player_universe_ids")
    if not isinstance(configuration.protected_pins, tuple):
        _fail("protected_pins must be a tuple")
    if any(not isinstance(pin, ProtectedPlayerPin) for pin in configuration.protected_pins):
        _fail("protected_pins must contain ProtectedPlayerPin records")
    pins = tuple(sorted(configuration.protected_pins, key=lambda item: (item.team_id, item.player_id)))
    if len(pins) != len(set(pins)):
        _fail("protected_pins contains duplicates")
    for pin in pins:
        if owners.get(pin.player_id) != pin.team_id:
            _fail("each protected pin must identify its player's current owner")
    rules = snapshot.rules.trades
    if not rules.enabled or rules.trade_limit == 0:
        _fail("canonical league rules prohibit trades")
    if rules.deadline_utc is not None and snapshot.retrieval_finished_at_utc > rules.deadline_utc:
        _fail("canonical snapshot was retrieved after the trade deadline")
    normalized = {
        "contract": "m5.6-chain-search-v1",
        "snapshot_id": snapshot.snapshot_id,
        "baseline_state_sha256": hashlib.sha256(state_to_json(state, snapshot).encode()).hexdigest(),
        "requesting_team_id": requester,
        "counterparty_team_ids": partners,
        "player_universe_ids": universe,
        "trade_shapes": [asdict(item) for item in shapes],
        "minimum_chain_length": configuration.minimum_chain_length,
        "maximum_chain_length": configuration.maximum_chain_length,
        "allowed_outgoing_player_ids": None if outgoing is None else tuple(sorted(outgoing)),
        "allowed_incoming_player_ids": None if incoming is None else tuple(sorted(incoming)),
        "protected_pins": [asdict(item) for item in pins],
        "maximum_completed_paths": limit,
    }
    return _Validated(
        _sha(normalized), normalized["baseline_state_sha256"], requester, partners, universe,
        shapes, outgoing, incoming, pins, configuration.minimum_chain_length,
        configuration.maximum_chain_length, limit,
    )


def _vacancy_after(count: int, capacity: int) -> int:
    return max(0, capacity - count)


def _apply_trade(
    snapshot: LeagueSnapshot,
    original_entries: dict[int, RosterEntry],
    ownership: dict[int, int],
    requester: int,
    partner: int,
    outgoing: tuple[int, ...],
    incoming: tuple[int, ...],
    transaction_index: int,
    priority_counter: int,
) -> tuple[dict[int, int], tuple[VacancyEvent, ...], tuple[IntermediateCapacity, ...], int]:
    capacity = _ordinary_capacity(snapshot)
    before = {team: _vacancy_after(_ordinary_count(snapshot, ownership, original_entries, team), capacity) for team in (requester, partner)}
    result = dict(ownership)
    for player_id in outgoing:
        if result.get(player_id) != requester:
            _fail(f"transaction {transaction_index} outgoing player {player_id} is not owned by requester")
        result[player_id] = partner
    for player_id in incoming:
        if result.get(player_id) != partner:
            _fail(f"transaction {transaction_index} incoming player {player_id} is not owned by counterparty")
        result[player_id] = requester
    events = []
    diagnostics = []
    for team in sorted((requester, partner)):
        count = _ordinary_count(snapshot, result, original_entries, team)
        after = _vacancy_after(count, capacity)
        created = max(0, after - before[team])
        reduced = max(0, before[team] - after)
        if created or reduced:
            if created:
                priority_counter += 1
            events.append(
                VacancyEvent(
                    transaction_index,
                    team,
                    created,
                    reduced,
                    after,
                    priority_counter if created else None,
                    VacancyEventOrigin.TRADE,
                )
            )
        diagnostics.append(IntermediateCapacity(transaction_index, team, count, capacity))
    return result, tuple(events), tuple(diagnostics), priority_counter


def _completion(
    snapshot: LeagueSnapshot,
    baseline: EvolvingLeagueState,
    ownership: dict[int, int],
    trades: tuple[ChainTrade, ...],
    events: tuple[VacancyEvent, ...],
    pins: tuple[ProtectedPlayerPin, ...],
    chain_id: str,
) -> CompletedManualScenario:
    original_entries = {item.player_id: item for item in baseline.roster_entries}
    original_owners = {item.player_id: item.team_id for item in baseline.roster_entries}
    capacity = _ordinary_capacity(snapshot)
    pin_pairs = {(item.team_id, item.player_id) for item in pins}
    for team_id, player_id in pin_pairs:
        if ownership.get(player_id) != team_id:
            _fail(f"protected pin player={player_id} is not owned by team={team_id} after chain")

    overfull = tuple(sorted(team.team_id for team in snapshot.teams if _ordinary_count(snapshot, ownership, original_entries, team.team_id) > capacity))
    options = []
    for team_id in overfull:
        excess = _ordinary_count(snapshot, ownership, original_entries, team_id) - capacity
        eligible = tuple(sorted(
            player_id for player_id, owner in ownership.items()
            if owner == team_id and (team_id, player_id) not in pin_pairs
            and _automatic_drop_allowed(snapshot, player_id)
            and not (player_id in original_entries and next(rule for rule in snapshot.rules.lineup_slots if rule.slot_id == original_entries[player_id].lineup_slot_id).kind is SlotKind.RESERVE)
        ))
        choices = tuple(itertools.combinations(eligible, excess))
        if not choices:
            _fail(f"team {team_id} cannot reach ordinary capacity while honoring protected pins")
        options.append(choices)
    pre_drop_owners = dict(ownership)
    best = None
    for selections in itertools.product(*options) if options else ((),):
        dropped = frozenset(player for group in selections for player in group)
        candidate_owners = {player: owner for player, owner in ownership.items() if player not in dropped}
        roster = _build_roster(snapshot, candidate_owners, original_entries)
        if roster is None:
            continue
        try:
            candidate_state = _state_with_roster(baseline, snapshot, roster, released_player_ids=dropped, completion_pool=True)
            values = tuple(value_roster(snapshot, candidate_state, team) for team in overfull)
        except ValueError:
            continue
        if any(not value.is_complete for value in values):
            continue
        key = (tuple(value.total_value for value in values), tuple(tuple(-player for player in group) for group in selections))
        if best is None or key > best[0]:
            best = (key, candidate_owners, dropped, roster, values)
    if best is None:
        _fail("no complete legal capacity-drop result exists")
    _, ownership, dropped, roster, drop_values = best
    forced = tuple(
        ScenarioRosterAction("automatic_capacity_drop", team, player, None, None, next(value.total_value for value in drop_values if value.team_id == team))
        for team in overfull for player in sorted(dropped) if pre_drop_owners.get(player) == team
    )

    # Reconcile final vacancies with their earliest still-relevant creation.
    priority: dict[int, int] = {}
    outstanding: dict[int, int] = {}
    for event in events:
        prior = outstanding.get(event.team_id, 0)
        now = prior + event.created_places - event.reduced_places
        outstanding[event.team_id] = max(0, now)
        if prior == 0 and now > 0:
            if event.chronological_priority is None:
                _fail(
                    f"vacancy event for team {event.team_id} creates an outstanding "
                    "vacancy without chronological priority"
                )
            priority[event.team_id] = event.chronological_priority
        if now == 0:
            priority.pop(event.team_id, None)
    vacancies = {
        team.team_id: capacity - _ordinary_count(snapshot, ownership, original_entries, team.team_id)
        for team in snapshot.teams
        if _ordinary_count(snapshot, ownership, original_entries, team.team_id) < capacity
    }
    if set(vacancies) - set(priority):
        _fail(f"vacancy ledger does not establish priority for teams {sorted(set(vacancies) - set(priority))}")
    active_priorities = [priority[team_id] for team_id in vacancies]
    if len(active_priorities) != len(set(active_priorities)):
        _fail("vacancy ledger has conflicting manager priorities")
    additions = []
    player_ids = {item.player_id for item in snapshot.players}
    for team_id in sorted(vacancies, key=priority.__getitem__):
        for ordinal in range(1, vacancies[team_id] + 1):
            choice = None
            for player_id in sorted(player_ids - set(ownership)):
                proposed = {**ownership, player_id: team_id}
                proposed_roster = _build_roster(snapshot, proposed, original_entries)
                if proposed_roster is None:
                    continue
                try:
                    proposed_state = _state_with_roster(baseline, snapshot, proposed_roster, released_player_ids=dropped, completion_pool=True)
                    value = value_roster(snapshot, proposed_state, team_id)
                except ValueError:
                    continue
                if not value.is_complete:
                    continue
                key = (value.total_value, -player_id)
                if choice is None or key > choice[0]:
                    choice = (key, player_id, proposed_roster, value.total_value)
            if choice is None:
                _fail(f"team {team_id} has an unfillable ordinary roster vacancy")
            _, player_id, roster, roster_value = choice
            ownership[player_id] = team_id
            additions.append(ScenarioRosterAction("automatic_vacancy_priority_add", team_id, player_id, original_owners.get(player_id), ordinal, roster_value))
    final_state = _state_with_roster(baseline, snapshot, roster, released_player_ids=dropped, completion_pool=False)
    has_pre_existing = any(event.origin is VacancyEventOrigin.PRE_EXISTING for event in events)
    if has_pre_existing:
        final_state = replace(
            final_state,
            assumption_ids=tuple(
                sorted(
                    {
                        *final_state.assumption_ids,
                        "initial_vacancy_frozen_priority_completion_v1",
                    }
                )
            ),
        )
        validate_evolving_state(final_state, snapshot)
    requester = original_owners[trades[0].outgoing_player_ids[0]]
    changes = tuple(
        change
        for trade in trades
        for change in (
            *(ExplicitRosterChange(player, requester, trade.counterparty_team_id) for player in trade.outgoing_player_ids),
            *(ExplicitRosterChange(player, trade.counterparty_team_id, requester) for player in trade.incoming_player_ids),
        )
    )
    # The path-specific records contain authoritative chronological owners; the
    # flattened changes are explanatory and intentionally retain repetitions.
    core = {
        "contract": "m5.6-chain-completion-v1", "chain_id": chain_id,
        "snapshot_id": snapshot.snapshot_id, "trades": [asdict(item) for item in trades],
        "state": json.loads(state_to_json(final_state, snapshot)),
    }
    return CompletedManualScenario(
        f"m5.6-{chain_id[:20]}", _sha(core), snapshot.snapshot_id or "", final_state,
        changes, pins, forced, tuple(additions),
        tuple(sorted({requester, *(trade.counterparty_team_id for trade in trades)})),
        tuple(
            sorted(
                {
                    "immediate_chain_structural_hypothetical_v1",
                    "all_capacity_drops_before_additions_v1",
                    "vacancy_chronology_manager_first_refill_v1",
                    "espn_intermediate_capacity_execution_unverified",
                    *(
                        ("initial_vacancy_frozen_priority_completion_v1",)
                        if has_pre_existing
                        else ()
                    ),
                }
            )
        ),
    )


def _chain_id(snapshot: LeagueSnapshot, search: _Validated, trades: tuple[ChainTrade, ...]) -> str:
    return _sha({
        "contract": "m5.6-chain-path-v1", "snapshot_id": snapshot.snapshot_id,
        "source_schema_version": snapshot.schema_version,
        "baseline_state_sha256": search.baseline_sha256,
        "configuration_sha256": search.configuration_sha256,
        "trades": [asdict(item) for item in trades],
    })


def _attempts(
    snapshot: LeagueSnapshot,
    baseline: EvolvingLeagueState,
    search: _Validated,
    counters: _Counters,
) -> Iterator[TradeChainCandidate]:
    original_entries = {item.player_id: item for item in baseline.roster_entries}
    initial = {item.player_id: item.team_id for item in baseline.roster_entries}
    pinned = {(item.team_id, item.player_id) for item in search.pins}
    capacity = _ordinary_capacity(snapshot)
    initial_events = []
    priority_counter = 0
    for team_id in baseline.initial_window_waiver_priority:
        vacancy_count = _vacancy_after(
            _ordinary_count(snapshot, initial, original_entries, team_id), capacity
        )
        if vacancy_count:
            priority_counter += 1
            initial_events.append(
                VacancyEvent(
                    None,
                    team_id,
                    vacancy_count,
                    0,
                    vacancy_count,
                    priority_counter,
                    VacancyEventOrigin.PRE_EXISTING,
                )
            )

    def visit(
        ownership: dict[int, int], trades: tuple[ChainTrade, ...], events: tuple[VacancyEvent, ...],
        diagnostics: tuple[IntermediateCapacity, ...], previous_received: frozenset[int],
        last_partner: int | None, priority_counter: int,
    ) -> Iterator[TradeChainCandidate]:
        depth = len(trades)
        if depth >= search.minimum:
            counters.raw_paths += 1
            chain_id = _chain_id(snapshot, search, trades)
            try:
                completed = _completion(snapshot, baseline, dict(ownership), trades, events, search.pins, chain_id)
            except (TradeChainError, ValueError) as exc:
                counters.infeasible += 1
                assert counters.codes is not None
                counters.codes[TradeChainRejectionCode.FINAL_COMPLETION_INFEASIBLE] += 1
                assert counters.reasons is not None
                counters.reasons[str(exc)] += 1
            else:
                yield TradeChainCandidate(
                    chain_id, snapshot.snapshot_id or "", snapshot.schema_version,
                    search.baseline_sha256, search.configuration_sha256, search.requester,
                    trades, events, diagnostics, completed,
                    completed_state_fingerprint(snapshot, completed.state),
                    ("counterparty_acceptance_not_modeled", "espn_transaction_execution_not_authorized", "intermediate_capacity_may_be_hypothetical"),
                )
        if depth == search.maximum:
            return
        requester_players = tuple(sorted(
            player for player in search.universe if ownership.get(player) == search.requester
            and (search.outgoing_filter is None or player in search.outgoing_filter)
            and (search.requester, player) not in pinned
        ))
        for partner in search.counterparties:
            partner_players = tuple(sorted(
                player for player in search.universe if ownership.get(player) == partner
                and (search.incoming_filter is None or player in search.incoming_filter)
                and (partner, player) not in pinned
            ))
            for shape in search.shapes:
                if shape.outgoing_count > len(requester_players) or shape.incoming_count > len(partner_players):
                    continue
                for outgoing in itertools.combinations(requester_players, shape.outgoing_count):
                    for incoming in itertools.combinations(partner_players, shape.incoming_count):
                        counters.transitions += 1
                        if partner == last_partner:
                            counters.rejected += 1
                            assert counters.codes is not None
                            counters.codes[TradeChainRejectionCode.CONSECUTIVE_COUNTERPARTY] += 1
                            continue
                        dependency = tuple(sorted(set(outgoing) & previous_received))
                        if depth and not dependency:
                            counters.rejected += 1
                            assert counters.codes is not None
                            counters.codes[TradeChainRejectionCode.IMMEDIATE_DEPENDENCY_MISSING] += 1
                            continue
                        try:
                            next_owners, new_events, new_diagnostics, next_priority = _apply_trade(
                                snapshot, original_entries, ownership, search.requester, partner,
                                outgoing, incoming, depth + 1, priority_counter,
                            )
                        except TradeChainError as exc:
                            counters.rejected += 1
                            assert counters.codes is not None
                            counters.codes[TradeChainRejectionCode.OWNERSHIP_TRANSITION_INVALID] += 1
                            assert counters.reasons is not None
                            counters.reasons[str(exc)] += 1
                            continue
                        trade = ChainTrade(depth + 1, partner, outgoing, incoming, dependency)
                        yield from visit(next_owners, (*trades, trade), (*events, *new_events), (*diagnostics, *new_diagnostics), frozenset(incoming), partner, next_priority)

    yield from visit(
        initial,
        (),
        tuple(initial_events),
        (),
        frozenset(),
        None,
        priority_counter,
    )


def iter_multi_trade_chains(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    configuration: TradeChainSearchConfiguration,
) -> Iterator[TradeChainCandidate]:
    """Lazily yield every feasible path; configured caps belong to materialization."""

    search = _validate(snapshot, state, configuration)
    if search.limit is not None:
        _fail(
            "maximum_completed_paths requires enumerate_multi_trade_chains so "
            "incomplete coverage can be reported"
        )
    counters = _Counters()
    yield from _attempts(snapshot, state, search, counters)


def enumerate_multi_trade_chains(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    configuration: TradeChainSearchConfiguration,
) -> TradeChainEnumeration:
    """Materialize feasible paths and report exact or explicitly truncated coverage."""

    search = _validate(snapshot, state, configuration)
    counters = _Counters()
    candidates = []
    truncated = False
    for candidate in _attempts(snapshot, state, search, counters):
        if search.limit is not None and len(candidates) == search.limit:
            truncated = True
            break
        candidates.append(candidate)
    reasons = counters.reasons or Counter()
    codes = counters.codes or Counter()
    return TradeChainEnumeration(
        search.configuration_sha256, search.baseline_sha256, tuple(candidates),
        TradeChainCoverage(
            counters.transitions, counters.rejected, counters.raw_paths,
            len(candidates), counters.infeasible,
            tuple(sorted(codes.items(), key=lambda item: item[0].value)),
            tuple(sorted(reasons.items())),
            not truncated, "completed_path_materialization" if truncated else None,
            "configured maximum_completed_paths reached" if truncated else None,
        ),
    )
