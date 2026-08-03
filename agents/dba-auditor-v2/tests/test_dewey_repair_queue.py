from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from dewey_repair_queue import claim_one, enqueue_issues, load_latest, summarize, update_issue


def issue(issue_id: str, lane: str, *, priority: int, collection: str = "sparta_controls") -> dict:
    return {
        "schema": "monitor_sparta.repair_issue.v1",
        "schema_version": 1,
        "issue_id": issue_id,
        "status": "READY",
        "lane": lane,
        "dimension": lane,
        "collection": collection,
        "slice": {"limit": 1},
        "priority": priority,
        "mutation_allowed": True,
        "requires_prompt_reviewer": lane == "qra_coverage_per_control",
    }


def test_claim_one_is_deterministic_and_append_only(tmp_path: Path) -> None:
    queue = tmp_path / "repair_queue.jsonl"
    issues = [
        issue("missing", "missing_qdrant_embeddings", priority=30, collection="b"),
        issue("inline", "inline_embedding_policy", priority=10, collection="a"),
    ]
    enqueue_issues(queue, issues)

    claimed = claim_one(queue, run_id="run-1")

    assert claimed is not None
    assert claimed["lane"] == "inline_embedding_policy"  # priority beats embedding_gaps
    assert claimed["status"] == "RUNNING"
    update_issue(queue, claimed, status="DONE", result={"ok": True})
    latest = load_latest(queue)
    assert latest[claimed["issue_id"]]["status"] == "DONE"
    summary = summarize(queue)
    assert summary["counts_by_status"]["DONE"] == 1
    assert summary["counts_by_status"]["READY"] == 1


def test_unknown_schema_version_fails_closed(tmp_path: Path) -> None:
    queue = tmp_path / "repair_queue.jsonl"
    enqueue_issues(queue, [dict(issue("bad", "inline_embedding_policy", priority=10), schema_version=999)])

    claimed = claim_one(queue, run_id="run-1")

    assert claimed is None
    summary = summarize(queue)
    assert summary["ready_issue_ids"] == []
