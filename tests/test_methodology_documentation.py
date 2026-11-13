"""Methodology examples and source-owner boundaries, not calibration evidence."""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from fantasy_football.canonical.model import (
    FantasyMatchup,
    MatchupEntryStatus,
    ProjectionClass,
)
from fantasy_football.evolving_state import (
    IRPolicy,
    advance_cycle,
    initialize_evolving_state,
)
from fantasy_football.lineup_optimizer import optimize_starting_lineup
from fantasy_football.live_scoring import NFLGameStatus
from fantasy_football.monte_carlo import (
    MonteCarloError,
    MonteCarloPartialWeekInput,
    run_monte_carlo_path,
    simulation_configuration_fingerprint,
)
from fantasy_football.partial_week import (
    DeterministicPlayerValue,
    EvidenceAuthority,
    LineupRole,
    LockState,
    PartialWeekError,
    PlayerScoreState,
    RemainingContributionStatus,
    compose_partial_week_scores,
    require_executable_partial_week_evidence,
    validate_partial_week_evidence,
    validate_proposed_lineup,
)
from fantasy_football.partial_week_serialization import partial_week_to_json
from fantasy_football.player_outcomes import ProvisionalNormalModel
from fantasy_football.postseason import (
    generate_championship_graph,
    initialize_postseason,
)
from fantasy_football.roster_value import ReplacementAccessContext, value_roster
from fantasy_football.season_simulator import (
    DeterministicScoreScenario,
    SeasonSimulationError,
)
from fantasy_football.transaction_cycle import validate_operational_policy_equivalence
from fantasy_football.weekly_engine import RealizedPlayerScore, initialize_standings
from fantasy_football.weekly_transactions import execute_weekly_essential_transactions
from tests.test_lineup_optimizer import _lineup_snapshot, _present, _reference
from tests.test_m33_player_outcomes import _model
from tests.test_partial_monte_carlo import _case as _mc_partial_case
from tests.test_partial_season import _execute, _multiweek, _partial, _timed
from tests.test_roster_value import (
    _assert_production_matches_oracle,
    _state,
    _valuation_snapshot,
)
from tests.test_season_simulator import (
    _fourteen_team_postseason_snapshot,
    _run,
    _snapshot,
)
from tests.test_weekly_transactions import _policy

ROOT = Path(__file__).resolve().parents[1]


def _guide() -> str:
    return (ROOT / "docs/METHODOLOGY.md").read_text(encoding="utf-8")


def test_normal_example_rows_match_actual_signed_and_degenerate_transform(
    monkeypatch,
) -> None:
    """Read the published arithmetic; force only its explicitly conditional Z."""
    text = _guide()
    table = text.split("| mu | base_stddev | projection_scale | Z | sigma | X |\n")[1]
    rows = []
    for line in table.splitlines()[1:]:
        if not line.startswith("|"):
            break
        rows.append(tuple(float(value.strip()) for value in line.strip("|").split("|")))
    assert len(rows) == 3
    for mu, base, scale, z, sigma, outcome in rows:
        model = ProvisionalNormalModel(base, scale)
        assert base + scale * abs(mu) == sigma
        monkeypatch.setattr(
            ProvisionalNormalModel, "_standard_normal", lambda *a, z=z, **k: z
        )
        snapshot = _snapshot()
        target = snapshot.player_weeks[0]
        # Reuse the canonical fixture's class, changing all nonzero values to
        # PRESENT; zero must exercise EXPLICIT_ZERO rather than missing policy.
        changed = replace(
            target,
            raw_projection=mu,
            effective_projection=mu,
            projection_class=(
                ProjectionClass.EXPLICIT_ZERO if mu == 0 else ProjectionClass.PRESENT
            ),
        )
        snapshot = replace(
            snapshot, player_weeks=(changed,) + snapshot.player_weeks[1:]
        )
        actual = model.generate_scenario(snapshot, master_seed=1, path_index=0)
        assert actual.scores[0].points == outcome


def test_empirical_example_preserves_zero_atoms_pooling_and_multiplicity() -> None:
    text = _guide()
    # These are the guide's worked target distributions, not sampled frequencies.
    # Existing fit fixtures construct exactly its four training pairs/bins/minimum.
    local = re.search(r"sorted atoms .*?\[([\d,]+)\]", text)
    pooled = re.search(r"pooled sorted atoms .*?\[([\d,]+)\]", text)
    assert local is not None and pooled is not None
    expected_local = tuple(float(value) for value in local[1].split(","))
    expected_pool = tuple(float(value) for value in pooled[1].split(","))
    model = _model()
    assert model.projection_bin_edges == (5.0, 15.0)
    assert model.minimum_group_size == 2
    group = dict(model.grouped_residual_atoms)[model._projection_bin(3.0)]
    assert len(group) >= model.minimum_group_size
    assert tuple(model._score(3.0, group, u) for u in (0.0, 0.5)) == expected_local
    sparse = dict(model.grouped_residual_atoms)[model._projection_bin(20.0)]
    assert len(sparse) < model.minimum_group_size
    assert (
        tuple(
            model._score(20.0, model.pooled_residual_atoms, u)
            for u in (0.0, 0.25, 0.5, 0.75)
        )
        == expected_pool
    )


def _validate_methodology(text: str) -> None:
    """Guard consequential definitions/gates without fixing editorial layout."""
    for definition in (
        r"\sigma = \text{base_stddev} + \text{projection_scale}\times|\mu|",
        r"X=\mu+\sigma Z",
        r"e_\ell=A_\ell-r_\ell",
        r"q_\ell=\mathbf1\{A_\ell=0\}",
        r"\mu+e_\ell",
        r"k=\min(\lfloor un\rfloor,n-1)",
        r"\widehat p_t(a)=\frac{1}{N}\sum_{i=1}^{N} C_{it}(a)",
    ):
        assert definition in text, f"Missing mathematical definition: {definition}"
    for contract in (
        "**effective_projection > 0**",
        "**every canonical in-horizon player-week**",
        "Earlier Normal checkpoints are incompatible",
        "unconditional probability estimates are suppressed",
        "zero authenticated pregame pairs",
        "Component-specific promotion",
    ):
        assert contract in text, f"Missing interpretation gate: {contract}"
    classes = {
        line.split("|")[1].strip(): [cell.strip() for cell in line.split("|")[2:-1]]
        for line in text.splitlines()
        if line.startswith(("| `MISSING` |", "| `EXPLICIT_ZERO` |"))
    }
    assert "Raw null" in classes["`MISSING`"][0]
    assert "Exactly `0.0`" in classes["`MISSING`"][1]
    assert "nonmissing draw path" in classes["`EXPLICIT_ZERO`"][1]
    assert "Exactly `0.0`" in classes["`EXPLICIT_ZERO`"][2]
    for owner in (
        "PLAYER_OUTCOME_MODEL.md#normal-distribution-and-draw-bytes",
        "PLAYER_OUTCOME_MODEL.md#identity-and-compatibility",
        "DATA.md#projection-contract",
        "RESEARCH.md#component-specific-promotion",
        "SEASON_SIMULATOR.md#weekly-progression",
        "MONTE_CARLO.md#aggregation-and-probability-estimators",
    ):
        assert f"]({owner})" in text, f"Missing current owner: {owner}"


def test_methodology_preserves_mathematical_and_evidence_contracts() -> None:
    _validate_methodology(_guide())


@pytest.mark.parametrize(
    "lost",
    (
        r"\mu+e_\ell",
        r"q_\ell=\mathbf1\{A_\ell=0\}",
        "nonmissing draw path",
        "unconditional probability estimates are suppressed",
        "RESEARCH.md#component-specific-promotion",
        "Earlier Normal checkpoints are incompatible",
    ),
)
def test_methodology_rejects_lost_transform_class_or_gate(lost: str) -> None:
    text = _guide()
    assert lost in text
    with pytest.raises(AssertionError):
        _validate_methodology(text.replace(lost, "REMOVED"))


def test_documented_flex_assignment_matches_exhaustive_reference() -> None:
    documented = re.search(
        r"Global assignment gives A→(\d+) and FLEX→(\d+), totaling \*\*(\d+)\*\*",
        _guide(),
    )
    assert documented is not None
    snapshot = _lineup_snapshot(
        starters=((2, 1), (3, 1)),
        player_specs=(
            _present(1, (2, 3), 10.0),
            _present(2, (2,), 9.0),
            _present(3, (3,), 1.0),
        ),
    )
    slots, expected = _reference(snapshot, 15)
    result = optimize_starting_lineup(snapshot, 1, 15)
    assignment = {item.slot: item.player_id for item in result.assignments}
    assert tuple(assignment[slot] for slot in slots) == expected
    assert expected == tuple(int(documented[index]) for index in (1, 2))
    assert result.total_projected_points == float(documented[3])


def test_documented_season_scores_standings_and_placements_match_fixture() -> None:
    text = _guide()
    table = text.split("| Week | Frozen team totals (teams 1,2,3,4) |")[1]
    rows = [
        line.split("|")[1:3]
        for line in table.splitlines()
        if re.match(r"\| 1[567] \|", line)
    ]
    snapshot = _snapshot()
    before = repr(snapshot)
    result = _run(snapshot)
    assert len(rows) == len(result.weeks) == 3
    for (week, totals), transition in zip(rows, result.weeks, strict=True):
        assert int(week) == transition.scoring_week
        assert tuple(float(value) for value in totals.split(",")) == tuple(
            item.realized_points for item in transition.frozen_team_weeks
        )
    regular_records = re.search(r"Final regular W/L/T: ([^|]+)", text)
    assert regular_records is not None
    expected = tuple(
        tuple(map(int, item))
        for item in re.findall(r"(\d+)/(\d+)/(\d+)", regular_records[1])
    )
    assert (
        tuple(
            (row.wins, row.losses, row.ties) for row in result.final_regular_standings
        )
        == expected
    )
    order = re.search(r"Final placement order is \*\*([\d,]+)\*\*", text)
    assert order is not None
    assert result.final_postseason_state is not None
    assert tuple(
        item.team_id for item in result.final_postseason_state.placements
    ) == tuple(map(int, order[1].split(",")))
    initial = {team.team_id: team for team in snapshot.teams}
    for row in result.final_regular_standings:
        scores = [
            next(
                item.realized_points
                for item in week.frozen_team_weeks
                if item.team_id == row.team_id
            )
            for week in result.weeks[:2]
        ]
        assert row.points_for == initial[row.team_id].points_for + sum(scores)
    assert repr(snapshot) == before


def test_documented_postseason_byes_and_incomplete_placement_boundary() -> None:
    six = generate_championship_graph(tuple(range(1, 7)), 3)
    bye_seeds = tuple(
        node.sources[0].seed
        for node in six.nodes
        if node.round_number == 1 and len(node.sources) == 1
    )
    assert bye_seeds == (1, 2)
    assert not six.unresolved_capabilities
    eight = generate_championship_graph(tuple(range(1, 9)), 3)
    assert eight.unresolved_capabilities == ("championship_complete_placement_mapping",)
    assert "seeds 1 and 2 byes" in _guide()
    assert (
        "eight qualifiers, retain `championship_complete_placement_mapping`" in _guide()
    )


def test_documented_essential_acquisition_matches_sequential_reference() -> None:
    snapshot = _valuation_snapshot()
    state = _state(snapshot)
    assert state.current_waiver_priority == (1, 2, 3, 4)
    result = execute_weekly_essential_transactions(snapshot, state, _policy())
    comparison = validate_operational_policy_equivalence(snapshot, state, _policy())
    assert comparison.equivalent
    assert len(result.acquisitions) == 1
    acquired = result.acquisitions[0]
    assert (acquired.team_id, acquired.acquired_player_id) == (1, -300)
    assert (acquired.vacancy_count_before, acquired.vacancy_count_after) == (1, 0)
    assert acquired.dropped_player_ids == ()
    assert dict(result.state.season_acquisition_counts)[1] == 1
    assert dict(result.state.matchup_acquisition_counts)[1] == 1
    assert result.final_waiver_priority == state.current_waiver_priority
    assert state.ledger == ()
    assert "only team 1 needs an acquisition" in _guide()


def test_documented_shared_pool_values_match_independent_allocation_leaves() -> None:
    text = _guide()
    example = text.split("**Synthetic competing-pool example:**")[1].split("\n\n")[0]
    expected = tuple(map(float, re.findall(r"\*\*V=(\d+)\*\*", example)))
    assert expected == (57.0, 51.0, 33.0)
    for competing, total in enumerate(expected):
        snapshot = _valuation_snapshot(competing_teams=competing)
        state = _state(snapshot)
        result = value_roster(snapshot, state, 1)
        _, oracle, _, _ = _assert_production_matches_oracle(
            snapshot,
            state,
            target_team_id=1,
            context=ReplacementAccessContext.FUTURE_CONSERVATIVE,
        )
        assert result.total_value == total
        assert (
            result.weeks[0].projected_lineup_points == oracle.target_attainable_points
        )
        assert state.ledger == ()


def test_wr023_documented_counterexample_retains_distinct_arithmetic_truth() -> None:
    snapshot = _lineup_snapshot(
        starters=((1, 1), (2, 1)),
        player_specs=(
            _present(1, (1,), 1e30),
            _present(2, (2,), 1.0),
            _present(3, (2,), 2.0),
        ),
    )
    with localcontext() as context:
        context.prec = 28
        observed = optimize_starting_lineup(snapshot, 1, 15)
    # This intentionally checks the documented current defect, not its approval.
    # Fraction is independent of ambient Decimal additions and display rounding.
    assert tuple(item.player_id for item in observed.assignments) == (1, 2)
    assert Fraction.from_float(1e30) + 2 > Fraction.from_float(1e30) + 1
    assert "selects **(1,2)**" in _guide()
    assert "favors **(1,3)**" in _guide()


def _validate_mechanics(text: str) -> None:
    for requirement in (
        r"x_{jk}\le e_{jk}",
        r"L_{tw}=\max_x",
        r"d_{tw}(E^c)<d_{tw}(E)",
        r"V_t(R_t,E_{w_0})=\operatorname{fsum}_{w=w_0}^{W}",
        "freeze assignments before reading realized scores",
        "maximize vacancies filled; maximize opposing projected improvement; minimize the target's best residual attainable lineup; then stable vacancy/player identity",
        "marginal opportunities, not persistent acquisitions",
        "reverse frozen opening priority",
        "WR-023 remains unresolved",
        "WR-024 remains unresolved",
        "selects **(1,2)**",
        "favors **(1,3)**",
        "Production excludes materially incomplete-valued plans",
        "`determination_complete=False`",
        "not a certified maximum over unresolved alternatives",
        "no aggregate multiweek regular-period reconciliation or equivalent universal preflight rejection",
        "unchanged correctness defects",
        "TRANSACTIONS.md#independent-reference-contracts",
        "BACKLOG.md#mechanics-review-obligations",
    ):
        assert requirement in text, f"Missing mechanics contract: {requirement}"


def test_mechanics_preserves_consequential_contracts_and_open_defects() -> None:
    _validate_mechanics(_guide())


@pytest.mark.parametrize(
    "lost",
    (
        r"d_{tw}(E^c)<d_{tw}(E)",
        "reverse frozen opening priority",
        "marginal opportunities, not persistent acquisitions",
        "favors **(1,3)**",
        "Production excludes materially incomplete-valued plans",
        "not a certified maximum over unresolved alternatives",
        "no aggregate multiweek regular-period reconciliation or equivalent universal preflight rejection",
    ),
)
def test_mechanics_rejects_lost_constraint_or_known_gap(lost: str) -> None:
    text = _guide()
    assert lost in text
    with pytest.raises(AssertionError, match="Missing mechanics contract"):
        _validate_mechanics(text.replace(lost, "REMOVED"))


def _signed_partial_example():
    """P4 table on the existing first-round, pre-horizon carry fixture."""
    snapshot, future, partial = _multiweek()
    evidence = replace(
        partial.evidence,
        players=tuple(
            replace(
                item,
                nfl_game_status=NFLGameStatus.COMPLETED,
                score_state=PlayerScoreState.COMPLETED_FIXED,
                fixed_actual_points=-2.0,
                full_game_projection=None,
                remaining_status=RemainingContributionStatus.NOT_APPLICABLE,
            )
            if item.player_id == -101
            else replace(
                item,
                nfl_game_status=NFLGameStatus.IN_PROGRESS,
                score_state=PlayerScoreState.IN_PROGRESS,
                fixed_actual_points=3.0,
            )
            if item.player_id == 1
            else item
            for item in partial.evidence.players
        ),
        lineups=tuple(
            replace(item, lock_state=LockState.VERIFIED_LOCKED)
            if item.player_id in {-101, 1}
            else item
            for item in partial.evidence.lineups
        ),
        matchups=tuple(
            replace(
                item,
                home_observed_week_points=1.0 if item.home_team_id == 1 else 0.0,
                away_observed_week_points=1.0 if item.away_team_id == 1 else 0.0,
            )
            for item in partial.evidence.matchups
        ),
    )
    partial = replace(
        partial,
        evidence=evidence,
        values=tuple(item for item in partial.values if item.player_id not in {-101, 1})
        + (DeterministicPlayerValue(1, approved_remaining_points=4.0),),
    )
    return snapshot, future, partial


def test_partial_table_matches_composer_and_once_only_postseason_execution() -> None:
    table = _guide().split("| Component | Points |\n")[1].split("\n\n")[0]
    values = {
        line.split("|")[1].strip(): float(line.split("|")[2])
        for line in table.splitlines()[1:]
    }
    snapshot, future, partial = _signed_partial_example()
    assert snapshot.first_simulation_week == 16
    assert partial.evidence.matchup_period_scoring_weeks == (15, 16, 17)
    assert partial.evidence.standings_cutoff.through_scoring_week == 14
    composed = compose_partial_week_scores(
        snapshot, partial.evidence, partial.lineup, partial.values
    )
    team = next(item for item in composed.teams if item.team_id == 1)
    completed, progress = sorted(team.starters, key=lambda item: item.player_id)
    assert completed.fixed_points == values["Completed fixed actual"]
    assert progress.fixed_points == values["In-progress actual-so-far"]
    assert team.fixed_points == values["Fixed current-week sum"]
    assert team.remaining_points == values["Approved deterministic remainder"]
    assert (
        team.fixed_points + team.remaining_points
        == values["Composed current-week total"]
    )
    assert team.carry_in_points == values["Verified week-15 carry"]
    assert (
        team.final_matchup_points
        == values["Composed period slice through modeled week 16"]
    )
    before = (repr(snapshot), partial_week_to_json(partial.evidence))
    result = _execute(snapshot, future, partial)
    assert not result.weeks[0].postseason_state.placements
    first = next(
        item for item in result.weeks[0].frozen_team_weeks if item.team_id == 1
    )
    assert first.realized_points == values["Composed current-week total"]
    final = result.final_postseason_state.championship_matchups[0]
    assert final.home_total == values["Final period total after all three weeks"]
    assert final.away_total == 45.0
    assert len(final.weekly_scores) == 6  # every paired team/week, carry replayed once
    assert (repr(snapshot), partial_week_to_json(partial.evidence)) == before


@pytest.mark.parametrize(
    ("fault", "message"),
    (
        ("observed", "differs from canonical roster slot"),
        ("locked", "locked or unresolved assignment cannot move"),
        ("unchanged_unresolved", "unresolved lock status"),
        ("missing_actual", "completed state requires completed game and fixed actual"),
        ("remainder", "no approved remainder"),
        ("cutoff", "immediately before the current matchup period"),
        ("membership", "membership differs from canonical schedule evidence"),
        ("duplicate_carry", "duplicate prior postseason team/week contribution"),
        ("missing_carry", "cover exactly every preceding current-period team/week"),
        ("first_week_score", "supplied only through partial realizations"),
    ),
)
def test_partial_example_falsification_cases(fault: str, message: str) -> None:
    snapshot, future, partial = _signed_partial_example()
    evidence = partial.evidence
    if fault == "observed":
        evidence = replace(
            evidence,
            lineups=tuple(
                replace(item, lineup_slot_id=20, role=LineupRole.BENCH)
                if item.player_id == 1
                else item
                for item in evidence.lineups
            ),
        )
    elif fault == "locked":
        partial = replace(
            partial,
            lineup=tuple(
                replace(item, lineup_slot_id=20) if item.player_id == 1 else item
                for item in partial.lineup
            ),
        )
    elif fault == "unchanged_unresolved":
        evidence = replace(
            evidence,
            lineups=tuple(
                replace(
                    item,
                    lock_state=LockState.UNRESOLVED,
                    lock_authority=EvidenceAuthority.UNVERIFIED,
                )
                if item.player_id == 1
                else item
                for item in evidence.lineups
            ),
        )
        validate_partial_week_evidence(snapshot, evidence)
        validate_proposed_lineup(snapshot, evidence, partial.lineup)
    elif fault in {"missing_actual", "remainder"}:
        evidence = replace(
            evidence,
            players=tuple(
                replace(item, fixed_actual_points=None)
                if fault == "missing_actual" and item.player_id == -101
                else replace(
                    item, remaining_status=RemainingContributionStatus.UNRESOLVED
                )
                if fault == "remainder" and item.player_id == 1
                else item
                for item in evidence.players
            ),
        )
    elif fault == "cutoff":
        evidence = replace(
            evidence,
            standings_cutoff=replace(
                evidence.standings_cutoff, through_scoring_week=15
            ),
        )
    elif fault == "membership":
        evidence = replace(evidence, matchup_period_scoring_weeks=(16, 17))
    elif fault == "duplicate_carry":
        partial = replace(
            partial,
            prior_postseason_scores=partial.prior_postseason_scores
            + partial.prior_postseason_scores[:1],
        )
    elif fault == "missing_carry":
        partial = replace(partial, prior_postseason_scores=())
    else:
        future = replace(
            future,
            scores=future.scores + (RealizedPlayerScore(1, snapshot.season, 16, 5.0),),
        )
    with pytest.raises((PartialWeekError, SeasonSimulationError), match=message):
        _execute(snapshot, future, replace(partial, evidence=evidence))


def test_partial_companion_basis_is_not_full_content_or_configuration_identity() -> (
    None
):
    snapshot, config, model = _mc_partial_case()
    evidence = config.partial_week.evidence
    changed = replace(
        evidence,
        lineups=tuple(
            replace(item, lock_state=LockState.VERIFIED_LOCKED)
            if item.player_id == 1
            else item
            for item in evidence.lineups
        ),
    )
    require_executable_partial_week_evidence(snapshot, changed)
    assert changed.evidence_digest_sha256 == evidence.evidence_digest_sha256
    assert partial_week_to_json(changed) != partial_week_to_json(evidence)
    other = replace(config, partial_week=replace(config.partial_week, evidence=changed))
    assert simulation_configuration_fingerprint(
        snapshot, config, model
    ) != simulation_configuration_fingerprint(snapshot, other, model)
    ordinary, baseline = run_monte_carlo_path(
        snapshot, replace(config, partial_week=None), model, 0, retain_result=True
    )
    actual, partial = run_monte_carlo_path(
        snapshot, config, model, 0, retain_result=True
    )
    assert actual == ordinary  # includes complete original scenario digest
    assert partial.weeks[0].frozen_team_weeks == baseline.weeks[0].frozen_team_weeks
    assert partial.weeks[1:] == baseline.weeks[1:]
    assert partial.final_postseason_state == baseline.final_postseason_state


class _NoPartialSampling:
    def generate_scenario(self, *args, **kwargs):
        pytest.fail("unsupported evidence must reject before sampling")


@pytest.mark.parametrize(
    ("slot", "role"), ((20, LineupRole.BENCH), (21, LineupRole.RESERVE))
)
def test_partial_mc_does_not_exempt_nonstarting_rostered_players(slot, role) -> None:
    snapshot, config, _ = _mc_partial_case()
    snapshot = replace(
        snapshot,
        roster_entries=tuple(
            replace(item, lineup_slot_id=slot) if item.player_id == 1 else item
            for item in snapshot.roster_entries
        ),
    )
    partial = config.partial_week
    evidence = replace(
        partial.evidence,
        lineups=tuple(
            replace(item, lineup_slot_id=slot, role=role)
            if item.player_id == 1
            else item
            for item in partial.evidence.lineups
        ),
        players=tuple(
            replace(
                item,
                nfl_game_status=NFLGameStatus.UNKNOWN,
                score_state=PlayerScoreState.NONPARTICIPATING,
                remaining_status=RemainingContributionStatus.NOT_APPLICABLE,
            )
            if item.player_id == 1
            else item
            for item in partial.evidence.players
        ),
    )
    lineup = tuple(
        replace(item, lineup_slot_id=slot) if item.player_id == 1 else item
        for item in partial.lineup
    )
    validate_partial_week_evidence(snapshot, evidence)
    validate_proposed_lineup(snapshot, evidence, lineup)
    with pytest.raises(MonteCarloError, match="LW2.3A requires unstarted.*player 1"):
        run_monte_carlo_path(
            snapshot,
            replace(
                config, partial_week=replace(partial, evidence=evidence, lineup=lineup)
            ),
            _NoPartialSampling(),
            0,
        )


def test_partial_mc_fantasy_bye_does_not_waive_player_gate() -> None:
    snapshot = _timed(_fourteen_team_postseason_snapshot())
    bracket = initialize_postseason(snapshot, initialize_standings(snapshot))
    games = bracket.championship_matchups + bracket.consolation_matchups
    snapshot = replace(
        snapshot,
        fantasy_matchups=tuple(
            FantasyMatchup(
                index,
                item.matchup_period_id,
                item.home_team_id,
                item.away_team_id,
                item.bracket_type.value,
                MatchupEntryStatus.BYE
                if item.away_team_id is None
                else MatchupEntryStatus.SCHEDULED,
            )
            for index, item in enumerate(games, 1)
        ),
    )
    full = DeterministicScoreScenario(
        "p4-synthetic-bye",
        tuple(
            RealizedPlayerScore(
                item.player_id, snapshot.season, snapshot.first_simulation_week, 10.0
            )
            for item in snapshot.players
        ),
    )
    deterministic, _ = _partial(snapshot, full)
    bye_teams = {item.home_team_id for item in games if item.away_team_id is None}
    target = next(
        item.player_id for item in snapshot.roster_entries if item.team_id in bye_teams
    )
    evidence = replace(
        deterministic.evidence,
        players=tuple(
            replace(
                item,
                nfl_game_status=NFLGameStatus.UNKNOWN,
                score_state=PlayerScoreState.NONPARTICIPATING,
                remaining_status=RemainingContributionStatus.NOT_APPLICABLE,
            )
            if item.player_id == target
            else item
            for item in deterministic.evidence.players
        ),
    )
    validate_partial_week_evidence(snapshot, evidence)
    _, config, _ = _mc_partial_case()
    with pytest.raises(
        MonteCarloError, match=f"LW2.3A requires unstarted.*player {target}"
    ):
        run_monte_carlo_path(
            snapshot,
            replace(
                config,
                partial_week=MonteCarloPartialWeekInput(evidence, deterministic.lineup),
            ),
            _NoPartialSampling(),
            0,
        )


def test_partial_confirmed_zero_stays_fixed_and_initial_ledger_is_rejected() -> None:
    snapshot, future, partial = _signed_partial_example()
    zero = replace(
        partial.evidence,
        players=tuple(
            replace(item, fixed_actual_points=0.0) if item.player_id == -101 else item
            for item in partial.evidence.players
        ),
        matchups=tuple(
            replace(item, home_observed_week_points=3.0)
            if item.home_team_id == 1
            else item
            for item in partial.evidence.matchups
        ),
    )
    result = compose_partial_week_scores(snapshot, zero, partial.lineup, partial.values)
    team = next(item for item in result.teams if item.team_id == 1)
    assert team.fixed_points == 3.0
    assert (
        next(item for item in team.starters if item.player_id == -101).fixed_points
        == 0.0
    )
    initial = initialize_evolving_state(
        snapshot, scoring_week=16, ir_policy=IRPolicy.PROJECTION_BASED
    )
    # A valid nonempty ledger is still a forbidden retroactive initial history.
    changed = advance_cycle(
        initial, snapshot, cycle_id=initial.cycle_id + 1, scoring_week=16
    )
    with pytest.raises(
        SeasonSimulationError, match="hypothetical initial transactions or rosters"
    ):
        _execute(snapshot, future, partial, initial_evolving_state=changed)


def _validate_partial_methodology(text: str) -> None:
    chapter = text.split("## Current-week and partial-week treatment\n")[1].split(
        "## Roster evolution and transaction rules\n"
    )[0]
    state_table = chapter.split(
        "| Score state | Preservable evidence | Deterministic starter contribution |\n"
    )[1].split("\n\n")[0]
    states = re.findall(r"^\| `([^`]+)` \|", state_table, re.MULTILINE)
    assert len(states) == len(PlayerScoreState) and set(states) == {
        item.value for item in PlayerScoreState
    }, "Unexpected player-score state table"
    for contract in (
        "exact canonical player/team/slot assignments",
        "even when the proposed slot is unchanged",
        "not a sixth score-state enum",
        "projection minus actual-so-far is not an authorized remainder",
        r"Q_{tw}=F^{\mathrm{fixed}}_{tw}+R^{\mathrm{rem}}_{tw}",
        "first actual period week minus one",
        "subsequent weeks only",
        "not aggregate carry again",
        "Every rostered current player, including bench and reserve",
        "does **not waive the rostered-player gate**",
        "complete canonical player-week universe exactly once per path",
        "original complete scenario ID and score-content digest",
        "not all companion content",
        "prescribed path range",
        "No public partial request fields",
        "S128–S136 and S165",
        "PARTIAL_WEEK.md#standings-and-period-authority",
        "PARTIAL_WEEK.md#monte-carlo-subset",
    ):
        assert contract in chapter, f"Missing partial-week contract: {contract}"
    assert not re.search(r"\]\([^)]*(?:VALIDATION|TECHNICAL_REFERENCE)\.md", chapter)


def test_partial_methodology_preserves_execution_and_source_boundaries() -> None:
    _validate_partial_methodology(_guide())


def test_partial_methodology_rejects_an_invented_unresolved_score_state() -> None:
    text = _guide().replace(
        "| `missing` | No invented actual or remainder |",
        "| `unresolved` | Invented score category | Not authorized |\n"
        "| `missing` | No invented actual or remainder |",
    )
    with pytest.raises(AssertionError, match="Unexpected player-score state table"):
        _validate_partial_methodology(text)


@pytest.mark.parametrize(
    "lost",
    (
        "exact canonical player/team/slot assignments",
        "even when the proposed slot is unchanged",
        "not aggregate carry again",
        "Every rostered current player, including bench and reserve",
        "not all companion content",
        "first actual period week minus one",
    ),
)
def test_partial_methodology_rejects_lost_permission_or_accounting_guard(
    lost: str,
) -> None:
    text = _guide()
    assert lost in text
    with pytest.raises(AssertionError, match="Missing partial-week contract"):
        _validate_partial_methodology(text.replace(lost, "REMOVED"))
