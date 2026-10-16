from pathlib import Path

import pytest

from fantasy_football.config import Settings, SettingsError
from fantasy_football.m0_verification import (
    EVIDENCE_DOCUMENTS,
    M0VerificationError,
    build_report,
    main,
)


def evidence_tree(root: Path) -> None:
    for relative in EVIDENCE_DOCUMENTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("sanitized evidence\n", encoding="utf-8")


def test_build_report_distinguishes_recorded_evidence_from_live_verification(tmp_path: Path) -> None:
    evidence_tree(tmp_path)
    report = build_report(tmp_path)

    assert report.live_verification_performed is False
    assert report.configuration_checked is False
    assert report.m1_gate == "GO_WITH_EXPLICIT_UNRESOLVED_METADATA"
    assert all(row["executed_by_this_command"] is False for row in report.diagnostics)
    assert "current_eight_team_consolation_ladder" in report.unresolved_rules


def test_build_report_fails_with_specific_missing_evidence(tmp_path: Path) -> None:
    evidence_tree(tmp_path)
    missing = tmp_path / EVIDENCE_DOCUMENTS[0]
    missing.unlink()

    with pytest.raises(M0VerificationError, match=EVIDENCE_DOCUMENTS[0]):
        build_report(tmp_path)


def test_configuration_check_records_identity_without_live_claim(tmp_path: Path) -> None:
    evidence_tree(tmp_path)
    settings = Settings(league_id=42, season=2026, log_level="INFO", credentials=None)
    report = build_report(tmp_path, check_config=True, settings_loader=lambda: settings)

    assert report.configuration_checked is True
    assert report.live_verification_performed is False


def test_main_returns_nonzero_for_invalid_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    evidence_tree(tmp_path)

    def fail() -> Settings:
        raise SettingsError("invalid test configuration")

    monkeypatch.setattr("fantasy_football.m0_verification.load_settings", fail)
    assert main(["--project-root", str(tmp_path), "--check-config"]) == 2


def test_main_normal_json_invocation(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    evidence_tree(tmp_path)
    assert main(["--project-root", str(tmp_path), "--json"]) == 0
    output = capsys.readouterr().out
    assert '"live_verification_performed": false' in output
    assert '"regular_matchup_tie_behavior"' in output
