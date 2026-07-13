from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


SCRIPT = Path(__file__).parents[1] / "scripts" / "webgpt_cli.py"
SPEC = spec_from_file_location("webgpt_cli", SCRIPT)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_execution_lock_requires_all_headings() -> None:
    assert MODULE.validate_execution_lock("## Objective\nRun tests") == [
        "current phase",
        "critical path",
        "deferred work",
        "stop condition",
    ]


def test_complete_execution_lock_is_accepted() -> None:
    text = "\n".join(f"## {heading.title()}" for heading in MODULE.EXECUTION_LOCK_HEADINGS)
    assert MODULE.validate_execution_lock(text) == []


def test_surf_runtime_path_expands_home() -> None:
    assert MODULE.SURF == Path.home() / "workspace/experiments/agent-skills/skills/surf/run.sh"
    assert "${HOME}" not in str(MODULE.SURF)
