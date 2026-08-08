"""test_blind_baseline_preflight - tests.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys


ORCH_DIR = Path(__file__).resolve().parents[1]


def load_module():
    sys.path.insert(0, str(ORCH_DIR))
    spec = importlib.util.spec_from_file_location("orchestrate_blind_baseline", ORCH_DIR / "structured_execute.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def task(module, cwd: Path, command: str):
    return module.TaskRuntime(
        task_id="1.1", title="journal", lane="journal", runner="code-runner",
        backend="codex", mode="iterative", prompt="implement", command="", cwd=cwd,
        definition_of_done={"command": "true", "assertion": "exit_code == 0"},
        allowlist=["target.py"], read_context=["target.py"], blind_tests=[command],
    )


def test_generic_failed_baseline_blocks_without_attempt(tmp_path: Path) -> None:
    module = load_module()
    command = "printf '%s\\n' '{\"category\":\"skill_structure\",\"public_hint\":\"sanity missing\"}'; false # test-lab/run.sh verify-task x --domain skills"
    runtime = task(module, tmp_path, command)
    assert asyncio.run(module._blind_baseline_preflight(runtime, tmp_path)) is False
    assert runtime.failure_code == "BLIND_BASELINE_FAILED"
    artifact = json.loads((tmp_path / "1.1.blind-baseline.json").read_text())
    assert artifact["checks"][0]["public_hint"] == "sanity missing"


def test_semantic_hidden_command_is_not_baseline_gated(tmp_path: Path) -> None:
    module = load_module()
    runtime = task(module, tmp_path, "python hidden_semantic.py journal .")
    assert asyncio.run(module._blind_baseline_preflight(runtime, tmp_path)) is True
    assert not (tmp_path / "1.1.blind-baseline.json").exists()


def test_blind_output_preserves_safe_category_and_hint() -> None:
    module = load_module()
    category, hint = module._blind_output_hint(
        '{"category":"journal_semantics","public_hint":"sequence gap"}\n', "fallback"
    )
    assert category == "journal_semantics"
    assert hint == "sequence gap"
