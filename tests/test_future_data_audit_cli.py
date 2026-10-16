from __future__ import annotations

from espn_api.requests.espn_requests import ESPNAccessDenied
from requests import ConnectionError

from fantasy_football import future_data_audit


def _settings() -> object:
    return type("Settings", (), {"log_level": "INFO"})()


def test_cli_reports_authentication_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(future_data_audit, "load_settings", _settings)
    monkeypatch.setattr(
        future_data_audit,
        "audit_live",
        lambda settings, expected_team_count: (_ for _ in ()).throw(
            ESPNAccessDenied("credentials rejected")
        ),
    )
    assert future_data_audit.main(["--expected-team-count", "14"]) == 2
    assert "credentials rejected" in capsys.readouterr().err


def test_cli_reports_connectivity_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(future_data_audit, "load_settings", _settings)
    monkeypatch.setattr(
        future_data_audit,
        "audit_live",
        lambda settings, expected_team_count: (_ for _ in ()).throw(
            ConnectionError("network unavailable")
        ),
    )
    assert future_data_audit.main(["--expected-team-count", "14"]) == 2
    assert "network unavailable" in capsys.readouterr().err


def test_live_audit_wraps_malformed_library_response(monkeypatch) -> None:
    class MalformedLeague:
        def __init__(self, **kwargs):
            raise KeyError("status")

    monkeypatch.setattr(future_data_audit, "League", MalformedLeague)
    settings = type(
        "Settings",
        (),
        {"league_id": 123, "season": 2026, "credentials": None},
    )()
    try:
        future_data_audit.audit_live(settings, expected_team_count=14)
    except future_data_audit.FutureDataAuditError as exc:
        assert "malformed or unsupported" in str(exc)
    else:
        raise AssertionError("Malformed response did not fail explicitly")
