from __future__ import annotations

from pathlib import Path

import pytest

from code_runner.spec import TaskSpec
from ..helpers.assertions import assert_result_failed
from ..helpers.git_repo import make_minimal_python_repo
from ..helpers.monkeypatch_scillm import FakeScillm, final_message
from ..helpers.runner import make_spec, run_spec
from ..helpers.source_snapshot import assert_source_snapshot_unchanged, snapshot_source


def test_output_dir_inside_source_rejected_before_artifact_writes(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    task_id = "output-dir-inside-source"
    output_dir = repo / ".code-runner-output" / task_id
    before = snapshot_source(repo)

    FakeScillm([final_message("no edit")]).install(monkeypatch)

    with pytest.raises(Exception):
        run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir))
    assert not output_dir.exists(), "runner must reject output_dir inside source before creating artifacts"
    assert_source_snapshot_unchanged(repo, before)


@pytest.mark.parametrize(
    "bad_allowlist",
    [
        ["/tmp/absolute.py"],
        ["../escape.py"],
        ["src/../../escape.py"],
        [""],
    ],
)
def test_bad_allowlist_paths_rejected_before_runtime(tmp_path: Path, bad_allowlist: list[str]) -> None:
    repo = make_minimal_python_repo(tmp_path)

    spec = make_spec(
        task_id="bad-allowlist-rejected",
        repo=repo,
        output_dir=tmp_path / "out",
        allowlist=bad_allowlist,
    )

    with pytest.raises(Exception):
        TaskSpec.model_validate(spec)
