from __future__ import annotations

from pathlib import Path

from ..helpers.assertions import assert_result_failed
from ..helpers.git_repo import git, make_minimal_python_repo, write
from ..helpers.monkeypatch_scillm import FakeScillm, final_message, tool_call
from ..helpers.runner import make_spec, run_spec
from ..helpers.source_snapshot import assert_source_snapshot_unchanged, snapshot_source


def test_complete_task_dirty_allowlisted_tracked_file_fails_before_apply(tmp_path: Path, monkeypatch) -> None:
    """
    Complete-task mode must fail closed before source apply if an allowlisted path is dirty.
    """
    repo = make_minimal_python_repo(tmp_path)
    task_id = "complete-dirty-allowlist-fail-closed"
    output_dir = tmp_path / "out" / task_id

    write(repo, "src/app.py", "def add_one(x):\n    return 'USER DIRTY WORK'\n")
    before = snapshot_source(repo)

    FakeScillm(
        [
            tool_call(
                "write_file",
                {
                    "path": "src/app.py",
                    "content": "def add_one(x):\n    return x + 1\n",
                },
            ),
            final_message("fixed isolated worktree"),
        ]
    ).install(monkeypatch)

    result = run_spec(
        make_spec(
            task_id=task_id,
            repo=repo,
            output_dir=output_dir,
            apply_to_source=True,
            rollback_on_failure=True,
        )
    )

    assert_result_failed(result)
    assert result["source_patch_applied"] is False
    assert result["source_rollback_applied"] is False
    assert_source_snapshot_unchanged(repo, before)


def test_complete_task_apply_not_started_when_isolated_dod_fails(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    task_id = "complete-no-apply-without-isolated-pass"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)

    FakeScillm([final_message("no edit, no pass")]).install(monkeypatch)

    result = run_spec(
        make_spec(
            task_id=task_id,
            repo=repo,
            output_dir=output_dir,
            apply_to_source=True,
            rollback_on_failure=True,
        )
    )

    assert_result_failed(result)
    assert result["source_patch_applied"] is False
    assert result["source_dod_passed"] is False
    assert_source_snapshot_unchanged(repo, before)


def test_complete_task_still_runs_backend_when_initial_dod_passes(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    write(repo, "src/app.py", "def add_one(x):\n    return x + 1\n")
    git(repo, "add", "src/app.py")
    git(repo, "commit", "-m", "baseline already satisfies visible dod")
    task_id = "complete-initial-dod-pass-still-implements"
    output_dir = tmp_path / "out" / task_id

    fake = FakeScillm(
        [
            tool_call(
                "write_file",
                {
                    "path": "src/app.py",
                    "content": "def add_one(x):\n    return x + 1  # implemented by code-runner\n",
                },
            ),
            final_message("implemented even though baseline DoD passed"),
        ]
    ).install(monkeypatch)

    result = run_spec(
        make_spec(
            task_id=task_id,
            repo=repo,
            output_dir=output_dir,
            apply_to_source=True,
            commit_on_success=True,
        )
    )

    assert result["status"] == "pass"
    assert result["source_patch_applied"] is True
    assert result["source_dod_passed"] is True
    assert result["source_commit"]
    assert result["rounds"] == 1
    assert result["round_details"][0]["changed_paths"] == ["src/app.py"]
    assert fake.requests[0]["round_num"] == 1
    assert "implemented by code-runner" in (repo / "src/app.py").read_text()


def test_initial_dod_pass_without_patch_fails_complete_task(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    write(repo, "src/app.py", "def add_one(x):\n    return x + 1\n")
    git(repo, "add", "src/app.py")
    git(repo, "commit", "-m", "baseline already satisfies visible dod")
    task_id = "complete-initial-dod-pass-no-patch-fails"
    output_dir = tmp_path / "out" / task_id
    before = snapshot_source(repo)

    FakeScillm([final_message("no edit needed")]).install(monkeypatch)

    result = run_spec(
        make_spec(
            task_id=task_id,
            repo=repo,
            output_dir=output_dir,
            apply_to_source=True,
            commit_on_success=True,
            extra={"max_rounds": 1},
        )
    )

    assert_result_failed(result)
    assert result["error"] == "no allowlisted changes produced"
    assert result["source_patch_applied"] is False
    assert result["source_commit"] == ""
    assert result["round_details"][0]["error"] == "no allowlisted changes produced"
    assert_source_snapshot_unchanged(repo, before)


def test_failed_round_is_restored_before_next_attempt(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    task_id = "failed-round-restored-before-retry"
    output_dir = tmp_path / "out" / task_id

    FakeScillm(
        [
            tool_call(
                "write_file",
                {
                    "path": "src/app.py",
                    "content": "def add_one(x):\n    return x +\n",
                },
                call_id="bad-edit",
            ),
            final_message("bad edit applied"),
            tool_call(
                "write_file",
                {
                    "path": "src/app.py",
                    "content": "def add_one(x):\n    return x + 1\n",
                },
                call_id="good-edit",
            ),
            final_message("fixed after restoring failed round"),
        ]
    ).install(monkeypatch)

    result = run_spec(
        make_spec(
            task_id=task_id,
            repo=repo,
            output_dir=output_dir,
            apply_to_source=True,
            commit_on_success=True,
            extra={"max_rounds": 2},
        )
    )

    assert result["status"] == "pass"
    assert result["rounds"] == 2
    assert result["round_details"][0]["dod_passed"] is False
    assert result["round_details"][1]["dod_passed"] is True
    assert result["source_patch_applied"] is True
    assert result["source_commit"]
    assert (repo / "src/app.py").read_text() == "def add_one(x):\n    return x + 1\n"
