from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from code_runner.cli import run_task
from code_runner.spec import TaskSpec


DOD_COMMAND = """python - <<'PY'
from pathlib import Path
ns = {}
exec(Path("src/app.py").read_text(), ns)
assert ns["add_one"](1) == 2
print("DOD_OK")
PY"""


def make_spec(
    *,
    task_id: str,
    repo: Path,
    output_dir: Path,
    allowlist: list[str] | None = None,
    apply_to_source: bool = False,
    commit_on_success: bool = False,
    rollback_on_failure: bool = True,
    prompt: str = "Fix the fixture implementation so the deterministic DoD passes.",
    dod_command: str = DOD_COMMAND,
    dod_assertion: str = "contains:DOD_OK",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "task_id": task_id,
        "title": task_id,
        "prompt": prompt,
        "backend": "test",
        "cwd": str(repo),
        "output_dir": str(output_dir),
        "allowlist": allowlist or ["src/app.py"],
        "definition_of_done": {
            "command": dod_command,
            "assertion": dod_assertion,
        },
        "read_context": ["src/app.py", "README.md"],
        "max_rounds": 3,
        "timeout_seconds": 60,
        "dirty_worktree_policy": "isolated_worktree",
        "apply_to_source": apply_to_source,
        "commit_on_success": commit_on_success,
        "rollback_on_failure": rollback_on_failure,
    }
    if extra:
        spec.update(extra)
    return spec


def run_spec(spec_dict: dict[str, Any]) -> dict[str, Any]:
    spec = TaskSpec.model_validate(spec_dict)
    output_dir = Path(spec_dict["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    spec_file = output_dir / f"{spec_dict['task_id']}.code-runner-spec.json"
    spec_file.write_text(json.dumps(spec_dict, indent=2))

    result = run_task(spec, spec_dict, str(spec_file))
    result_path = output_dir / f"{spec_dict['task_id']}.result.json"
    assert result_path.exists(), f"runner did not write result: {result_path}"
    return json.loads(result_path.read_text())
