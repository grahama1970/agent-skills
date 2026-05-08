from __future__ import annotations

from pathlib import Path

from ..helpers.assertions import assert_result_failed
from ..helpers.git_repo import make_minimal_python_repo, write
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
