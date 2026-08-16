#!/usr/bin/env python3
"""Adversarial reliability eval for Live Evidence.

This runner exercises two failure families that matter during interviews:

1. noisy transcript windows must recover and identify the real interviewer
   question without letting candidate speech or repeated STT updates trigger a
   card storm;
2. a degraded/slow Memory lane must not prevent a code-question answer card from
   appearing through the local HTTP application path.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from live_evidence.config import InterviewProfile
from live_evidence.models import Speaker, TranscriptEvent, TranscriptKind
from live_evidence.question_window import QuestionWindowBuilder

load_dotenv(override=False)


CODE_QUESTIONS = [
    "Given a string input with lowercase characters and invalid parentheses, how would you remove the minimum number of parentheses to return a valid string output?",
    "How would you implement binary search over a sorted array and return the target index?",
    "Can you describe a stack based algorithm to validate opening and closing parentheses in a string?",
    "What function would you write to find the minimum removals needed for a valid parenthesis string?",
]

NOISE = [
    "I think I would start by clarifying examples before coding.",
    "when I worked on this project we kept the interface compact",
    "The transcript is still settling and these words should not trigger retrieval",
    "okay let me think through edge cases out loud",
    "we might need to account for duplicates and empty input",
]


def free_port() -> int:
    """Reserve and release one localhost port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def event(
    *,
    speaker: Speaker,
    kind: TranscriptKind,
    sequence: int,
    text: str,
    suffix: str,
) -> TranscriptEvent:
    return TranscriptEvent(
        event_id=f"evt_{suffix}_{sequence:04d}",
        speaker=speaker,
        kind=kind,
        source="api",
        sequence=sequence,
        text=text,
    )


def profile() -> InterviewProfile:
    return InterviewProfile(
        name="reliability-adversarial-eval",
        watch_terms=[
            "invalid parentheses",
            "binary search",
            "stack",
            "interview question",
        ],
        project_aliases={
            "reliability-eval": [
                "parenthesis interview",
                "binary search",
                "stack solution",
            ]
        },
        repo_priorities=["reliability-eval"],
    )


def run_transcript_window_samples(samples: int, seed: int) -> dict[str, Any]:
    """Sample adversarial transcript windows against the production windowing code."""

    rng = random.Random(seed)
    accepted = 0
    duplicate_suppressed = 0
    false_candidate_suppressed = 0
    recovered_after_candidate_boundary = 0
    span_checked = 0

    for index in range(samples):
        builder = QuestionWindowBuilder(profile(), duplicate_ttl_s=60.0)
        suffix = f"{seed:x}_{index:x}"
        seq = 1

        candidate_noise = rng.choice(NOISE)
        candidate_outcome = builder.ingest(
            event(
                speaker=Speaker.GRAHAM,
                kind=TranscriptKind.FINAL,
                sequence=seq,
                text=candidate_noise,
                suffix=suffix,
            )
        )
        seq += 1
        if candidate_outcome.candidate is not None:
            raise RuntimeError(f"candidate speech produced a question candidate: {candidate_outcome}")
        false_candidate_suppressed += 1

        partial = f"transcript settling filler {index} with no retrieval lead"
        partial_outcome = builder.ingest(
            event(
                speaker=Speaker.INTERVIEWER,
                kind=TranscriptKind.STABILIZED,
                sequence=seq,
                text=partial.lower(),
                suffix=suffix,
            )
        )
        seq += 1
        if partial_outcome.candidate is not None:
            raise RuntimeError(f"partial stabilized text triggered too early: {partial_outcome}")
        false_candidate_suppressed += 1

        final_question = rng.choice(CODE_QUESTIONS)
        if rng.random() < 0.5:
            final_question = f"{final_question} Please include the complexity."
        accepted_outcome = builder.ingest(
            event(
                speaker=Speaker.INTERVIEWER,
                kind=TranscriptKind.FINAL,
                sequence=seq,
                text=final_question,
                suffix=suffix,
            )
        )
        seq += 1
        if accepted_outcome.candidate is None or accepted_outcome.duplicate:
            raise RuntimeError(f"final interviewer question was not accepted: {accepted_outcome}")
        if accepted_outcome.reason != "accepted":
            raise RuntimeError(f"unexpected acceptance reason: {accepted_outcome}")
        candidate = accepted_outcome.candidate
        if candidate.trigger_reason != "code-question":
            raise RuntimeError(f"question did not route as code-question: {candidate}")
        if candidate.start_sequence > candidate.end_sequence:
            raise RuntimeError(f"candidate span order is invalid: {candidate}")
        if not candidate.source_spans or candidate.source_spans[-1].end_offset <= 0:
            raise RuntimeError(f"candidate lacks usable source spans: {candidate}")
        accepted += 1
        recovered_after_candidate_boundary += 1
        span_checked += 1

        duplicate_builder = QuestionWindowBuilder(profile(), duplicate_ttl_s=60.0)
        duplicate_question = rng.choice(CODE_QUESTIONS)
        first_duplicate_outcome = duplicate_builder.ingest(
            event(
                speaker=Speaker.INTERVIEWER,
                kind=TranscriptKind.FINAL,
                sequence=1,
                text=duplicate_question,
                suffix=f"{suffix}_dup_first",
            )
        )
        if first_duplicate_outcome.candidate is None or first_duplicate_outcome.duplicate:
            raise RuntimeError(f"duplicate control question was not accepted: {first_duplicate_outcome}")
        duplicate_outcome = duplicate_builder.ingest(
            event(
                speaker=Speaker.INTERVIEWER,
                kind=TranscriptKind.FINAL,
                sequence=2,
                text=duplicate_question,
                suffix=f"{suffix}_dup",
            )
        )
        if duplicate_outcome.candidate is None or not duplicate_outcome.duplicate:
            raise RuntimeError(f"duplicate question was not suppressed: {duplicate_outcome}")
        duplicate_suppressed += 1

    print(f"sampled transcript recovery: PASS ({accepted}/{samples})")
    print(f"false trigger suppression: PASS ({false_candidate_suppressed}/{samples * 2})")
    print(f"duplicate question suppression: PASS ({duplicate_suppressed}/{samples})")
    return {
        "samples": samples,
        "seed": seed,
        "accepted_code_questions": accepted,
        "false_candidate_suppressed": false_candidate_suppressed,
        "duplicate_suppressed": duplicate_suppressed,
        "recovered_after_candidate_boundary": recovered_after_candidate_boundary,
        "span_checked": span_checked,
    }


class SlowMemoryHandler(BaseHTTPRequestHandler):
    """Memory-compatible HTTP handler that intentionally responds too slowly."""

    delay_s = 1.4

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("content-length", "0") or "0")
        if length:
            self.rfile.read(length)
        time.sleep(self.delay_s)
        payload = {
            "found": False,
            "items": [],
            "results": [],
            "recall_profile": "procedural_memory",
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            return

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def start_slow_memory_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", free_port()), SlowMemoryHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}"


def write_profile(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: reliability-adversarial-eval",
                "watch_terms:",
                "  - invalid parentheses",
                "  - binary search",
                "  - stack",
                "project_aliases:",
                "  reliability-eval:",
                "    - parenthesis interview",
                "    - binary search",
                "    - stack solution",
                "repo_priorities:",
                "  - reliability-eval",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ask_fixture_runner(path: Path) -> Path:
    runner = path / "ask-reliability-fixture-runner.sh"
    runner.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'run_dir="${LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR:?}"',
                'mkdir -p "$run_dir/node-artifacts/handler-fixture"',
                'printf "%s\\n" "$*" > "$run_dir/argv.txt"',
                'cat > "$run_dir/node-artifacts/handler-fixture/response.md" <<\'EOF\'',
                "Ask solution: For invalid parentheses, use a stack of opening indices, remove unmatched closing parentheses as they appear, remove leftover openings, then join the character array. For binary search, keep low/high bounds and halve the search window until the target is found or absent. Complexity: O(n) for the stack pass or O(log n) for binary search.",
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


def wait_for_cards(client: httpx.Client, count: int, *, timeout_s: float = 9.0) -> dict[str, Any]:
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


def assert_answer_card(state: dict[str, Any], *, expected_text: str) -> None:
    cards = state.get("cards") or []
    if not cards:
        raise RuntimeError(f"state has no cards: {state}")
    top = cards[0]
    if top.get("status") != "supported":
        raise RuntimeError(f"expected supported top card: {top}")
    sources = top.get("sources") or []
    if not any(source.get("lane") == "ask" for source in sources):
        raise RuntimeError(f"top card missing Ask solution source: {top}")
    combined = " ".join(
        [
            str(top.get("talking_point") or ""),
            str(top.get("proof") or ""),
            str(top.get("qualifier") or ""),
            " ".join(str(source.get("excerpt") or "") for source in sources),
        ]
    ).casefold()
    if expected_text.casefold() not in combined:
        raise RuntimeError(f"top card missing expected answer text {expected_text!r}: {top}")


def lane_state(state: dict[str, Any], lane: str) -> dict[str, Any]:
    for item in state.get("lanes") or []:
        if item.get("lane") == lane:
            return item
    raise RuntimeError(f"lane {lane!r} missing from state: {state}")


def run_live_http_recovery(root: Path, samples: int, seed: int) -> dict[str, Any]:
    """Run one live HTTP recovery path with sampled pre-question noise."""

    rng = random.Random(seed)
    slow_memory, memory_url = start_slow_memory_server()
    with tempfile.TemporaryDirectory(prefix="live-evidence-reliability-eval-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "reliability-eval"
        repo.mkdir(parents=True)
        (repo / "remove_invalid_parentheses.js").write_text(
            "\n".join(
                [
                    "export function removeInvalidParentheses(input) {",
                    "  const chars = input.split('');",
                    "  const stack = [];",
                    "  for (let index = 0; index < chars.length; index += 1) {",
                    "    if (chars[index] === '(') stack.push(index);",
                    "    else if (chars[index] === ')' && stack.length > 0) stack.pop();",
                    "    else if (chars[index] === ')') chars[index] = '';",
                    "  }",
                    "  while (stack.length) chars[stack.pop()] = '';",
                    "  return chars.join('');",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        (repo / "binary_search.py").write_text(
            "def binary_search(values, target):\n"
            "    low, high = 0, len(values) - 1\n"
            "    while low <= high:\n"
            "        mid = (low + high) // 2\n"
            "        if values[mid] == target:\n"
            "            return mid\n"
            "        if values[mid] < target:\n"
            "            low = mid + 1\n"
            "        else:\n"
            "            high = mid - 1\n"
            "    return -1\n",
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
            "LIVE_EVIDENCE_HTTP_TIMEOUT": "1.0",
            "LIVE_EVIDENCE_PROCESS_TIMEOUT": "3",
            "LIVE_EVIDENCE_MAX_CARDS": "5",
            "LIVE_EVIDENCE_MAX_TRANSCRIPT_EVENTS": "160",
            "LIVE_EVIDENCE_ASK_RUNNER": str(ask_runner),
            "LIVE_EVIDENCE_ASK_HANDLER": "fixture-handler",
            "LIVE_EVIDENCE_ASK_TIMEOUT": "4",
            "LIVE_EVIDENCE_ASK_FIXTURE_RUN_DIR": str(ask_run_dir),
            "MEMORY_SERVICE_URL": memory_url,
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
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=4.0) as client:
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
                for sequence in range(1, min(samples, 25) + 1):
                    post_turn(
                        client,
                        speaker="graham" if sequence % 2 else "interviewer",
                        sequence=sequence,
                        text=rng.choice(NOISE),
                    )
                time.sleep(0.35)
                state = client.get("/api/state").json()
                if state.get("cards"):
                    raise RuntimeError(f"noise produced cards before a real question: {state['cards']}")

                post_turn(
                    client,
                    speaker="interviewer",
                    sequence=100,
                    text=CODE_QUESTIONS[0],
                )
                state = wait_for_cards(client, 1)
                assert_answer_card(state, expected_text="invalid parentheses")
                memory = lane_state(state, "memory")
                ask = lane_state(state, "ask")
                if ask.get("state") != "ok":
                    raise RuntimeError(f"Ask lane did not recover to ok: {ask}")
                if memory.get("state") not in {"running", "degraded", "error"}:
                    raise RuntimeError(f"Memory lane did not expose degraded/running state: {memory}")

                client.post("/api/session/stop").raise_for_status()
                client.post("/api/session/start", json={"consent_confirmed": True}).raise_for_status()
                post_turn(
                    client,
                    speaker="interviewer",
                    sequence=200,
                    text=CODE_QUESTIONS[1],
                )
                recovered_state = wait_for_cards(client, 1)
                assert_answer_card(recovered_state, expected_text="binary search")
                final_cards = recovered_state.get("cards") or []
                if len(final_cards) > 5:
                    raise RuntimeError(f"card storm exceeded max card bound: {len(final_cards)}")

                print("memory degradation self-recovery: PASS")
                print("card storm suppression: PASS")
                return {
                    "samples": samples,
                    "seed": seed,
                    "local_http_api": True,
                    "slow_memory_url": memory_url,
                    "memory_lane_after_first_question": memory,
                    "ask_lane_after_first_question": ask,
                    "first_session_cards": len(state.get("cards") or []),
                    "recovered_session_cards": len(final_cards),
                    "card_cap": 5,
                    "ask_fixture_invoked": (ask_run_dir / "argv.txt").is_file(),
                    "server_log": str(log_path),
                }
        finally:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
            slow_memory.shutdown()
            slow_memory.server_close()


def write_receipt(root: Path, scenario: str, checks: dict[str, Any]) -> Path:
    receipt = {
        "schema": "live_evidence.reliability_adversarial_eval_receipt.v1",
        "status": "PASS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario,
        "mocked": True,
        "live": False,
        "fixture_backed": True,
        "exercised": {
            "local_http_api": "http_recovery" in checks,
            "production_question_window": "transcript_window" in checks,
            "production_coordinator": "http_recovery" in checks,
            "production_react_ui": False,
            "ask_provider_call": False,
            "ask_fixture_runner": "http_recovery" in checks,
            "memory_service": "slow local fault-injection server" if "http_recovery" in checks else "not exercised",
        },
        "claims": {
            "proves": "sampled adversarial transcript windows recover to code-question candidates, suppress candidate/noisy partial triggers and duplicate STT updates, and the live HTTP app can still surface bounded Ask answer cards while Memory is slow/degraded",
            "does_not_prove": "live microphone/PipeWire capture, GPU STT inference, real Graph Memory relevance, live Ask provider/model/browser execution, Brave/Dogpile search, or React visual quality",
        },
        "skill_root": str(root),
        "checks": checks,
    }
    receipt_dir = Path(os.getenv("LIVE_EVIDENCE_DATA_DIR", tempfile.gettempdir()))
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"reliability-adversarial-{scenario}-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    stable_path = Path("/tmp/live-evidence-reliability-adversarial-eval-receipt.json")
    shutil.copy2(receipt_path, stable_path)
    print(f"reliability adversarial receipt: {receipt_path}")
    return receipt_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_root", nargs="?", default=".")
    parser.add_argument(
        "--scenario",
        choices=["all", "transcript-window", "http-recovery"],
        default="all",
    )
    parser.add_argument("--samples", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.skill_root).resolve()
    if args.samples < 50:
        raise SystemExit("--samples must be >= 50 for adversarial reliability evals")
    seed = args.seed or int(time.time_ns() % 2_147_483_647)
    checks: dict[str, Any] = {}
    if args.scenario in {"all", "transcript-window"}:
        checks["transcript_window"] = run_transcript_window_samples(args.samples, seed)
    if args.scenario in {"all", "http-recovery"}:
        checks["http_recovery"] = run_live_http_recovery(root, args.samples, seed)
    write_receipt(root, args.scenario, checks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
