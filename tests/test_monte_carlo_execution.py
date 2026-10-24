from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from fantasy_football.monte_carlo_execution import (
    DETAILED_PROFILE,
    QUICK_PROFILE,
    ExecutionProfileName,
    ExecutionRecoveryError,
    MonteCarloCheckpointStore,
    SimulationExecutionProfile,
    execute_monte_carlo_profile,
    execution_policy_fingerprint,
)
from fantasy_football.monte_carlo_parallel import ParallelExecutionConfiguration
from fantasy_football.monte_carlo_precision import PrecisionConfiguration, StoppingReason
from tests.test_monte_carlo import PrescribedModel, _config
from tests.test_season_simulator import _snapshot


def _profile(*, parallel=False, target=0.01):
    return SimulationExecutionProfile(
        ExecutionProfileName.CUSTOM,
        PrecisionConfiguration(0.95, target, 2, 4, 1),
        ParallelExecutionConfiguration(2, 1) if parallel else None,
    )


def _store(tmp_path):
    root = tmp_path / "approved"
    return MonteCarloCheckpointStore(root / "run.json", approved_root=root)


def _rewrite(store, transform):
    envelope = json.loads(store.path.read_text(encoding="utf-8"))
    transform(envelope["checkpoint"])
    encoded = json.dumps(
        envelope["checkpoint"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    envelope["sha256"] = hashlib.sha256(encoded).hexdigest()
    store.path.write_text(
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True),
        encoding="utf-8",
    )


def test_quick_and_detailed_profiles_are_explicit_runtime_policies() -> None:
    assert QUICK_PROFILE.name is ExecutionProfileName.QUICK
    assert DETAILED_PROFILE.name is ExecutionProfileName.DETAILED
    assert QUICK_PROFILE.precision.maximum_paths < DETAILED_PROFILE.precision.maximum_paths
    assert QUICK_PROFILE.precision.target_half_width > DETAILED_PROFILE.precision.target_half_width
    assert QUICK_PROFILE.parallel.worker_count < DETAILED_PROFILE.parallel.worker_count
    assert execution_policy_fingerprint(QUICK_PROFILE) != execution_policy_fingerprint(
        DETAILED_PROFILE
    )


def test_progressive_results_are_intermediate_then_final(tmp_path) -> None:
    updates = []
    result = execute_monte_carlo_profile(
        _snapshot(), _config(0, 4), PrescribedModel(), _profile(),
        checkpoint_store=_store(tmp_path), progress_callback=updates.append,
    )
    assert [item.result.requested_paths for item in updates] == [2, 3, 4]
    assert [item.is_final for item in updates] == [False, False, True]
    assert [item.result.stopping_reason for item in updates] == [
        StoppingReason.IN_PROGRESS,
        StoppingReason.IN_PROGRESS,
        StoppingReason.MAXIMUM_PATHS_REACHED,
    ]
    assert result.result == updates[-1].result


def test_cancelled_checkpoint_resumes_to_identical_uninterrupted_result(tmp_path) -> None:
    snapshot = _snapshot()
    model = PrescribedModel()
    profile = _profile()
    config = _config(0, 4)
    store = _store(tmp_path)
    cancelled = execute_monte_carlo_profile(
        snapshot, config, model, profile,
        checkpoint_store=store, cancellation_requested=lambda: True,
    )
    assert cancelled.result.stopping_reason is StoppingReason.CANCELLED
    assert cancelled.result.requested_paths == 2
    resumed = execute_monte_carlo_profile(
        snapshot, config, model, profile, checkpoint_store=store, resume=True,
    )
    uninterrupted = execute_monte_carlo_profile(snapshot, config, model, profile)
    assert resumed.resumed and resumed.recovered_paths == 2
    assert resumed.newly_executed_paths == 2
    assert resumed.result == uninterrupted.result


def test_callback_interruption_leaves_atomic_recoverable_checkpoint(tmp_path) -> None:
    store = _store(tmp_path)

    def interrupt(_update):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        execute_monte_carlo_profile(
            _snapshot(), _config(0, 4), PrescribedModel(), _profile(),
            checkpoint_store=store, progress_callback=interrupt,
        )
    assert store.path.is_file()
    resumed = execute_monte_carlo_profile(
        _snapshot(), _config(0, 4), PrescribedModel(), _profile(),
        checkpoint_store=store, resume=True,
    )
    assert resumed.recovered_paths == 2


def test_corrupt_checkpoint_checksum_is_rejected(tmp_path) -> None:
    store = _store(tmp_path)
    execute_monte_carlo_profile(
        _snapshot(), _config(0, 4), PrescribedModel(), _profile(),
        checkpoint_store=store, cancellation_requested=lambda: True,
    )
    store.path.write_bytes(store.path.read_bytes() + b"x")
    with pytest.raises(ExecutionRecoveryError, match="JSON|checksum"):
        execute_monte_carlo_profile(
            _snapshot(), _config(0, 4), PrescribedModel(), _profile(),
            checkpoint_store=store, resume=True,
        )


@pytest.mark.parametrize("change", ("seed", "model", "precision", "execution"))
def test_incompatible_checkpoint_identity_is_rejected(tmp_path, change) -> None:
    store = _store(tmp_path)
    snapshot = _snapshot()
    config = _config(0, 4)
    profile = _profile()
    resume_model = PrescribedModel()
    execute_monte_carlo_profile(
        snapshot, config, PrescribedModel(), profile,
        checkpoint_store=store, cancellation_requested=lambda: True,
    )
    if change == "seed":
        config = replace(config, master_seed=999)
    elif change == "model":
        resume_model = _AlternateModel()
    elif change == "precision":
        profile = replace(
            profile, precision=replace(profile.precision, target_half_width=0.02)
        )
    else:
        profile = replace(profile, parallel=ParallelExecutionConfiguration(2, 1))
    with pytest.raises(ExecutionRecoveryError, match="does not match"):
        execute_monte_carlo_profile(
            snapshot, config, resume_model, profile,
            checkpoint_store=store, resume=True,
        )


@pytest.mark.parametrize("defect", ("duplicate", "missing"))
def test_checkpoint_duplicate_or_missing_path_coverage_is_rejected(tmp_path, defect) -> None:
    store = _store(tmp_path)
    execute_monte_carlo_profile(
        _snapshot(), _config(0, 4), PrescribedModel(), _profile(),
        checkpoint_store=store, cancellation_requested=lambda: True,
    )

    def corrupt(core):
        if defect == "duplicate":
            core["paths"][1] = core["paths"][0]
        else:
            core["paths"].pop()

    _rewrite(store, corrupt)
    with pytest.raises((ExecutionRecoveryError, ValueError)):
        execute_monte_carlo_profile(
            _snapshot(), _config(0, 4), PrescribedModel(), _profile(),
            checkpoint_store=store, resume=True,
        )


def test_forged_precision_history_is_rejected_even_with_valid_checksum(tmp_path) -> None:
    store = _store(tmp_path)
    execute_monte_carlo_profile(
        _snapshot(), _config(0, 4), PrescribedModel(), _profile(),
        checkpoint_store=store, cancellation_requested=lambda: True,
    )
    _rewrite(
        store,
        lambda core: core["precision_checkpoints"][0].update(
            {"league_wide_precision_reached": True}
        ),
    )
    with pytest.raises(ExecutionRecoveryError, match="path evidence"):
        execute_monte_carlo_profile(
            _snapshot(), _config(0, 4), PrescribedModel(), _profile(),
            checkpoint_store=store, resume=True,
        )


def test_incomplete_capabilities_stop_without_renormalized_progress(tmp_path) -> None:
    snapshot = _snapshot()
    snapshot = replace(
        snapshot,
        rules=replace(
            snapshot.rules,
            consolation=replace(snapshot.rules.consolation, enabled=False),
        ),
    )
    result = execute_monte_carlo_profile(
        snapshot,
        _config(0, 4, complete=False),
        PrescribedModel(),
        _profile(),
        checkpoint_store=_store(tmp_path),
    )
    assert result.result.stopping_reason is StoppingReason.INCOMPLETE_CAPABILITIES
    assert result.result.requested_paths == 2
    assert all(
        estimate.probability is estimate.interval is None
        for team in result.result.teams
        for estimate in (
            team.championship,
            team.playoff_qualification,
            *team.final_placements,
        )
    )


def test_parallel_resumed_and_sequential_results_are_identical(tmp_path) -> None:
    snapshot = _snapshot()
    model = PrescribedModel()
    parallel_profile = _profile(parallel=True)
    store = _store(tmp_path)
    execute_monte_carlo_profile(
        snapshot, _config(0, 4), model, parallel_profile,
        checkpoint_store=store, cancellation_requested=lambda: True,
    )
    resumed = execute_monte_carlo_profile(
        snapshot, _config(0, 4), model, parallel_profile,
        checkpoint_store=store, resume=True,
    )
    sequential = execute_monte_carlo_profile(
        snapshot, _config(0, 4), model, _profile()
    )
    assert resumed.result.batch == sequential.result.batch
    assert resumed.result.teams == sequential.result.teams
    assert resumed.result.stopping_reason == sequential.result.stopping_reason


def test_checkpoint_path_must_be_beneath_explicit_approved_root(tmp_path) -> None:
    with pytest.raises(ExecutionRecoveryError, match="approved root"):
        MonteCarloCheckpointStore(
            tmp_path / "outside.json", approved_root=tmp_path / "approved"
        )


class _AlternateModel(PrescribedModel):
    @property
    def model_id(self):
        return "alternate-evidence-model-v1"
