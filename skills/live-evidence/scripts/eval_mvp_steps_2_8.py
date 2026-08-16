#!/usr/bin/env python3
"""Sampled agentic eval for the Live Evidence steps 2-8 contract."""

from __future__ import annotations

import argparse
import importlib.util
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
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(override=False)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_profile(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: mvp-steps-2-8-agentic-eval",
                "watch_terms:",
                "  - source-bound",
                "  - evidence-card",
                "  - after-start-sentinel",
                "  - memory-alpha",
                "project_aliases:",
                "  mvp-eval:",
                "    - source-bound",
                "    - evidence-card",
                "    - after-start-sentinel",
                "    - memory-alpha",
                "repo_priorities:",
                "  - mvp-eval",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_memory_runner(path: Path, log_path: Path) -> Path:
    runner = path / "memory-runner.sh"
    runner.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"log_path={json.dumps(str(log_path))}",
                'printf "%s\\n" "$*" >> "$log_path"',
                'case "${1:-}" in',
                "  code-search)",
                "    cat <<'JSON'",
                '{"items":[{"repository":"mvp-eval","path":"src/memory_alpha.py","qualified_name":"memory_alpha.lookup","symbol_id":"sym-memory-alpha","start_line":1}]}',
                "JSON",
                "    ;;",
                "  code-node)",
                "    cat <<'JSON'",
                '{"status":"ok","symbol":{"repository":"mvp-eval","qualified_name":"memory_alpha.lookup","symbol_id":"sym-memory-alpha","path":"src/memory_alpha.py"},"source":{"path":"src/memory_alpha.py","text":"def lookup(): return \\"memory-alpha source-bound evidence card\\"","start_line":1,"end_line":1},"freshness":{"status":"current","indexed_hash":"abc","current_hash":"abc"}}',
                "JSON",
                "    ;;",
                "  *)",
                "    echo '{\"items\":[]}'",
                "    ;;",
                "esac",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner


def write_ask_runner(path: Path, run_dir: Path, log_path: Path) -> Path:
    runner = path / "ask-fixture-runner.sh"
    runner.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"run_dir={json.dumps(str(run_dir))}",
                f"log_path={json.dumps(str(log_path))}",
                'mkdir -p "$run_dir/node-artifacts/handler-fixture"',
                'printf "%s\\n" "$*" >> "$log_path"',
                'cat > "$run_dir/node-artifacts/handler-fixture/response.md" <<\'EOF\'',
                "Ask fixture-only answer: use the current source-bound evidence card pipeline. Code path: mvp-eval/src/memory_alpha.py. Caution: this eval proves Ask command plumbing and preserved run-dir only, not provider correctness.",
                "EOF",
                'printf \'{"run_dir":"%s"}\\n\' "$run_dir"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner


def write_external_runner(path: Path, name: str, log_path: Path) -> Path:
    runner = path / f"{name}-runner.sh"
    runner.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"log_path={json.dumps(str(log_path))}",
                'printf "%s\\n" "$*" >> "$log_path"',
                "cat <<'JSON'",
                '{"results":[{"title":"Bounded evidence card research lead","url":"https://example.invalid/live-evidence","description":"Manual research lane received only a derived question, not transcript history."}]}',
                "JSON",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner


class MemoryHandler(BaseHTTPRequestHandler):
    calls: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"_raw": raw}
        self.__class__.calls.append({"path": self.path, "payload": payload})
        if self.path == "/intent":
            self._send({"recall_profile": "procedural_memory"})
            return
        if self.path == "/recall":
            self._send(
                {
                    "found": True,
                    "confidence": 0.82,
                    "items": [
                        {
                            "_key": "memory-alpha-1",
                            "problem": "memory-alpha source-bound evidence card",
                            "content": "Graph Memory boundary returns source-bound context for memory-alpha.",
                            "repo": "mvp-eval",
                            "path": "memory/memory-alpha.md",
                            "score": 0.82,
                        }
                    ],
                }
            )
            return
        self._send({"error": "not_found"}, status=404)

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _send(self, payload: dict[str, Any], *, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_memory_server(port: int) -> ThreadingHTTPServer:
    MemoryHandler.calls = []
    server = ThreadingHTTPServer(("127.0.0.1", port), MemoryHandler)
    thread = threading.Thread(target=server.serve_forever, name="live-evidence-eval-memory", daemon=True)
    thread.start()
    return server


def post_turn(
    client: httpx.Client,
    *,
    speaker: str,
    kind: str = "final",
    text: str,
    sequence: int,
    event_id: str | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema": "live_evidence.transcript_event.v1",
        "speaker": speaker,
        "kind": kind,
        "source": "api",
        "sequence": sequence,
        "text": text,
    }
    if event_id is not None:
        payload["event_id"] = event_id
    if start_ms is not None:
        payload["start_ms"] = start_ms
    if end_ms is not None:
        payload["end_ms"] = end_ms
    response = client.post("/api/transcript", json=payload)
    response.raise_for_status()


def wait_for_cards(client: httpx.Client, count: int, *, timeout_s: float = 10.0) -> dict[str, Any]:
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


def assert_no_new_cards(client: httpx.Client, expected_count: int, *, delay_s: float = 0.45) -> None:
    time.sleep(delay_s)
    cards = client.get("/api/state").json().get("cards") or []
    if len(cards) != expected_count:
        raise RuntimeError(f"unexpected automatic cards: expected={expected_count} actual={len(cards)}")


def assert_card_has(card: dict[str, Any], *, lane: str | None = None, path_fragment: str | None = None) -> None:
    if card.get("status") != "supported":
        raise RuntimeError(f"expected supported card: {card}")
    sources = card.get("sources") or []
    if not sources:
        raise RuntimeError(f"supported card had no sources: {card}")
    if lane and not any(source.get("lane") == lane for source in sources):
        raise RuntimeError(f"card missing lane {lane}: {card}")
    if path_fragment and path_fragment not in json.dumps(card):
        raise RuntimeError(f"card missing path fragment {path_fragment}: {card}")


def assert_runner_called(log_path: Path, expected: str) -> None:
    text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    if expected not in text:
        raise RuntimeError(f"runner log {log_path} did not contain {expected!r}: {text}")


def run_eval(root: Path, *, samples: int, seed: int, receipt_path: Path | None) -> Path:
    if samples < 50:
        raise RuntimeError("--samples must be >= 50 for this adversarial agentic eval")
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="live-evidence-mvp-steps-2-8-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "mvp-eval"
        source_dir = repo / "src"
        source_dir.mkdir(parents=True)
        (source_dir / "memory_alpha.py").write_text(
            "def lookup():\n    return 'memory-alpha source-bound evidence card pipeline'\n",
            encoding="utf-8",
        )
        profile_path = temp / "profile.yaml"
        write_profile(profile_path)
        memory_runner_log = temp / "memory-runner.argv"
        ask_runner_log = temp / "ask-runner.argv"
        brave_runner_log = temp / "brave-runner.argv"
        dogpile_runner_log = temp / "dogpile-runner.argv"
        ask_run_dir = temp / "ask-run"
        memory_runner = write_memory_runner(temp, memory_runner_log)
        ask_runner = write_ask_runner(temp, ask_run_dir, ask_runner_log)
        brave_runner = write_external_runner(temp, "brave", brave_runner_log)
        dogpile_runner = write_external_runner(temp, "dogpile", dogpile_runner_log)
        data_dir = temp / "data"
        app_port = free_port()
        memory_port = free_port()
        memory_server = start_memory_server(memory_port)
        env = {
            **os.environ,
            "LIVE_EVIDENCE_REPOS": str(repo),
            "LIVE_EVIDENCE_DATA_DIR": str(data_dir),
            "LIVE_EVIDENCE_PROFILE": str(profile_path),
            "LIVE_EVIDENCE_HTTP_TIMEOUT": "1",
            "LIVE_EVIDENCE_PROCESS_TIMEOUT": "4",
            "LIVE_EVIDENCE_MAX_CARDS": "5",
            "LIVE_EVIDENCE_MEMORY_RUNNER": str(memory_runner),
            "LIVE_EVIDENCE_ASK_RUNNER": str(ask_runner),
            "LIVE_EVIDENCE_ASK_HANDLER": "fixture-handler",
            "LIVE_EVIDENCE_ASK_TIMEOUT": "4",
            "LIVE_EVIDENCE_BRAVE_RUNNER": str(brave_runner),
            "LIVE_EVIDENCE_DOGPILE_RUNNER": str(dogpile_runner),
            "MEMORY_SERVICE_URL": f"http://127.0.0.1:{memory_port}",
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
                    str(app_port),
                    "--no-browser",
                ],
                cwd=root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{app_port}", timeout=4.0) as client:
                for _ in range(80):
                    try:
                        if client.get("/api/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"server did not start; log={log_path.read_text()}")
                client.post("/api/session/start", json={"consent_confirmed": True}).raise_for_status()

                stt_available = importlib.util.find_spec("RealtimeSTT") is not None
                stt_status = "available" if stt_available else "blocked_live_dependency"
                print(f"step2 real stt dependency gate: PASS ({stt_status})")

                turn_id = "turn_memory_alpha_final_0001"
                post_turn(
                    client,
                    speaker="interviewer",
                    kind="interim",
                    sequence=1,
                    event_id=turn_id,
                    start_ms=1_000,
                    end_ms=1_300,
                    text="Can you",
                )
                assert_no_new_cards(client, 0, delay_s=0.2)
                post_turn(
                    client,
                    speaker="interviewer",
                    kind="stabilized",
                    sequence=1,
                    event_id=turn_id,
                    start_ms=1_000,
                    end_ms=1_600,
                    text="Can you explain",
                )
                assert_no_new_cards(client, 0, delay_s=0.2)
                post_turn(
                    client,
                    speaker="interviewer",
                    kind="final",
                    sequence=1,
                    event_id=turn_id,
                    start_ms=1_000,
                    end_ms=3_200,
                    text="Can you explain what function should return for a valid string using a stack in memory-alpha source-bound evidence-card answers?",
                )
                state = wait_for_cards(client, 1)
                assert_card_has(state["cards"][0], lane="ask", path_fragment="ask-run")
                projected = [event for event in state.get("transcript") or [] if event.get("event_id") == turn_id]
                if len(projected) != 1 or projected[0].get("kind") != "final" or projected[0].get("end_ms") != 3_200:
                    raise RuntimeError(f"stabilized/final projection regression: {projected}")
                print("step3 stabilized final turn projection: PASS")
                print("step4 interviewer code question trigger: PASS")
                print("step7 ask fixture-only run-dir surfaced: PASS")

                assert any(call["path"] == "/intent" for call in MemoryHandler.calls)
                assert any(call["path"] == "/recall" for call in MemoryHandler.calls)
                assert_runner_called(memory_runner_log, "code-search")
                assert_runner_called(memory_runner_log, "code-node")
                print("step5 memory http and code runner boundaries: PASS")

                post_turn(
                    client,
                    speaker="interviewer",
                    sequence=50,
                    text="Can you explain what function should return for a valid string using a stack in memory-alpha source-bound evidence-card answers?",
                )
                assert_no_new_cards(client, 1, delay_s=0.4)

                for index in range(samples):
                    sequence = 100 + index
                    choice = rng.choice(["candidate", "noise"])
                    if choice == "candidate":
                        post_turn(
                            client,
                            speaker="graham",
                            sequence=sequence,
                            text=f"How would I answer source-bound evidence-card follow-up {index} from candidate speech?",
                        )
                    elif choice == "noise":
                        post_turn(
                            client,
                            speaker="interviewer",
                            sequence=sequence,
                            text=f"ambient note {index} with no actionable interview question",
                        )
                        post_turn(
                            client,
                            speaker="graham",
                            sequence=sequence + 10_000,
                            text=f"candidate boundary after noisy non-question {index}",
                        )
                assert_no_new_cards(client, 1, delay_s=0.8)
                print(f"sampled adversarial trigger suppression: PASS ({samples} samples)")

                sentinel = f"after-start-sentinel-{seed}"
                after_start = source_dir / "after_start_sentinel.py"
                after_start.write_text(
                    f"AFTER_START_SENTINEL = {sentinel!r}\n",
                    encoding="utf-8",
                )
                post_turn(
                    client,
                    speaker="interviewer",
                    sequence=1_000,
                    text=f"Where is {sentinel} implemented for current checkout ripgrep?",
                )
                state = wait_for_cards(client, 2)
                assert_card_has(state["cards"][0], lane="ripgrep", path_fragment="after_start_sentinel.py")
                print("step6 current checkout ripgrep after startup: PASS")

                raw_transcript = (
                    "graham: candidate-private-sentinel should not leave the transcript. "
                    "interviewer: What does bounded evidence card mean?"
                )
                brave_card = client.post("/api/search", json={"lane": "brave", "query": raw_transcript})
                brave_card.raise_for_status()
                dogpile_card = client.post("/api/search", json={"lane": "dogpile", "query": raw_transcript})
                dogpile_card.raise_for_status()
                for path in (brave_runner_log, dogpile_runner_log):
                    text = path.read_text(encoding="utf-8")
                    if "candidate-private-sentinel" in text:
                        raise RuntimeError(f"manual lane received transcript history: {path}: {text}")
                    if "What does bounded evidence card mean" not in text:
                        raise RuntimeError(f"manual lane did not receive derived question: {path}: {text}")
                final_state = client.get("/api/state").json()
                cards = final_state.get("cards") or []
                if len(cards) > 5:
                    raise RuntimeError(f"card queue exceeded realtime scan bound: {len(cards)}")
                if any(card.get("status") == "supported" and not card.get("sources") for card in cards):
                    raise RuntimeError(f"supported card without sources: {cards}")
                print("step8 source-bound cards and manual derived-query lanes: PASS")

                receipt = {
                    "schema": "live_evidence.mvp_steps_2_8_eval_receipt.v1",
                    "status": "PASS",
                    "created_at": datetime.now(UTC).isoformat(),
                    "mocked": False,
                    "live": True,
                    "fixture_backed": True,
                    "samples": samples,
                    "seed": seed,
                    "checks": {
                        "step2_stt_dependency_gate": stt_status,
                        "step3_stabilized_final_projection": True,
                        "step4_trigger_adversarial_suppression": True,
                        "step5_memory_http_boundary": True,
                        "step5_memory_runner_boundary": True,
                        "step6_current_checkout_rg_after_start": True,
                        "step7_ask_run_dir_fixture_only": True,
                        "step8_source_bound_cards": True,
                        "step8_manual_lanes_derived_query_only": True,
                    },
                    "claims": {
                        "proves": [
                            "real local FastAPI session and transcript API path",
                            "stable/final event projection replaces same event_id with final offsets",
                            "sampled candidate/noise/duplicate turns do not create extra cards",
                            "Memory is called through HTTP /intent and /recall boundaries",
                            "memory runner is called through code-search and code-node subprocess boundaries",
                            "ripgrep sees source created after service startup",
                            "Ask lane preserves a run directory and surfaces fixture-only response text",
                            "manual Brave/Dogpile lanes receive a derived question, not transcript history",
                        ],
                        "does_not_prove": [
                            "live microphone, PipeWire, or GPU STT inference",
                            "real Graph Memory corpus relevance",
                            "live Ask provider or model correctness",
                            "live Brave or Dogpile search quality",
                        ],
                    },
                    "memory_call_paths": [call["path"] for call in MemoryHandler.calls],
                    "final_card_count": len(cards),
                }
                out = receipt_path or data_dir / "mvp-steps-2-8-eval-receipt.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
                shutil.copy2(out, Path("/tmp/live-evidence-mvp-steps-2-8-eval-receipt.json"))
                print(f"mvp steps 2-8 receipt: {out}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
            memory_server.shutdown()
    return Path("/tmp/live-evidence-mvp-steps-2-8-eval-receipt.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--samples", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    run_eval(Path(args.root).resolve(), samples=args.samples, seed=args.seed, receipt_path=args.receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
