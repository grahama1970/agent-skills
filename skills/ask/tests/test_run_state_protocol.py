"""Runtime artifact protocol tests for ask."""

import json
import os
import time
from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

import ask.ask as ask_module
import ask.nightly as nightly_module
import ask.os_learn as os_learn_module
import ask.os_query as os_query_module
import ask.pipeline as pipeline_module
import ask.status as status_module
from ask.doctor import run_doctor
from ask.runtime_schema import validate_run_dir, validate_runtime_tree
from ask.run_state import AskRunState, make_run_id, list_runs, prune_runs, read_status, watch_status


def age_run_status(run: AskRunState, days: int = 30) -> None:
    old_time = time.time() - days * 24 * 60 * 60
    payload = json.loads(run.status_path.read_text())
    payload["updated_at"] = datetime.fromtimestamp(old_time, tz=timezone.utc).isoformat()
    run.status_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.utime(run.status_path, (old_time, old_time))
    os.utime(run.run_dir, (old_time, old_time))


def test_run_state_writes_request_status_and_events(tmp_path):
    run = AskRunState("protocol-test", output_root=tmp_path)
    run.write_request({"question": "what changed?", "scope": "ask"})
    run.event("custom_event", detail="ok")
    run.finish({"question": "what changed?", "scope": "ask", "items": [{"solution": "ok"}]})

    assert run.request_path.exists()
    assert run.status_path.exists()
    assert run.events_path.exists()

    request = json.loads(run.request_path.read_text())
    status = json.loads(run.status_path.read_text())
    events = [json.loads(line) for line in run.events_path.read_text().splitlines()]

    assert request["runtime_protocol_version"] == "ask.runtime.v1"
    assert status["state"] == "answered"
    assert status["artifacts"]["request"] == str(run.request_path)
    assert [event["event"] for event in events] == ["request_written", "custom_event", "finished"]
    assert validate_run_dir(run.run_dir)["ok"]


def test_runtime_tree_schema_validation_reports_invalid_runs(tmp_path):
    valid = AskRunState("schema-valid", output_root=tmp_path)
    valid.write_request({"question": "schema"})
    valid.finish({"question": "schema", "items": []})
    invalid = tmp_path / "schema-invalid"
    invalid.mkdir()
    (invalid / "schema-invalid.status.json").write_text("{}")

    result = validate_runtime_tree(tmp_path)

    assert not result["ok"]
    assert result["runs_checked"] == 2
    assert any(item["run_dir"].endswith("schema-invalid") for item in result["invalid_runs"])


def test_read_status_includes_event_tail(tmp_path):
    run = AskRunState("tail-test", output_root=tmp_path)
    run.write_request({"question": "tail?", "scope": "ask"})
    run.event("middle")
    run.finish({"question": "tail?", "scope": "ask", "items": []})

    status = read_status("tail-test", tail_events=2, output_root=tmp_path)

    assert status["state"] == "no_results"
    assert [event["event"] for event in status["event_tail"]] == ["middle", "finished"]


def test_run_state_needs_attention_and_artifact_registration_survive_finish(tmp_path):
    run = AskRunState("attention-test", output_root=tmp_path)
    run.write_request({"question": "safe to proceed?", "scope": "ask"})
    attention = run.needs_attention(
        reason="missing_deep_review_target",
        question="Deep review needs an explicit target.",
        resume_hint="Run again with --deep-review-target <target>.",
    )
    run.add_artifacts({"review_md": tmp_path / "review.md", "review_json": tmp_path / "review.json"})
    run.finish({"question": "safe to proceed?", "items": []}, state="needs_attention")

    status = read_status("attention-test", tail_events=10, output_root=tmp_path)

    assert attention["reason"] == "missing_deep_review_target"
    assert status["state"] == "needs_attention"
    assert status["artifacts"]["review_md"].endswith("review.md")
    assert status["needs_attention"]["resume_hint"] == "Run again with --deep-review-target <target>."


def test_cli_ask_writes_runtime_artifacts(monkeypatch, tmp_path):
    captured = {}

    def fake_ask(**kwargs):
        captured.update(kwargs)
        return {"question": kwargs["question"], "scope": kwargs["scope"], "items": [{"solution": "ok"}]}

    monkeypatch.setattr(ask_module, "ask", fake_ask)
    result = CliRunner().invoke(
        ask_module.app,
        [
            "what",
            "changed?",
            "--ask-id",
            "cli-protocol",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    status = read_status("cli-protocol", tail_events=10, output_root=tmp_path)
    request = json.loads((tmp_path / "cli-protocol" / "cli-protocol.request.json").read_text())

    assert captured["question"] == "what changed?"
    assert request["question"] == "what changed?"
    assert status["state"] == "answered"
    assert [event["event"] for event in status["event_tail"]] == ["request_written", "ask_started", "finished"]


def test_cli_deep_review_missing_target_pauses_with_needs_attention(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "safe",
            "to",
            "proceed?",
            "--ask-id",
            "missing-target",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    status = read_status("missing-target", tail_events=10, output_root=tmp_path)
    assert status["state"] == "needs_attention"
    assert status["needs_attention"]["reason"] == "missing_deep_review_target"
    assert status["needs_attention"]["safe_default"] == "do_not_run_review"
    assert any(event["event"] == "needs_attention" for event in status["event_tail"])
    payload = json.loads(result.stdout)
    assert payload["needs_attention"]["safe_default"] == "do_not_run_review"


def test_doctor_reports_runtime_sections():
    result = run_doctor()

    assert result["status"] in {"pass", "fail"}
    assert result["run_root"]
    assert any(check["name"] == "artifact_root_writable" for check in result["checks"])
    assert any(check["name"] == "runtime_artifact_schema" for check in result["checks"])
    assert any(check["name"] == "skill:memory" for check in result["checks"])


def test_list_runs_returns_recent_statuses(tmp_path):
    older = AskRunState("older", output_root=tmp_path)
    older.write_request({"question": "older"})
    older.finish({"question": "older", "items": []})
    newer = AskRunState("newer", output_root=tmp_path)
    newer.write_request({"question": "newer"})
    newer.finish({"question": "newer", "items": [{"solution": "ok"}]})

    runs = list_runs(output_root=tmp_path, limit=2)

    assert {run["ask_id"] for run in runs} == {"older", "newer"}
    assert all("_status_path" in run for run in runs)


def test_runtime_index_is_append_only_and_powers_runs_listing(tmp_path):
    run = AskRunState("indexed", output_root=tmp_path)
    run.write_request({"command": "ask", "question": "indexed"})
    run.finish({"question": "indexed", "items": [{"solution": "ok"}]})

    index_path = tmp_path / "index.jsonl"
    runs = list_runs(output_root=tmp_path, limit=1)

    assert index_path.exists()
    assert len(index_path.read_text().splitlines()) >= 2
    assert runs[0]["ask_id"] == "indexed"


def test_prune_runs_removes_old_run_dirs(tmp_path):
    old = AskRunState("old-run", output_root=tmp_path)
    old.write_request({"question": "old"})
    old.finish({"question": "old", "items": []})
    new = AskRunState("new-run", output_root=tmp_path)
    new.write_request({"question": "new"})
    new.finish({"question": "new", "items": []})
    age_run_status(old)

    preview = prune_runs(output_root=tmp_path, older_than_days=14, dry_run=True)
    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert str(old.run_dir) in preview["removed"]
    assert str(old.run_dir) in result["removed"]
    assert not old.run_dir.exists()
    assert new.run_dir.exists()


def test_prune_runs_keeps_old_running_run(tmp_path):
    run = AskRunState("old-running", output_root=tmp_path)
    run.write_request({"question": "still running"})
    run.update("running", current_step="oracle")
    old_time = time.time() - 30 * 24 * 60 * 60
    os.utime(run.run_dir, (old_time, old_time))

    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert run.run_dir.exists()
    assert str(run.run_dir) in result["kept"]
    assert str(run.run_dir) not in result["removed"]


def test_prune_runs_uses_status_updated_at_not_directory_mtime(tmp_path):
    run = AskRunState("recent-status-old-dir", output_root=tmp_path)
    run.write_request({"question": "recent status"})
    run.finish({"question": "recent status", "items": []})
    old_time = time.time() - 30 * 24 * 60 * 60
    os.utime(run.run_dir, (old_time, old_time))

    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert run.run_dir.exists()
    assert str(run.run_dir) in result["kept"]
    assert str(run.run_dir) not in result["removed"]


def test_prune_runs_falls_back_to_status_file_mtime_for_malformed_updated_at(tmp_path):
    run = AskRunState("malformed-updated-at", output_root=tmp_path)
    run.write_request({"question": "old status file"})
    run.finish({"question": "old status file", "items": []})
    old_time = time.time() - 30 * 24 * 60 * 60
    payload = json.loads(run.status_path.read_text())
    payload["updated_at"] = "not-a-timestamp"
    run.status_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.utime(run.status_path, (old_time, old_time))

    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert str(run.run_dir) in result["removed"]
    assert not run.run_dir.exists()


def test_prune_runs_keeps_unrecognized_old_dirs(tmp_path):
    unrelated = tmp_path / "unrelated-old-dir"
    unrelated.mkdir()
    old_time = time.time() - 30 * 24 * 60 * 60
    os.utime(unrelated, (old_time, old_time))

    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert unrelated.exists()
    assert str(unrelated) not in result["removed"]
    assert str(unrelated) in result["kept"]


def test_prune_runs_keeps_malformed_and_mismatched_status_dirs(tmp_path):
    malformed = tmp_path / "malformed"
    malformed.mkdir()
    (malformed / "malformed.status.json").write_text("{not-json")
    mismatch = tmp_path / "mismatch"
    mismatch.mkdir()
    (mismatch / "mismatch.status.json").write_text(json.dumps({
        "runtime_protocol_version": "ask.runtime.v1",
        "ask_id": "other",
        "artifacts": {"run_dir": str(mismatch)},
    }))
    old_time = time.time() - 30 * 24 * 60 * 60
    os.utime(malformed, (old_time, old_time))
    os.utime(mismatch, (old_time, old_time))

    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert malformed.exists()
    assert mismatch.exists()
    assert str(malformed) in result["kept"]
    assert str(mismatch) in result["kept"]


def test_prune_runs_keeps_symlinked_dirs(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    symlink = tmp_path / "linked"
    symlink.symlink_to(target, target_is_directory=True)
    old_time = time.time() - 30 * 24 * 60 * 60
    os.utime(symlink, (old_time, old_time), follow_symlinks=False)

    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert symlink.exists()
    assert target.exists()
    assert str(symlink) not in result["removed"]


def test_cli_status_prune_dry_run_lists_old_run_dirs(tmp_path):
    old = AskRunState("old-cli-run", output_root=tmp_path)
    old.write_request({"question": "old"})
    old.finish({"question": "old", "items": []})
    age_run_status(old)

    result = CliRunner().invoke(
        status_module.app,
        ["--prune", "--older-than-days", "14", "--dry-run", "--run-output-root", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert str(old.run_dir) in payload["removed"]
    assert old.run_dir.exists()


def test_reused_ask_id_is_rejected_by_default(tmp_path):
    first = AskRunState("same-id", output_root=tmp_path)
    first.write_request({"question": "one"})
    first.finish({"question": "one", "items": [{"solution": "ok"}]})

    with pytest.raises(FileExistsError):
        AskRunState("same-id", output_root=tmp_path)


def test_overwrite_replaces_existing_run_dir(tmp_path):
    first = AskRunState("same-id", output_root=tmp_path)
    first.write_request({"question": "one"})
    first.finish({"question": "one", "items": [{"solution": "ok"}]})

    second = AskRunState("same-id", output_root=tmp_path, overwrite=True)
    second.write_request({"question": "two"})

    request = json.loads(second.request_path.read_text())
    assert request["question"] == "two"


def test_resume_rejects_terminal_state(tmp_path):
    first = AskRunState("done-id", output_root=tmp_path)
    first.write_request({"question": "done"})
    first.finish({"question": "done", "items": [{"solution": "ok"}]})

    with pytest.raises(FileExistsError):
        AskRunState("done-id", output_root=tmp_path, resume=True)


def test_resume_accepts_running_state(tmp_path):
    first = AskRunState("running-id", output_root=tmp_path)
    first.write_request({"question": "running"})
    first.update("running", current_step="memory_recall")

    resumed = AskRunState("running-id", output_root=tmp_path, resume=True)

    assert resumed.ask_id == "running-id"


def test_resume_does_not_overwrite_original_request(tmp_path):
    first = AskRunState("resume-id", output_root=tmp_path)
    first.write_request({"command": "ask", "question": "original", "scope": "ask"})
    first.update("running", current_step="memory_recall")

    resumed = AskRunState("resume-id", output_root=tmp_path, resume=True)
    resumed.write_request({"command": "ask", "question": "original", "scope": "ask"})

    request = json.loads(first.request_path.read_text())
    events = [json.loads(line)["event"] for line in first.events_path.read_text().splitlines()]
    assert request["question"] == "original"
    assert "resumed" in events


def test_resume_rejects_conflicting_request(tmp_path):
    first = AskRunState("resume-conflict", output_root=tmp_path)
    first.write_request({"command": "ask", "question": "original", "scope": "ask"})
    first.update("running", current_step="memory_recall")

    resumed = AskRunState("resume-conflict", output_root=tmp_path, resume=True)
    with pytest.raises(ValueError):
        resumed.write_request({"command": "ask", "question": "changed", "scope": "ask"})


def test_resume_rejects_missing_original_request(tmp_path):
    first = AskRunState("missing-request", output_root=tmp_path)
    first.write_request({"command": "ask", "question": "original", "scope": "ask"})
    first.update("running", current_step="memory_recall")
    first.request_path.unlink()

    resumed = AskRunState("missing-request", output_root=tmp_path, resume=True)

    with pytest.raises(FileNotFoundError):
        resumed.write_request({"command": "ask", "question": "original", "scope": "ask"})


def test_resume_rejects_malformed_original_request(tmp_path):
    first = AskRunState("malformed-request", output_root=tmp_path)
    first.write_request({"command": "ask", "question": "original", "scope": "ask"})
    first.update("running", current_step="memory_recall")
    first.request_path.write_text("{not-json")

    resumed = AskRunState("malformed-request", output_root=tmp_path, resume=True)

    with pytest.raises(ValueError):
        resumed.write_request({"command": "ask", "question": "original", "scope": "ask"})


def test_make_run_id_same_question_does_not_collide():
    assert make_run_id("same question") != make_run_id("same question")


def test_watch_status_times_out_for_nonterminal_run(tmp_path):
    run = AskRunState("stuck", output_root=tmp_path)
    run.write_request({"question": "stuck"})
    run.update("running", current_step="memory_recall")

    with pytest.raises(TimeoutError):
        watch_status("stuck", output_root=tmp_path, interval=0.01, timeout_seconds=0.05)


def test_cli_status_watch_timeout_exits_nonzero(tmp_path):
    run = AskRunState("stuck-cli", output_root=tmp_path)
    run.write_request({"question": "stuck"})
    run.update("running", current_step="memory_recall")

    result = CliRunner().invoke(
        status_module.app,
        [
            "--run",
            "stuck-cli",
            "--watch",
            "--watch-timeout-seconds",
            "0.05",
            "--poll-interval-seconds",
            "0.01",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 2
    assert "Timed out watching" in result.stderr


def test_artifact_write_failure_degrades_plain_ask(monkeypatch):
    def broken_run_state(*args, **kwargs):
        raise OSError("read-only artifact root")

    def fake_ask(**kwargs):
        return {"question": kwargs["question"], "scope": kwargs["scope"], "items": [{"solution": "ok"}]}

    monkeypatch.setattr(ask_module, "AskRunState", broken_run_state)
    monkeypatch.setattr(ask_module, "ask", fake_ask)

    result = CliRunner().invoke(ask_module.app, ["what", "changed?"])

    assert result.exit_code == 0
    assert "Runtime artifacts disabled" in result.stderr


def test_artifact_write_failure_fails_closed_for_deep_review(monkeypatch):
    def broken_run_state(*args, **kwargs):
        raise OSError("read-only artifact root")

    monkeypatch.setattr(ask_module, "AskRunState", broken_run_state)

    result = CliRunner().invoke(ask_module.app, ["safe", "to", "proceed?", "--deep-review"])

    assert result.exit_code != 0
    assert "Runtime artifacts disabled" not in result.stderr


def test_cli_ask_dry_run_emits_spec_without_artifacts(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "safe",
            "to",
            "proceed?",
            "--deep-review",
            "--dry-run",
            "--ask-id",
            "dry-ask",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["spec_protocol_version"] == "ask.dry_run.v1"
    assert payload["options"]["deep_review"] is True
    assert not (tmp_path / "dry-ask").exists()


def test_cli_ask_chain_and_reviewer_specs_feed_dry_run_options(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "runtime",
            "--chain",
            "deep-review-safety",
            "--reviewer-spec",
            "security",
            "--dry-run",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    options = payload["options"]
    assert options["deep_review"] is True
    assert options["parallel_review"] is True
    assert "secret-persistence" in options["deep_review_focus"]


def test_cli_ask_dry_run_includes_context_policy(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "runtime",
            "--dry-run",
            "--review-context",
            "inherited",
            "--inherit-memory",
            "full",
            "--inherit-skills",
            "all",
            "--inherit-project-context",
            "summary",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    policy = payload["options"]["context_policy"]
    assert policy["review_context"] == "inherited"
    assert policy["inherit_memory"] == "full"
    assert policy["inherit_skills"] == "all"
    assert policy["inherit_project_context"] == "summary"
    assert policy["memory_as_evidence"] is True


def test_deep_review_context_policy_never_treats_memory_as_evidence(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "runtime",
            "--deep-review",
            "--deep-review-target",
            "skills/ask/src/ask/run_state.py",
            "--dry-run",
            "--inherit-memory",
            "full",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    policy = payload["options"]["context_policy"]
    assert policy["mode"] == "deep-review"
    assert policy["inherit_memory"] == "full"
    assert policy["memory_as_evidence"] is False


def test_cli_real_non_oracle_ask_smoke_writes_granular_events(monkeypatch, tmp_path):
    def fake_recall(question, scope, k):
        return {
            "returncode": 0,
            "stdout": json.dumps({"items": [{"problem": question, "solution": "Runtime protocol exists."}]}),
            "stderr": "",
        }

    monkeypatch.setattr(ask_module, "run_memory_recall", fake_recall)
    monkeypatch.setattr(ask_module, "_has_relevant_domain_items", lambda items, question: True)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "what",
            "changed?",
            "--raw",
            "--ask-id",
            "real-smoke",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    status = read_status("real-smoke", tail_events=20, output_root=tmp_path)
    events = [event["event"] for event in status["event_tail"]]
    assert "memory_recall_started" in events
    assert "memory_recall_finished" in events
    assert "synthesis_started" in events
    assert "synthesis_finished" in events
    assert status["state"] == "answered"


def test_cli_learn_writes_runtime_artifacts(monkeypatch, tmp_path):
    captured = {}

    def fake_learn(**kwargs):
        captured.update(kwargs)
        return {"topic": kwargs["topic"], "stored": 0, "memory_existing": 1, "items": []}

    monkeypatch.setattr(pipeline_module, "learn", fake_learn)
    result = CliRunner().invoke(
        pipeline_module.app,
        ["topic", "--ask-id", "learn-smoke", "--run-output-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert captured["run_state"].ask_id == "learn-smoke"
    assert read_status("learn-smoke", output_root=tmp_path)["state"] == "completed"


def test_cli_learn_dry_run_emits_spec_without_artifacts(tmp_path):
    result = CliRunner().invoke(
        pipeline_module.app,
        ["topic", "--dry-run", "--ask-id", "learn-dry", "--run-output-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "learn"
    assert not (tmp_path / "learn-dry").exists()


def test_cli_nightly_writes_runtime_artifacts(monkeypatch, tmp_path):
    def fake_nightly_update(**kwargs):
        return {
            "scope": kwargs["scope"],
            "personas_checked": 0,
            "personas_updated": 1,
            "items_stored": 1,
            "errors": [],
        }

    monkeypatch.setattr(nightly_module, "nightly_update", fake_nightly_update)
    result = CliRunner().invoke(
        nightly_module.app,
        ["--ask-id", "nightly-smoke", "--run-output-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert read_status("nightly-smoke", output_root=tmp_path)["state"] == "completed"


def test_cli_nightly_dry_run_emits_spec_without_artifacts(tmp_path):
    result = CliRunner().invoke(
        nightly_module.app,
        ["--dry-run", "--ask-id", "nightly-dry", "--run-output-root", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "nightly"
    assert not (tmp_path / "nightly-dry").exists()


def test_cli_os_learn_writes_runtime_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(
        os_learn_module,
        "learn_os",
        lambda **kwargs: {"stored": 1, "dry_run": False, "items": [], "errors": 0},
    )
    result = CliRunner().invoke(
        os_learn_module.app,
        ["--ask-id", "os-learn-smoke", "--run-output-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert read_status("os-learn-smoke", output_root=tmp_path)["state"] == "completed"


def test_cli_os_learn_dry_run_emits_spec_without_artifacts(tmp_path):
    result = CliRunner().invoke(
        os_learn_module.app,
        ["--dry-run", "--ask-id", "os-learn-dry", "--run-output-root", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "os learn"
    assert not (tmp_path / "os-learn-dry").exists()


def test_cli_os_ask_writes_runtime_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(
        os_query_module,
        "recall_os",
        lambda question, k=5, tags=None, timeout=15: [{"problem": question, "solution": "memory skill"}],
    )
    result = CliRunner().invoke(
        os_query_module.app,
        ["ask", "which skills provide memory?", "--ask-id", "os-ask-smoke", "--run-output-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert read_status("os-ask-smoke", output_root=tmp_path)["state"] == "answered"


def test_cli_os_health_writes_runtime_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(os_query_module, "get_health_data", lambda subsystem: {"status": "ok"})
    monkeypatch.setattr(os_query_module, "recall_os", lambda *args, **kwargs: [])
    result = CliRunner().invoke(
        os_query_module.app,
        [
            "health",
            "is memory healthy?",
            "--subsystem",
            "memory",
            "--ask-id",
            "os-health-smoke",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert read_status("os-health-smoke", output_root=tmp_path)["state"] == "completed"
