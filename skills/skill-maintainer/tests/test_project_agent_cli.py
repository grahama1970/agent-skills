from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest


def load_cli():
    path = Path(__file__).resolve().parents[1] / "scripts" / "project_agent_cli.py"
    spec = importlib.util.spec_from_file_location("project_agent_cli", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_is_terminal_requires_success_status_and_completed_disposition():
    cli = load_cli()

    assert cli.is_terminal({
        "status": "fixed_with_deterministic_proof_webgpt_advisory",
        "terminal_disposition_status": "completed",
    })
    assert not cli.is_terminal({
        "status": "fixed_with_deterministic_proof_webgpt_advisory",
        "terminal_disposition_status": "not_started",
    })


def test_is_terminal_treats_blockers_as_terminal():
    cli = load_cli()

    assert cli.is_terminal({"status": "blocked_publication:git_commit_failed"})
    assert cli.is_terminal({"closure_decision": "blocked_waiting_for_human"})


def test_is_terminal_allows_review_receipt_blocks_to_resume():
    cli = load_cli()

    assert not cli.is_terminal({"status": "blocked_invalid_review_receipt:nonpassing_decision:fail"})


def test_step_uses_webgpt_when_receipt_gate_passes(monkeypatch, tmp_path):
    cli = load_cli()
    calls = []

    monkeypatch.setattr(cli, "status_for", lambda issue_dir: {
        "phase": "terminal_disposition",
        "receipt_gate": {"overall": "pass"},
    })
    monkeypatch.setattr(cli, "run_cycle", lambda args: calls.append(args) or {"status": "ok"})

    assert cli.step(tmp_path, run_webgpt=True) == {"status": "ok"}
    assert calls == [["--continue-issue-dir", str(tmp_path), "--run-webgpt"]]


def test_step_dispatches_subagents_before_receipt_gate_passes(monkeypatch, tmp_path):
    cli = load_cli()
    calls = []

    monkeypatch.setattr(cli, "status_for", lambda issue_dir: {
        "phase": "repair",
        "receipt_gate": {"overall": "blocked"},
    })
    monkeypatch.setattr(cli, "run_cycle", lambda args: calls.append(args) or {"status": "ok"})

    assert cli.step(tmp_path, run_webgpt=True) == {"status": "ok"}
    assert calls == [["--continue-issue-dir", str(tmp_path), "--dispatch-subagents", "--run-webgpt"]]


def test_step_can_dispatch_without_webgpt(monkeypatch, tmp_path):
    cli = load_cli()
    calls = []

    monkeypatch.setattr(cli, "status_for", lambda issue_dir: {
        "phase": "repair",
        "receipt_gate": {"overall": "blocked"},
    })
    monkeypatch.setattr(cli, "run_cycle", lambda args: calls.append(args) or {"status": "ok"})

    assert cli.step(tmp_path, run_webgpt=False) == {"status": "ok"}
    assert calls == [["--continue-issue-dir", str(tmp_path), "--dispatch-subagents"]]


def test_step_respects_no_webgpt_after_receipt_gate_passes(monkeypatch, tmp_path):
    cli = load_cli()
    calls = []

    monkeypatch.setattr(cli, "status_for", lambda issue_dir: {
        "phase": "terminal_disposition",
        "receipt_gate": {"overall": "pass"},
    })
    monkeypatch.setattr(cli, "run_cycle", lambda args: calls.append(args) or {"status": "ok"})

    assert cli.step(tmp_path, run_webgpt=False) == {"status": "ok"}
    assert calls == [["--continue-issue-dir", str(tmp_path), "--dispatch-subagents"]]


def test_scheduler_invokes_single_issue_cycle_and_writes_event_log(monkeypatch, tmp_path, capsys):
    cli = load_cli()
    calls = []
    event_log = tmp_path / "scheduler-events.jsonl"
    monkeypatch.setattr(cli, "SCHEDULER_EVENT_LOG", event_log)
    monkeypatch.setattr(cli, "run_cycle", lambda args: calls.append(args) or {
        "status": "repair_subagent_started",
        "artifact_dir": "/tmp/issue-17",
        "issue": 17,
        "closure_decision": "waiting_for_repair_subagent_receipt",
    })

    code = cli.command_scheduler(argparse.Namespace(
        issue=None,
        max_issues=1,
        run_webgpt=True,
        github_dry_run=False,
    ))

    stdout_lines = capsys.readouterr().out.strip().splitlines()
    event_lines = event_log.read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in event_lines]

    assert code == 0
    assert calls == [["--max-issues", "1", "--dispatch-subagents", "--run-webgpt"]]
    assert [event["event"] for event in events] == ["scheduler_tick", "scheduler_result"]
    assert events[1]["issue"] == 17
    assert stdout_lines[0] == event_lines[0]
    assert stdout_lines[1] == event_lines[1]
    assert json.loads("\n".join(stdout_lines[2:]))["status"] == "repair_subagent_started"


def test_scheduler_can_target_explicit_issue(monkeypatch, tmp_path, capsys):
    cli = load_cli()
    calls = []
    event_log = tmp_path / "scheduler-events.jsonl"
    monkeypatch.setattr(cli, "SCHEDULER_EVENT_LOG", event_log)
    monkeypatch.setattr(cli, "run_cycle", lambda args: calls.append(args) or {
        "status": "repair_subagent_started",
        "artifact_dir": "/tmp/issue-15",
        "issue": 15,
        "closure_decision": "waiting_for_repair_subagent_receipt",
    })

    code = cli.command_scheduler(argparse.Namespace(
        issue=15,
        max_issues=1,
        run_webgpt=True,
        github_dry_run=False,
    ))

    stdout_lines = capsys.readouterr().out.strip().splitlines()
    events = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()]

    assert code == 0
    assert calls == [["--issue", "15", "--dispatch-subagents", "--run-webgpt"]]
    assert events[1]["issue"] == 15
    assert json.loads("\n".join(stdout_lines[2:]))["issue"] == 15


def test_run_cycle_preserves_nonzero_json_artifact_result(monkeypatch, tmp_path):
    cli = load_cli()
    issue_dir = tmp_path / "issue-16"

    class Completed:
        returncode = 2
        stdout = json.dumps({
            "status": "blocked_missing_target_paths",
            "artifact_dir": str(issue_dir),
            "issue": 16,
        })
        stderr = ""

    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: Completed())

    result = cli.run_cycle(["--issue", "16", "--dispatch-subagents"])

    assert result["status"] == "blocked_missing_target_paths"
    assert result["artifact_dir"] == str(issue_dir)
    assert result["cycle_returncode"] == 2
    assert result["cycle_cmd"][-3:] == ["--issue", "16", "--dispatch-subagents"]


def test_drive_fresh_issue_persists_emitted_events(monkeypatch, tmp_path, capsys):
    cli = load_cli()
    issue_dir = tmp_path / "issue-13"
    event_log = issue_dir / "drive-events.jsonl"

    def fake_run_cycle(args):
        if args == ["--issue", "13", "--dispatch-subagents"]:
            return {
                "status": "repair_subagent_started",
                "artifact_dir": str(issue_dir),
                "issue": 13,
            }
        if args == ["--status-issue-dir", str(issue_dir)]:
            return {
                "status": "fixed_with_deterministic_proof",
                "phase": "terminal_disposition",
                "closure_decision": "fixed_with_deterministic_proof",
                "terminal_disposition_status": "completed",
            }
        raise AssertionError(f"unexpected run_cycle args: {args}")

    monkeypatch.setattr(cli, "run_cycle", fake_run_cycle)

    code = cli.command_drive(argparse.Namespace(
        issue=13,
        artifact_dir=None,
        timeout_seconds=60,
        poll_seconds=0,
        run_webgpt=False,
        file_audit_issue=False,
    ))

    stdout_lines = capsys.readouterr().out.strip().splitlines()
    file_lines = event_log.read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in stdout_lines]

    assert code == 0
    assert file_lines == stdout_lines
    assert [event["event"] for event in events] == ["start", "event_log", "status", "post_job_audit", "terminal"]
    assert events[1]["event_log_path"] == str(event_log)
    assert events[3]["classification"] == "maintainer_ok"
    audit = json.loads((issue_dir / "post-job-audit.json").read_text(encoding="utf-8"))
    assert audit["classification"] == "maintainer_ok"
    assert audit["recommended_action"] == "none"
    assert audit["event_log"] == str(event_log)
    assert "drive-events.jsonl" in audit["evidence_paths"]


def test_drive_fresh_issue_fail_closed_start_writes_audit(monkeypatch, tmp_path, capsys):
    cli = load_cli()
    issue_dir = tmp_path / "issue-13"

    def fake_run_cycle(args):
        if args == ["--issue", "13", "--dispatch-subagents"]:
            return {
                "status": "blocked_missing_target_paths",
                "artifact_dir": str(issue_dir),
                "issue": 13,
                "closure_decision": "blocked_missing_target_paths",
            }
        if args == ["--status-issue-dir", str(issue_dir)]:
            return {
                "status": "blocked_missing_target_paths",
                "artifact_dir": str(issue_dir),
                "issue": 13,
                "phase": "missing_targets",
                "closure_decision": "blocked_missing_target_paths",
                "terminal_disposition_status": "completed",
            }
        raise AssertionError(f"unexpected run_cycle args: {args}")

    monkeypatch.setattr(cli, "run_cycle", fake_run_cycle)

    code = cli.command_drive(argparse.Namespace(
        issue=13,
        artifact_dir=None,
        timeout_seconds=60,
        poll_seconds=0,
        run_webgpt=False,
        file_audit_issue=False,
    ))

    stdout_lines = capsys.readouterr().out.strip().splitlines()
    events = [json.loads(line) for line in stdout_lines]
    audit = json.loads((issue_dir / "post-job-audit.json").read_text(encoding="utf-8"))

    assert code == 2
    assert [event["event"] for event in events] == ["start", "event_log", "status", "post_job_audit", "terminal"]
    assert events[0]["status"] == "blocked_missing_target_paths"
    assert events[0]["issue"] == 13
    assert events[3]["classification"] == "maintainer_degraded"
    assert audit["classification"] == "maintainer_degraded"
    assert audit["source_issue"] == 13


def test_drive_fresh_issue_command_failure_without_artifact_still_emits_start(monkeypatch, capsys):
    cli = load_cli()

    monkeypatch.setattr(cli, "run_cycle", lambda args: {
        "status": "cycle_command_failed",
        "returncode": 2,
        "issue": 13,
    })

    with pytest.raises(SystemExit):
        cli.command_drive(argparse.Namespace(
            issue=13,
            artifact_dir=None,
            timeout_seconds=60,
            poll_seconds=0,
            run_webgpt=False,
            file_audit_issue=False,
        ))

    events = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]

    assert [event["event"] for event in events] == ["start"]
    assert events[0]["status"] == "cycle_command_failed"


def test_drive_resume_appends_to_existing_event_log(monkeypatch, tmp_path, capsys):
    cli = load_cli()
    issue_dir = tmp_path / "issue-13"
    issue_dir.mkdir()
    event_log = issue_dir / "drive-events.jsonl"
    event_log.write_text('{"event": "prior"}\n', encoding="utf-8")

    monkeypatch.setattr(cli, "status_for", lambda observed_dir: {
        "status": "fixed_with_deterministic_proof",
        "phase": "terminal_disposition",
        "closure_decision": "fixed_with_deterministic_proof",
        "terminal_disposition_status": "completed",
        "artifact_dir": str(observed_dir),
    })

    code = cli.command_drive(argparse.Namespace(
        issue=None,
        artifact_dir=str(issue_dir),
        timeout_seconds=60,
        poll_seconds=0,
        run_webgpt=False,
        file_audit_issue=False,
    ))

    stdout_lines = capsys.readouterr().out.strip().splitlines()
    file_lines = event_log.read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in stdout_lines]

    assert code == 0
    assert json.loads(file_lines[0]) == {"event": "prior"}
    assert file_lines[1:] == stdout_lines
    assert [event["event"] for event in events] == ["resume", "status", "post_job_audit", "terminal"]
    assert events[0]["event_log_path"] == str(event_log)


def test_audit_run_classifies_blocked_cycle_as_self_improvement_issue(monkeypatch, tmp_path, capsys):
    cli = load_cli()
    issue_dir = tmp_path / "issue-15"
    issue_dir.mkdir()
    (issue_dir / "drive-events.jsonl").write_text('{"event": "status"}\n', encoding="utf-8")

    monkeypatch.setattr(cli, "status_for", lambda observed_dir: {
        "status": "cycle_command_failed",
        "closure_decision": "blocked_cycle_command_failed",
        "terminal_disposition_status": "completed",
        "issue": 15,
        "artifact_dir": str(observed_dir),
    })

    code = cli.command_audit_run(argparse.Namespace(
        artifact_dir=str(issue_dir),
        file_issue=False,
    ))

    audit = json.loads(capsys.readouterr().out)
    persisted = json.loads((issue_dir / "post-job-audit.json").read_text(encoding="utf-8"))

    assert code == 0
    assert audit == persisted
    assert audit["source_issue"] == 15
    assert audit["classification"] == "maintainer_bug_detected"
    assert audit["recommended_action"] == "file_self_improvement_issue"


def test_audit_run_classifies_invalid_repair_receipt_as_self_improvement_issue(monkeypatch, tmp_path, capsys):
    cli = load_cli()
    issue_dir = tmp_path / "issue-15"
    issue_dir.mkdir()
    (issue_dir / "drive-events.jsonl").write_text('{"event": "status"}\n', encoding="utf-8")

    monkeypatch.setattr(cli, "status_for", lambda observed_dir: {
        "status": "blocked_invalid_repair_receipt:missing_files_changed",
        "closure_decision": "blocked_invalid_repair_receipt:missing_files_changed",
        "terminal_disposition_status": "completed",
        "issue": 15,
        "artifact_dir": str(observed_dir),
    })

    code = cli.command_audit_run(argparse.Namespace(
        artifact_dir=str(issue_dir),
        file_issue=False,
    ))

    audit = json.loads(capsys.readouterr().out)

    assert code == 0
    assert audit["classification"] == "maintainer_bug_detected"
    assert audit["recommended_action"] == "file_self_improvement_issue"


def test_audit_run_can_file_self_improvement_issue(monkeypatch, tmp_path, capsys):
    cli = load_cli()
    issue_dir = tmp_path / "issue-16"
    issue_dir.mkdir()
    (issue_dir / "drive-events.jsonl").write_text('{"event": "status"}\n', encoding="utf-8")

    monkeypatch.setattr(cli, "status_for", lambda observed_dir: {
        "status": "cycle_command_failed",
        "closure_decision": "blocked_cycle_command_failed",
        "terminal_disposition_status": "completed",
        "issue": 16,
        "artifact_dir": str(observed_dir),
    })
    monkeypatch.setattr(cli, "file_self_improvement_issue", lambda audit_path, audit: {
        "status": "created",
        "returncode": 0,
        "stdout": "https://github.example/issues/99",
        "stderr": "",
        "issue_url": "https://github.example/issues/99",
    })

    code = cli.command_audit_run(argparse.Namespace(
        artifact_dir=str(issue_dir),
        file_issue=True,
    ))

    audit = json.loads(capsys.readouterr().out)

    assert code == 0
    assert audit["self_improvement_issue_url"] == "https://github.example/issues/99"
    assert audit["self_improvement_issue_filing"]["status"] == "created"
