from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "cursor_agents_api.py"
load_dotenv()


class Handler(BaseHTTPRequestHandler):
    seen: list[dict[str, str]] = []

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        Handler.seen.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization", ""),
            }
        )
        if self.path == "/v1/models":
            self._json({"items": [{"id": "default", "displayName": "Auto"}]})
            return
        if self.path == "/v1/agents/agent-1/runs?limit=7":
            self._json({"items": [{"id": "run-1"}]})
            return
        if self.path == "/v1/agents/agent-1/usage?runId=run-1":
            self._json({"totalCents": 3})
            return
        self._json({"error": "not found", "path": self.path}, status=404)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        Handler.seen.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization", ""),
            }
        )
        self._json({"ok": True})

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def server_url() -> tuple[str, ThreadingHTTPServer]:
    Handler.seen.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_port}", server


def run_cli(args: list[str], base_url: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CURSOR_API_KEY"] = "test-key"
    env["CURSOR_API_BASE_URL"] = base_url
    env["PYTHONPATH"] = str(SKILL_DIR)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=SKILL_DIR,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_models_uses_basic_auth_and_writes_receipt(tmp_path: Path) -> None:
    base_url, server = server_url()
    receipt = tmp_path / "receipt.json"
    try:
        result = run_cli(["models", "--json", "--receipt", str(receipt)], base_url, tmp_path)
    finally:
        server.shutdown()

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["items"][0]["id"] == "default"
    saved = json.loads(receipt.read_text())
    assert saved["ok"] is True
    assert saved["path"] == "/v1/models"
    assert saved["credential_env"] == "CURSOR_API_KEY"
    assert "test-key" not in receipt.read_text()

    auth = Handler.seen[0]["authorization"]
    assert auth.startswith("Basic ")
    assert base64.b64decode(auth.removeprefix("Basic ")).decode() == "test-key:"


def test_runs_and_usage_build_documented_paths(tmp_path: Path) -> None:
    base_url, server = server_url()
    try:
        runs_result = run_cli(["runs", "agent-1", "--limit", "7", "--json"], base_url, tmp_path)
        usage_result = run_cli(
            ["usage", "agent-1", "--run-id", "run-1", "--json"],
            base_url,
            tmp_path,
        )
    finally:
        server.shutdown()

    assert runs_result.returncode == 0, runs_result.stderr
    assert usage_result.returncode == 0, usage_result.stderr
    assert [entry["path"] for entry in Handler.seen] == [
        "/v1/agents/agent-1/runs?limit=7",
        "/v1/agents/agent-1/usage?runId=run-1",
    ]


def test_raw_mutation_requires_explicit_yes(tmp_path: Path) -> None:
    base_url, server = server_url()
    try:
        result = run_cli(["raw", "POST", "/v1/agents", "--data", "{}"], base_url, tmp_path)
    finally:
        server.shutdown()

    assert result.returncode == 2
    assert "requires --yes" in result.stderr
    assert Handler.seen == []


def test_raw_rejects_non_v1_path(tmp_path: Path) -> None:
    base_url, server = server_url()
    try:
        result = run_cli(["raw", "GET", "/teams/members"], base_url, tmp_path)
    finally:
        server.shutdown()

    assert result.returncode == 2
    assert "Use a documented /v1/..." in result.stderr
