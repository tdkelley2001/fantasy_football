from __future__ import annotations

from dataclasses import replace

import pytest

from fantasy_football.canonical.model import ProjectionClass, ProjectionSource
from fantasy_football.evolving_state import IRPolicy
from fantasy_football.monte_carlo import (
    MonteCarloConfig,
    combine_monte_carlo_batches,
    run_monte_carlo_batch,
    simulation_configuration_fingerprint,
)
from fantasy_football.outcome_distribution_research import (
    CandidateFamily,
    CandidateSpecification,
    Conditioning,
    research_outcome_distributions,
)
from fantasy_football.player_outcomes import (
    EmpiricalEvidenceStatus,
    PlayerOutcomeError,
    fit_projection_empirical_residual_model,
)
from fantasy_football.weekly_transactions import WaiverBoundaryPolicy, WeeklyTransactionPolicy
from tests.test_outcome_distribution_research import _config, _dataset, _record
from tests.test_season_simulator import _snapshot


def _evidence(*, changed_actual: bool = False, minimum_group_size: int = 2):
    training = (
        _record(101, 2024, 1, 2.0, 0.0),
        _record(102, 2024, 1, 3.0, 5.0),
        _record(103, 2024, 1, 10.0, 12.0),
        _record(104, 2024, 1, 20.0, 16.0 if changed_actual else 15.0),
    )
    evaluation = (
        _record(201, 2025, 1, 3.0, 0.0),
        _record(202, 2025, 1, 10.0, 11.0),
    )
    dataset = _dataset(((2024, 1, training), (2025, 1, evaluation)))
    config = _config(minimum_group_size=minimum_group_size)
    report = research_outcome_distributions(
        dataset,
        config,
        candidates=(CandidateSpecification(
            "projection_empirical_residual",
            CandidateFamily.EMPIRICAL,
            Conditioning.PROJECTION,
        ),),
    )
    assert report.exploratory_best_candidate_id == "projection_empirical_residual"
    return dataset, report


def _model(**changes):
    dataset, report = _evidence(**changes)
    return fit_projection_empirical_residual_model(
        dataset, report, selection_reference="M3.2-accepted-exploratory-selection",
    )


def _score_map(scenario):
    return {(item.player_id, item.season, item.scoring_week): item.points for item in scenario.scores}


def _mc_config():
    return MonteCarloConfig(
        master_seed=81,
        path_count=1,
        first_path_index=0,
        ir_policy=IRPolicy.PROJECTION_BASED,
        transaction_policy=WeeklyTransactionPolicy(waiver_boundary=WaiverBoundaryPolicy.MODELED_WEEKLY_V1),
    )


def test_fit_records_unverified_evidence_and_complete_reproducible_identity() -> None:
    model = _model()
    parameters = dict(model.parameters)
    assert model.evidence_status is EmpiricalEvidenceStatus.UNVERIFIED_EXPLORATORY
    assert parameters["dataset_sha256"] == model.dataset_sha256
    assert parameters["research_report_sha256"] == model.research_report_sha256
    assert parameters["training_evidence_sha256"] == model.training_evidence_sha256
    assert parameters["fitted_atoms_sha256"] == model.fitted_atoms_sha256
    assert parameters["conditional_bias_correction"] is False
    assert model.training_row_count == 4


def test_empirical_quantiles_preserve_discrete_zero_mass_and_residual_atoms() -> None:
    model = _model()
    snapshot = _snapshot()
    target = snapshot.player_weeks[0]
    weeks = tuple(
        replace(
            item,
            raw_projection=3.0,
            projection_class=ProjectionClass.PRESENT,
            effective_projection=3.0,
            effective_source=ProjectionSource.ESPN,
        ) if item == target else item
        for item in snapshot.player_weeks
    )
    changed = replace(snapshot, player_weeks=weeks)
    observed = {
        _score_map(model.generate_scenario(changed, master_seed=71, path_index=index))[
            (target.player_id, target.season, target.scoring_week)
        ]
        for index in range(100)
    }
    assert observed == {0.0, 5.0}


def test_sparse_projection_group_uses_only_explicit_pooled_empirical_policy() -> None:
    model = _model(minimum_group_size=2)
    assert dict(model.parameters)["sparse_group_policy"] == "pooled_empirical"
    snapshot = _snapshot()
    target = snapshot.player_weeks[0]
    weeks = tuple(
        replace(
            item,
            raw_projection=20.0,
            projection_class=ProjectionClass.PRESENT,
            effective_projection=20.0,
            effective_source=ProjectionSource.ESPN,
        ) if item == target else item
        for item in snapshot.player_weeks
    )
    changed = replace(snapshot, player_weeks=weeks)
    observed = {
        _score_map(model.generate_scenario(changed, master_seed=72, path_index=index))[
            (target.player_id, target.season, target.scoring_week)
        ]
        for index in range(200)
    }
    assert observed == {0.0, 15.0, 22.0}


def test_missing_and_explicit_zero_remain_unavailable_deterministic_zero() -> None:
    model = _model()
    snapshot = _snapshot()
    weeks = list(snapshot.player_weeks)
    weeks[0] = replace(
        weeks[0], raw_projection=None, projection_class=ProjectionClass.MISSING,
        effective_projection=0.0, effective_source=ProjectionSource.MISSING_PROJECTION_POLICY,
    )
    weeks[1] = replace(
        weeks[1], raw_projection=0.0, projection_class=ProjectionClass.EXPLICIT_ZERO,
        effective_projection=0.0, effective_source=ProjectionSource.ESPN,
    )
    changed = replace(snapshot, player_weeks=tuple(weeks))
    scores = _score_map(model.generate_scenario(changed, master_seed=7, path_index=4))
    assert scores[(weeks[0].player_id, weeks[0].season, weeks[0].scoring_week)] == 0.0
    assert scores[(weeks[1].player_id, weeks[1].season, weeks[1].scoring_week)] == 0.0
    assert changed.player_weeks == tuple(weeks)


def test_baseline_and_hypothetical_ownership_receive_matched_player_week_draws() -> None:
    model = _model()
    baseline = _snapshot()
    first = next(item for item in baseline.roster_entries if item.team_id == 1)
    second = next(item for item in baseline.roster_entries if item.team_id == 2)
    swapped = tuple(
        replace(item, team_id=2) if item == first
        else replace(item, team_id=1) if item == second
        else item
        for item in baseline.roster_entries
    )
    hypothetical = replace(
        baseline,
        roster_entries=tuple(reversed(swapped)),
        players=tuple(reversed(baseline.players)),
        player_weeks=tuple(reversed(baseline.player_weeks)),
    )
    expected = _score_map(model.generate_scenario(baseline, master_seed=91, path_index=12))
    actual = _score_map(model.generate_scenario(hypothetical, master_seed=91, path_index=12))
    assert actual == expected


def test_empirical_model_preserves_batch_partition_and_combination_replay() -> None:
    snapshot = _snapshot()
    model = _model()
    whole_config = replace(_mc_config(), path_count=2)
    whole = run_monte_carlo_batch(snapshot, whole_config, model)
    left = run_monte_carlo_batch(snapshot, replace(whole_config, path_count=1), model)
    right = run_monte_carlo_batch(
        snapshot, replace(whole_config, first_path_index=1, path_count=1), model,
    )
    assert combine_monte_carlo_batches(snapshot, whole_config, model, (right, left)) == whole


def test_random_key_dimensions_are_stable_and_distinct() -> None:
    model = _model()
    common = dict(master_seed=1, path_index=2, player_id=3, season=2026, scoring_week=4)
    value = model._uniform(**common)
    assert model._uniform(**common) == value
    assert model._uniform(**(common | {"path_index": 3})) != value
    assert model._uniform(**(common | {"player_id": 4})) != value
    assert model._uniform(**(common | {"scoring_week": 5})) != value


def test_research_evidence_and_configuration_change_simulation_fingerprint() -> None:
    snapshot = _snapshot()
    config = _mc_config()
    baseline = _model()
    evidence_changed = _model(changed_actual=True)
    grouping_changed = _model(minimum_group_size=3)
    fingerprints = {
        simulation_configuration_fingerprint(snapshot, config, model)
        for model in (baseline, evidence_changed, grouping_changed)
    }
    assert len(fingerprints) == 3

    altered_pooled = ((baseline.pooled_residual_atoms[0][0] + 0.5, baseline.pooled_residual_atoms[0][1]),) + baseline.pooled_residual_atoms[1:]
    first_key, first_group = baseline.grouped_residual_atoms[0]
    altered_group = ((first_group[0][0] + 0.5, first_group[0][1]),) + first_group[1:]
    altered_atoms = replace(
        baseline,
        pooled_residual_atoms=altered_pooled,
        grouped_residual_atoms=((first_key, altered_group),) + baseline.grouped_residual_atoms[1:],
    )
    assert simulation_configuration_fingerprint(snapshot, config, altered_atoms) not in fingerprints


def test_batch_fingerprint_is_unchanged_by_path_range_for_empirical_model() -> None:
    snapshot = _snapshot()
    model = _model()
    config = _mc_config()
    assert simulation_configuration_fingerprint(snapshot, config, model) == simulation_configuration_fingerprint(
        snapshot, replace(config, first_path_index=500, path_count=20), model,
    )


def test_fit_rejects_mismatched_or_incomplete_research_evidence() -> None:
    dataset, report = _evidence()
    other_dataset, _ = _evidence(changed_actual=True)
    with pytest.raises(PlayerOutcomeError, match="source dataset identity"):
        fit_projection_empirical_residual_model(
            other_dataset, report, selection_reference="approved-test-selection",
        )
    pooled_report = research_outcome_distributions(
        dataset,
        report.configuration,
        candidates=(CandidateSpecification(
            "pooled_empirical_residual",
            CandidateFamily.EMPIRICAL,
            Conditioning.POOLED,
        ),),
    )
    with pytest.raises(PlayerOutcomeError, match="does not select"):
        fit_projection_empirical_residual_model(
            dataset,
            pooled_report,
            selection_reference="approved-test-selection",
        )
    mislabeled_report = research_outcome_distributions(
        dataset,
        report.configuration,
        candidates=(CandidateSpecification(
            "projection_empirical_residual",
            CandidateFamily.NORMAL,
            Conditioning.PROJECTION,
        ),),
    )
    with pytest.raises(PlayerOutcomeError, match="must be empirical residuals"):
        fit_projection_empirical_residual_model(
            dataset, mislabeled_report, selection_reference="approved-test-selection",
        )
    sparse_config = replace(report.configuration, minimum_training_rows=99)
    sparse_report = research_outcome_distributions(
        dataset,
        sparse_config,
        candidates=(CandidateSpecification(
            "projection_empirical_residual",
            CandidateFamily.EMPIRICAL,
            Conditioning.PROJECTION,
        ),),
    )
    with pytest.raises(PlayerOutcomeError, match="does not select"):
        fit_projection_empirical_residual_model(
            dataset, sparse_report, selection_reference="approved-test-selection",
        )


def test_invalid_random_identity_and_empty_selection_reference_fail() -> None:
    dataset, report = _evidence()
    with pytest.raises(PlayerOutcomeError, match="selection_reference"):
        fit_projection_empirical_residual_model(dataset, report, selection_reference="")
    model = _model()
    with pytest.raises(PlayerOutcomeError, match="master_seed"):
        model.generate_scenario(_snapshot(), master_seed=True, path_index=0)
    with pytest.raises(PlayerOutcomeError, match="path_index"):
        model.generate_scenario(_snapshot(), master_seed=1, path_index=-1)


def test_fit_and_generation_make_no_network_calls(monkeypatch) -> None:
    def blocked(*args, **kwargs):
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr("urllib.request.urlopen", blocked)
    model = _model()
    model.generate_scenario(_snapshot(), master_seed=1, path_index=0)
