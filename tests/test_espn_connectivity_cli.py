from __future__ import annotations

from espn_api.requests.espn_requests import ESPNAccessDenied
from requests import ConnectionError

from fantasy_football import espn_connectivity


def test_cli_reports_authentication_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        espn_connectivity,
        "load_settings",
        lambda: type("Settings", (), {"log_level": "INFO"})(),
    )
    monkeypatch.setattr(
        espn_connectivity,
        "fetch_and_audit",
        lambda settings, expected_team_count: (_ for _ in ()).throw(
            ESPNAccessDenied("credentials rejected")
        ),
    )

    assert espn_connectivity.main(["--expected-team-count", "14"]) == 2
    assert "credentials rejected" in capsys.readouterr().err


def test_cli_reports_connectivity_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        espn_connectivity,
        "load_settings",
        lambda: type("Settings", (), {"log_level": "INFO"})(),
    )
    monkeypatch.setattr(
        espn_connectivity,
        "fetch_and_audit",
        lambda settings, expected_team_count: (_ for _ in ()).throw(
            ConnectionError("network unavailable")
        ),
    )

    assert espn_connectivity.main(["--expected-team-count", "14"]) == 2
    assert "network unavailable" in capsys.readouterr().err


def test_fetch_reports_malformed_response(monkeypatch) -> None:
    class MalformedLeague:
        def __init__(self, **kwargs):
            raise KeyError("settings")

    monkeypatch.setattr(espn_connectivity, "League", MalformedLeague)
    settings = type(
        "Settings",
        (),
        {"league_id": 123456, "season": 2026, "credentials": None},
    )()

    try:
        espn_connectivity.fetch_and_audit(settings, expected_team_count=14)
    except espn_connectivity.ConnectivityAuditError as exc:
        assert "malformed or unsupported" in str(exc)
    else:
        raise AssertionError("Malformed response did not raise ConnectivityAuditError")
