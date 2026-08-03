from pathlib import Path
import json
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dewey_lane_runner
from dewey_lane_runner import CommandResult, apply_precondition_error, run_lane
from dewey_repair_queue import normalize_issue


def base_issue(lane="missing_qdrant_embeddings", *, slice_=None, mutation_allowed=True):
    return normalize_issue({
        "issue_id": f"test:{lane}",
        "lane": lane,
        "dimension": "embedding_gaps",
        "collection": "sparta_controls",
        "status": "READY",
        "mutation_allowed": mutation_allowed,
        "expected_before_count": 9,
        "slice": {"scope": "all", "limit": None, "expected_before_count": 9, **(slice_ or {})},
    })


def fake_preflight_command(**kwargs):
    artifact_dir = Path(kwargs["artifact_dir"])
    cmd = list(kwargs["cmd"]); output = Path(cmd[cmd.index("--output") + 1])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"before_count": 9, "after_count": 9, "changed_count": 0}) + "\n")
    return CommandResult(
        id=kwargs["command_id"],
        cmd=list(kwargs["cmd"]),
        cwd=str(kwargs.get("cwd")),
        exit_code=0,
        ok=True,
        dry_run=False,
        duration_s=0.01,
        timed_out=False,
        stdout_path=str(artifact_dir / "stdout.log"),
        stderr_path=str(artifact_dir / "stderr.log"),
    )


def test_embedding_apply_requires_full_scope_when_limited():
    issue = base_issue(slice_={"scope": "limited", "limit": 10})
    assert apply_precondition_error(issue, lane="missing_qdrant_embeddings") == (
        "embedding apply requires full scope: set slice.scope='all' or omit/clear slice.limit"
    )


def test_embedding_apply_accepts_all_scope_and_omits_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(dewey_lane_runner, "run_command", fake_preflight_command)
    issue = base_issue(slice_={"scope": "all", "limit": None, "batch_size": 777})
    assert apply_precondition_error(issue, lane="missing_qdrant_embeddings") is None
    result = run_lane(
        issue,
        run_dir=tmp_path / "run",
        memory_root=tmp_path / "memory",
        agent_skills_root=tmp_path / "agent-skills",
        apply=False,
        timeout_s=10,
        heartbeat_s=1,
    )
    cmd = result["commands"][0]["cmd"]
    assert result["scope"] == "all"
    assert result["limit"] is None
    assert result["batch_size"] == 777
    assert result["bulk_embedding_contract"] == "full_scope_apply"
    assert "dewey_embedding_repair.py" in " ".join(cmd)
    assert "--dry-run" in cmd
    assert "--limit" not in cmd
    assert cmd[cmd.index("--batch-size") + 1] == "777"


def test_limited_embedding_dry_run_fails_fast_without_command(tmp_path):
    issue = base_issue(slice_={"scope": "limited", "limit": 5, "batch_size": 5})
    result = run_lane(
        issue,
        run_dir=tmp_path / "run",
        memory_root=tmp_path / "memory",
        agent_skills_root=tmp_path / "agent-skills",
        apply=False,
        timeout_s=10,
        heartbeat_s=1,
    )
    assert result["terminal_status"] == "OPERATOR_REQUIRED"
    assert result["commands"] == []
    assert "finite limit" in result["reason"] or "full scope" in result["reason"]
