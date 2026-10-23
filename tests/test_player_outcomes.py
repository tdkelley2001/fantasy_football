from __future__ import annotations

from dataclasses import replace

import pytest

from fantasy_football.canonical.model import ProjectionClass, ProjectionSource
from fantasy_football.player_outcomes import PlayerOutcomeError, ProvisionalNormalModel
from tests.test_season_simulator import _snapshot


def _score_map(scenario):
    return {
        (item.player_id, item.season, item.scoring_week): item.points
        for item in scenario.scores
    }


def test_same_key_reproduces_and_different_paths_change_draws() -> None:
    snapshot = _snapshot()
    model = ProvisionalNormalModel(base_stddev=3.0, projection_scale=0.25)
    first = model.generate_scenario(snapshot, master_seed=701, path_index=10)
    replay = model.generate_scenario(snapshot, master_seed=701, path_index=10)
    other = model.generate_scenario(snapshot, master_seed=701, path_index=11)
    assert first == replay
    assert _score_map(first) != _score_map(other)


def test_reordering_and_unrelated_player_do_not_perturb_existing_draws() -> None:
    snapshot = _snapshot()
    model = ProvisionalNormalModel(2.0, 0.1)
    expected = _score_map(model.generate_scenario(snapshot, master_seed=8, path_index=2))
    reordered = replace(
        snapshot,
        players=tuple(reversed(snapshot.players)),
        player_weeks=tuple(reversed(snapshot.player_weeks)),
    )
    assert _score_map(model.generate_scenario(reordered, master_seed=8, path_index=2)) == expected

    extra_player = replace(snapshot.players[-1], player_id=999, display_name="Unrelated")
    extra_weeks = tuple(
        replace(item, player_id=999)
        for item in snapshot.player_weeks
        if item.player_id == snapshot.players[-1].player_id
    )
    expanded = replace(
        snapshot,
        players=snapshot.players + (extra_player,),
        player_weeks=snapshot.player_weeks + extra_weeks,
    )
    actual = _score_map(model.generate_scenario(expanded, master_seed=8, path_index=2))
    assert {key: actual[key] for key in expected} == expected


def test_zero_missing_and_negative_effective_values_keep_distinct_source_records() -> None:
    snapshot = _snapshot()
    weeks = list(snapshot.player_weeks)
    weeks[0] = replace(
        weeks[0],
        raw_projection=0.0,
        projection_class=ProjectionClass.EXPLICIT_ZERO,
        effective_projection=0.0,
        effective_source=ProjectionSource.ESPN,
    )
    weeks[1] = replace(
        weeks[1],
        raw_projection=None,
        projection_class=ProjectionClass.MISSING,
        effective_projection=0.0,
        effective_source=ProjectionSource.MISSING_PROJECTION_POLICY,
    )
    weeks[2] = replace(
        weeks[2],
        raw_projection=-2.0,
        projection_class=ProjectionClass.PRESENT,
        effective_projection=-2.0,
        effective_source=ProjectionSource.ESPN,
    )
    changed = replace(snapshot, player_weeks=tuple(weeks))
    before = changed.player_weeks
    scenario = ProvisionalNormalModel(4.0, 0.2).generate_scenario(
        changed, master_seed=9, path_index=0
    )
    assert changed.player_weeks == before
    assert len(scenario.scores) == len(changed.player_weeks)
    assert all(item.points == item.points and abs(item.points) != float("inf") for item in scenario.scores)
    assert changed.player_weeks[0].projection_class is ProjectionClass.EXPLICIT_ZERO
    assert changed.player_weeks[1].projection_class is ProjectionClass.MISSING
    assert changed.player_weeks[2].effective_projection == -2.0


@pytest.mark.parametrize(
    ("base", "scale"),
    ((-1.0, 0.1), (1.0, -0.1), (float("nan"), 0.1), (0.0, 0.0)),
)
def test_invalid_dispersion_rejected(base: float, scale: float) -> None:
    with pytest.raises(PlayerOutcomeError):
        ProvisionalNormalModel(base, scale)


def test_invalid_random_identity_rejected() -> None:
    model = ProvisionalNormalModel(1.0, 0.1)
    with pytest.raises(PlayerOutcomeError, match="master_seed"):
        model.generate_scenario(_snapshot(), master_seed=True, path_index=0)
    with pytest.raises(PlayerOutcomeError, match="path_index"):
        model.generate_scenario(_snapshot(), master_seed=1, path_index=-1)
