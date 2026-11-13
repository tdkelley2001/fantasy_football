import json
import re
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from fantasy_football.config import Settings, SettingsError
from fantasy_football.m0_verification import (
    DIAGNOSTICS,
    EVIDENCE_DOCUMENTS,
    EVIDENCE_ROLES,
    M0VerificationError,
    build_report,
    main,
    render_summary,
)


def evidence_tree(root: Path) -> None:
    for relative in EVIDENCE_DOCUMENTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        source = Path(__file__).resolve().parents[1] / relative
        path.write_bytes(source.read_bytes())


def test_build_report_distinguishes_recorded_evidence_from_live_verification(
    tmp_path: Path,
) -> None:
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


def test_configuration_check_records_identity_without_live_claim(
    tmp_path: Path,
) -> None:
    evidence_tree(tmp_path)
    settings = Settings(league_id=42, season=2026, log_level="INFO", credentials=None)
    report = build_report(tmp_path, check_config=True, settings_loader=lambda: settings)

    assert report.configuration_checked is True
    assert report.live_verification_performed is False


def test_main_returns_nonzero_for_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence_tree(tmp_path)

    def fail() -> Settings:
        raise SettingsError("invalid test configuration")

    monkeypatch.setattr("fantasy_football.m0_verification.load_settings", fail)
    assert main(["--project-root", str(tmp_path), "--check-config"]) == 2


def test_main_normal_json_invocation(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    evidence_tree(tmp_path)
    assert main(["--project-root", str(tmp_path), "--json"]) == 0
    output = capsys.readouterr().out
    assert '"live_verification_performed": false' in output
    assert '"regular_matchup_tie_behavior"' in output


def edit_contract(root: Path, change) -> None:
    path = root / "docs/DATA.md"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(```json m0-evidence\n)(.*?)(\n```)", text, re.DOTALL)
    assert match is not None
    contract = json.loads(match[2])
    change(contract)
    path.write_text(
        text[: match.start(2)] + json.dumps(contract, indent=2) + text[match.end(2) :],
        encoding="utf-8",
    )


@pytest.mark.parametrize("document", EVIDENCE_DOCUMENTS)
def test_each_authoritative_document_is_required(tmp_path: Path, document: str) -> None:
    evidence_tree(tmp_path)
    (tmp_path / document).unlink()
    with pytest.raises(M0VerificationError, match=re.escape(document)):
        build_report(tmp_path)


@pytest.mark.parametrize(
    "reference", sorted({ref for role in EVIDENCE_ROLES for ref in role.sections})
)
def test_each_role_requires_its_mapped_section(tmp_path: Path, reference: str) -> None:
    evidence_tree(tmp_path)
    path, anchor = reference.split("#")
    document = tmp_path / path
    text = document.read_text(encoding="utf-8")
    title = next(
        line
        for line in text.splitlines()
        if line.startswith("#")
        and re.sub(r"[^\w -]", "", line.lstrip("# ").lower()).replace(" ", "-")
        == anchor
    )
    document.write_text(
        text.replace(title, "## Removed required section", 1), encoding="utf-8"
    )
    with pytest.raises(
        M0VerificationError, match="requires nonempty section|role contract missing"
    ):
        build_report(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c["roles"].pop(),
        lambda c: c["roles"].append(c["roles"][0]),
        lambda c: c["roles"][0].update(role="unknown"),
        lambda c: c["roles"][0].update(sections=c["roles"][1]["sections"]),
        lambda c: c["roles"][0].update(interfaces=c["roles"][1]["interfaces"]),
        lambda c: c["roles"][0].update(
            historical_reference="https://github.com/tdkelley2001/fantasy_football/blob/main/docs/ESPN_CONNECTIVITY.md"
        ),
        lambda c: c["roles"][0].update(historical_sha256="0" * 64),
        lambda c: c.update(schema_version=True),
        lambda c: c["roles"][0].update(live_verification_performed=True),
    ],
)
def test_invalid_role_sets_mappings_and_historical_identities_fail_closed(
    tmp_path: Path, mutation
) -> None:
    evidence_tree(tmp_path)
    edit_contract(tmp_path, mutation)
    with pytest.raises(M0VerificationError, match="M0 evidence role"):
        build_report(tmp_path)


@pytest.mark.parametrize("module", [row[1] for row in DIAGNOSTICS])
def test_missing_diagnostic_modules_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: str
) -> None:
    import fantasy_football.m0_verification as m0

    evidence_tree(tmp_path)
    find_spec = m0.importlib.util.find_spec
    monkeypatch.setattr(
        m0.importlib.util,
        "find_spec",
        lambda name: None if name == module else find_spec(name),
    )
    with pytest.raises(
        M0VerificationError,
        match=re.escape(f"M0 diagnostic modules are unavailable: {module}"),
    ):
        build_report(tmp_path)


def test_missing_implementation_definition_is_not_module_availability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fantasy_football.m0_verification as m0

    evidence_tree(tmp_path)
    module = tmp_path / "available_but_wrong.py"
    module.write_text("def unrelated(): pass\n", encoding="utf-8")
    find_spec = m0.importlib.util.find_spec
    monkeypatch.setattr(
        m0.importlib.util,
        "find_spec",
        lambda name: (
            SimpleNamespace(origin=str(module))
            if name == "fantasy_football.espn_connectivity"
            else find_spec(name)
        ),
    )
    with pytest.raises(
        M0VerificationError,
        match="interface definition unavailable: fantasy_football.espn_connectivity:audit_league",
    ):
        build_report(tmp_path)


def test_fenced_fake_headings_and_empty_sections_cannot_supply_evidence(
    tmp_path: Path,
) -> None:
    evidence_tree(tmp_path)
    path = tmp_path / "docs/RESEARCH.md"
    text = path.read_text(encoding="utf-8")
    start = text.index("## Coverage and leakage")
    end = text.index("## Temporal evaluation", start)
    fake = "## Coverage and leakage\n\n```text\n## Coverage and leakage\nforged evidence\n```\n\n"
    path.write_text(text[:start] + fake + text[end:], encoding="utf-8")
    with pytest.raises(
        M0VerificationError, match="historical_projections requires nonempty section"
    ):
        build_report(tmp_path)


def test_role_register_detached_from_owning_section_is_rejected(tmp_path: Path) -> None:
    evidence_tree(tmp_path)
    path = tmp_path / "docs/DATA.md"
    text = path.read_text(encoding="utf-8")
    block = re.search(r"```json m0-evidence\n.*?\n```", text, re.DOTALL)[0]
    path.write_text(
        text.replace(block, "") + "\n## Detached\n" + block, encoding="utf-8"
    )
    with pytest.raises(M0VerificationError, match="role contract missing or ambiguous"):
        build_report(tmp_path)


def test_duplicate_json_fields_and_duplicate_anchors_are_rejected(
    tmp_path: Path,
) -> None:
    evidence_tree(tmp_path)
    path = tmp_path / "docs/DATA.md"
    original = path.read_text(encoding="utf-8")
    path.write_text(
        original.replace(
            '"schema_version": 1,', '"schema_version": 1, "schema_version": 1,'
        ),
        encoding="utf-8",
    )
    with pytest.raises(M0VerificationError, match="invalid JSON"):
        build_report(tmp_path)
    path.write_text(
        original + "\n## Projection contract\nDuplicate\n", encoding="utf-8"
    )
    with pytest.raises(M0VerificationError, match="ambiguous section anchors"):
        build_report(tmp_path)


def test_historical_identity_never_claims_offline_content_authentication(
    tmp_path: Path,
) -> None:
    evidence_tree(tmp_path)
    assert not (tmp_path / ".git").exists()
    # Even an incidental file with a retired name must not become an implicit fallback.
    (tmp_path / "docs/ESPN_CONNECTIVITY.md").write_text(
        "forged historical bytes", encoding="utf-8"
    )
    report = build_report(tmp_path)
    assert report.evidence_documents == EVIDENCE_DOCUMENTS
    historical = [row for row in report.evidence_roles if row["historical_reference"]]
    assert len(historical) == 6
    assert all(row["historical_identity_verified"] for row in historical)
    assert all(
        row["historical_content_verified"] is False for row in report.evidence_roles
    )
    assert all(
        row["historical_content_status"] == "not_inspected_or_authenticated_offline"
        for row in historical
    )
    assert all(
        row["live_verification_performed"] is False for row in report.evidence_roles
    )
    assert "not current ESPN compatibility or release readiness" in render_summary(
        report
    )


def test_record_order_and_markdown_emphasis_do_not_change_report(
    tmp_path: Path,
) -> None:
    evidence_tree(tmp_path)
    expected = build_report(tmp_path).to_dict()
    edit_contract(tmp_path, lambda c: c["roles"].reverse())
    path = tmp_path / "docs/DATA.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "## Retrieval and provenance", "## **Retrieval and provenance**"
        ),
        encoding="utf-8",
    )
    assert build_report(tmp_path).to_dict() == expected


def test_default_and_json_are_stable_offline_without_credentials_or_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import subprocess

    import requests

    import fantasy_football.m0_verification as m0

    evidence_tree(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "network, subprocess, credentials or diagnostics must not execute"
        )

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(m0, "load_settings", forbidden)
    for name, module, command, private in DIAGNOSTICS:
        if module != "fantasy_football":
            import importlib

            monkeypatch.setattr(importlib.import_module(module), "main", forbidden)
    expected = build_report(tmp_path)
    for _ in range(2):
        assert main(["--project-root", str(tmp_path)]) == 0
        assert capsys.readouterr().out == render_summary(expected) + "\n"
        assert main(["--project-root", str(tmp_path), "--json"]) == 0
        output = capsys.readouterr().out
        assert json.loads(output) == json.loads(json.dumps(expected.to_dict()))
    assert (
        expected.evidence_state
        == "recorded_historical_evidence_plus_credential_free_manifest_check"
    )
    assert expected.credential_free_test_command == "python -m pytest"
    assert expected.evidence_role_contract_version == 1


def test_untrusted_evidence_values_and_config_exception_are_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    evidence_tree(tmp_path)
    secret = "synthetic-secret-do-not-echo"
    edit_contract(tmp_path, lambda c: c["roles"][0].update(historical_reference=secret))
    assert main(["--project-root", str(tmp_path)]) == 2
    assert secret not in caplog.text
    assert "mapping or historical identity mismatch: connectivity" in caplog.text
    evidence_tree(tmp_path)

    def fail():
        raise SettingsError(secret)

    monkeypatch.setattr("fantasy_football.m0_verification.load_settings", fail)
    assert main(["--project-root", str(tmp_path), "--check-config"]) == 2
    assert secret not in caplog.text
    assert "optional configuration validation failed" in caplog.text


@pytest.mark.parametrize("role", EVIDENCE_ROLES, ids=lambda role: role.role)
def test_each_role_is_required_once(tmp_path: Path, role) -> None:
    evidence_tree(tmp_path)
    edit_contract(
        tmp_path,
        lambda c: c.update(roles=[r for r in c["roles"] if r["role"] != role.role]),
    )
    with pytest.raises(M0VerificationError, match="all seven roles exactly once"):
        build_report(tmp_path)


@pytest.mark.parametrize("role", EVIDENCE_ROLES, ids=lambda role: role.role)
def test_declared_evidence_limits_cannot_be_upgraded(tmp_path: Path, role) -> None:
    evidence_tree(tmp_path)

    def upgrade(contract):
        row = next(row for row in contract["roles"] if row["role"] == role.role)
        row["evidence_limits"] = {
            key: "Verified live" for key in row["evidence_limits"]
        }

    edit_contract(tmp_path, upgrade)
    with pytest.raises(M0VerificationError, match=f"identity mismatch: {role.role}"):
        build_report(tmp_path)


@pytest.mark.parametrize("source", [b"def malformed(:", b"\xff", None])
def test_uninspectable_interface_source_fails_safely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source
) -> None:
    import fantasy_football.m0_verification as m0

    evidence_tree(tmp_path)
    path = tmp_path / "synthetic-private-module.py"
    if source is not None:
        path.write_bytes(source)
    find_spec = m0.importlib.util.find_spec
    monkeypatch.setattr(
        m0.importlib.util,
        "find_spec",
        lambda name: (
            SimpleNamespace(origin=str(path))
            if name == "fantasy_football.espn_adapter"
            else find_spec(name)
        ),
    )
    with pytest.raises(
        M0VerificationError,
        match="interface source unavailable: fantasy_football.espn_adapter:load_manual_rule_config",
    ) as error:
        build_report(tmp_path)
    assert str(path) not in str(error.value)


def test_function_cannot_impersonate_a_canonical_record_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fantasy_football.m0_verification as m0

    evidence_tree(tmp_path)
    path = tmp_path / "wrong_record.py"
    path.write_text("def SourceReference(): pass\n", encoding="utf-8")
    find_spec = m0.importlib.util.find_spec
    monkeypatch.setattr(
        m0.importlib.util,
        "find_spec",
        lambda name: (
            SimpleNamespace(origin=str(path))
            if name == "fantasy_football.canonical.model"
            else find_spec(name)
        ),
    )
    with pytest.raises(
        M0VerificationError,
        match="definition unavailable: fantasy_football.canonical.model:SourceReference.payload_sha256",
    ):
        build_report(tmp_path)


def test_optional_configuration_success_is_checked_once_without_identity_disclosure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import fantasy_football.m0_verification as m0

    evidence_tree(tmp_path)
    calls = []

    def settings():
        calls.append("settings")
        return Settings(league_id=42, season=2026, log_level="INFO", credentials=None)

    monkeypatch.setattr(m0, "load_settings", settings)
    monkeypatch.setattr(m0, "configure_logging", lambda level: calls.append(level))
    monkeypatch.chdir(tmp_path)
    assert main(["--check-config", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["configuration_checked"] is True
    assert result["live_verification_performed"] is False
    assert "league_id" not in result
    assert calls == ["settings", "INFO"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [("{", "is invalid JSON"), ("[]", "has invalid schema or fields")],
    ids=["malformed-json", "wrong-root-type"],
)
def test_malformed_json_or_schema_is_a_sanitized_domain_failure(
    tmp_path: Path, payload: str, message: str
) -> None:
    evidence_tree(tmp_path)
    path = tmp_path / "docs/DATA.md"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(```json m0-evidence\n)(.*?)(\n```)", text, re.DOTALL)
    path.write_text(
        text[: match.start(2)] + payload + text[match.end(2) :], encoding="utf-8"
    )
    with pytest.raises(M0VerificationError, match=f"role contract {message}"):
        build_report(tmp_path)


def test_json_recursion_failure_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fantasy_football.m0_verification as m0

    evidence_tree(tmp_path)

    def exhausted(*args, **kwargs):
        raise RecursionError("synthetic private parser detail")

    monkeypatch.setattr(m0.json, "loads", exhausted)
    with pytest.raises(
        M0VerificationError, match="role contract is invalid JSON"
    ) as error:
        build_report(tmp_path)
    assert "private parser detail" not in str(error.value)


def test_numeric_zero_cannot_impersonate_false_in_evidence_limits(
    tmp_path: Path,
) -> None:
    evidence_tree(tmp_path)

    def alter(contract):
        row = next(row for row in contract["roles"] if row["role"] == "m0_handoff")
        row["evidence_limits"]["live_verification"] = 0

    edit_contract(tmp_path, alter)
    with pytest.raises(M0VerificationError, match="identity mismatch: m0_handoff"):
        build_report(tmp_path)
