#!/usr/bin/env python3
"""Live Memory recall eval for LeetCode-style interview problem cards."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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


_RAW_MEMORY_URL = os.getenv(
    "LIVE_EVIDENCE_EVAL_MEMORY_URL",
    os.getenv("MEMORY_SERVICE_URL", "http://127.0.0.1:8601"),
).rstrip("/")
MEMORY_URL = (
    _RAW_MEMORY_URL
    if _RAW_MEMORY_URL.startswith(("http://", "https://"))
    else "http://127.0.0.1:8601"
)
STORAGE_ROOT = Path("/mnt/storage12tb/skills/live-evidence/agentic-evals/leetcode-memory-recall")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_profile(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: leetcode-memory-recall-live-eval",
                "memory_scope: live-evidence",
                "memory_collections:",
                "  - project_memory_active",
                "watch_terms:",
                "  - minimum remove",
                "  - valid parentheses",
                "  - opening parentheses",
                "  - closing parentheses",
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


def memory_health(client: httpx.Client) -> dict[str, Any]:
    response = client.get("/health")
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Memory health is not ok: {payload}")
    return payload


def promote_problem_record(client: httpx.Client, run_id: str) -> dict[str, Any]:
    source_key = f"live-evidence-eval-source-minimum-remove-valid-parentheses-{run_id}"
    topic_id = f"leetcode/minimum-remove-to-make-valid-parentheses/{run_id}"
    now = datetime.now(UTC).isoformat()
    problem_text = (
        "LeetCode Minimum Remove to Make Valid Parentheses: Given a string with opening "
        "and closing parentheses, remove the minimum number of parentheses so the result "
        "is valid. Answer outline: use a stack of opening-parenthesis indices and a set "
        "of invalid closing/opening indices, then rebuild the string. Canonical URL "
        "https://leetcode.com/problems/minimum-remove-to-make-valid-parentheses/. "
        "Public source index https://github.com/haoel/leetcode. "
        f"Live Evidence eval marker {run_id}."
    )
    source_doc = {
        "_key": source_key,
        "kind": "leetcode_public_index_source",
        "title": "Public LeetCode index source",
        "source_repo": "haoel/leetcode",
        "source_url": "https://github.com/haoel/leetcode",
        "retrieval_text": problem_text,
        "tags": ["live-evidence-eval", "leetcode", "public-github-index"],
        "observed_at": now,
    }
    upsert = client.post(
        "/upsert",
        json={"collection": "leetcode_problem_index", "documents": [source_doc]},
        headers={"X-Caller-Skill": "live-evidence"},
    )
    upsert.raise_for_status()
    upsert_payload = upsert.json()
    if upsert_payload.get("errors"):
        raise RuntimeError(f"source upsert returned errors: {upsert_payload}")

    candidate = {
        "_key": f"live-evidence-eval-minimum-remove-valid-parentheses-{run_id}",
        "project_id": "live-evidence",
        "scope_key": "live-evidence",
        "topic_id": topic_id,
        "topic_kind": "leetcode_problem",
        "title": "LeetCode: Minimum Remove to Make Valid Parentheses",
        "text": problem_text,
        "retrieval_text": problem_text,
        "claims": [
            {
                "type": "answer_outline",
                "text": "Use stack/set of invalid indices, then rebuild the string.",
                "evidence_refs": [f"leetcode_problem_index/{source_key}"],
            }
        ],
        "input_digest": "github:haoel/leetcode",
        "source_digest": "sha256:" + hashlib.sha256(problem_text.encode("utf-8")).hexdigest(),
        "generated_by": {"tool": "live-evidence-agentic-eval", "run_id": run_id},
        "tags": [
            "live-evidence",
            "leetcode",
            "leetcode-problem-index",
            "string",
            "stack",
            "parentheses",
        ],
        "created_at": now,
        "updated_at": now,
    }
    stage = client.post(
        "/project-memory/stage",
        json={
            "candidate": candidate,
            "evidence_refs": [f"leetcode_problem_index/{source_key}"],
            "run": {
                "project_id": "live-evidence",
                "scope_key": "live-evidence",
                "status": "leetcode-memory-recall-eval-stage",
            },
        },
        headers={"X-Caller-Skill": "live-evidence"},
    )
    stage.raise_for_status()
    stage_payload = stage.json()
    if not stage_payload.get("ok"):
        raise RuntimeError(f"project-memory stage failed: {stage_payload}")

    promote = client.post(
        "/project-memory/promote",
        json={
            "candidate_ref": stage_payload["candidate_ref"],
            "run_ref": stage_payload["run_ref"],
            "expected_head": {
                "project_id": "live-evidence",
                "topic_id": topic_id,
                "generation": 0,
            },
            "approval_required": False,
        },
        headers={"X-Caller-Skill": "live-evidence"},
    )
    promote.raise_for_status()
    promote_payload = promote.json()
    if not promote_payload.get("ok"):
        raise RuntimeError(f"project-memory promote failed: {promote_payload}")

    recall_payload: dict[str, Any] = {}
    top_keys: list[str] = []
    recall_request = {
        "q": (
            "How do I remove minimum invalid parentheses from a string and return "
            f"a valid string for Live Evidence eval marker {run_id}?"
        ),
        "k": 8,
        "scope": "live-evidence",
        "collections": ["project_memory_active"],
    }
    deadline = time.monotonic() + 12.0
    while time.monotonic() < deadline:
        recall = client.post(
            "/recall",
            json=recall_request,
            headers={"X-Caller-Skill": "live-evidence"},
        )
        recall.raise_for_status()
        recall_payload = recall.json()
        top_keys = [str(item.get("_key") or "") for item in recall_payload.get("items") or []]
        if candidate["_key"] in top_keys:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError(f"promoted project-memory record was not recalled: {recall_payload}")

    return {
        "source_upsert": upsert_payload,
        "stage": stage_payload,
        "promote": promote_payload,
        "recall": {
            "found": recall_payload.get("found"),
            "confidence": recall_payload.get("confidence"),
            "top_keys": top_keys,
            "item_count": len(recall_payload.get("items") or []),
        },
        "candidate_key": candidate["_key"],
        "topic_id": topic_id,
        "run_id": run_id,
        "source_ref": f"leetcode_problem_index/{source_key}",
    }


def post_turn(client: httpx.Client, text: str) -> None:
    response = client.post(
        "/api/transcript",
        json={
            "schema": "live_evidence.transcript_event.v1",
            "event_id": "leetcode_memory_recall_eval_turn_0001",
            "speaker": "interviewer",
            "kind": "final",
            "source": "api",
            "sequence": 1,
            "start_ms": 1000,
            "end_ms": 6800,
            "text": text,
        },
    )
    response.raise_for_status()


def wait_for_card(client: httpx.Client, *, timeout_s: float = 12.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get("/api/state")
        response.raise_for_status()
        last_state = response.json()
        cards = last_state.get("cards") or []
        if cards:
            return cards[0]
        time.sleep(0.15)
    raise RuntimeError(f"timed out waiting for Memory-backed card; last_state={last_state}")


def assert_memory_card(card: dict[str, Any], candidate_key: str) -> dict[str, Any]:
    sources = card.get("sources") or []
    memory_sources = [source for source in sources if source.get("lane") == "memory"]
    if card.get("status") != "supported":
        raise RuntimeError(f"expected supported Memory card: {card}")
    if not memory_sources:
        raise RuntimeError(f"card did not include a Memory source: {card}")
    first_key = (memory_sources[0].get("metadata") or {}).get("_key")
    if first_key != candidate_key:
        raise RuntimeError(f"first Memory source was not the promoted candidate: {first_key} != {candidate_key}")
    serialized = json.dumps(card, sort_keys=True)
    required_terms = [
        candidate_key,
        "Minimum Remove to Make Valid Parentheses",
        "stack",
        "rebuild",
        "project_memory_active",
    ]
    missing = [term for term in required_terms if term not in serialized]
    if missing:
        raise RuntimeError(f"Memory card missing terms {missing}: {card}")
    return {
        "card_id": card.get("card_id"),
        "source_count": len(sources),
        "memory_source_count": len(memory_sources),
        "first_memory_label": memory_sources[0].get("label"),
        "first_memory_key": first_key,
    }


def run_eval(root: Path, receipt_path: Path | None) -> Path:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    default_receipt = STORAGE_ROOT / run_id / "receipt.json"
    out_path = receipt_path or default_receipt
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=MEMORY_URL, timeout=httpx.Timeout(30.0, connect=2.0)) as memory:
        health = memory_health(memory)
        memory_seed = promote_problem_record(memory, run_id)

    with tempfile.TemporaryDirectory(prefix="live-evidence-leetcode-memory-") as temp_name:
        temp = Path(temp_name)
        profile_path = temp / "profile.yaml"
        data_dir = temp / "data"
        write_profile(profile_path)
        memory_runner = write_noop_memory_runner(temp)
        port = free_port()
        env = {
            **os.environ,
            "LIVE_EVIDENCE_DATA_DIR": str(data_dir),
            "LIVE_EVIDENCE_PROFILE": str(profile_path),
            "LIVE_EVIDENCE_REPOS": "",
            "LIVE_EVIDENCE_HTTP_TIMEOUT": "6",
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
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=8.0) as app:
                for _ in range(80):
                    try:
                        if app.get("/api/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"server did not start; log={log_path.read_text(encoding='utf-8')}")
                app.post("/api/session/start", json={"consent_confirmed": True}).raise_for_status()
                post_turn(
                    app,
                    (
                        "How do I solve the interview problem where given a string with opening "
                        "and closing parentheses, I remove the minimum number of parentheses "
                        f"so the result is valid for Live Evidence eval marker {run_id}?"
                    ),
                )
                card = wait_for_card(app)
                card_check = assert_memory_card(card, memory_seed["candidate_key"])
                state = app.get("/api/state").json()
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    receipt = {
        "schema": "live_evidence.leetcode_memory_recall_eval_receipt.v1",
        "status": "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "memory_url": MEMORY_URL,
        "memory_health": health,
        "memory_seed": memory_seed,
        "checks": {
            "memory_health_ok": bool(health.get("ok")),
            "project_memory_promoted": True,
            "memory_recall_returned_seed": True,
            "transcript_triggered_card": True,
            "card_has_memory_source": True,
            "card_has_problem_answer_terms": True,
        },
        "card_check": card_check,
        "state_counts": {
            "cards": len(state.get("cards") or []),
            "transcript": len(state.get("transcript") or []),
        },
        "claims": {
            "proves": [
                "Live Evidence can retrieve a LeetCode-style problem record from real Memory /recall after transcript ingestion.",
                "The question/answer content is stored in Memory project_memory_active, not hardcoded in React.",
            ],
            "does_not_prove": [
                "Bulk ingestion of all public GitHub LeetCode repositories.",
                "Live microphone/PipeWire/STT audio capture.",
                "Ask provider solution generation.",
            ],
        },
        "artifacts": {"server_log": str(log_path)},
    }
    out_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    mirror = Path("/tmp/live-evidence-leetcode-memory-recall-receipt.json")
    mirror.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--receipt-path", type=Path)
    args = parser.parse_args()
    receipt = run_eval(args.root.resolve(), args.receipt_path)
    print(json.dumps({"status": "PASS", "receipt": str(receipt)}, indent=2))


if __name__ == "__main__":
    main()
