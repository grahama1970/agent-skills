from __future__ import annotations

import sys
import json
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import dewey_lane_runner
from dewey_lane_runner import CommandResult, _terminal_from_commands, run_lane, write_json


def test_inline_lane_dry_run_never_calls_repair_cycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_command(**kwargs):
        artifact_dir = Path(kwargs["artifact_dir"])
        output = artifact_dir / "before_counts.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"before_count": 3, "after_count": 3, "changed_count": 0, "proof_ok": True}) + "\n")
        return CommandResult(
            id=kwargs["command_id"],
            cmd=list(kwargs["cmd"]),
            cwd=str(kwargs.get("cwd")),
            exit_code=0,
            ok=True,
            dry_run=False,
            duration_s=0.01,
            timed_out=False,
        )

    monkeypatch.setattr(dewey_lane_runner, "run_command", fake_run_command)
    issue = {
        "issue_id": "issue-1",
        "status": "RUNNING",
        "lane": "inline_embedding_policy",
        "dimension": "inline_embedding_policy",
        "collection": "sparta_controls",
        "expected_before_count": 3,
        "slice": {"scope": "all", "limit": None, "expected_before_count": 3},
        "mutation_allowed": True,
    }

    result = run_lane(
        issue,
        run_dir=tmp_path / "run",
        memory_root=tmp_path / "memory",
        agent_skills_root=tmp_path / "agent-skills",
        apply=False,
        timeout_s=10,
        heartbeat_s=1,
    )

    assert result["terminal_status"] == "DRY_RUN_PASS"
    assert result["ok"] is True
    assert result["mutation_applied"] is False
    assert result["preflight"]["before_count"] == 3
    commands = result["commands"]
    assert len(commands) == 1
    assert "repair-cycle" not in " ".join(commands[0]["cmd"])


def test_receipt_artifacts_reject_inline_vectors(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_json(tmp_path / "bad.json", {"embedding": [1.0, 2.0]})


def test_source_text_lane_uses_validation_script_path(tmp_path: Path) -> None:
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    issue = {
        "issue_id": "issue-source",
        "status": "RUNNING",
        "lane": "source_text_qra_coverage",
        "dimension": "source_text_qra_coverage",
        "slice": {"limit": 2},
        "mutation_allowed": False,
    }

    result = run_lane(
        issue,
        run_dir=tmp_path / "run-source",
        memory_root=memory_root,
        agent_skills_root=tmp_path / "agent-skills",
        apply=False,
        timeout_s=10,
        heartbeat_s=1,
    )

    cmd = result["commands"][0]["cmd"]
    assert "scripts/validation/source_text_qra_coverage.py" in " ".join(cmd)
    assert "scripts/source_text_qra_coverage.py" not in " ".join(cmd)


def test_create_qras_commands_use_uv_project(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"jobs": []}\n', encoding="utf-8")
    agent_skills = tmp_path / "agent-skills"
    create_qras_dir = agent_skills / "skills" / "create-qras"
    create_qras_dir.mkdir(parents=True)
    run_sh = create_qras_dir / "run.sh"
    run_sh.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    run_sh.chmod(0o755)
    issue = {
        "issue_id": "issue-qra",
        "status": "RUNNING",
        "lane": "qra_coverage_per_control",
        "dimension": "qra_coverage_per_control",
        "slice": {"limit": 1, "manifest_path": str(manifest)},
        "mutation_allowed": True,
        "requires_prompt_reviewer": False,
    }

    result = run_lane(
        issue,
        run_dir=tmp_path / "run-qra",
        memory_root=tmp_path / "memory",
        agent_skills_root=agent_skills,
        apply=False,
        timeout_s=10,
        heartbeat_s=1,
    )

    commands = [command["cmd"] for command in result["commands"]]
    assert commands
    for cmd in commands:
        assert cmd[:3] == ["uv", "run", "--project"]
        assert "./run.sh" in cmd


def test_timeout_classifies_as_blocked_timeout() -> None:
    result = CommandResult(
        id="timeout",
        cmd=["slow"],
        cwd=None,
        exit_code=143,
        ok=False,
        dry_run=False,
        duration_s=10.0,
        timed_out=True,
    )

    terminal, ok = _terminal_from_commands([result], dry_run=False)

    assert terminal == "BLOCKED_TIMEOUT"
    assert ok is False
