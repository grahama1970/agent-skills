#!/usr/bin/env python3
"""Exercise a YouTube-derived coding interview fixture through Live Evidence.

The fixture is distilled from an ingested public mock interview transcript, but
keeps the committed text small and paraphrased. The source transcript receipt is
an input artifact, not a runtime dependency for the deterministic eval.
"""

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


YOUTUBE_URL = "https://youtu.be/c6zu897JVQY"
YOUTUBE_TITLE = "Google Coding Interview With a Meta Software Engineer"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_profile(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: youtube-derived-interview-eval",
                "watch_terms:",
                "  - invalid parentheses",
                "  - stack",
                "  - javascript",
                "  - remove invalid",
                "project_aliases:",
                "  youtube-eval:",
                "    - parenthesis interview",
                "    - stack solution",
                "    - javascript solution",
                "repo_priorities:",
                "  - youtube-eval",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ask_fixture_runner(path: Path) -> Path:
    runner = path / "ask-youtube-fixture-runner.sh"
    runner.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'run_dir="${LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR:?}"',
                'mkdir -p "$run_dir/node-artifacts/handler-fixture"',
                'printf "%s\\n" "$*" > "$run_dir/argv.txt"',
                'cat > "$run_dir/node-artifacts/handler-fixture/response.md" <<\'EOF\'',
                "Ask solution: Use a stack of opening-parenthesis indices, blank invalid closing parentheses immediately, then blank leftover opening indices and join the character array. Code path: youtube-eval/remove_invalid_parentheses.js. Caution: multiple minimum-removal outputs can be valid.",
                "EOF",
                'printf \'{"run_dir":"%s"}\\n\' "$run_dir"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner


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


def assert_top_card(card: dict[str, Any], *, lane: str, path_fragment: str | None = None) -> None:
    if card.get("status") != "supported":
        raise RuntimeError(f"expected supported card, got {card}")
    sources = card.get("sources") or []
    if not any(source.get("lane") == lane for source in sources):
        raise RuntimeError(f"card missing {lane} source: {card}")
    if path_fragment and not any(path_fragment in str(source.get("path")) for source in sources):
        raise RuntimeError(f"card missing source path fragment {path_fragment!r}: {card}")


def assert_ask_receipt_backed(card: dict[str, Any]) -> None:
    for source in card.get("sources") or []:
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        if (
            source.get("lane") == "ask"
            and metadata.get("run_dir")
            and metadata.get("response_path")
            and metadata.get("response_sha256")
        ):
            return
    raise RuntimeError(f"card missing Ask run-dir/response hash metadata: {card}")


def assert_card_text(card: dict[str, Any], expected: list[str]) -> None:
    visible = " ".join(
        str(card.get(field) or "") for field in ("talking_point", "proof", "qualifier")
    )
    source_text = " ".join(str(source.get("excerpt") or "") for source in card.get("sources") or [])
    combined = f"{visible} {source_text}".casefold()
    missing = [phrase for phrase in expected if phrase.casefold() not in combined]
    if missing:
        raise RuntimeError(f"card missing answer text {missing}: {card}")


def assert_ask_prompt(path: Path, expected: list[str]) -> None:
    prompt = path.read_text(encoding="utf-8").casefold()
    missing = [phrase for phrase in expected if phrase.casefold() not in prompt]
    if missing:
        raise RuntimeError(f"Ask prompt missing expected question/evidence text {missing}: {prompt}")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    with tempfile.TemporaryDirectory(prefix="live-evidence-youtube-eval-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "youtube-eval"
        repo.mkdir(parents=True)
        (repo / "remove_invalid_parentheses.js").write_text(
            "\n".join(
                [
                    "// Stack solution for removing minimum invalid parentheses from a string.",
                    "export function removeInvalidParentheses(input) {",
                    "  const chars = input.split('');",
                    "  const stack = [];",
                    "  for (let index = 0; index < chars.length; index += 1) {",
                    "    if (chars[index] === '(') stack.push(index);",
                    "    if (chars[index] === ')' && stack.length > 0) stack.pop();",
                    "    else if (chars[index] === ')') chars[index] = '';",
                    "  }",
                    "  while (stack.length > 0) chars[stack.pop()] = '';",
                    "  return chars.join('');",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        profile_path = temp / "profile.yaml"
        write_profile(profile_path)
        ask_run_dir = temp / "ask-run"
        ask_runner = write_ask_fixture_runner(temp)
        data_dir = temp / "data"
        port = free_port()
        env = {
            **os.environ,
            "LIVE_EVIDENCE_REPOS": str(repo),
            "LIVE_EVIDENCE_DATA_DIR": str(data_dir),
            "LIVE_EVIDENCE_PROFILE": str(profile_path),
            "LIVE_EVIDENCE_HTTP_TIMEOUT": "0.3",
            "LIVE_EVIDENCE_PROCESS_TIMEOUT": "3",
            "LIVE_EVIDENCE_MAX_CARDS": "6",
            "LIVE_EVIDENCE_ASK_RUNNER": str(ask_runner),
            "LIVE_EVIDENCE_ASK_HANDLER": "fixture-handler",
            "LIVE_EVIDENCE_ASK_TIMEOUT": "3",
            "LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR": str(ask_run_dir),
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
                for _ in range(450):
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
                    text="Given letters mixed with parentheses, how would you remove the minimum invalid parentheses and return any valid string?",
                )
                state = wait_for_cards(client, 1)
                assert_top_card(state["cards"][0], lane="ask")
                assert_ask_receipt_backed(state["cards"][0])
                ask_prompt_path = ask_run_dir / "argv.txt"
                if not ask_prompt_path.is_file():
                    raise RuntimeError("Ask fixture runner was not invoked for YouTube-derived prompt")
                assert_ask_prompt(
                    ask_prompt_path,
                    [
                        "remove the minimum invalid parentheses",
                        "remove_invalid_parentheses.js",
                        "stack",
                    ],
                )
                assert_card_text(
                    state["cards"][0],
                    [
                        "stack of opening-parenthesis indices",
                        "blank invalid closing parentheses",
                        "remove_invalid_parentheses.js",
                    ],
                )
                print("youtube-derived prompt routes to Ask solution: PASS")
                print("youtube-derived answer text surfaced: PASS")

                post_turn(
                    client,
                    speaker="graham",
                    sequence=2,
                    text="I would explain that valid closing parentheses need a prior opening parenthesis and keep the implementation grounded.",
                )
                time.sleep(0.4)
                if len(client.get("/api/state").json().get("cards") or []) != 1:
                    raise RuntimeError("candidate explanation triggered a new automatic evidence card")
                print("candidate explanation suppressed: PASS")

                post_turn(
                    client,
                    speaker="interviewer",
                    sequence=3,
                    text="Where does the JavaScript stack solution handle extra closing parentheses and dangling openings?",
                )
                state = wait_for_cards(client, 2)
                assert_top_card(state["cards"][0], lane="ripgrep", path_fragment="remove_invalid_parentheses.js")
                assert_card_text(
                    state["cards"][0],
                    [
                        "Stack solution for removing minimum invalid parentheses",
                        "removeInvalidParentheses",
                    ],
                )
                print("youtube-derived follow-up routes to source-backed code card: PASS")

                receipt = {
                    "schema": "live_evidence.youtube_interview_eval_receipt.v1",
                    "status": "PASS",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "mocked": False,
                    "live": False,
                    "fixture_backed": True,
                    "youtube_source": {
                        "url": YOUTUBE_URL,
                        "title": YOUTUBE_TITLE,
                        "ingest_receipt": os.getenv(
                            "LIVE_EVIDENCE_YOUTUBE_INGEST_RECEIPT",
                            "/tmp/live-evidence-youtube-transcript-c6zu897JVQY-full.json",
                        ),
                        "committed_text_policy": "distilled-paraphrase",
                    },
                    "checks": {
                        "interviewer_prompt_to_ask_card": True,
                        "ask_prompt_contains_question_and_evidence": True,
                        "ask_response_hash_preserved": True,
                        "answer_text_surfaced_in_card": True,
                        "candidate_turn_suppressed": True,
                        "follow_up_to_source_backed_ask_card": True,
                    },
                }
                receipt_dir = Path(os.getenv("LIVE_EVIDENCE_DATA_DIR", str(data_dir)))
                receipt_dir.mkdir(parents=True, exist_ok=True)
                receipt_path = receipt_dir / "youtube-interview-eval-receipt.json"
                receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                shutil.copy2(receipt_path, Path("/tmp/live-evidence-youtube-interview-eval-receipt.json"))
                print(f"youtube interview receipt: {receipt_path}")
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
