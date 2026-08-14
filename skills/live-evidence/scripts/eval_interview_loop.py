#!/usr/bin/env python3
"""Exercise the interview question-to-card loop through the local HTTP API."""

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
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(override=False)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def post_turn(client: httpx.Client, *, speaker: str, text: str, sequence: int) -> None:
    response = client.post(
        "/api/transcript",
        json={
            "schema": "live_evidence.transcript_event.v1",
            "speaker": speaker,
            "kind": "final",
            "source": "api",
            "sequence": sequence,
            "text": text,
        },
    )
    response.raise_for_status()


def wait_for_cards(client: httpx.Client, count: int, *, timeout_s: float = 8.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get("/api/state")
        response.raise_for_status()
        last_state = response.json()
        if len(last_state.get("cards") or []) >= count:
            return last_state
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for {count} cards; last_state={last_state}")


def assert_card(
    card: dict[str, Any],
    *,
    status: str,
    path_fragment: str | None = None,
    lane: str | None = None,
) -> None:
    if card.get("status") != status:
        raise RuntimeError(f"expected card status {status!r}, got {card}")
    sources = card.get("sources") or []
    if status == "supported" and not sources:
        raise RuntimeError(f"supported card has no sources: {card}")
    if lane and not any(source.get("lane") == lane for source in sources):
        raise RuntimeError(f"card missing {lane} source: {card}")
    if path_fragment and not any(path_fragment in str(source.get("path")) for source in sources):
        raise RuntimeError(f"card missing source path fragment {path_fragment!r}: {card}")


def write_profile(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: interview-loop-eval",
                "watch_terms:",
                "  - interview",
                "  - evidence-loop",
                "  - realtime-card-sorting",
                "project_aliases:",
                "  evalrepo:",
                "    - evidence-loop",
                "    - ambient hud",
                "    - memory vault",
                "    - realtime-card-sorting",
                "repo_priorities:",
                "  - evalrepo",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    with tempfile.TemporaryDirectory(prefix="live-evidence-interview-eval-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "evalrepo"
        source_dir = repo / "src"
        source_dir.mkdir(parents=True)
        (source_dir / "interview_evidence.py").write_text(
            "def evidence_loop():\n"
            "    return 'evidence-loop routes interviewer questions into ambient hud cards and memory vault records'\n",
            encoding="utf-8",
        )
        profile_path = temp / "profile.yaml"
        write_profile(profile_path)
        data_dir = temp / "data"
        port = free_port()
        env = {
            **os.environ,
            "LIVE_EVIDENCE_REPOS": str(repo),
            "LIVE_EVIDENCE_DATA_DIR": str(data_dir),
            "LIVE_EVIDENCE_PROFILE": str(profile_path),
            "LIVE_EVIDENCE_HTTP_TIMEOUT": "0.3",
            "LIVE_EVIDENCE_PROCESS_TIMEOUT": "3",
            "LIVE_EVIDENCE_MAX_CARDS": "5",
            "MEMORY_SERVICE_URL": "http://127.0.0.1:9",
        }
        log_path = temp / "server.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "live_evidence", "serve", "--host", "127.0.0.1", "--port", str(port), "--no-browser"],
                cwd=root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=3.0) as client:
                for _ in range(60):
                    try:
                        if client.get("/api/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"server did not start; log={log_path.read_text()}")
                client.post("/api/session/start", json={"consent_confirmed": True}).raise_for_status()

                post_turn(
                    client,
                    speaker="graham",
                    sequence=1,
                    text="I built the evidence-loop so the ambient hud stays compact during interviews.",
                )
                time.sleep(0.4)
                if client.get("/api/state").json().get("cards"):
                    raise RuntimeError("Graham candidate turn triggered retrieval")
                print("graham turns do not trigger retrieval: PASS")

                post_turn(
                    client,
                    speaker="interviewer",
                    sequence=2,
                    text="How does the evidence-loop put interviewer questions into ambient hud cards?",
                )
                state = wait_for_cards(client, 1)
                assert_card(state["cards"][0], status="supported", path_fragment="interview_evidence.py", lane="ripgrep")
                print("existing code evidence card: PASS")

                (source_dir / "new_code_path.ts").write_text(
                    "export const realtimeCardSorting = 'realtime-card-sorting keeps new code visible as interview cards';\n",
                    encoding="utf-8",
                )
                post_turn(
                    client,
                    speaker="interviewer",
                    sequence=3,
                    text="Where does realtime-card-sorting make newly written code visible during the interview?",
                )
                state = wait_for_cards(client, 2)
                assert_card(state["cards"][0], status="supported", path_fragment="new_code_path.ts", lane="ripgrep")
                print("new code evidence card: PASS")

                post_turn(
                    client,
                    speaker="interviewer",
                    sequence=4,
                    text="How should quasar checksum banana-scheduler prove an unrelated algorithm?",
                )
                state = wait_for_cards(client, 3)
                assert_card(state["cards"][0], status="insufficient")
                print("unsupported question fail-closed: PASS")

                for index in range(6):
                    term = f"bounded-card-{index}"
                    (source_dir / f"{term}.md").write_text(
                        f"{term} evidence-loop cards stay bounded for realtime scanning.\n",
                        encoding="utf-8",
                    )
                    post_turn(
                        client,
                        speaker="interviewer",
                        sequence=10 + index,
                        text=f"How does {term} keep evidence-loop cards bounded for realtime scanning?",
                    )
                    wait_for_cards(client, min(5, 4 + index))
                final_state = client.get("/api/state").json()
                cards = final_state.get("cards") or []
                if len(cards) > 5:
                    raise RuntimeError(f"card queue exceeded realtime cap: {len(cards)}")
                if any(len(card.get("sources") or []) > 8 for card in cards):
                    raise RuntimeError("card source list exceeded scannable bound")
                print("card queue bounded for realtime scanning: PASS")

                receipt = {
                    "schema": "live_evidence.interview_loop_eval_receipt.v1",
                    "status": "PASS",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "mocked": False,
                    "live": False,
                    "fixture_backed": False,
                    "checks": {
                        "local_http_api": True,
                        "interviewer_question_trigger": True,
                        "graham_turn_suppressed": True,
                        "existing_code_card": True,
                        "new_code_card": True,
                        "unsupported_fail_closed": True,
                        "bounded_card_queue": True,
                    },
                    "card_count": len(cards),
                }
                receipt_dir = Path(os.getenv("LIVE_EVIDENCE_DATA_DIR", str(data_dir)))
                receipt_dir.mkdir(parents=True, exist_ok=True)
                receipt_path = receipt_dir / "interview-loop-eval-receipt.json"
                receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                shutil.copy2(receipt_path, Path("/tmp/live-evidence-interview-loop-eval-receipt.json"))
                print(f"interview loop receipt: {receipt_path}")
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
