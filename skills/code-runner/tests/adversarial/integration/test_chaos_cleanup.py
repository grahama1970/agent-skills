from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_runner.worktree import WorktreeError
from ..helpers.assertions import assert_no_residual_code_runner_worktree, assert_result_failed, read_json
from ..helpers.git_repo import make_minimal_python_repo
from ..helpers.monkeypatch_scillm import FakeScillm, final_message, tool_call
from ..helpers.runner import make_spec, run_spec
from ..helpers.source_snapshot import assert_source_snapshot_unchanged, snapshot_source


def _assert_finalized_failure(output_dir: Path, task_id: str, result: dict) -> None:
    assert_result_failed(result)
    for suffix in ("request.json", "status.json", "events.jsonl", "result.json"):
        assert (output_dir / f"{task_id}.{suffix}").exists(), f"missing finalized artifact: {suffix}"
    status = read_json(output_dir / f"{task_id}.status.json")
    assert status["task_id"] == task_id
    assert status["status"] == "fail"


def _run_failing_spec(tmp_path: Path, monkeypatch, task_id: str, *, extra: dict | None = None) -> tuple[Path, Path, dict]:
    repo = make_minimal_python_repo(tmp_path)
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)
    FakeScillm([final_message("no write")]).install(monkeypatch)

    result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir, extra=extra))

    _assert_finalized_failure(output_dir, task_id, result)
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)
    return repo, output_dir, result


def test_chaos_worktree_creation_failure_finalizes_diagnostics(tmp_path: Path, monkeypatch) -> None:
    import code_runner.cli as cli

    def fail_create(_source_root: Path, _task_id: str):
        raise WorktreeError("injected worktree creation failure")

    monkeypatch.setattr(cli, "create", fail_create)

    _repo, _output_dir, result = _run_failing_spec(tmp_path, monkeypatch, "chaos-create-failure")

    assert "injected worktree creation failure" in result["error"]
    assert result["worktree_removed"] is False


def test_chaos_dependency_mirroring_failure_removes_worktree(tmp_path: Path, monkeypatch) -> None:
    import code_runner.cli as cli

    def fail_mirror(_source: Path, _destination: Path) -> list[str]:
        raise RuntimeError("injected dependency mirror failure")

    monkeypatch.setattr(cli, "mirror_dependency_dirs", fail_mirror)

    _repo, _output_dir, result = _run_failing_spec(tmp_path, monkeypatch, "chaos-mirror-failure")

    assert "injected dependency mirror failure" in result["error"]
    assert result["worktree_removed"] is True


def test_chaos_initial_dod_exception_removes_worktree(tmp_path: Path, monkeypatch) -> None:
    import code_runner.cli as cli

    def fail_dod(*_args, **_kwargs):
        raise RuntimeError("injected initial DoD failure")

    monkeypatch.setattr(cli, "run_dod", fail_dod)

    _repo, _output_dir, result = _run_failing_spec(tmp_path, monkeypatch, "chaos-initial-dod-failure")

    assert "injected initial DoD failure" in result["error"]
    assert result["worktree_removed"] is True


def test_chaos_tool_execution_exception_is_diagnostic_failure(tmp_path: Path, monkeypatch) -> None:
    import code_runner.scillm as scillm

    repo = make_minimal_python_repo(tmp_path)
    task_id = "chaos-tool-exception"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)
    FakeScillm([tool_call("write_file", {"path": "src/app.py", "content": "def add_one(x):\n    return x + 1\n"}), final_message("done")]).install(monkeypatch)

    def fail_execute(*_args, **_kwargs) -> str:
        raise RuntimeError("injected tool execution failure")

    monkeypatch.setattr(scillm, "execute", fail_execute)

    result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir, extra={"max_rounds": 1}))

    _assert_finalized_failure(output_dir, task_id, result)
    assert "injected tool execution failure" in result["error"]
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)


def test_chaos_post_round_dod_exception_removes_worktree(tmp_path: Path, monkeypatch) -> None:
    import code_runner.cli as cli
    from code_runner.dod import DodResult

    calls = 0

    def flaky_dod(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return DodResult("injected", "contains:DOD_OK", 1, "", "initial fail", False)
        raise RuntimeError("injected post-round DoD failure")

    monkeypatch.setattr(cli, "run_dod", flaky_dod)

    repo = make_minimal_python_repo(tmp_path)
    task_id = "chaos-post-round-dod"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)
    FakeScillm([tool_call("write_file", {"path": "src/app.py", "content": "def add_one(x):\n    return x + 1\n"})]).install(monkeypatch)

    result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir, extra={"max_rounds": 1}))

    _assert_finalized_failure(output_dir, task_id, result)
    assert "injected post-round DoD failure" in result["error"]
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)


def test_chaos_patch_export_failure_preserves_source_and_removes_worktree(tmp_path: Path, monkeypatch) -> None:
    import code_runner.cli as cli

    def fail_export(*_args, **_kwargs) -> None:
        raise RuntimeError("injected patch export failure")

    monkeypatch.setattr(cli, "export_patch", fail_export)

    repo = make_minimal_python_repo(tmp_path)
    task_id = "chaos-patch-export"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)
    FakeScillm([tool_call("write_file", {"path": "src/app.py", "content": "def add_one(x):\n    return x + 1\n"}), final_message("fixed")]).install(monkeypatch)

    result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir))

    _assert_finalized_failure(output_dir, task_id, result)
    assert "injected patch export failure" in result["error"]
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)


def test_chaos_scillm_connection_failure_preserves_source_and_cleans_worktree(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    task_id = "chaos-scillm-connection"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)
    FakeScillm(error=RuntimeError("injected scillm connection failure")).install(monkeypatch)

    result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir))

    _assert_finalized_failure(output_dir, task_id, result)
    assert "injected scillm connection failure" in result["error"]
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)


def test_chaos_scillm_timeout_retries_then_finalizes(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    task_id = "chaos-scillm-timeout"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)
    FakeScillm(error=TimeoutError("injected scillm timeout")).install(monkeypatch)
    monkeypatch.setattr("code_runner.scillm.time.sleep", lambda _seconds: None)

    result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir, extra={"max_rounds": 1}))

    _assert_finalized_failure(output_dir, task_id, result)
    assert result["error"] == "definition_of_done did not pass"
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)


def test_chaos_source_apply_failure_rolls_back_allowlist(tmp_path: Path, monkeypatch) -> None:
    import code_runner.cli as cli

    def fail_apply(*_args, **_kwargs) -> None:
        raise RuntimeError("injected source apply failure")

    monkeypatch.setattr(cli, "apply_patch", fail_apply)

    repo = make_minimal_python_repo(tmp_path)
    task_id = "chaos-source-apply"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)
    FakeScillm([tool_call("write_file", {"path": "src/app.py", "content": "def add_one(x):\n    return x + 1\n"}), final_message("fixed")]).install(monkeypatch)

    result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir, apply_to_source=True))

    _assert_finalized_failure(output_dir, task_id, result)
    assert "injected source apply failure" in result["error"]
    assert result["source_rollback_applied"] is True
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)


def test_chaos_source_dod_exception_rolls_back_allowlist(tmp_path: Path, monkeypatch) -> None:
    import code_runner.cli as cli
    from code_runner.dod import DodResult

    calls = 0

    def flaky_dod(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            return DodResult(
                "injected",
                "contains:DOD_OK",
                0 if calls == 2 else 1,
                "DOD_OK\n" if calls == 2 else "",
                "",
                calls == 2,
            )
        raise RuntimeError("injected source DoD exception")

    monkeypatch.setattr(cli, "run_dod", flaky_dod)

    repo = make_minimal_python_repo(tmp_path)
    task_id = "chaos-source-dod"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)
    FakeScillm([tool_call("write_file", {"path": "src/app.py", "content": "def add_one(x):\n    return x + 1\n"})]).install(monkeypatch)

    result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir, apply_to_source=True, extra={"max_rounds": 1}))

    _assert_finalized_failure(output_dir, task_id, result)
    assert "injected source DoD exception" in result["error"]
    assert result["source_rollback_applied"] is True
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)


def test_chaos_commit_failure_rolls_back_allowlist(tmp_path: Path, monkeypatch) -> None:
    import code_runner.cli as cli

    def fail_commit(*_args, **_kwargs) -> str:
        raise RuntimeError("injected commit failure")

    monkeypatch.setattr(cli, "commit_allowlist", fail_commit)

    repo = make_minimal_python_repo(tmp_path)
    task_id = "chaos-commit-failure"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)
    FakeScillm([tool_call("write_file", {"path": "src/app.py", "content": "def add_one(x):\n    return x + 1\n"}), final_message("fixed")]).install(monkeypatch)

    result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir, apply_to_source=True, commit_on_success=True))

    _assert_finalized_failure(output_dir, task_id, result)
    assert "injected commit failure" in result["error"]
    assert result["source_rollback_applied"] is True
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)


def test_chaos_result_artifact_contains_json_after_failure(tmp_path: Path, monkeypatch) -> None:
    import code_runner.cli as cli

    monkeypatch.setattr(cli, "export_patch", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected late failure")))

    repo = make_minimal_python_repo(tmp_path)
    task_id = "chaos-result-json"
    output_dir = tmp_path / "out" / task_id
    FakeScillm([tool_call("write_file", {"path": "src/app.py", "content": "def add_one(x):\n    return x + 1\n"})]).install(monkeypatch)

    result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir, extra={"max_rounds": 1}))

    parsed = json.loads((output_dir / f"{task_id}.result.json").read_text())
    assert parsed == result
    assert parsed["status"] == "fail"
