from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from code_runner.spec import TaskSpec
from code_runner.cli import run_task
from ..helpers.assertions import assert_no_residual_code_runner_worktree, assert_result_passed, read_json
from ..helpers.git_repo import make_minimal_python_repo
from ..helpers.runner import make_spec
from ..helpers.source_snapshot import assert_source_snapshot_unchanged, snapshot_source


pytestmark = pytest.mark.soak


def _mock_response() -> str:
    return (
        "### FILE: src/app.py\n"
        "```python\n"
        "def add_one(x):\n"
        "    return x + 1\n"
        "```\n"
    )


def _run_patch_only_spec(spec_dict: dict) -> dict:
    output_dir = Path(spec_dict["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    spec_file = output_dir / f"{spec_dict['task_id']}.code-runner-spec.json"
    spec_file.write_text(json.dumps(spec_dict, indent=2))
    spec = TaskSpec.model_validate(spec_dict)
    return run_task(spec, spec_dict, str(spec_file)).model_dump()


def test_100_parallel_patch_only_runs_preserve_source_and_artifacts(tmp_path: Path, monkeypatch) -> None:
    repo = make_minimal_python_repo(tmp_path)
    before = snapshot_source(repo)
    monkeypatch.setenv("CODE_RUNNER_MOCK_RESPONSE", _mock_response())

    specs = [
        make_spec(
            task_id=f"soak-parallel-patch-{index:03d}",
            repo=repo,
            output_dir=tmp_path / "out" / f"soak-parallel-patch-{index:03d}",
        )
        for index in range(100)
    ]

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_run_patch_only_spec, spec) for spec in specs]
        results = [future.result() for future in as_completed(futures)]

    assert len(results) == 100
    seen_outputs = set()
    for result in results:
        assert_result_passed(result)
        task_id = result["task_id"]
        output_dir = tmp_path / "out" / task_id
        assert str(output_dir) not in seen_outputs
        seen_outputs.add(str(output_dir))
        assert read_json(output_dir / f"{task_id}.result.json")["task_id"] == task_id
        assert read_json(output_dir / f"{task_id}.status.json")["task_id"] == task_id
        assert_no_residual_code_runner_worktree(repo, task_id)

    assert_source_snapshot_unchanged(repo, before)
