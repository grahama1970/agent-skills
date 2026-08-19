#!/usr/bin/env python3
"""Live eval for public LeetCode corpus ingestion and transcript recall."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

STORAGE_ROOT = Path("/mnt/storage12tb/skills/live-evidence/agentic-evals/leetcode-public-corpus")
_RAW_MEMORY_URL = os.getenv(
    "LIVE_EVIDENCE_EVAL_MEMORY_URL",
    os.getenv("MEMORY_SERVICE_URL", "http://127.0.0.1:8601"),
).rstrip("/")
# The login environment may export a unix:// socket URL for other memory
# clients; httpx lanes here require HTTP, so fall back to the local boundary.
MEMORY_URL = (
    _RAW_MEMORY_URL
    if _RAW_MEMORY_URL.startswith(("http://", "https://"))
    else "http://127.0.0.1:8601"
)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_profile(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: leetcode-public-corpus-live-eval",
                "memory_scope: live-evidence",
                "memory_collections:",
                "  - lessons_v2",
                "watch_terms:",
                "  - array",
                "  - target",
                "  - substring",
                "  - repeating characters",
                "  - linked list",
                "  - merge sorted lists",
                "project_aliases: {}",
                "repo_priorities: []",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_noop_memory_runner(path: Path) -> Path:
    runner = path / "memory-runner-noop.sh"
    runner.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "case \"${1:-}\" in",
                "  code-search) printf '{\"items\":[]}\\n' ;;",
                "  code-node) printf '{\"status\":\"not_found\"}\\n' ;;",
                "  *) printf '{\"items\":[]}\\n' ;;",
                "esac",
                "",
            ]
        ),
        encoding="utf-8",
    )
    runner.chmod(0o755)
    return runner


def run_importer(root: Path, receipt_dir: Path) -> dict[str, Any]:
    receipt_path = receipt_dir / "import-receipt.json"
    command = [
        sys.executable,
        str(root / "scripts" / "ingest_leetcode_public_repos.py"),
        "--memory-url",
        MEMORY_URL,
        "--receipt-path",
        str(receipt_path),
        "--max-records",
        "350",
        "--probe-title",
        "Two Sum",
        "--probe-title",
        "Longest Substring Without Repeating Characters",
        "--probe-title",
        "Merge k Sorted Lists",
    ]
    result = subprocess.run(command, cwd=root, check=False, capture_output=True, text=True, timeout=300)
    (receipt_dir / "import-stdout.log").write_text(result.stdout, encoding="utf-8")
    (receipt_dir / "import-stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"leetcode importer failed: {result.stderr or result.stdout}")
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    checks = payload.get("checks") or {}
    if not all(checks.values()):
        raise RuntimeError(f"leetcode importer checks failed: {checks}")
    return payload


def post_turn(client: httpx.Client, text: str, sequence: int) -> None:
    response = client.post(
        "/api/transcript",
        json={
            "schema": "live_evidence.transcript_event.v1",
            "event_id": f"leetcode_public_eval_turn_{sequence:04d}",
            "speaker": "interviewer",
            "kind": "final",
            "source": "api",
            "sequence": sequence,
            "start_ms": sequence * 1_000,
            "end_ms": sequence * 1_000 + 2_500,
            "text": text,
        },
    )
    response.raise_for_status()


def wait_for_cards(client: httpx.Client, count: int, *, timeout_s: float = 14.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get("/api/state")
        response.raise_for_status()
        last_state = response.json()
        if len(last_state.get("cards") or []) >= count:
            return last_state
        time.sleep(0.15)
    raise RuntimeError(f"timed out waiting for {count} cards: {last_state}")


def assert_card_has_memory_match(card: dict[str, Any], expected_key: str, expected_title: str) -> dict[str, Any]:
    sources = card.get("sources") or []
    memory_sources = [source for source in sources if source.get("lane") == "memory"]
    keys = [(source.get("metadata") or {}).get("_key") for source in memory_sources]
    if expected_key not in keys:
        raise RuntimeError(f"missing expected Memory key {expected_key}: {card}")
    serialized = json.dumps(card, sort_keys=True)
    for term in [expected_title, "Clarify:", "leetcode-problem-index"]:
        if term not in serialized:
            raise RuntimeError(f"card missing imported-corpus term {term}: {card}")
    return {
        "card_id": card.get("card_id"),
        "expected_key": expected_key,
        "memory_source_count": len(memory_sources),
        "source_count": len(sources),
        "top_memory_keys": keys[:5],
    }


def run_eval(root: Path, receipt_path: Path | None) -> Path:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = receipt_path or STORAGE_ROOT / run_id / "receipt.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import_receipt = run_importer(root, out_path.parent)

    runtime_dir = out_path.parent / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    profile_path = runtime_dir / "profile.yaml"
    data_dir = runtime_dir / "data"
    write_profile(profile_path)
    memory_runner = write_noop_memory_runner(runtime_dir)
    port = free_port()
    env = {
        **os.environ,
        "LIVE_EVIDENCE_DATA_DIR": str(data_dir),
        "LIVE_EVIDENCE_PROFILE": str(profile_path),
        "LIVE_EVIDENCE_REPOS": "",
        "LIVE_EVIDENCE_HTTP_TIMEOUT": "8",
        "LIVE_EVIDENCE_PROCESS_TIMEOUT": "2",
        "LIVE_EVIDENCE_MAX_CARDS": "5",
        "LIVE_EVIDENCE_MEMORY_RUNNER": str(memory_runner),
        "MEMORY_SERVICE_URL": MEMORY_URL,
    }
    log_path = out_path.parent / "server.log"
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
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10.0) as app:
            for _ in range(100):
                try:
                    if app.get("/api/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError(f"server did not start; log={log_path.read_text(encoding='utf-8')}")
            app.post("/api/session/start", json={"consent_confirmed": True}).raise_for_status()

            checks: list[dict[str, Any]] = []
            scenarios = [
                (
                    "Given an array of integers and a target, return two indices whose values add up to the target.",
                    "live-evidence-leetcode-public-two-sum",
                    "LeetCode: Two Sum",
                ),
                (
                    "How do you find the length of the longest substring without repeating characters?",
                    "live-evidence-leetcode-public-longest-substring-without-repeating-characters",
                    "LeetCode: Longest Substring Without Repeating Characters",
                ),
            ]
            for index, (text, expected_key, expected_title) in enumerate(scenarios, start=1):
                post_turn(app, text, index)
                state = wait_for_cards(app, index)
                checks.append(assert_card_has_memory_match(state["cards"][0], expected_key, expected_title))
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    receipt = {
        "schema": "live_evidence.leetcode_public_corpus_eval_receipt.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "memory_url": MEMORY_URL,
        "import_receipt": str(out_path.parent / "import-receipt.json"),
        "import_summary": {
            "unique_problem_count": import_receipt.get("unique_problem_count"),
            "selected_record_count": import_receipt.get("selected_record_count"),
            "upsert": import_receipt.get("upsert"),
            "source_repo_heads": import_receipt.get("source_repo_heads"),
        },
        "checks": {
            "public_repos_parsed": True,
            "memory_upsert_completed": True,
            "two_sum_transcript_matched_memory": True,
            "substring_transcript_matched_memory": True,
            "cards_include_clarifying_questions": True,
        },
        "card_checks": checks,
        "artifacts": {"server_log": str(log_path)},
        "claims": {
            "proves": [
                "A bounded public GitHub LeetCode corpus was ingested into real Memory through /upsert.",
                "Live Evidence transcript questions can retrieve imported LeetCode Memory records into visible evidence cards.",
                "The card content includes reasoning/clarification context from Memory, not hardcoded React data.",
            ],
            "does_not_prove": [
                "Full corpus coverage beyond the importer selected_record_count.",
                "Canonical LeetCode prompt text completeness.",
                "Live microphone/PipeWire/GPU STT capture.",
                "Live external Ask provider execution.",
            ],
        },
    }
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "receipt": str(out_path)}, indent=2))
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--receipt-path", type=Path)
    args = parser.parse_args()
    run_eval(args.root.resolve(), args.receipt_path)


if __name__ == "__main__":
    main()
