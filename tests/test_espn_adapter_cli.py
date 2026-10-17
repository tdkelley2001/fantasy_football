from __future__ import annotations

from fantasy_football.config import Settings
from fantasy_football.espn_adapter import EspnAdapterError, main, translate_bundle
from tests.adapter_fixtures import source_bundle


def test_cli_success_emits_only_sanitized_aggregate_report(monkeypatch, capsys) -> None:
    result = translate_bundle(source_bundle())
    monkeypatch.setattr("fantasy_football.espn_adapter.load_settings", lambda: Settings(77, 2026, "INFO"))
    monkeypatch.setattr("fantasy_football.espn_adapter.fetch_and_translate", lambda *args, **kwargs: result)

    assert main(["--first-simulation-week", "2", "--json"]) == 0
    output = capsys.readouterr().out
    assert '"player_count": 5' in output
    assert "Sanitized Player" not in output
    assert "payload" not in output


def test_cli_failure_is_nonzero_and_contextual(monkeypatch, capsys) -> None:
    monkeypatch.setattr("fantasy_football.espn_adapter.load_settings", lambda: Settings(77, 2026, "INFO"))

    def fail(*args, **kwargs):
        raise EspnAdapterError("week=3 offset=4: terminal page missing")

    monkeypatch.setattr("fantasy_football.espn_adapter.fetch_and_translate", fail)
    assert main(["--first-simulation-week", "2"]) == 2
    assert "week=3 offset=4" in capsys.readouterr().err
