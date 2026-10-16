"""Offline M0 evidence manifest and reproduction guide.

This module verifies that the consolidated handoff references existing evidence and
diagnostics. It deliberately does not execute live ESPN requests or build M1 data.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import importlib.util
import json
import logging
from pathlib import Path
from typing import Callable, Sequence

from fantasy_football.config import Settings, SettingsError, load_settings
from fantasy_football.logging_config import configure_logging


LOGGER = logging.getLogger(__name__)

EVIDENCE_DOCUMENTS = (
    "docs/ESPN_CONNECTIVITY.md",
    "docs/ESPN_FUTURE_DATA_AUDIT.md",
    "docs/ESPN_LEAGUE_RULES_AUDIT.md",
    "docs/ESPN_HISTORICAL_PROJECTION_AUDIT.md",
    "docs/MISSING_PROJECTION_POLICY.md",
    "docs/ESPN_DATA_DICTIONARY.md",
    "docs/M0_FEASIBILITY_AND_M1_HANDOFF.md",
)

DIAGNOSTICS = (
    ("M0.1 configuration", "fantasy_football", "python -m fantasy_football", False),
    ("M0.2 connectivity", "fantasy_football.espn_connectivity", "python -m fantasy_football.espn_connectivity --expected-team-count <count>", True),
    ("M0.3 future data", "fantasy_football.future_data_audit", "python -m fantasy_football.future_data_audit --expected-team-count <count>", True),
    ("M0.4 league rules", "fantasy_football.league_rules_audit", "python -m fantasy_football.league_rules_audit [--expected-team-count <count>] [--historical-season <year>]", True),
    ("M0.5 history", "fantasy_football.historical_projection_audit", "python -m fantasy_football.historical_projection_audit --sample <season:week>", True),
)

UNRESOLVED_RULES = (
    "current_eight_team_consolation_ladder",
    "multiple_waiver_claim_processing",
    "regular_matchup_tie_behavior",
    "playoff_matchup_tie_behavior",
    "secondary_standings_tiebreaks",
    "dropped_player_waiver_reentry",
    "waiver_process_time_timezone_semantics",
    "trade_review_workflow",
)


class M0VerificationError(RuntimeError):
    """Raised when the checked-out M0 evidence set is incomplete."""


@dataclass(frozen=True, slots=True)
class M0VerificationReport:
    evidence_state: str
    live_verification_performed: bool
    configuration_checked: bool
    evidence_documents: tuple[str, ...]
    diagnostics: tuple[dict[str, object], ...]
    credential_free_test_command: str
    unresolved_rules: tuple[str, ...]
    m1_gate: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_report(
    project_root: Path,
    *,
    check_config: bool = False,
    settings_loader: Callable[[], Settings] = load_settings,
) -> M0VerificationReport:
    root = project_root.resolve()
    missing = [relative for relative in EVIDENCE_DOCUMENTS if not (root / relative).is_file()]
    if missing:
        raise M0VerificationError(f"M0 evidence documents are missing: {', '.join(missing)}")

    diagnostic_rows: list[dict[str, object]] = []
    unavailable = []
    for name, module, command, requires_credentials in DIAGNOSTICS:
        importable = importlib.util.find_spec(module) is not None
        if not importable:
            unavailable.append(module)
        diagnostic_rows.append({
            "name": name,
            "module": module,
            "command": command,
            "requires_private_credentials": requires_credentials,
            "executed_by_this_command": False,
            "module_available": importable,
        })
    if unavailable:
        raise M0VerificationError(f"M0 diagnostic modules are unavailable: {', '.join(unavailable)}")

    if check_config:
        settings_loader()
    return M0VerificationReport(
        evidence_state="recorded_historical_evidence_plus_credential_free_manifest_check",
        live_verification_performed=False,
        configuration_checked=check_config,
        evidence_documents=EVIDENCE_DOCUMENTS,
        diagnostics=tuple(diagnostic_rows),
        credential_free_test_command="python -m pytest",
        unresolved_rules=UNRESOLVED_RULES,
        m1_gate="GO_WITH_EXPLICIT_UNRESOLVED_METADATA",
    )


def render_summary(report: M0VerificationReport) -> str:
    lines = [
        "M0 consolidated verification manifest",
        f"Evidence: {report.evidence_state}",
        f"Live ESPN verification performed now: {report.live_verification_performed}",
        f"Configuration checked: {report.configuration_checked}",
        f"M1 gate: {report.m1_gate}",
        "",
        "Diagnostics (listed, not executed):",
    ]
    lines.extend(
        f"- {row['name']}: {row['command']} (credentials={row['requires_private_credentials']})"
        for row in report.diagnostics
    )
    lines.extend(("", "Credential-free verification:", f"- {report.credential_free_test_command}", "", "Unresolved rules:"))
    lines.extend(f"- {rule}" for rule in report.unresolved_rules)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify and print the consolidated M0 evidence manifest; no ESPN requests are made.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--check-config", action="store_true", help="Validate local configuration without making a network request.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.check_config:
            settings = load_settings()
            configure_logging(settings.log_level)
            report = build_report(args.project_root, check_config=True, settings_loader=lambda: settings)
        else:
            report = build_report(args.project_root)
    except (SettingsError, M0VerificationError) as exc:
        LOGGER.error("M0 verification failed: %s", exc)
        return 2
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True) if args.json else render_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
