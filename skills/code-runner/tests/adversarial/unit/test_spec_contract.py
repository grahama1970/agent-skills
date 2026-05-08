from __future__ import annotations

from pathlib import Path

import pytest

from code_runner.spec import TaskSpec
from ..helpers.git_repo import make_minimal_python_repo
from ..helpers.runner import make_spec


@pytest.mark.parametrize(
    "field,value",
    [
        ("hidden_tests", ["pytest -q tests/hidden"]),
        ("skills", ["memory", "planner"]),
        ("memory", {"enabled": True}),
        ("planner", {"enabled": True}),
        ("reviewer", {"enabled": True}),
        ("backend_racing", ["codex", "claude"]),
    ],
)
def test_orchestration_fields_are_rejected(field: str, value, tmp_path: Path) -> None:
    repo = make_minimal_python_repo(tmp_path)
    spec = make_spec(
        task_id=f"reject-{field.replace('_', '-')}",
        repo=repo,
        output_dir=tmp_path / "out",
        extra={field: value},
    )

    with pytest.raises(Exception):
        TaskSpec.model_validate(spec)


@pytest.mark.parametrize(
    "allowlist",
    [
        ["../src/app.py"],
        ["/tmp/src/app.py"],
        ["src/../../secrets.txt"],
        [""],
    ],
)
def test_invalid_allowlist_entries_are_rejected(allowlist: list[str], tmp_path: Path) -> None:
    repo = make_minimal_python_repo(tmp_path)
    spec = make_spec(
        task_id="reject-invalid-allowlist",
        repo=repo,
        output_dir=tmp_path / "out",
        allowlist=allowlist,
    )

    with pytest.raises(Exception):
        TaskSpec.model_validate(spec)


@pytest.mark.parametrize("missing_field", ["allowlist", "definition_of_done"])
def test_required_task_fields_are_rejected(missing_field: str, tmp_path: Path) -> None:
    repo = make_minimal_python_repo(tmp_path)
    spec = make_spec(
        task_id=f"reject-missing-{missing_field.replace('_', '-')}",
        repo=repo,
        output_dir=tmp_path / "out",
    )
    spec.pop(missing_field)

    with pytest.raises(Exception):
        TaskSpec.model_validate(spec)


def test_output_dir_inside_source_is_rejected_by_schema_or_preflight(tmp_path: Path) -> None:
    repo = make_minimal_python_repo(tmp_path)
    spec = make_spec(
        task_id="reject-output-dir-inside-source",
        repo=repo,
        output_dir=repo / ".runner-output",
    )

    with pytest.raises(Exception):
        TaskSpec.model_validate(spec)
