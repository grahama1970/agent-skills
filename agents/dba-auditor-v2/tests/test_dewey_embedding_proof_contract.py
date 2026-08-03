from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dewey_issue_worker
import dewey_lane_runner
from dewey_lane_runner import CommandResult
from dewey_repair_queue import enqueue_issue, load_latest


def _monitor_queue_module():
    path = ROOT.parents[2] / "memory" / "scripts" / "validation" / "monitor_sparta_repair_queue.py"
    spec = importlib.util.spec_from_file_location("monitor_sparta_repair_queue", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_monitor_queue_builder_emits_full_scope_embedding_issues(tmp_path: Path):
    builder = _monitor_queue_module()
    health = {
        "checks": [
            {"dimension": "embedding_gaps", "ok": False, "gaps": {"sparta_controls": {"missing": 5080}}},
            {"dimension": "inline_embedding_policy", "ok": False, "by_collection": [{"collection": "sparta_qra", "inline_embedding_arrays": 12}]},
            {"dimension": "qdrant_pointer_metadata", "ok": False, "collection": "sparta_url_knowledge", "missing_or_stale_pointer_count": 7},
        ]
    }
    issues = builder.issues_from_health(health, source="fixture-health.json", limit=1)
    by_lane = {issue["lane"]: issue for issue in issues}

    missing = by_lane["missing_qdrant_embeddings"]
    assert missing["slice"]["scope"] == "all"
    assert missing["slice"]["limit"] is None
    assert missing["expected_before_count"] == 5080
    assert missing["slice"]["observed_missing_count"] == 5080
    assert missing["success_condition"] == {"after_affected_count": 0}
    assert missing["slice"]["repair_primitive"].endswith("dewey_embedding_repair.py")

    inline = by_lane["inline_embedding_policy"]
    assert inline["slice"]["scope"] == "all"
    assert inline["slice"]["limit"] is None
    assert inline["expected_before_count"] == 12

    pointer = by_lane["qdrant_pointer_metadata"]
    assert pointer["slice"]["scope"] == "all"
    assert pointer["slice"]["limit"] is None
    assert pointer["expected_before_count"] == 7


def _issue(lane: str, **overrides):
    issue = {
        "issue_id": f"issue:{lane}",
        "lane": lane,
        "dimension": lane,
        "collection": "sparta_controls",
        "slice": {"scope": "all", "limit": None, "expected_before_count": 3},
        "expected_before_count": 3,
        "mutation_allowed": True,
        "requires_prompt_reviewer": False,
    }
    issue.update(overrides)
    return issue


def _fake_command_writer(*, apply_payload: dict | None = None, preflight_payload: dict | None = None):
    preflight_payload = preflight_payload or {"before_count": 3, "after_count": 3, "changed_count": 0}

    def fake_run_command(**kwargs):
        artifact_dir = Path(kwargs["artifact_dir"])
        cmd = list(kwargs["cmd"])
        output = Path(cmd[cmd.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        if "--dry-run" in cmd:
            output.write_text(json.dumps(preflight_payload) + "\n")
        else:
            payload = dict(apply_payload or {})
            if "rollback_manifest" in payload:
                rollback = Path(payload["rollback_manifest"])
                rollback.parent.mkdir(parents=True, exist_ok=True)
                rollback.write_text(''.join('{"_key":"k%s"}\n' % i for i in range(int(payload.get("rollback_records", 0)))))
            output.write_text(json.dumps(payload) + "\n")
        return CommandResult(
            id=kwargs["command_id"],
            cmd=cmd,
            cwd=str(kwargs.get("cwd")),
            exit_code=0,
            ok=True,
            dry_run=False,
            duration_s=0.01,
            timed_out=False,
        )

    return fake_run_command


def test_embedding_full_scope_command_omits_limit_and_keeps_batch_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dewey_lane_runner, "run_command", _fake_command_writer())
    issue = _issue("missing_qdrant_embeddings", slice={"scope": "all", "limit": None, "expected_before_count": 5080, "batch_size": 777})
    result = dewey_lane_runner.run_lane(
        issue,
        run_dir=tmp_path / "run",
        memory_root=tmp_path / "memory",
        agent_skills_root=tmp_path / "agent-skills",
        apply=False,
        timeout_s=60,
        heartbeat_s=1,
    )
    cmd = result["commands"][0]["cmd"]
    assert "--limit" not in cmd
    assert "--batch-size" in cmd
    assert "777" in cmd
    assert "dewey_embedding_repair.py" in " ".join(cmd)
    assert result["preflight"]["before_count"] == 3
    assert result["preflight"]["mutation_applied"] is False


def test_lane_result_extraction_fails_closed_when_rollback_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dewey_lane_runner, "run_command", _fake_command_writer(apply_payload={"before_count": 3, "after_count": 0, "changed_count": 3}))
    result = dewey_lane_runner.run_lane(
        _issue("missing_qdrant_embeddings"),
        run_dir=tmp_path / "run",
        memory_root=tmp_path / "memory",
        agent_skills_root=tmp_path / "agent-skills",
        apply=True,
        timeout_s=60,
        heartbeat_s=1,
    )
    assert result["terminal_status"] == "OPERATOR_REQUIRED"
    assert result["ok"] is False
    assert result["mutation_applied"] is False
    assert result["proof_ok"] is False
    assert "rollback_manifest" in result["proof"]["reason"]


def test_lane_result_extraction_succeeds_with_rollback_proof(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    rollback = tmp_path / "rollback.jsonl"
    monkeypatch.setattr(
        dewey_lane_runner,
        "run_command",
        _fake_command_writer(
            apply_payload={
                "before_count": 3,
                "after_count": 0,
                "changed_count": 3,
                "rollback_manifest": str(rollback),
                "rollback_records": 3,
            }
        ),
    )
    result = dewey_lane_runner.run_lane(
        _issue("missing_qdrant_embeddings"),
        run_dir=tmp_path / "run",
        memory_root=tmp_path / "memory",
        agent_skills_root=tmp_path / "agent-skills",
        apply=True,
        timeout_s=60,
        heartbeat_s=1,
    )
    assert result["terminal_status"] == "DONE"
    assert result["ok"] is True
    assert result["mutation_applied"] is True
    assert result["before_count"] == 3
    assert result["after_count"] == 0
    assert result["changed_count"] == 3
    assert result["rollback_records"] == 3
    assert result["proof_ok"] is True


def test_qdrant_pointer_apply_uses_memory_owned_primitive_not_legacy_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dewey_lane_runner, "run_command", _fake_command_writer())
    result = dewey_lane_runner.run_lane(
        _issue("qdrant_pointer_metadata"),
        run_dir=tmp_path / "run",
        memory_root=tmp_path / "memory",
        agent_skills_root=tmp_path / "agent-skills",
        apply=False,
        timeout_s=60,
        heartbeat_s=1,
    )
    cmd = result["commands"][0]["cmd"]
    assert "dewey_embedding_repair.py" in " ".join(cmd)
    assert "qdrant-pointer-metadata" in cmd
    assert "sparta_repair_manifests.py" not in " ".join(cmd)


def test_worker_receipt_surfaces_embedding_proof_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    queue = tmp_path / "repair_queue.jsonl"
    enqueue_issue(queue, _issue("missing_qdrant_embeddings"))

    def fake_run_lane(*args, **kwargs):
        return {
            "schema": "dewey.lane_result.v1",
            "lane": "missing_qdrant_embeddings",
            "terminal_status": "DONE",
            "ok": True,
            "mutation_applied": True,
            "proof_ok": True,
            "before_count": 3,
            "after_count": 0,
            "changed_count": 3,
            "rollback_manifest": str(tmp_path / "rollback.jsonl"),
            "rollback_records": 3,
            "preflight": {"before_count": 3, "mutation_applied": False},
            "proof": {"proof_ok": True, "before_count": 3, "after_count": 0, "changed_count": 3},
            "commands": [{"cmd": ["memory", "repair"], "dry_run": False}],
        }

    monkeypatch.setattr(dewey_issue_worker, "run_lane", fake_run_lane)
    rc, receipt = dewey_issue_worker.run_one_issue(
        run_id="run-proof",
        run_root=tmp_path / "runs",
        queue_path=queue,
        memory_root=tmp_path / "memory",
        agent_skills_root=tmp_path / "agent-skills",
        apply=True,
        bootstrap=False,
        bootstrap_limit=1,
        timeout_s=60,
        health_timeout_s=60,
        heartbeat_s=1,
    )
    assert rc == 0
    assert receipt["mutation_applied"] is True
    assert receipt["proof_ok"] is True
    assert receipt["before_count"] == 3
    assert receipt["after_count"] == 0
    assert receipt["changed_count"] == 3
    assert receipt["ran_more_than_one_lane"] is False
    assert receipt["ran_repair_cycle"] is False

    latest = load_latest(queue)
    assert list(latest.values())[0]["status"] == "DONE"
