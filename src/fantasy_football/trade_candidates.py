"""M5.1 exhaustive deterministic single-trade candidate reference."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
import itertools
import json
import math
from typing import Iterator

from fantasy_football.canonical.model import LeagueSnapshot
from fantasy_football.canonical.validation import validate_snapshot
from fantasy_football.evolving_state import (
    EvolvingLeagueState,
    state_to_json,
    validate_evolving_state,
)
from fantasy_football.scenario_evaluator import (
    CompletedManualScenario,
    ExplicitRosterChange,
    ManualScenario,
    ProtectedPlayerPin,
    ScenarioEvaluationError,
    complete_manual_scenario,
)


class TradeCandidateError(ValueError):
    """Raised when a finite trade universe is malformed or unsupported."""


class TradeExecutionStatus(StrEnum):
    STRUCTURAL_HYPOTHETICAL_ONLY = "structural_hypothetical_only"


@dataclass(frozen=True, slots=True, order=True)
class TradeShape:
    outgoing_count: int
    incoming_count: int


@dataclass(frozen=True, slots=True)
class SingleTradeSearchConfiguration:
    requesting_team_id: int
    counterparty_team_ids: tuple[int, ...]
    player_universe_ids: tuple[int, ...]
    trade_shapes: tuple[TradeShape, ...]
    allowed_outgoing_player_ids: tuple[int, ...] | None = None
    allowed_incoming_player_ids: tuple[int, ...] | None = None
    protected_pins: tuple[ProtectedPlayerPin, ...] = ()


@dataclass(frozen=True, slots=True)
class SingleTradeCandidate:
    candidate_id: str
    snapshot_id: str
    source_schema_version: int
    baseline_state_sha256: str
    search_configuration_sha256: str
    requesting_team_id: int
    counterparty_team_id: int
    shape: TradeShape
    outgoing_player_ids: tuple[int, ...]
    incoming_player_ids: tuple[int, ...]
    explicit_changes: tuple[ExplicitRosterChange, ...]
    structural_feasible: bool
    execution_status: TradeExecutionStatus
    execution_caveats: tuple[str, ...]
    completed_scenario: CompletedManualScenario


@dataclass(frozen=True, slots=True)
class TradeCandidateCoverage:
    declared_player_count: int
    counterparty_count: int
    shape_count: int
    combination_count: int
    structurally_feasible_count: int
    structurally_infeasible_count: int
    infeasible_reason_counts: tuple[tuple[str, int], ...]
    complete: bool


@dataclass(frozen=True, slots=True)
class TradeCandidateEnumeration:
    search_configuration_sha256: str
    baseline_state_sha256: str
    candidates: tuple[SingleTradeCandidate, ...]
    coverage: TradeCandidateCoverage


@dataclass(frozen=True, slots=True)
class _ValidatedSearch:
    configuration_sha256: str
    baseline_state_sha256: str
    requester: int
    counterparties: tuple[int, ...]
    universe: tuple[int, ...]
    shapes: tuple[TradeShape, ...]
    outgoing: tuple[int, ...]
    incoming_by_counterparty: tuple[tuple[int, tuple[int, ...]], ...]
    pins: tuple[ProtectedPlayerPin, ...]
    caveats: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _RejectedCandidate:
    reason: str


def _fail(message: str) -> None:
    raise TradeCandidateError(message)


def _ids(values: tuple[int, ...], label: str, *, allow_empty: bool) -> tuple[int, ...]:
    if not isinstance(values, tuple):
        _fail(f"{label} must be a tuple")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value == 0:
            _fail(f"{label} must contain nonzero integer IDs")
    if len(values) != len(set(values)):
        _fail(f"{label} contains duplicate IDs")
    if not allow_empty and not values:
        _fail(f"{label} must be nonempty")
    return tuple(sorted(values))


def _validate_shape(shape: TradeShape) -> None:
    if not isinstance(shape, TradeShape):
        _fail("trade_shapes must contain TradeShape records")
    for label, value in (
        ("outgoing_count", shape.outgoing_count),
        ("incoming_count", shape.incoming_count),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            _fail(f"trade shape {label} must be a positive integer")


def _execution_caveats(snapshot: LeagueSnapshot) -> tuple[str, ...]:
    trade = snapshot.rules.trades
    caveats = {
        "counterparty_acceptance_not_modeled",
        "espn_transaction_execution_not_authorized",
        "structural_completion_is_m4_what_if_policy",
    }
    if trade.review_hours:
        caveats.add("trade_review_outcome_unverified")
    if trade.veto_votes_required:
        caveats.add("trade_veto_outcome_unverified")
    if trade.trade_limit is not None:
        caveats.add("remaining_trade_limit_unresolved")
    return tuple(sorted(caveats))


def _validate_search(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    configuration: SingleTradeSearchConfiguration,
) -> _ValidatedSearch:
    validate_snapshot(snapshot)
    validate_evolving_state(state, snapshot)
    if not isinstance(configuration, SingleTradeSearchConfiguration):
        _fail("configuration must be SingleTradeSearchConfiguration")
    if snapshot.snapshot_id is None:
        _fail("trade enumeration requires an identified canonical snapshot")
    team_ids = {item.team_id for item in snapshot.teams}
    requester = configuration.requesting_team_id
    if isinstance(requester, bool) or not isinstance(requester, int) or requester not in team_ids:
        _fail(f"requesting team {requester!r} is unknown")
    counterparties = _ids(
        configuration.counterparty_team_ids, "counterparty_team_ids", allow_empty=False
    )
    unknown_teams = set(counterparties) - team_ids
    if unknown_teams:
        _fail(f"counterparty_team_ids contain unknown teams {sorted(unknown_teams)}")
    if requester in counterparties:
        _fail("requesting team cannot also be a counterparty")

    universe = _ids(configuration.player_universe_ids, "player_universe_ids", allow_empty=False)
    known_players = {item.player_id for item in snapshot.players}
    unknown_players = set(universe) - known_players
    if unknown_players:
        _fail(f"player_universe_ids contain unknown players {sorted(unknown_players)}")
    owners = {item.player_id: item.team_id for item in state.roster_entries}
    invalid_universe = tuple(
        player_id
        for player_id in universe
        if owners.get(player_id) not in {requester, *counterparties}
    )
    if invalid_universe:
        _fail(
            "player_universe_ids must be owned by the requester or an allowed counterparty; "
            f"invalid players {list(invalid_universe)}"
        )

    if not isinstance(configuration.trade_shapes, tuple) or not configuration.trade_shapes:
        _fail("trade_shapes must be a nonempty tuple")
    for shape in configuration.trade_shapes:
        _validate_shape(shape)
    if len(configuration.trade_shapes) != len(set(configuration.trade_shapes)):
        _fail("trade_shapes contains duplicates")
    shapes = tuple(sorted(configuration.trade_shapes))

    requester_owned = {player_id for player_id in universe if owners[player_id] == requester}
    if configuration.allowed_outgoing_player_ids is None:
        outgoing = tuple(sorted(requester_owned))
    else:
        outgoing = _ids(
            configuration.allowed_outgoing_player_ids,
            "allowed_outgoing_player_ids",
            allow_empty=True,
        )
        if not set(outgoing).issubset(universe):
            _fail("allowed_outgoing_player_ids must be inside player_universe_ids")
        wrong = set(outgoing) - requester_owned
        if wrong:
            _fail(f"outgoing players are not owned by requesting team {requester}: {sorted(wrong)}")

    if configuration.allowed_incoming_player_ids is None:
        incoming_filter = {
            player_id for player_id in universe if owners[player_id] in set(counterparties)
        }
    else:
        incoming = _ids(
            configuration.allowed_incoming_player_ids,
            "allowed_incoming_player_ids",
            allow_empty=True,
        )
        if not set(incoming).issubset(universe):
            _fail("allowed_incoming_player_ids must be inside player_universe_ids")
        wrong = tuple(
            player_id for player_id in incoming if owners[player_id] not in counterparties
        )
        if wrong:
            _fail(f"incoming players are not owned by an allowed counterparty: {list(wrong)}")
        incoming_filter = set(incoming)

    if not isinstance(configuration.protected_pins, tuple):
        _fail("protected_pins must be a tuple")
    pin_pairs = []
    for pin in configuration.protected_pins:
        if not isinstance(pin, ProtectedPlayerPin):
            _fail("protected_pins must contain ProtectedPlayerPin records")
        if pin.team_id not in team_ids or pin.player_id not in known_players:
            _fail(f"protected pin team={pin.team_id}, player={pin.player_id} is unknown")
        if owners.get(pin.player_id) != pin.team_id:
            _fail(
                f"protected pin player={pin.player_id} is not currently owned by team={pin.team_id}"
            )
        pin_pairs.append(pin)
    pins = tuple(sorted(pin_pairs, key=lambda item: (item.team_id, item.player_id)))
    if len(pins) != len(set(pins)):
        _fail("protected_pins contains duplicates")

    trade = snapshot.rules.trades
    if not trade.enabled:
        _fail("canonical league rules disable trades")
    if trade.deadline_utc is not None and snapshot.retrieval_finished_at_utc > trade.deadline_utc:
        _fail("canonical snapshot was retrieved after the configured trade deadline")
    if trade.trade_limit == 0:
        _fail("canonical league trade limit prohibits trades")

    incoming_by_counterparty = tuple(
        (
            team_id,
            tuple(
                sorted(
                    player_id
                    for player_id in incoming_filter
                    if owners[player_id] == team_id
                )
            ),
        )
        for team_id in counterparties
    )
    normalized = {
        "contract": "m5.1-single-trade-search-v1",
        "snapshot_id": snapshot.snapshot_id,
        "source_schema_version": snapshot.schema_version,
        "requesting_team_id": requester,
        "counterparty_team_ids": counterparties,
        "player_universe_ids": universe,
        "trade_shapes": [asdict(item) for item in shapes],
        "allowed_outgoing_player_ids": (
            None
            if configuration.allowed_outgoing_player_ids is None
            else tuple(sorted(configuration.allowed_outgoing_player_ids))
        ),
        "allowed_incoming_player_ids": (
            None
            if configuration.allowed_incoming_player_ids is None
            else tuple(sorted(configuration.allowed_incoming_player_ids))
        ),
        "protected_pins": [asdict(item) for item in pins],
    }
    configuration_sha256 = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    baseline_state_sha256 = hashlib.sha256(
        state_to_json(state, snapshot).encode("utf-8")
    ).hexdigest()
    return _ValidatedSearch(
        configuration_sha256,
        baseline_state_sha256,
        requester,
        counterparties,
        universe,
        shapes,
        outgoing,
        incoming_by_counterparty,
        pins,
        _execution_caveats(snapshot),
    )


def _candidate_identity(
    snapshot: LeagueSnapshot,
    search: _ValidatedSearch,
    counterparty_team_id: int,
    shape: TradeShape,
    outgoing: tuple[int, ...],
    incoming: tuple[int, ...],
) -> str:
    payload = {
        "contract": "m5.1-single-trade-candidate-v1",
        "snapshot_id": snapshot.snapshot_id,
        "source_schema_version": snapshot.schema_version,
        "baseline_state_sha256": search.baseline_state_sha256,
        "requesting_team_id": search.requester,
        "counterparty_team_id": counterparty_team_id,
        "shape": asdict(shape),
        "outgoing_player_ids": outgoing,
        "incoming_player_ids": incoming,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _combinations_count(search: _ValidatedSearch) -> int:
    incoming = dict(search.incoming_by_counterparty)
    return sum(
        math.comb(len(search.outgoing), shape.outgoing_count)
        * math.comb(len(incoming[team_id]), shape.incoming_count)
        for team_id in search.counterparties
        for shape in search.shapes
        if shape.outgoing_count <= len(search.outgoing)
        and shape.incoming_count <= len(incoming[team_id])
    )


def _candidate_attempts(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    search: _ValidatedSearch,
) -> Iterator[SingleTradeCandidate | _RejectedCandidate]:
    incoming_by_counterparty = dict(search.incoming_by_counterparty)
    requester = search.requester
    for counterparty in search.counterparties:
        for shape in search.shapes:
            for outgoing in itertools.combinations(search.outgoing, shape.outgoing_count):
                for incoming in itertools.combinations(
                    incoming_by_counterparty[counterparty], shape.incoming_count
                ):
                    candidate_id = _candidate_identity(
                        snapshot, search, counterparty, shape, outgoing, incoming
                    )
                    changes = tuple(
                        sorted(
                            (
                                *(
                                    ExplicitRosterChange(player_id, requester, counterparty)
                                    for player_id in outgoing
                                ),
                                *(
                                    ExplicitRosterChange(player_id, counterparty, requester)
                                    for player_id in incoming
                                ),
                            ),
                            key=lambda item: item.player_id,
                        )
                    )
                    try:
                        completed = complete_manual_scenario(
                            snapshot,
                            state,
                            ManualScenario(
                                f"m5.1-{candidate_id[:20]}", changes, search.pins
                            ),
                        )
                    except ScenarioEvaluationError as exc:
                        yield _RejectedCandidate(str(exc))
                        continue
                    yield SingleTradeCandidate(
                        candidate_id,
                        snapshot.snapshot_id or "",
                        snapshot.schema_version,
                        search.baseline_state_sha256,
                        search.configuration_sha256,
                        requester,
                        counterparty,
                        shape,
                        outgoing,
                        incoming,
                        changes,
                        True,
                        TradeExecutionStatus.STRUCTURAL_HYPOTHETICAL_ONLY,
                        search.caveats,
                        completed,
                    )


def enumerate_single_trade_candidates(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    configuration: SingleTradeSearchConfiguration,
) -> TradeCandidateEnumeration:
    """Exhaust the declared finite universe and retain every M4-feasible trade."""

    search = _validate_search(snapshot, state, configuration)
    candidates = []
    reasons: Counter[str] = Counter()
    for result in _candidate_attempts(snapshot, state, search):
        if isinstance(result, _RejectedCandidate):
            reasons[result.reason] += 1
        else:
            candidates.append(result)
    candidates.sort(
        key=lambda item: (
            item.counterparty_team_id,
            item.shape,
            item.outgoing_player_ids,
            item.incoming_player_ids,
        )
    )
    combination_count = _combinations_count(search)
    infeasible_count = sum(reasons.values())
    if combination_count != len(candidates) + infeasible_count:
        _fail("internal exhaustive coverage reconciliation failed")
    coverage = TradeCandidateCoverage(
        len(search.universe),
        len(search.counterparties),
        len(search.shapes),
        combination_count,
        len(candidates),
        infeasible_count,
        tuple(sorted(reasons.items())),
        True,
    )
    return TradeCandidateEnumeration(
        search.configuration_sha256,
        search.baseline_state_sha256,
        tuple(candidates),
        coverage,
    )


def iter_single_trade_candidates(
    snapshot: LeagueSnapshot,
    state: EvolvingLeagueState,
    configuration: SingleTradeSearchConfiguration,
) -> Iterator[SingleTradeCandidate]:
    """Yield every feasible candidate in stable ID order without retaining the result set.

    Use :func:`enumerate_single_trade_candidates` when rejected-combination
    reconciliation and the complete coverage summary are required.
    """

    search = _validate_search(snapshot, state, configuration)
    for item in _candidate_attempts(snapshot, state, search):
        if isinstance(item, SingleTradeCandidate):
            yield item
