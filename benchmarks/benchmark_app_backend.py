"""Reproducible synthetic M6.3 backend benchmark; never contacts ESPN."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from importlib.metadata import version
import math
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from fantasy_football.app.background import (  # noqa: E402
    BackgroundRunCoordinator,
    BackgroundRunPolicy,
    BackgroundRunStore,
)
from fantasy_football.app.contracts import (  # noqa: E402
    BaselineAnalysisRequest,
    ManualScenarioRequest,
    TradeShapeInput,
    UnifiedCandidateConfiguration,
)
from fantasy_football.app.http import create_app  # noqa: E402
from fantasy_football.app.service import ApplicationDependencies, ApplicationService  # noqa: E402
from tests.test_app_service import (  # noqa: E402
    FixtureStore,
    _action_request,
    _model,
    _precision,
    _selector,
    _simulation,
)
from tests.test_scenario_evaluator import _scenario_snapshot_with_bench  # noqa: E402
from tests.test_season_simulator import _fourteen_team_postseason_snapshot  # noqa: E402


def _rss_bytes() -> int | None:
    try:
        import psutil
    except ImportError:
        return None
    return psutil.Process().memory_info().rss


def _wait(store: BackgroundRunStore, run_id: str) -> None:
    while store.get(run_id).status not in {"completed", "failed", "cancelled"}:
        time.sleep(0.005)


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(0.95 * len(values)) - 1)]


def _combined_action_request(snapshot):
    base = _action_request(snapshot)
    return base.model_copy(update={
        "candidate_search": UnifiedCandidateConfiguration(
            requesting_team_id=1,
            action_families=("trade", "trade_chain", "acquisition"),
            action_orderings=(
                "trade_then_acquisition", "acquisition_then_trade",
                "chain_then_acquisition",
            ),
            counterparty_team_ids=(2, 3),
            tradeable_player_ids=(-101, 1, 2, 3, 10, 11, 12),
            acquisition_player_ids=(-101,), eligible_drop_player_ids=(10,),
            trade_shapes=(TradeShapeInput(outgoing_count=1, incoming_count=1),),
            minimum_trade_chain_length=2, maximum_trade_chain_length=2,
            maximum_total_action_count=3, waiver_boundary="modeled_weekly_v1",
        )
    })


def _measure_tier(name: str, snapshot, repetitions: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="fantasy-football-m6-3-") as directory:
        store = BackgroundRunStore(Path(directory) / "runs.sqlite3")
        service = ApplicationService(ApplicationDependencies(FixtureStore(snapshot)))
        coordinator = BackgroundRunCoordinator(
            service, store, BackgroundRunPolicy(maximum_retained_runs=max(10, repetitions + 3))
        )
        app = create_app(service, background_coordinator=coordinator)
        baseline = BaselineAnalysisRequest(
            snapshot=_selector(snapshot), simulation=_simulation(), precision=_precision(),
            outcome_model=_model(),
        )
        manual = ManualScenarioRequest(
            snapshot=_selector(snapshot), simulation=_simulation(), precision=_precision(),
            outcome_model=_model(),
            scenario={"scenario_id": f"{name}-identity", "changes": (), "protected_players": ()},
        )
        rss_before = _rss_bytes()
        cpu_before = time.process_time()
        tracemalloc.start()
        started = time.perf_counter()
        baseline_result = service.run_baseline(baseline)
        baseline_seconds = time.perf_counter() - started
        started = time.perf_counter()
        service.run_manual_scenario(manual)
        manual_seconds = time.perf_counter() - started
        search_seconds = None
        page_latencies = []
        detail_latencies = []
        with TestClient(app) as client:
            poll_latencies = []
            health_latencies = []
            started = time.perf_counter()
            submitted = client.post("/api/v1/runs/baseline", json=baseline.model_dump(mode="json"))
            submission_seconds = time.perf_counter() - started
            run_id = submitted.json()["run_id"]
            while True:
                polled = time.perf_counter()
                status = client.get(f"/api/v1/runs/{run_id}")
                poll_latencies.append(time.perf_counter() - polled)
                health_started = time.perf_counter()
                client.get("/api/v1/health")
                health_latencies.append(time.perf_counter() - health_started)
                if status.json()["status"] == "completed":
                    break
                time.sleep(0.005)
            if len(snapshot.teams) <= 4:
                search = _combined_action_request(snapshot)
                started = time.perf_counter()
                search_run = client.post(
                    "/api/v1/runs/action-search", json=search.model_dump(mode="json")
                ).json()["run_id"]
                _wait(store, search_run)
                search_seconds = time.perf_counter() - started
                for _ in range(repetitions):
                    queried = time.perf_counter()
                    page = client.get(
                        f"/api/v1/runs/{search_run}/candidates",
                        params={"limit": 50, "sort_key": "requester_improvement", "direction": "desc"},
                    )
                    page_latencies.append(time.perf_counter() - queried)
                    if page.json()["candidates"]:
                        candidate_id = page.json()["candidates"][0]["candidate_id"]
                        queried = time.perf_counter()
                        client.get(f"/api/v1/runs/{search_run}/candidates/{candidate_id}")
                        detail_latencies.append(time.perf_counter() - queried)
            for _ in range(repetitions - 1):
                run = coordinator.submit("baseline", baseline)
                _wait(store, run.run_id)
        _, traced_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss_after = _rss_bytes()
        cpu_seconds = time.process_time() - cpu_before
        database_bytes = store.storage_bytes()
        coordinator.close()
        return {
            "tier": name,
            "teams": len(snapshot.teams),
            "players": len(snapshot.players),
            "paths": baseline_result.completed_paths,
            "baseline_seconds": baseline_seconds,
            "manual_seconds": manual_seconds,
            "action_search_seconds": search_seconds,
            "submission_seconds": submission_seconds,
            "poll_p95_seconds": _p95(poll_latencies),
            "health_p95_seconds": _p95(health_latencies),
            "candidate_page_p95_seconds": _p95(page_latencies),
            "candidate_detail_p95_seconds": _p95(detail_latencies),
            "sqlite_bytes": database_bytes,
            "traced_python_peak_bytes": traced_peak,
            "rss_before_bytes": rss_before,
            "rss_after_bytes": rss_after,
            "parent_cpu_seconds": cpu_seconds,
            "peak_child_processes": None,
            "transient_coordinator_references": coordinator.transient_reference_count(),
            "repetitions": repetitions,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=("small", "representative", "stress", "all"), default="all")
    args = parser.parse_args()
    source = _scenario_snapshot_with_bench()
    small = replace(
        source,
        fantasy_matchups=tuple(
            matchup for matchup in source.fantasy_matchups if matchup.bracket_type is None
        ),
    )
    representative = _fourteen_team_postseason_snapshot()
    tiers = {
        "small": (small, 5),
        "representative": (representative, 3),
        "stress": (small, 50),
    }
    selected = tiers if args.tier == "all" else {args.tier: tiers[args.tier]}
    report = {
        "environment": {
            "os": platform.platform(), "python": platform.python_version(),
            "logical_cores": os.cpu_count(), "processor": platform.processor() or "unavailable",
            "physical_ram_bytes": None,
            "dependency_versions": {
                name: version(name) for name in ("fastapi", "starlette", "uvicorn", "pydantic")
            },
            "model": "provisional_normal", "master_seed": 8128,
            "execution_policy": {
                "active_runs": 1, "engine_workers_per_run": 2,
                "note": "peak child-process RSS/count unavailable in this harness",
            },
            "note": "synthetic sanitized fixtures; not a live ESPN benchmark",
        },
        "tiers": [_measure_tier(name, snapshot, count) for name, (snapshot, count) in selected.items()],
    }
    try:
        import psutil
    except ImportError:
        pass
    else:
        report["environment"]["physical_ram_bytes"] = psutil.virtual_memory().total
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
