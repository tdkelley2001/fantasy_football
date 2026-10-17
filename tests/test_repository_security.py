from __future__ import annotations

from pathlib import Path
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_local_env_file_is_ignored() -> None:
    result = _git("check-ignore", ".env")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ".env"


def test_no_local_env_file_is_tracked() -> None:
    result = _git("ls-files", ".env", ".env.*")

    assert result.returncode == 0, result.stderr
    assert ".env" not in result.stdout.splitlines()
    assert set(result.stdout.splitlines()) <= {".env.example"}

    example = REPOSITORY_ROOT / ".env.example"
    assert example.is_file()
    ignored_example = _git("check-ignore", ".env.example")
    assert ignored_example.returncode == 1


def test_local_league_rule_configuration_is_ignored() -> None:
    result = _git("check-ignore", "config/league_rules.local.yaml")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "config/league_rules.local.yaml"
