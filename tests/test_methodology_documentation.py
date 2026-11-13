"""P2 mathematical examples and source-owner boundaries, not calibration evidence."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from fantasy_football.canonical.model import ProjectionClass
from fantasy_football.player_outcomes import ProvisionalNormalModel
from tests.test_m33_player_outcomes import _model
from tests.test_season_simulator import _snapshot

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
