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
        "failure policy",
        "stop condition",
        "max_identical_failures_per_family: 3",
        "systemic_failure_action: stop_family_mark_remaining_blocked_continue_independent_families",
        "reviewer_scope_authority: none",
    ]


def test_complete_execution_lock_is_accepted() -> None:
    text = "\n".join(
        [f"## {heading.title()}" for heading in MODULE.EXECUTION_LOCK_HEADINGS]
        + list(MODULE.EXECUTION_LOCK_DIRECTIVES)
    )
    assert MODULE.validate_execution_lock(text) == []


def test_execution_lock_rejects_non_fail_fast_campaign_policy() -> None:
    text = "\n".join(
        [f"## {heading.title()}" for heading in MODULE.EXECUTION_LOCK_HEADINGS]
        + [
            "max_identical_failures_per_family: 20",
            "systemic_failure_action: finish_all_cases",
            "reviewer_scope_authority: implicit",
        ]
    )
    assert MODULE.validate_execution_lock(text) == list(MODULE.EXECUTION_LOCK_DIRECTIVES)


def test_surf_runtime_path_expands_home() -> None:
    assert MODULE.SURF == Path.home() / "workspace/experiments/agent-skills/skills/surf/run.sh"
    assert "${HOME}" not in str(MODULE.SURF)


def test_surf_runtime_path_honors_env_override(monkeypatch) -> None:
    monkeypatch.setenv("SURF_RUN_SH", "/tmp/custom-surf/run.sh")
    spec = spec_from_file_location("webgpt_cli_env_override", SCRIPT)
    assert spec and spec.loader
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module.SURF == Path("/tmp/custom-surf/run.sh")
