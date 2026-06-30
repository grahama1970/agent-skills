from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QRA_SCRIPTS = ROOT / "qra-auditor" / "scripts"
UX_SCRIPTS = ROOT / "ux-coverage-auditor" / "scripts"
OPS_SCRIPTS = ROOT / "ops-arango" / "scripts"
for path in (QRA_SCRIPTS, UX_SCRIPTS, OPS_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import ops_arango_issue_worker
import ux_coverage_issue_worker


def append_issue(queue: Path, issue: dict) -> None:
    queue.parent.mkdir(parents=True, exist_ok=True)
    with queue.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(issue, sort_keys=True) + "\n")


def fake_tau_handoff(run_dir: Path, *, filename_stem: str, handoff: dict, active_goal_hash: str = "") -> dict:
    handoff_path = run_dir / f"{filename_stem}.tau_handoff.json"
    validation_path = run_dir / f"{filename_stem}.tau_validation.json"
    handoff_path.write_text(json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validation = {"ok": True, "mocked": True, "live": False, "active_goal_hash": active_goal_hash}
    validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "schema": "tau.agent_handoff.artifacts.v1",
        "handoff_path": str(handoff_path),
        "validation_path": str(validation_path),
        "validation": validation,
        "ok": True,
    }


def test_ux_coverage_worker_emits_tau_handoff(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ux_coverage_issue_worker, "write_tau_handoff_artifacts", fake_tau_handoff)
    queue = tmp_path / "repair_queue.jsonl"
    run_root = tmp_path / "runs"
    append_issue(
        queue,
        {
            "schema": "monitor_sparta.repair_issue.v1",
            "issue_id": "ux-1",
            "status": "READY",
            "lane": "ux_coverage",
            "owner_subagent": "ux-coverage-auditor",
            "priority": 42,
            "source_check": {"failures": ["missing data-qid"], "checked_files": ["ui.tsx"]},
            "slice": {"observed_guardrail_failures": 1},
        },
    )

    rc, receipt = ux_coverage_issue_worker.run(
        argparse.Namespace(
            run_id="ux-run",
            run_root=run_root,
            queue=queue,
            memory_root=tmp_path / "memory",
            issue_id=None,
            apply=False,
        )
    )

    assert rc == 0
    assert receipt["terminal_status"] == "REVIEW_REQUIRED"
    assert receipt["tau_handoff"]["ok"] is True
    handoff = json.loads(Path(receipt["tau_handoff"]["handoff_path"]).read_text(encoding="utf-8"))
    assert handoff["schema"] == "tau.agent_handoff.v1"
    assert handoff["previous_subagent"] == "ux-coverage-auditor"
    assert handoff["next_agent"]["name"] == "human"
    assert "fresh monitor-sparta health JSON" in handoff["required_evidence"][0]


def test_ops_arango_worker_emits_tau_handoff_for_operator_required(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ops_arango_issue_worker, "write_tau_handoff_artifacts", fake_tau_handoff)
    queue = tmp_path / "repair_queue.jsonl"
    run_root = tmp_path / "runs"
    append_issue(
        queue,
        {
            "schema": "monitor_sparta.repair_issue.v1",
            "issue_id": "backup-1",
            "status": "READY",
            "lane": "backup_freshness",
            "owner_subagent": "ops-arango",
            "priority": 90,
            "source_check": {"age_hours": 99, "max_age_hours": 24},
            "slice": {"age_hours": 99, "max_age_hours": 24},
        },
    )

    rc, receipt = ops_arango_issue_worker.run(
        argparse.Namespace(
            run_id="ops-run",
            run_root=run_root,
            queue=queue,
            memory_root=tmp_path / "memory",
            issue_id=None,
            apply=False,
            timeout_s=10,
        )
    )

    assert rc == 0
    assert receipt["terminal_status"] == "OPERATOR_REQUIRED"
    assert receipt["tau_handoff"]["ok"] is True
    handoff = json.loads(Path(receipt["tau_handoff"]["handoff_path"]).read_text(encoding="utf-8"))
    assert handoff["schema"] == "tau.agent_handoff.v1"
    assert handoff["previous_subagent"] == "ops-arango"
    assert handoff["next_agent"]["name"] == "human"
    assert "latest_backup_receipt.json exists" in handoff["required_evidence"]
