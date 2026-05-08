from __future__ import annotations

from pathlib import Path

from ..helpers.assertions import assert_result_passed, committed_paths
from ..helpers.git_repo import git, make_minimal_python_repo, write
from ..helpers.monkeypatch_scillm import FakeScillm, final_message, tool_call
from ..helpers.runner import make_spec, run_spec


def test_commit_on_success_commits_only_allowlisted_paths(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    task_id = "commit-only-allowlisted"
    output_dir = tmp_path / "out" / task_id

    write(repo, "docs/user-notes.md", "tracked docs\n")
    git(repo, "add", "docs/user-notes.md")
    git(repo, "commit", "-m", "add docs")

    before_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    write(repo, "docs/user-notes.md", "dirty nonallowlisted user work\n")

    FakeScillm(
        [
            tool_call(
                "write_file",
                {
                    "path": "src/app.py",
                    "content": "def add_one(x):\n    return x + 1\n",
                },
            ),
            final_message("fixed and ready to commit"),
        ]
    ).install(monkeypatch)

    result = run_spec(
        make_spec(
            task_id=task_id,
            repo=repo,
            output_dir=output_dir,
            apply_to_source=True,
            commit_on_success=True,
            rollback_on_failure=True,
        )
    )

    assert_result_passed(result)
    after_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    assert after_head != before_head
    assert committed_paths(repo, "HEAD") == {"src/app.py"}

    # User's unrelated dirty work must still be dirty and must not be committed.
    assert (repo / "docs/user-notes.md").read_text() == "dirty nonallowlisted user work\n"
    status = git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
    assert "docs/user-notes.md" in status
