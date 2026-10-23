"""Provisional, replaceable player-week outcome generation for M2.6."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Protocol

from fantasy_football.canonical.model import LeagueSnapshot, ProjectionClass
from fantasy_football.season_simulator import DeterministicScoreScenario
from fantasy_football.weekly_engine import RealizedPlayerScore


class PlayerOutcomeError(ValueError):
    """Raised when an outcome-model configuration or output is invalid."""


class PlayerOutcomeModel(Protocol):
    """Small swappable boundary between score draws and league mechanics."""

    @property
    def model_id(self) -> str: ...

    @property
    def parameters(self) -> tuple[tuple[str, str | int | float | bool], ...]: ...

    def generate_scenario(
        self, snapshot: LeagueSnapshot, *, master_seed: int, path_index: int
    ) -> DeterministicScoreScenario: ...


@dataclass(frozen=True, slots=True)
class ProvisionalNormalModel:
    """Illustrative independent Normal(mean=effective projection, sigma) model.

    ``sigma = base_stddev + projection_scale * abs(effective_projection)``.
    Both values are explicit provisional assumptions, not calibrated estimates.
    """

    base_stddev: float
    projection_scale: float
    version: str = "provisional-independent-normal-v1"

    def __post_init__(self) -> None:
        for name, value in (
            ("base_stddev", self.base_stddev),
            ("projection_scale", self.projection_scale),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise PlayerOutcomeError(f"{name} must be a finite nonnegative number")
        if self.base_stddev == 0 and self.projection_scale == 0:
            raise PlayerOutcomeError("at least one dispersion parameter must be positive")
        if not isinstance(self.version, str) or not self.version.strip():
            raise PlayerOutcomeError("model version must be a nonempty string")

    @property
    def model_id(self) -> str:
        return self.version

    @property
    def parameters(self) -> tuple[tuple[str, str | int | float | bool], ...]:
        return (
            ("base_stddev", float(self.base_stddev)),
            ("projection_scale", float(self.projection_scale)),
            ("conditional_independence", True),
        )

    def _standard_normal(
        self,
        *,
        master_seed: int,
        path_index: int,
        player_id: int,
        season: int,
        scoring_week: int,
    ) -> float:
        key = json.dumps(
            (
                "fantasy-football-player-week-draw-v1",
                master_seed,
                path_index,
                player_id,
                season,
                scoring_week,
                self.model_id,
                self.parameters,
            ),
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        first = int.from_bytes(hashlib.sha256(key + b"\x00").digest(), "big")
        second = int.from_bytes(hashlib.sha256(key + b"\x01").digest(), "big")
        denominator = float(1 << 256)
        u1 = (first + 0.5) / denominator
        u2 = (second + 0.5) / denominator
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def generate_scenario(
        self, snapshot: LeagueSnapshot, *, master_seed: int, path_index: int
    ) -> DeterministicScoreScenario:
        if isinstance(master_seed, bool) or not isinstance(master_seed, int):
            raise PlayerOutcomeError("master_seed must be an integer")
        if isinstance(path_index, bool) or not isinstance(path_index, int) or path_index < 0:
            raise PlayerOutcomeError("path_index must be a nonnegative integer")
        scores = []
        seen: set[tuple[int, int, int]] = set()
        for player_week in sorted(
            snapshot.player_weeks,
            key=lambda item: (item.player_id, item.season, item.scoring_week),
        ):
            if not (
                snapshot.first_simulation_week
                <= player_week.scoring_week
                <= snapshot.final_simulation_week
            ):
                continue
            key = (
                player_week.player_id,
                player_week.season,
                player_week.scoring_week,
            )
            if key in seen:
                raise PlayerOutcomeError(f"duplicate canonical player-week {key}")
            seen.add(key)
            mean = float(player_week.effective_projection)
            sigma = self.base_stddev + self.projection_scale * abs(mean)
            points = mean + sigma * self._standard_normal(
                master_seed=master_seed,
                path_index=path_index,
                player_id=player_week.player_id,
                season=player_week.season,
                scoring_week=player_week.scoring_week,
            )
            if not math.isfinite(points):
                raise PlayerOutcomeError(f"nonfinite generated score for player-week {key}")
            scores.append(
                RealizedPlayerScore(
                    player_week.player_id,
                    player_week.season,
                    player_week.scoring_week,
                    points,
                )
            )
        expected = {
            (item.player_id, item.season, item.scoring_week)
            for item in snapshot.player_weeks
            if snapshot.first_simulation_week
            <= item.scoring_week
            <= snapshot.final_simulation_week
        }
        if seen != expected:
            raise PlayerOutcomeError("generated player-week universe is incomplete")
        return DeterministicScoreScenario(
            scenario_id=f"mc:{self.model_id}:seed={master_seed}:path={path_index}",
            scores=tuple(scores),
        )


def projection_class_counts(snapshot: LeagueSnapshot) -> tuple[tuple[str, int], ...]:
    """Report source classes without changing their common provisional draw rule."""

    counts = {item.value: 0 for item in ProjectionClass}
    for item in snapshot.player_weeks:
        if snapshot.first_simulation_week <= item.scoring_week <= snapshot.final_simulation_week:
            counts[item.projection_class.value] += 1
    return tuple(sorted(counts.items()))
