from __future__ import annotations

from espn_api.requests.espn_requests import ESPNAccessDenied
from requests import ConnectionError

from fantasy_football import projection_ui_reconciliation


def _settings() -> object:
    return type("Settings", (), {"log_level": "INFO"})()


def test_cli_reports_authentication_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(projection_ui_reconciliation, "load_settings", _settings)
    monkeypatch.setattr(
        projection_ui_reconciliation,
        "reconcile_live",
        lambda settings, week: (_ for _ in ()).throw(
            ESPNAccessDenied("credentials rejected")
        ),
    )
    assert projection_ui_reconciliation.main([]) == 2
    assert "credentials rejected" in capsys.readouterr().err


def test_cli_reports_connectivity_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(projection_ui_reconciliation, "load_settings", _settings)
    monkeypatch.setattr(
        projection_ui_reconciliation,
        "reconcile_live",
        lambda settings, week: (_ for _ in ()).throw(
            ConnectionError("network unavailable")
        ),
    )
    assert projection_ui_reconciliation.main(["--week", "7"]) == 2
    assert "network unavailable" in capsys.readouterr().err
