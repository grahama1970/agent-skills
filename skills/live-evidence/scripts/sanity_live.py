#!/usr/bin/env python3
"""Run a non-mocked local HTTP + ripgrep evidence canary."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(override=False)


def free_port() -> int:
    """Reserve and release a loopback port for the canary server."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    with tempfile.TemporaryDirectory(prefix="live-evidence-sanity-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "tau"
        repo.mkdir()
        shutil.copy2(root / "fixtures" / "repo" / "tau" / "README.md", repo / "README.md")
        data_dir = temp / "data"
        port = free_port()
        env = {
            **os.environ,
            "LIVE_EVIDENCE_REPOS": str(repo),
            "LIVE_EVIDENCE_DATA_DIR": str(data_dir),
            "LIVE_EVIDENCE_PROFILE": str(root / "config" / "default.yaml"),
            "LIVE_EVIDENCE_HTTP_TIMEOUT": "0.3",
            "LIVE_EVIDENCE_PROCESS_TIMEOUT": "3",
            "MEMORY_SERVICE_URL": "http://127.0.0.1:9",
        }
        log_path = temp / "server.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "live_evidence",
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-browser",
                ],
                cwd=root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        base_url = f"http://127.0.0.1:{port}"
        try:
            with httpx.Client(base_url=base_url, timeout=3.0) as client:
                for _ in range(60):
                    try:
                        response = client.get("/api/health")
                        if response.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"server did not start; log={log_path.read_text()}")

                start = client.post("/api/session/start", json={"consent_confirmed": True})
                start.raise_for_status()
                event = {
                    "schema": "live_evidence.transcript_event.v1",
                    "speaker": "interviewer",
                    "kind": "final",
                    "source": "demo",
                    "text": "How does Tau use receipt admission to prevent an agent from silently drifting during a long-running workflow?",
                }
                accepted = client.post("/api/transcript", json=event)
                accepted.raise_for_status()

                card = None
                state = None
                for _ in range(80):
                    state_response = client.get("/api/state")
                    state_response.raise_for_status()
                    state = state_response.json()
                    cards = state.get("cards") or []
                    if cards:
                        card = cards[0]
                        break
                    time.sleep(0.1)
                if card is None or state is None:
                    raise RuntimeError("no evidence card was produced")
                if card.get("status") != "supported":
                    raise RuntimeError(f"card was not supported: {card}")
                sources = card.get("sources") or []
                if not any(source.get("lane") == "ripgrep" for source in sources):
                    raise RuntimeError(f"real ripgrep source missing: {sources}")
                if not any("README.md" in str(source.get("path")) for source in sources):
                    raise RuntimeError(f"source locator missing: {sources}")

                receipt = {
                    "schema": "live_evidence.sanity_receipt.v1",
                    "status": "PASS",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "mocked": False,
                    "checks": {
                        "http_server": True,
                        "typed_transcript_event": True,
                        "background_retrieval": True,
                        "real_ripgrep": True,
                        "source_bound_card": True,
                        "memory_live": False,
                        "realtimestt_live": False,
                        "pipewire_live": False,
                        "external_search_live": False,
                    },
                    "card_id": card.get("card_id"),
                    "source_count": len(sources),
                }
                receipt_dir = Path(os.getenv("LIVE_EVIDENCE_DATA_DIR", str(data_dir)))
                receipt_dir.mkdir(parents=True, exist_ok=True)
                receipt_path = receipt_dir / "sanity-receipt.json"
                receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                print(f"live HTTP/ripgrep canary: PASS ({receipt_path})")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
