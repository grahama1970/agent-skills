from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import dewey_issue_worker
from dewey_issue_worker import run_one_issue
from dewey_repair_queue import enqueue_issues, load_latest


def test_worker_claims_one_issue_and_exits_without_repair_cycle(tmp_path: Path, monkeypatch) -> None:
    def fake_run_lane(*args, **kwargs):
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "inline_embedding_policy",
            "terminal_status": "DRY_RUN_PASS",
            "ok": True,
            "scope": "all",
            "bulk_embedding_contract": "full_scope_apply",
            "mutation_applied": False,
            "proof_ok": False,
            "before_count": 2,
            "preflight": {"before_count": 2, "mutation_applied": False},
            "proof": {},
            "commands": [{"cmd": ["memory", "dewey_embedding_repair.py", "inline-vectors"], "dry_run": False}],
        }

    monkeypatch.setattr(dewey_issue_worker, "run_lane", fake_run_lane)
    queue = tmp_path / "repair_queue.jsonl"
    run_root = tmp_path / "runs"
    issues = [
        {
            "schema": "monitor_sparta.repair_issue.v1",
            "schema_version": 1,
            "issue_id": "inline-1",
            "status": "READY",
                "lane": "inline_embedding_policy",
                "dimension": "inline_embedding_policy",
                "collection": "sparta_controls",
                "expected_before_count": 2,
                "slice": {"scope": "all", "limit": None, "expected_before_count": 2},
                "priority": 10,
                "mutation_allowed": True,
                "requires_prompt_reviewer": False,
        }
    ]
    enqueue_issues(queue, issues)

    rc, receipt = run_one_issue(
        run_id="run-1",
        run_root=run_root,
        queue_path=queue,
        memory_root=tmp_path / "memory",
        agent_skills_root=tmp_path / "agent-skills",
        apply=False,
        bootstrap=False,
        bootstrap_limit=2,
        timeout_s=10,
        health_timeout_s=10,
        heartbeat_s=1,
    )

    assert rc == 0
    assert receipt["terminal_status"] == "DRY_RUN_DONE"
    assert receipt["claimed_issue_id"] == issues[0]["issue_id"]
    assert receipt["ran_more_than_one_lane"] is False
    assert receipt["ran_repair_cycle"] is False
    assert (run_root / "run-1" / "receipt.json").is_file()
    latest = load_latest(queue)
    assert latest[issues[0]["issue_id"]]["status"] == "DRY_RUN_DONE"


def test_worker_empty_queue_bootstrap_does_not_build_health_issues(tmp_path: Path) -> None:
    queue = tmp_path / "repair_queue.jsonl"
    run_root = tmp_path / "runs"

    rc, receipt = run_one_issue(
        run_id="run-empty",
        run_root=run_root,
        queue_path=queue,
        memory_root=tmp_path / "memory",
        agent_skills_root=tmp_path / "agent-skills",
        apply=False,
        bootstrap=True,
        bootstrap_limit=2,
        timeout_s=10,
        health_timeout_s=10,
        heartbeat_s=1,
    )

    assert rc == 3
    assert receipt["terminal_status"] == "NO_READY_ISSUE"
    assert receipt["bootstrap"]["reason"] == "queue_construction_owned_by_monitor_sparta"
