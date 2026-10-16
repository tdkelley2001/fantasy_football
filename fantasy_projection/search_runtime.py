"""Runtime budgets and transparent approximate pruning for move searches."""
from __future__ import annotations

from dataclasses import dataclass

from .season import SeasonModelError


@dataclass(frozen=True)
class SearchRuntime:
    mode: str
    candidate_limit: int | None
    monte_carlo_finalists: int
    simulations: int


_PROFILES = {
    "quick": SearchRuntime("quick", 1_000, 3, 500),
    "standard": SearchRuntime("standard", 5_000, 5, 1_000),
    "deep": SearchRuntime("deep", None, 10, 2_000),
}


def runtime_profile(mode="standard", *, candidate_limit=None,
                    monte_carlo_finalists=None, simulations=None):
    mode = str(mode).lower()
    if mode == "custom":
        if type(candidate_limit) is not int or not 1 <= candidate_limit <= 100_000:
            raise SeasonModelError("Custom candidate limit must be from 1 to 100,000.")
        finalists = 0 if monte_carlo_finalists is None else monte_carlo_finalists
        draws = 1_000 if simulations is None else simulations
        result = SearchRuntime(mode, candidate_limit, finalists, draws)
    elif mode in _PROFILES:
        base = _PROFILES[mode]
        result = SearchRuntime(mode, base.candidate_limit,
            base.monte_carlo_finalists if monte_carlo_finalists is None else monte_carlo_finalists,
            base.simulations if simulations is None else simulations)
    else:
        raise SeasonModelError("Search mode must be Quick, Standard, Deep, or Custom.")
    if type(result.monte_carlo_finalists) is not int or not 0 <= result.monte_carlo_finalists <= 25:
        raise SeasonModelError("Monte Carlo finalists must be from 0 to 25.")
    if type(result.simulations) is not int or not 100 <= result.simulations <= 20_000:
        raise SeasonModelError("Search simulations must be from 100 to 20,000.")
    return result


def prune_ranked(candidates, limit, key):
    """Keep the best approximate candidates deterministically; return metadata."""
    generated = len(candidates)
    if limit is None or generated <= limit:
        return candidates, dict(generated=generated, evaluated=generated, pruned=0,
                                approximate_pruning=False)
    kept = sorted(candidates, key=key)[:limit]
    return kept, dict(generated=generated, evaluated=len(kept), pruned=generated-len(kept),
                      approximate_pruning=True)
