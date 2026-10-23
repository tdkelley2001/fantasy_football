from __future__ import annotations

from dataclasses import replace

import pytest

from fantasy_football.monte_carlo import (
    combine_monte_carlo_batches,
    run_monte_carlo_batch,
)
from fantasy_football.monte_carlo_precision import (
    PrecisionConfiguration,
    PrecisionError,
    ProbabilityMetric,
    StoppingReason,
    analyze_monte_carlo_precision,
    binomial_wilson_interval,
    precision_configuration_fingerprint,
    run_monte_carlo_to_precision,
)
from tests.test_monte_carlo import PrescribedModel, _config
from tests.test_season_simulator import _snapshot


def _precision(**changes) -> PrecisionConfiguration:
    base = PrecisionConfiguration(
        confidence_level=0.95,
        target_half_width=0.2,
        minimum_paths=2,
        maximum_paths=4,
        evaluation_interval=1,
    )
    return replace(base, **changes)


def test_wilson_known_toy_probability_and_boundary_events() -> None:
    middle = binomial_wilson_interval(
        50, 100, family_confidence_level=0.95, simultaneous_metric_count=1,
    )
    assert middle.lower == pytest.approx(0.4038315, abs=1e-6)
    assert middle.upper == pytest.approx(0.5961685, abs=1e-6)
    zero = binomial_wilson_interval(
        0, 10, family_confidence_level=0.95, simultaneous_metric_count=1,
    )
    all_event = binomial_wilson_interval(
        10, 10, family_confidence_level=0.95, simultaneous_metric_count=1,
    )
    assert zero.lower == 0.0 and 0.0 < zero.upper < 1.0
    assert all_event.upper == 1.0 and 0.0 < all_event.lower < 1.0
    assert zero.upper == pytest.approx(1.0 - all_event.lower)


def test_simultaneous_adjustment_is_more_conservative() -> None:
    individual = binomial_wilson_interval(
        50, 100, family_confidence_level=0.95, simultaneous_metric_count=1,
    )
    league_wide = binomial_wilson_interval(
        50, 100, family_confidence_level=0.95, simultaneous_metric_count=20,
    )
    assert league_wide.confidence_level > individual.confidence_level
    assert league_wide.half_width > individual.half_width


def test_planned_repeated_checkpoint_looks_are_in_simultaneous_family() -> None:
    snapshot = _snapshot()
    batch = run_monte_carlo_batch(snapshot, _config(0, 4), PrescribedModel())
    one_look = analyze_monte_carlo_precision(
        batch, _precision(minimum_paths=4, maximum_paths=4),
    )
    three_looks = analyze_monte_carlo_precision(
        batch, _precision(minimum_paths=2, maximum_paths=4, evaluation_interval=1),
    )
    assert three_looks.per_interval_confidence_level > one_look.per_interval_confidence_level
    assert (
        three_looks.teams[0].championship.interval.half_width
        > one_look.teams[0].championship.interval.half_width
    )


@pytest.mark.parametrize(
    "changes",
    (
        {"confidence_level": 1.0},
        {"target_half_width": 0.0},
        {"minimum_paths": 0},
        {"maximum_paths": 1, "minimum_paths": 2},
        {"evaluation_interval": 0},
    ),
)
def test_invalid_precision_configuration_fails(changes) -> None:
    with pytest.raises(PrecisionError):
        _precision(**changes)


def test_every_team_probability_and_placement_count_reconciles() -> None:
    snapshot = _snapshot()
    batch = run_monte_carlo_batch(snapshot, _config(0, 4), PrescribedModel())
    result = analyze_monte_carlo_precision(batch, _precision(target_half_width=0.49))
    assert result.monitored_metrics == len(snapshot.teams) * (len(snapshot.teams) + 2)
    assert len(result.teams) == len(snapshot.teams)
    assert sum(item.championship.probability for item in result.teams) == pytest.approx(1.0)
    assert sum(item.playoff_qualification.probability for item in result.teams) == pytest.approx(
        snapshot.rules.championship.qualifier_count
    )
    for place in range(1, len(snapshot.teams) + 1):
        assert sum(
            next(metric.probability for metric in team.final_placements if metric.placement == place)
            for team in result.teams
        ) == pytest.approx(1.0)
    assert all(
        metric.metric is ProbabilityMetric.FINAL_PLACEMENT
        for team in result.teams
        for metric in team.final_placements
    )


def test_one_team_metric_can_converge_while_another_does_not_without_stopping() -> None:
    snapshot = _snapshot()
    batch = run_monte_carlo_batch(snapshot, _config(0, 4), PrescribedModel())
    metric_count = len(snapshot.teams) * (len(snapshot.teams) + 2) * 3
    boundary = binomial_wilson_interval(
        0, 4, family_confidence_level=0.95, simultaneous_metric_count=metric_count,
    ).half_width
    middle = binomial_wilson_interval(
        2, 4, family_confidence_level=0.95, simultaneous_metric_count=metric_count,
    ).half_width
    result = analyze_monte_carlo_precision(
        batch, _precision(target_half_width=(boundary + middle) / 2),
    )
    by_team = {item.team_id: item for item in result.teams}
    assert by_team[3].championship.precision_reached
    assert not by_team[1].championship.precision_reached
    assert not result.league_wide_precision_reached


def test_adaptive_runner_stops_at_first_league_wide_precision_checkpoint() -> None:
    snapshot = _snapshot()
    simulation = _config(0, 4)
    result = run_monte_carlo_to_precision(
        snapshot,
        simulation,
        PrescribedModel(),
        _precision(target_half_width=0.49, minimum_paths=2, maximum_paths=4),
    )
    assert result.stopping_reason is StoppingReason.PRECISION_REACHED
    assert result.league_wide_precision_reached
    assert result.requested_paths == 2
    assert len(result.checkpoints) == 1


def test_adaptive_runner_reports_maximum_paths_without_false_convergence() -> None:
    result = run_monte_carlo_to_precision(
        _snapshot(),
        _config(0, 4),
        PrescribedModel(),
        _precision(target_half_width=0.01, minimum_paths=2, maximum_paths=4),
    )
    assert result.stopping_reason is StoppingReason.MAXIMUM_PATHS_REACHED
    assert not result.league_wide_precision_reached
    assert result.requested_paths == 4
    assert tuple(item.requested_paths for item in result.checkpoints) == (2, 3, 4)


def test_incomplete_capabilities_publish_no_probabilities_or_intervals() -> None:
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        rules=replace(
            snapshot.rules,
            consolation=replace(snapshot.rules.consolation, enabled=False),
        ),
    )
    simulation = _config(0, 4, complete=False)
    result = run_monte_carlo_to_precision(
        snapshot,
        simulation,
        PrescribedModel(),
        _precision(target_half_width=0.49, minimum_paths=2, maximum_paths=4),
    )
    assert result.stopping_reason is StoppingReason.INCOMPLETE_CAPABILITIES
    assert result.requested_paths == 2
    assert result.completed_paths == 0
    assert result.incomplete_paths == 2
    assert not result.league_wide_precision_reached
    assert all(
        estimate.probability is estimate.interval is None
        for team in result.teams
        for estimate in (team.championship, team.playoff_qualification, *team.final_placements)
    )


def test_partitioned_and_whole_execution_have_identical_precision_analysis() -> None:
    snapshot = _snapshot()
    model = PrescribedModel()
    config = _config(0, 4)
    whole = run_monte_carlo_batch(snapshot, config, model)
    left = run_monte_carlo_batch(snapshot, _config(0, 2), model)
    right = run_monte_carlo_batch(snapshot, _config(2, 2), model)
    combined = combine_monte_carlo_batches(snapshot, config, model, (right, left))
    precision = _precision(target_half_width=0.1)
    assert combined == whole
    assert analyze_monte_carlo_precision(combined, precision) == analyze_monte_carlo_precision(
        whole, precision,
    )


def test_precision_identity_changes_with_every_stopping_control() -> None:
    base = _precision()
    expected = precision_configuration_fingerprint(base)
    variants = (
        replace(base, confidence_level=0.9),
        replace(base, target_half_width=0.1),
        replace(base, minimum_paths=1),
        replace(base, maximum_paths=5),
        replace(base, evaluation_interval=2),
    )
    assert all(precision_configuration_fingerprint(item) != expected for item in variants)


def test_runner_requires_explicit_maximum_path_alignment() -> None:
    with pytest.raises(PrecisionError, match="path_count must equal"):
        run_monte_carlo_to_precision(
            _snapshot(), _config(0, 2), PrescribedModel(), _precision(maximum_paths=4),
        )
