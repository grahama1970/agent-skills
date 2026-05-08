from __future__ import annotations

from pathlib import Path

from ..helpers.assertions import assert_no_residual_code_runner_worktree, assert_result_failed
from ..helpers.git_repo import make_minimal_python_repo
from ..helpers.http_scillm import FakeScillmHTTPServer, ScillmResponse, content_delta, done, empty_delta
from ..helpers.runner import make_spec, run_spec
from ..helpers.source_snapshot import assert_source_snapshot_unchanged, snapshot_source


def test_stream_chat_http_400_writes_diagnostic_result_and_cleans_worktree(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    task_id = "real-http-400-cleanup"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)
    response = ScillmResponse(status=400, body='{"error":"bad request"}', content_type="application/json")

    with FakeScillmHTTPServer([response]) as server:
        monkeypatch.setenv("SCILLM_API_BASE", server.base_url)

        result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir))

    assert_result_failed(result)
    assert "scillm HTTP 400" in result["error"]
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)


def test_stream_chat_missing_done_preserves_source_and_cleans_worktree(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    task_id = "missing-done-cleanup"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)

    with FakeScillmHTTPServer([ScillmResponse(lines=[content_delta("partial")])]) as server:
        monkeypatch.setenv("SCILLM_API_BASE", server.base_url)
        monkeypatch.setattr("code_runner.scillm.time.sleep", lambda _seconds: None)

        result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir, extra={"max_rounds": 1}))

    assert_result_failed(result)
    assert result["error"] == "definition_of_done did not pass"
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)
    assert len(server.requests) == 5


def test_stream_chat_empty_delta_preserves_source_and_cleans_worktree(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    task_id = "empty-delta-cleanup"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)

    with FakeScillmHTTPServer([ScillmResponse(lines=[empty_delta(finish_reason="stop"), done()])]) as server:
        monkeypatch.setenv("SCILLM_API_BASE", server.base_url)
        monkeypatch.setattr("code_runner.scillm.time.sleep", lambda _seconds: None)

        result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir, extra={"max_rounds": 1}))

    assert_result_failed(result)
    assert result["error"] == "definition_of_done did not pass"
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)
    assert len(server.requests) == 5


def test_stream_chat_malformed_json_preserves_source_and_cleans_worktree(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    task_id = "malformed-json-cleanup"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)

    with FakeScillmHTTPServer([ScillmResponse(lines=["data: {not-json", done()])]) as server:
        monkeypatch.setenv("SCILLM_API_BASE", server.base_url)

        result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir))

    assert_result_failed(result)
    assert "Expecting property name" in result["error"]
    assert_source_snapshot_unchanged(repo, before)
    assert_no_residual_code_runner_worktree(repo, task_id)
    assert len(server.requests) == 1
