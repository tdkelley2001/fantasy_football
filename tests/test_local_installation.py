from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

import pytest
from fastapi.testclient import TestClient

from fantasy_football.app.http import create_app
from fantasy_football.app.server import LOOPBACK_HOST, main

ROOT = Path(__file__).resolve().parents[1]


def _frontend(path: Path) -> Path:
    (path / "assets").mkdir(parents=True)
    (path / "index.html").write_text("<main id='root'>War Room</main>", encoding="utf-8")
    (path / "assets" / "app.js").write_text("window.warRoom=true", encoding="utf-8")
    return path


def _port() -> int:
    with socket.socket() as listener:
        listener.bind((LOOPBACK_HOST, 0))
        return listener.getsockname()[1]


def test_production_frontend_routes_are_isolated_from_api(tmp_path: Path) -> None:
    frontend = _frontend(tmp_path / "built frontend")
    with TestClient(
        create_app(database_path=tmp_path / "private.sqlite3", frontend_directory=frontend)
    ) as client:
        assert client.get("/").text == "<main id='root'>War Room</main>"
        assert client.get("/simulation-center").status_code == 200
        asset = client.get("/assets/app.js")
        assert asset.status_code == 200
        assert "javascript" in asset.headers["content-type"]
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/assets/%2e%2e/index.html").status_code == 404
        assert client.get("/missing.js").status_code == 404
        invalid_api = client.get("/api/v1/not-real")
        assert invalid_api.status_code == 404
        assert invalid_api.headers["content-type"].startswith("application/json")
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_frontend_build_validation_fails_before_serving(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Production frontend build is incomplete"):
        create_app(database_path=tmp_path / "db.sqlite3", frontend_directory=tmp_path / "absent")


def test_server_rejects_non_loopback_configuration_and_bad_shutdown_pair() -> None:
    assert LOOPBACK_HOST == "127.0.0.1"
    with pytest.raises(SystemExit):
        main(["--shutdown-file", "request.txt"])


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell launcher is Windows-specific")
def test_launcher_start_stop_restart_and_persistence(tmp_path: Path) -> None:
    frontend = _frontend(tmp_path / "frontend assets")
    database = tmp_path / "persisted data" / "league.sqlite3"
    logs = tmp_path / "runtime logs"
    port = _port()
    start = ROOT / "scripts" / "start-local.ps1"
    stop = ROOT / "scripts" / "stop-local.ps1"
    common = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(start),
        "-Port", str(port), "-Database", str(database), "-Frontend", str(frontend),
        "-LogDirectory", str(logs), "-PythonExecutable", sys.executable, "-NoBrowser",
        "-ReadinessTimeoutSeconds", "20",
    ]
    try:
        first = subprocess.run(
            common, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30,
        )
        assert first.returncode == 0
        with urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
            assert b"War Room" in response.read()
        with urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=5) as response:
            assert json.load(response)["api_schema_version"] == "1.0"
        database.parent.mkdir(parents=True, exist_ok=True)
        marker = database.parent / "persistence-marker.txt"
        marker.write_text("preserve", encoding="utf-8")

        duplicate = subprocess.run(
            common, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=15,
        )
        assert duplicate.returncode == 0

        stopped = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(stop)],
            cwd=ROOT, text=True, capture_output=True, timeout=30,
        )
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr
        assert marker.read_text(encoding="utf-8") == "preserve"

        restarted = subprocess.run(
            common, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30,
        )
        assert restarted.returncode == 0
    finally:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(stop)],
            cwd=ROOT, text=True, capture_output=True, timeout=30,
        )


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell launcher is Windows-specific")
def test_launcher_does_not_take_over_occupied_port(tmp_path: Path) -> None:
    port = _port()
    listener = socket.socket()
    listener.bind((LOOPBACK_HOST, port))
    listener.listen()
    try:
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(ROOT / "scripts" / "start-local.ps1"), "-Port", str(port),
                "-Database", str(tmp_path / "db.sqlite3"), "-Frontend",
                str(_frontend(tmp_path / "front")), "-LogDirectory", str(tmp_path / "logs"),
                "-PythonExecutable", sys.executable, "-NoBrowser",
            ],
            cwd=ROOT, text=True, capture_output=True, timeout=15,
        )
        assert result.returncode != 0
        assert "not owned by this launcher" in result.stderr
    finally:
        listener.close()
