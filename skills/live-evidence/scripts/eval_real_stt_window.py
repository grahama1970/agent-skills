#!/usr/bin/env python3
"""Replay the real-STT YouTube valid-parentheses window through Live Evidence."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(override=False)


YOUTUBE_URL = "https://youtu.be/c6zu897JVQY"
REALTIME_TEXT = (
    "What makes a parentheses string valid? A opening parentheses always has to come before closing, right? "
    "So if we sort of iterate to our string, each closing parenthesis needs a previous opening parenthesis."
)


def free_port() -> int:
    """Return an available localhost port for the eval server."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_profile(path: Path) -> None:
    """Write a focused coding-interview profile."""

    path.write_text(
        "\n".join(
            [
                "name: real-stt-valid-parentheses-eval",
                "watch_terms:",
                "  - valid parentheses",
                "  - opening parentheses",
                "  - closing parenthesis",
                "  - stack",
                "project_aliases:",
                "  stt-eval:",
                "    - valid parentheses",
                "    - stack solution",
                "repo_priorities:",
                "  - stt-eval",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ask_fixture_runner(path: Path) -> Path:
    """Create a bounded Ask fixture that behaves like a local Ask receipt."""

    runner = path / "ask-real-stt-fixture-runner.sh"
    runner.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'run_dir="${LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR:?}"',
                'mkdir -p "$run_dir/node-artifacts/handler-fixture"',
                'printf "%s\\n" "$*" > "$run_dir/argv.txt"',
                'cat > "$run_dir/node-artifacts/handler-fixture/response.md" <<\'EOF\'',
                "Use a stack: push opening-parenthesis indices, pop for each valid closing parenthesis, reject a closing parenthesis when the stack is empty, and reject leftover openings after the scan. Code path: stt-eval/valid_parentheses.py. Caution: this checks validity; minimum-removal variants need a second pass.",
                "EOF",
                'printf \'{"run_dir":"%s"}\\n\' "$run_dir"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner


def post_turn(
    client: httpx.Client,
    *,
    speaker: str,
    text: str,
    sequence: int,
    start_ms: int,
    end_ms: int,
) -> None:
    """Post one transcript event with stable replay offsets."""

    response = client.post(
        "/api/transcript",
        json={
            "schema": "live_evidence.transcript_event.v1",
            "speaker": speaker,
            "kind": "final",
            "source": "api",
            "sequence": sequence,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": text,
        },
    )
    response.raise_for_status()


def wait_for_cards(client: httpx.Client, count: int, *, timeout_s: float = 8.0) -> dict[str, Any]:
    """Wait until the app projects enough cards."""

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


def assert_scannable_card(card: dict[str, Any], ask_run_dir: Path) -> None:
    """Require explicit question, answer, and evidence fields."""

    if card.get("status") != "supported":
        raise RuntimeError(f"expected supported card, got {card}")
    question = str(card.get("question") or "")
    answer = str(card.get("answer") or "")
    evidence = str(card.get("evidence") or "")
    if "opening parentheses always has to come before closing" not in question.casefold():
        raise RuntimeError(f"card question did not preserve the selected STT question: {card}")
    if "stack" not in answer.casefold():
        raise RuntimeError(f"card answer did not surface the stack solution: {card}")
    if "valid_parentheses.py" not in evidence and "valid_parentheses.py" not in json.dumps(card):
        raise RuntimeError(f"card evidence did not cite the local code path: {card}")
    if not any(source.get("lane") == "ask" for source in card.get("sources") or []):
        raise RuntimeError(f"card did not include Ask solution source: {card}")
    if not any(_ask_source_has_receipt(source) for source in card.get("sources") or []):
        raise RuntimeError(f"Ask solution source did not preserve run-dir/response hash metadata: {card}")
    if not (ask_run_dir / "argv.txt").is_file():
        raise RuntimeError("Ask fixture runner was not invoked")


def _ask_source_has_receipt(source: dict[str, Any]) -> bool:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    return (
        source.get("lane") == "ask"
        and bool(metadata.get("run_dir"))
        and bool(metadata.get("response_path"))
        and bool(metadata.get("response_sha256"))
    )


def main() -> int:
    """Run the replay eval against a real local Live Evidence server."""

    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    with tempfile.TemporaryDirectory(prefix="live-evidence-real-stt-window-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "stt-eval"
        repo.mkdir(parents=True)
        (repo / "valid_parentheses.py").write_text(
            "\n".join(
                [
                    '"""Stack-based valid-parentheses interview solution."""',
                    "",
                    "def is_valid_parentheses(text: str) -> bool:",
                    "    stack: list[str] = []",
                    "    for char in text:",
                    "        if char == '(':",
                    "            stack.append(char)",
                    "        elif char == ')':",
                    "            if not stack:",
                    "                return False",
                    "            stack.pop()",
                    "    return not stack",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        profile_path = temp / "profile.yaml"
        write_profile(profile_path)
        data_dir = temp / "data"
        ask_run_dir = temp / "ask-run"
        ask_runner = write_ask_fixture_runner(temp)
        port = free_port()
        env = {
            **os.environ,
            "LIVE_EVIDENCE_REPOS": str(repo),
            "LIVE_EVIDENCE_DATA_DIR": str(data_dir),
            "LIVE_EVIDENCE_PROFILE": str(profile_path),
            "LIVE_EVIDENCE_HTTP_TIMEOUT": "0.3",
            "LIVE_EVIDENCE_PROCESS_TIMEOUT": "3",
            "LIVE_EVIDENCE_MAX_CARDS": "5",
            "LIVE_EVIDENCE_ASK_RUNNER": str(ask_runner),
            "LIVE_EVIDENCE_ASK_HANDLER": "fixture-handler",
            "LIVE_EVIDENCE_ASK_TIMEOUT": "3",
            "LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR": str(ask_run_dir),
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
                    speaker="interviewer",
                    sequence=1,
                    start_ms=120_000,
                    end_ms=123_000,
                    text="Now let's look at the parentheses problem setup.",
                )
                post_turn(
                    client,
                    speaker="interviewer",
                    sequence=2,
                    start_ms=123_000,
                    end_ms=154_976,
                    text=REALTIME_TEXT,
                )
                post_turn(
                    client,
                    speaker="graham",
                    sequence=3,
                    start_ms=155_000,
                    end_ms=160_000,
                    text="I would answer with a stack and then discuss edge cases.",
                )
                state = wait_for_cards(client, 1)
                assert_scannable_card(state["cards"][0], ask_run_dir)
                transcript = state.get("transcript") or []
                if not any(event.get("start_ms") == 123_000 and event.get("end_ms") == 154_976 for event in transcript):
                    raise RuntimeError(f"transcript offsets were not preserved: {transcript}")

                receipt = {
                    "schema": "live_evidence.real_stt_window_eval_receipt.v1",
                    "status": "PASS",
                    "created_at": datetime.now(UTC).isoformat(),
                    "mocked": False,
                    "live": False,
                    "fixture_backed": True,
                    "real_stt_replay": True,
                    "youtube_source": YOUTUBE_URL,
                    "checks": {
                        "stt_window_offsets_preserved": True,
                        "question_detected": True,
                        "ask_solution_invoked": True,
                        "ask_response_hash_preserved": True,
                        "card_question_answer_evidence_split": True,
                        "local_code_path_cited": True,
                    },
                    "window": {
                        "previous_sequence": 1,
                        "current_sequence": 2,
                        "next_sequence": 3,
                        "current_start_ms": 123_000,
                        "current_end_ms": 154_976,
                    },
                    "card": {
                        "question": state["cards"][0].get("question"),
                        "answer": state["cards"][0].get("answer"),
                        "evidence": state["cards"][0].get("evidence"),
                        "lanes": state["cards"][0].get("lanes"),
                    },
                }
                receipt_dir = Path(os.getenv("LIVE_EVIDENCE_DATA_DIR", str(data_dir)))
                receipt_dir.mkdir(parents=True, exist_ok=True)
                receipt_path = receipt_dir / "real-stt-window-eval-receipt.json"
                receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                shutil.copy2(receipt_path, Path("/tmp/live-evidence-real-stt-window-eval-receipt.json"))
                print("real STT window question-answer card: PASS")
                print(f"real STT window receipt: {receipt_path}")
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
