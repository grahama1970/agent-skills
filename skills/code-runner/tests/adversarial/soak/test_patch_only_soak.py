from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..helpers.assertions import assert_no_residual_code_runner_worktree, assert_result_passed, read_json
from ..helpers.git_repo import make_minimal_python_repo
from ..helpers.monkeypatch_scillm import FakeScillm, final_message, tool_call
from ..helpers.runner import make_spec, run_spec
from ..helpers.source_snapshot import assert_source_snapshot_unchanged, snapshot_source


pytestmark = pytest.mark.soak


def test_100_serial_patch_only_runs_preserve_source_and_artifacts(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    before = snapshot_source(repo)

    for index in range(100):
        task_id = f"soak-serial-patch-{index:03d}"
        output_dir = tmp_path / "out" / task_id
        FakeScillm(
            [
                tool_call("write_file", {"path": "src/app.py", "content": "def add_one(x):\n    return x + 1\n"}),
                final_message("fixed"),
            ]
        ).install(monkeypatch)

        result = run_spec(make_spec(task_id=task_id, repo=repo, output_dir=output_dir))

        assert_result_passed(result)
        assert result["apply_to_source"] is False
        assert (output_dir / f"{task_id}.result.json").exists()
        assert (output_dir / f"{task_id}.status.json").exists()
        assert read_json(output_dir / f"{task_id}.result.json")["task_id"] == task_id
        assert read_json(output_dir / f"{task_id}.status.json")["task_id"] == task_id
        json.loads((output_dir / f"{task_id}.events.jsonl").read_text().splitlines()[-1])
        assert_no_residual_code_runner_worktree(repo, task_id)
        assert_source_snapshot_unchanged(repo, before)
