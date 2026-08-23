#!/usr/bin/env python3
"""Transparent proof: start the real server, post a real question, print the
card VERBATIM. Same mechanism as sanity_live.py, but pointed at the real Sparta
repo and live Graph Memory (:8601). No assertions, no PASS/FAIL -- just the raw
card the running product produced, so a human can read it directly."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main() -> int:
    import tempfile

    key = os.environ.get("SCILLM_MASTER_KEY") or os.environ.get("LIVE_EVIDENCE_SCILLM_KEY", "")
    question = (sys.argv[1] if len(sys.argv) > 1
                else "What are the hard read first rules recorded in the Sparta project memory index?")
    data = Path(tempfile.mkdtemp(prefix="le-proof-"))
    port = free_port()
    env = {
        **os.environ,
        "LIVE_EVIDENCE_REPOS": str(Path.home() / "workspace" / "experiments" / "sparta"),
        "LIVE_EVIDENCE_DATA_DIR": str(data),
        "LIVE_EVIDENCE_PROFILE": str(ROOT / "config" / "default.yaml"),
        "MEMORY_SERVICE_URL": "http://127.0.0.1:8601",
        "LIVE_EVIDENCE_SCILLM_KEY": key,
        "PYTHONPATH": str(ROOT / "src"),
    }
    log = (data / "server.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "live_evidence", "serve", "--host", "127.0.0.1",
         "--port", str(port), "--no-browser"],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
    print(f"### real server: {' '.join(proc.args)}")
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5.0) as client:
            for _ in range(120):
                try:
                    if client.get("/api/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            else:
                print("server did not start; log:\n", (data / "server.log").read_text()[-1500:])
                return 1
            client.post("/api/session/start", json={"consent_confirmed": True}).raise_for_status()
            print(f"### posted question: {question}")
            client.post("/api/transcript", json={
                "schema": "live_evidence.transcript_event.v1", "speaker": "interviewer",
                "kind": "final", "source": "demo", "text": question}).raise_for_status()
            card = None
            for _ in range(90):
                cards = (client.get("/api/state").json().get("cards") or [])
                real = [c for c in cards if (c.get("answer") or "").strip()
                        and c.get("answer") != "No source-bound support surfaced yet."]
                if real:
                    card = real[0]
                    break
                time.sleep(1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("\n===== RAW CARD from the running server =====")
    if not card:
        print("NO CARD PRODUCED")
        return 1
    print("QUERY :", card.get("query"))
    print("STATUS:", card.get("status"))
    print("ANSWER:", card.get("answer"))
    print("SOURCES:")
    for s in card.get("sources") or []:
        loc = s.get("path") or (s.get("metadata") or {}).get("_key") or s.get("url") or "(generated)"
        print(f"   [{s.get('lane')}] {loc}")
        print(f"       {(s.get('excerpt') or '')[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
