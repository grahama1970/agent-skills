#!/usr/bin/env python3
"""Agentic eval for the transcript-to-leetcode pre-Ask gate."""

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


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_profile(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: leetcode-gate-eval",
                "watch_terms:",
                "  - array",
                "  - target",
                "  - two numbers",
                "project_aliases:",
                "  leetcode-eval:",
                "    - two sum",
                "    - target sum",
                "repo_priorities:",
                "  - leetcode-eval",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ask_fixture_runner(path: Path, run_dir: Path, log_path: Path) -> Path:
    runner = path / "ask-leetcode-gate-fixture-runner.sh"
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
                "Use a hash map from value to index. For each number, check target - number, return the distinct stored index and current index. Code path: leetcode-eval/two_sum.py.",
                "EOF",
                'printf \'{"run_dir":"%s"}\\n\' "$run_dir"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner


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


def post_turn(client: httpx.Client, text: str) -> None:
    response = client.post(
        "/api/transcript",
        json={
            "schema": "live_evidence.transcript_event.v1",
            "speaker": "interviewer",
            "kind": "final",
            "source": "api",
            "sequence": 1,
            "text": text,
        },
    )
    response.raise_for_status()


def assert_clarification_card(card: dict[str, Any], expected_ids: set[str]) -> None:
    if card.get("status") != "insufficient":
        raise RuntimeError(f"expected insufficient clarification card: {card}")
    source = (card.get("sources") or [{}])[0]
    metadata = source.get("metadata") or {}
    ids = [item.get("id") for item in metadata.get("clarifying_questions") or []]
    if not expected_ids <= set(ids):
        raise RuntimeError(f"missing blocking clarification ids {expected_ids}: {card}")
    if metadata.get("solution_allowed") is not False:
        raise RuntimeError(f"clarification card did not block solution: {card}")
    if not metadata.get("transcript_sha256"):
        raise RuntimeError(f"clarification card missing transcript hash: {card}")


def assert_answer_card(card: dict[str, Any], ask_log: Path) -> None:
    if card.get("status") != "supported":
        raise RuntimeError(f"expected supported answer card: {card}")
    ask_sources = [source for source in card.get("sources") or [] if source.get("lane") == "ask"]
    if len(ask_sources) != 1:
        raise RuntimeError(f"expected exactly one Ask source: {card}")
    metadata = ask_sources[0].get("metadata") or {}
    for key in ("run_dir", "response_path", "response_sha256", "leetcode_gate_status", "solver_prompt_sha256"):
        if not metadata.get(key):
            raise RuntimeError(f"Ask source missing {key}: {card}")
    if metadata.get("leetcode_gate_status") != "ready_for_solution":
        raise RuntimeError(f"Ask source did not record ready gate status: {card}")
    if ask_log.read_text(encoding="utf-8").count("Solve this interview coding problem") != 1:
        raise RuntimeError(f"Ask fixture was not invoked exactly once with solver prompt: {ask_log.read_text()}")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    receipt_arg = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    with tempfile.TemporaryDirectory(prefix="live-evidence-leetcode-gate-") as temp_name:
        temp = Path(temp_name)
        repo = temp / "leetcode-eval"
        repo.mkdir(parents=True)
        (repo / "two_sum.py").write_text(
            "\n".join(
                [
                    "def two_sum(nums: list[int], target: int) -> list[int]:",
                    "    seen: dict[int, int] = {}",
                    "    for index, value in enumerate(nums):",
                    "        complement = target - value",
                    "        if complement in seen:",
                    "            return [seen[complement], index]",
                    "        seen[value] = index",
                    "    raise ValueError('no solution')",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        profile_path = temp / "profile.yaml"
        write_profile(profile_path)
        ask_run_dir = temp / "ask-run"
        ask_log = temp / "ask.argv"
        ask_runner = write_ask_fixture_runner(temp, ask_run_dir, ask_log)
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
                post_turn(
                    client,
                    "Given an array of numbers and a target, find two numbers that add up to the target and return the output.",
                )
                phase_a = wait_for_cards(client, 1)
                clarify_card = phase_a["cards"][0]
                assert_clarification_card(clarify_card, {"return-contract", "element-reuse", "multiple-solutions"})
                if ask_log.exists():
                    raise RuntimeError(f"Ask fixture ran during clarification phase: {ask_log.read_text()}")

                partial = client.post(
                    f"/api/cards/{clarify_card['card_id']}/clarifications",
                    json={"answers": {"return-contract": "Return the two indices."}},
                )
                partial.raise_for_status()
                assert_clarification_card(partial.json(), {"element-reuse", "multiple-solutions"})
                if ask_log.exists():
                    raise RuntimeError(f"Ask fixture ran after partial clarification: {ask_log.read_text()}")

                full = client.post(
                    f"/api/cards/{clarify_card['card_id']}/clarifications",
                    json={
                        "answers": {
                            "return-contract": "Return the two indices.",
                            "element-reuse": "The indices must be distinct.",
                            "multiple-solutions": "Exactly one solution exists.",
                        }
                    },
                )
                full.raise_for_status()
                assert_answer_card(full.json(), ask_log)
                final_state = client.get("/api/state").json()
                out = receipt_arg or data_dir / "leetcode-gate-eval-receipt.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                ask_log_artifact = out.parent / "ask.argv"
                ask_run_artifact = out.parent / "ask-run"
                final_state_artifact = out.parent / "final-state.json"
                shutil.copy2(ask_log, ask_log_artifact)
                if ask_run_dir.exists():
                    shutil.copytree(ask_run_dir, ask_run_artifact, dirs_exist_ok=True)
                final_state_artifact.write_text(
                    json.dumps(final_state, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                receipt = {
                    "schema": "live_evidence.leetcode_gate_eval_receipt.v1",
                    "status": "PASS",
                    "created_at": datetime.now(UTC).isoformat(),
                    "mocked": False,
                    "live": True,
                    "fixture_backed": True,
                    "checks": {
                        "phase_a_needs_clarification": True,
                        "phase_a_ask_invocation_count": 0,
                        "partial_answer_remains_needs_clarification": True,
                        "partial_answer_ask_invocation_count": 0,
                        "phase_b_ready_for_solution": True,
                        "phase_b_ask_invocation_count": 1,
                        "transcript_sha256_preserved": True,
                        "solver_prompt_hash_recorded": True,
                        "final_card_visible_in_state": full.json()["card_id"]
                        in [card.get("card_id") for card in final_state.get("cards") or []],
                    },
                    "clarification_card_id": clarify_card["card_id"],
                    "answer_card_id": full.json()["card_id"],
                    "ask_log": str(ask_log_artifact),
                    "ask_run_artifact": str(ask_run_artifact),
                    "final_state_artifact": str(final_state_artifact),
                    "claims": {
                        "proves": [
                            "automatic code-question path blocks Ask while transcript-to-leetcode returns needs_clarification",
                            "partial clarification answers do not invoke Ask",
                            "complete clarification answers rerun the same analysis input and invoke Ask once with solver_prompt",
                            "Ask answer cards preserve run_dir, response_path, response_sha256, transcript_sha256, and solver_prompt_sha256",
                        ],
                        "does_not_prove": [
                            "live microphone, PipeWire, or GPU STT inference",
                            "live Ask provider correctness",
                            "human UI form ergonomics for entering clarification answers",
                        ],
                    },
                }
                out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                shutil.copy2(out, Path("/tmp/live-evidence-leetcode-gate-eval-receipt.json"))
                print(f"leetcode gate receipt: {out}")
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
