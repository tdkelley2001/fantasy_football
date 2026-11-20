"""Sanitized source-contract tests; fixtures do not establish live semantics."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fantasy_football.current_week import (
    CurrentWeekEvidenceError,
    _reconcile_standings_prefix,
    _reconciled_current_total,
    build_current_week_input,
)
from fantasy_football.espn_adapter import capture_response, translate_bundle
from fantasy_football.partial_week import PlayerScoreState
from fantasy_football.snapshot_store import SnapshotStore, publish_and_verify
from tests.adapter_fixtures import source_bundle


def _bundle():
    bundle = source_bundle()
    root = bundle.league_initial.payload
    root["schedule"][:0] = [
        {
            "id": 10,
            "matchupPeriodId": 1,
            "home": {"teamId": 1, "totalPoints": 10.0},
            "away": {"teamId": 2, "totalPoints": 7.0},
            "winner": "HOME",
        },
        {
            "id": 11,
            "matchupPeriodId": 1,
            "home": {"teamId": 3, "totalPoints": 3.0},
            "away": {"teamId": 4, "totalPoints": 4.0},
            "winner": "AWAY",
        },
    ]
    for team, values in zip(
        root["teams"],
        [(1, 0, 10.0, 7.0), (0, 1, 7.0, 10.0), (0, 1, 3.0, 4.0), (1, 0, 4.0, 3.0)],
        strict=True,
    ):
        wins, losses, pf, pa = values
        team["record"]["overall"].update(
            wins=wins, losses=losses, ties=0, pointsFor=pf, pointsAgainst=pa
        )
    for page in bundle.current_player_pages + bundle.future_player_pages:
        for entry in page.response.payload["players"]:
            entry["lineupLocked"] = entry["id"] in (2, 3)
            entry["rosterLocked"] = entry["lineupLocked"]
            entry["tradeLocked"] = False
            if page.scoring_week == 2 and entry["id"] in (2, 3):
                entry["player"]["stats"].append(
                    {
                        "seasonId": 2026,
                        "scoringPeriodId": 2,
                        "statSourceId": 0,
                        "statSplitTypeId": 1,
                        "appliedTotal": 13.25 if entry["id"] == 2 else 0.0,
                    }
                )
            if page.scoring_week == 2 and entry["id"] == 4:
                entry["player"]["stats"] = [
                    {
                        "seasonId": 2026,
                        "scoringPeriodId": 2,
                        "statSourceId": 1,
                        "statSplitTypeId": 1,
                        "appliedTotal": 10.0,
                    }
                ]
    for team in bundle.pro_schedule.payload["settings"]["proTeams"]:
        for game in team.get("proGamesByScoringPeriod", {}).get("2", []):
            if game["homeProTeamId"] == 3:
                game["status"] = "STATUS_FINAL"
    for team in root["teams"]:
        for entry in team["roster"]["entries"]:
            entry["playerPoolEntry"].update(
                lineupLocked=entry["playerId"] in (2, 3),
                rosterLocked=entry["playerId"] in (2, 3),
                tradeLocked=False,
            )
    for game in root["schedule"][2:]:
        for side in ("home", "away"):
            data = game[side]
            team = next(t for t in root["teams"] if t["id"] == data["teamId"])
            points = 13.25 if data["teamId"] == 2 else 0.0
            data["pointsByScoringPeriod"] = {"2": points}
            data["rosterForCurrentScoringPeriod"] = {
                "entries": deepcopy(team["roster"]["entries"]),
                "appliedStatTotal": points,
            }
    bundle.league_reconciliation.payload.update(deepcopy(root))
    return replace(bundle, preserve_current_week=True)


def _publish(tmp_path, bundle):
    def recapture(response):
        return capture_response(
            response.payload,
            source_id=response.source_id,
            request_type=response.request_type,
            endpoint=response.endpoint,
            view=response.view,
            parameters=response.parameters,
            retrieved_at_utc=response.retrieved_at_utc,
        )

    bundle = replace(
        bundle,
        league_initial=recapture(bundle.league_initial),
        league_reconciliation=recapture(bundle.league_reconciliation),
        pro_schedule=recapture(bundle.pro_schedule),
        current_player_pages=tuple(
            replace(p, response=recapture(p.response))
            for p in bundle.current_player_pages
        ),
        future_player_pages=tuple(
            replace(p, response=recapture(p.response))
            for p in bundle.future_player_pages
        ),
    )
    result = translate_bundle(bundle)
    store = SnapshotStore(tmp_path / "snapshots.sqlite3")
    store.initialize()
    metadata = publish_and_verify(store, result)
    loaded = store.load(metadata.snapshot_id)
    return loaded.snapshot, tuple(r.response for r in loaded.raw_sources)


def test_completed_and_unstarted_source_reconciles(tmp_path):
    snapshot, responses = _publish(tmp_path, _bundle())
    result = build_current_week_input(snapshot, responses)
    states = {p.player_id: p for p in result.evidence.players}
    assert states[2].score_state is PlayerScoreState.COMPLETED_FIXED
    assert states[2].fixed_actual_points == 13.25
    assert states[3].fixed_actual_points == 0.0
    assert states[4].score_state is PlayerScoreState.UNSTARTED
    assert result.evidence.standings_cutoff.current_matchup_period_included is False


@pytest.mark.parametrize(
    "mutation,message",
    [
        ("slot", "differs from canonical"),
        ("lock", "lineup locks disagree"),
        ("score", "do not reconcile"),
        ("duplicate", "duplicate identifier"),
        ("standings", "completed matchup prefix"),
    ],
)
def test_source_disagreement_fails_closed(tmp_path, mutation, message):
    bundle = _bundle()
    root = bundle.league_initial.payload
    side = root["schedule"][2]["home"]
    if mutation == "slot":
        side["rosterForCurrentScoringPeriod"]["entries"][0]["lineupSlotId"] = 20
    elif mutation == "lock":
        side["rosterForCurrentScoringPeriod"]["entries"][0]["playerPoolEntry"][
            "lineupLocked"
        ] = True
    elif mutation == "score":
        side["pointsByScoringPeriod"]["2"] = 1.0
    elif mutation == "duplicate":
        root["schedule"].append(deepcopy(root["schedule"][2]))
    elif mutation == "standings":
        root["schedule"][0]["home"]["totalPoints"] += 1
    bundle.league_reconciliation.payload.update(deepcopy(root))
    from fantasy_football.espn_adapter import EspnAdapterError

    with pytest.raises((CurrentWeekEvidenceError, EspnAdapterError), match=message):
        snapshot, responses = _publish(tmp_path, bundle)
        build_current_week_input(snapshot, responses)


def test_decimal_source_reconciliation_does_not_change_float_composition():
    assert _reconciled_current_total(0.3, 0.3, [0.1, 0.2]) == 0.30000000000000004
    with pytest.raises(CurrentWeekEvidenceError, match="do not reconcile"):
        _reconciled_current_total(0.3001, 0.3001, [0.1, 0.2])


def test_application_routes_validated_source_companion(tmp_path):
    from fantasy_football.app.contracts import SimulationConfiguration, SnapshotSelector
    from fantasy_football.app.service import ApplicationDependencies, ApplicationService

    snapshot, responses = _publish(tmp_path, _bundle())
    store = SnapshotStore(tmp_path / "snapshots.sqlite3")
    service = ApplicationService(ApplicationDependencies(store))
    summary = service.inspect_snapshot(
        SnapshotSelector(snapshot_id=snapshot.snapshot_id)
    )
    assert summary.live_scoring.current_week_execution_available is True
    configuration = SimulationConfiguration(
        master_seed=1,
        path_count=1,
        ir_policy="projection_based",
        waiver_boundary="modeled_weekly_v1",
        use_observed_current_week_lineup=True,
    )
    prepared = service._simulation(
        configuration, loaded=store.load(snapshot.snapshot_id)
    )
    assert prepared.partial_week == build_current_week_input(snapshot, responses)
    old = configuration.model_copy(update={"use_observed_current_week_lineup": False})
    assert "use_observed_current_week_lineup" not in old.model_dump()


def test_mutated_raw_source_is_rejected_without_republication(tmp_path):
    snapshot, responses = _publish(tmp_path, _bundle())
    responses[0].payload["scoringPeriodId"] = 99
    with pytest.raises(CurrentWeekEvidenceError, match="immutable snapshot provenance"):
        build_current_week_input(snapshot, responses)


def test_started_game_without_completion_has_no_approved_sampler(tmp_path):
    bundle = _bundle()
    for team in bundle.pro_schedule.payload["settings"]["proTeams"]:
        for game in team.get("proGamesByScoringPeriod", {}).get("2", []):
            if game["homeProTeamId"] == 3:
                game["status"] = "STATUS_IN_PROGRESS"
    snapshot, responses = _publish(tmp_path, bundle)
    with pytest.raises(
        CurrentWeekEvidenceError, match="no approved remaining-performance model"
    ):
        build_current_week_input(snapshot, responses)


def test_historical_standings_reconcile_exact_decimal_totals():
    teams = [
        SimpleNamespace(
            team_id=1, wins=2, losses=0, ties=0, points_for=30.3, points_against=3.3
        ),
        SimpleNamespace(
            team_id=2, wins=0, losses=2, ties=0, points_for=3.3, points_against=30.3
        ),
    ]
    schedule = [
        {
            "matchupPeriodId": period,
            "winner": "HOME",
            "home": {"teamId": 1, "totalPoints": home},
            "away": {"teamId": 2, "totalPoints": away},
        }
        for period, home, away in [(1, 10.1, 1.1), (2, 20.2, 2.2)]
    ]
    assert _reconcile_standings_prefix(teams, schedule, {1, 2}, 2) == {1, 2}
    teams[0].points_for = teams[1].points_against = 10.1 + 20.2
    teams[1].points_for = teams[0].points_against = 1.1 + 2.2
    assert _reconcile_standings_prefix(teams, schedule, {1, 2}, 2) == {1, 2}
    teams[0].points_for = 30.300000000000004
    with pytest.raises(
        CurrentWeekEvidenceError, match="Cumulative standings do not reconcile"
    ):
        _reconcile_standings_prefix(teams, schedule, {1, 2}, 2)


def test_current_week_trade_rejects_before_paired_sampling(tmp_path, monkeypatch):
    from fantasy_football.app import service as app
    from fantasy_football.app.contracts import ManualScenarioRequest

    snapshot, _ = _publish(tmp_path, _bundle())
    service = app.ApplicationService(
        app.ApplicationDependencies(SnapshotStore(tmp_path / "snapshots.sqlite3"))
    )
    request = ManualScenarioRequest.model_validate(
        {
            "snapshot": {"snapshot_id": snapshot.snapshot_id},
            "simulation": {
                "master_seed": 1,
                "path_count": 1,
                "ir_policy": "projection_based",
                "waiver_boundary": "modeled_weekly_v1",
                "use_observed_current_week_lineup": True,
            },
            "scenario": {
                "scenario_id": "partial-trade",
                "changes": [
                    {"player_id": -101, "from_team_id": 1, "to_team_id": 4},
                    {"player_id": 4, "from_team_id": 4, "to_team_id": 1},
                ],
            },
            "precision": {
                "family_confidence_level": 0.95,
                "target_half_width_probability": 0.1,
                "minimum_paths": 1,
                "maximum_paths": 1,
                "evaluation_interval_paths": 1,
            },
            "outcome_model": {"base_stddev_points": 4.0, "projection_scale": 0.2},
        }
    )

    def unexpected_evaluation(*args, **kwargs):
        pytest.fail("unresolved trade timing must reject before paired evaluation")

    monkeypatch.setattr(app, "evaluate_manual_scenario", unexpected_evaluation)
    with pytest.raises(
        app.ApplicationServiceError, match="Trade timing permission is unresolved"
    ) as exc:
        service.run_manual_scenario(request)
    assert exc.value.code == "partial_week_trade_timing_unresolved"


@pytest.mark.parametrize(
    ("players", "earliest"),
    [
        ((-101, 4), 2),
        ((-101, 2), 3),
        ((2, 3), 3),
        ((-101, 2, 4), 3),
    ],
)
def test_trade_timing_checks_every_participant(tmp_path, players, earliest):
    from fantasy_football.effective_trades import (
        EffectiveTradeError,
        TradeTransfer,
        current_trade_eligibility,
        resolve_effective_trades,
    )

    snapshot, sources = _publish(tmp_path, _bundle())
    snapshot = replace(
        snapshot,
        rules=replace(
            snapshot.rules,
            trades=replace(snapshot.rules.trades, deadline_utc=None),
        ),
    )
    partial = build_current_week_input(snapshot, sources)
    weeks, eligibility = current_trade_eligibility(snapshot, partial, sources)
    owners = {item.player_id: item.team_id for item in snapshot.roster_entries}
    transfers = tuple(
        TradeTransfer(pid, owners[pid], owners[players[(i + 1) % len(players)]])
        for i, pid in enumerate(players)
    )
    assert (
        resolve_effective_trades(snapshot, ((None, transfers),), weeks, eligibility)[
            0
        ].scoring_week
        == earliest
    )
    assert (
        resolve_effective_trades(snapshot, ((3, transfers),), weeks, eligibility)[
            0
        ].scoring_week
        == 3
    )
    if earliest == 3:
        with pytest.raises(EffectiveTradeError, match="earlier than"):
            resolve_effective_trades(snapshot, ((2, transfers),), weeks, eligibility)
    back = tuple(
        TradeTransfer(t.player_id, t.to_team_id, t.from_team_id) for t in transfers
    )
    sequence = resolve_effective_trades(
        snapshot, ((3, transfers), (None, back)), weeks, eligibility
    )
    assert tuple(item.scoring_week for item in sequence) == (3, 3)
    with pytest.raises(EffectiveTradeError, match="no longer owned"):
        resolve_effective_trades(
            snapshot, ((3, transfers), (None, transfers)), weeks, eligibility
        )


def test_source_trade_restriction_does_not_clear_at_next_boundary(tmp_path):
    from fantasy_football.effective_trades import current_trade_eligibility

    bundle = _bundle()
    for page in bundle.current_player_pages:
        for item in page.response.payload["players"]:
            if item["id"] == 2:
                item["tradeLocked"] = True
    for team in bundle.league_initial.payload["teams"]:
        for entry in team["roster"]["entries"]:
            if entry["playerId"] == 2:
                entry["playerPoolEntry"]["tradeLocked"] = True
    snapshot, sources = _publish(tmp_path, bundle)
    partial = build_current_week_input(snapshot, sources)
    _, eligibility = current_trade_eligibility(snapshot, partial, sources)
    assert 2 not in eligibility
