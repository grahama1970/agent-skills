from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills" / "orchestrate"))
sys.path.insert(0, str(ROOT / "skills" / "_shared"))

from loop_contract import (  # noqa: E402
    build_interview_request,
    build_scillm_exec_graph,
    compile_loop_prompt,
    loop_ambiguities,
)
from loop_prompt_compiler import compile_prompt  # noqa: E402
from structured_plan import validate_structured_plan  # noqa: E402


def _task(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        task_id="implement-timeout",
        title="Implement timeout parser",
        prompt="implement parse_user_timeout(input: str) -> int in src/timeouts.py",
        cwd=tmp_path,
        backend="gpt-5.5",
        max_rounds=2,
        timeout_seconds=900,
        definition_of_done={"command": "python -m pytest tests/test_timeouts.py"},
        loop={
            "max_attempts": 2,
            "producer": {"agent": "coder", "model": "gpt-5.5", "reasoning": "medium"},
            "verifier": {"agent": "code-reviewer", "model": "gpt-5.5", "reasoning": "high"},
            "scope": {"include": ["src/timeouts.py", "tests/test_timeouts.py"], "exclude": [".loop/**"]},
            "final_receipt": ".loop/runs/r1/final-receipt.json",
            "scope_from_file": ".loop/runs/r1/attempts/01/changed-files.txt",
        },
    )


def test_loop_ambiguities_emit_interview_questions_for_missing_runtime(tmp_path: Path) -> None:
    task = _task(tmp_path)
    task.loop = {"scope": {}}

    questions = loop_ambiguities(task)
    request = build_interview_request(task)

    ids = {q["id"] for q in questions}
    assert {"allowed_scope", "loop_runtime"}.issubset(ids)
    assert request["questions"] == questions


def test_compile_loop_prompt_contains_agents_models_reasoning_and_scope(tmp_path: Path) -> None:
    prompt = compile_loop_prompt(_task(tmp_path))

    assert "$loop implement parse_user_timeout(input: str) -> int in src/timeouts.py" in prompt
    assert "Use coder as the producer subagent:" in prompt
    assert "- reasoning: medium" in prompt
    assert "Use code-reviewer as the fresh read-only verifier:" in prompt
    assert "- reasoning: high" in prompt
    assert "- allowed: src/timeouts.py" in prompt
    assert "python -m pytest tests/test_timeouts.py" in prompt


def test_build_scillm_exec_graph_uses_one_loop_node(tmp_path: Path) -> None:
    task = _task(tmp_path)
    prompt_path = tmp_path / "compiled-loop-prompt.md"
    graph = build_scillm_exec_graph(task, tmp_path, prompt_path)

    assert graph["exec_graph_version"] == "scillm.exec.graph.v1"
    assert graph["max_concurrency"] == 1
    assert len(graph["nodes"]) == 1
    node = graph["nodes"][0]
    assert node["type"] == "local_command"
    assert node["timeout_s"] == 900
    assert node["idle_timeout_s"] == 900
    assert node["metadata"]["node_type"] == "loop/artifact-transaction"
    command = node["command"]
    assert "--receipt" in command
    assert ".loop/runs/r1/final-receipt.json" in command
    assert "--scope-from-file" in command
    assert "--check-command" in command


def test_structured_plan_accepts_loop_runner_with_artifact_transaction_mode(tmp_path: Path) -> None:
    plan = {
        "repo_root": str(tmp_path),
        "metadata": {"title": "Loop runner proof"},
        "capability_overlap": "Use /orchestrate for outer DAG and $loop for inner artifact repair.",
        "lanes": [{"id": "0", "label": "Proof"}],
        "tasks": [
            {
                "id": "1",
                "title": "Implement timeout parser",
                "lane": "0",
                "runner": "loop",
                "mode": "artifact_transaction",
                "prompt": "implement parse_user_timeout(input: str) -> int in src/timeouts.py",
                "definition_of_done": {
                    "command": "python -m pytest tests/test_timeouts.py",
                    "assertion": "tests pass",
                },
                "loop": {
                    "scope": {"include": ["src/timeouts.py", "tests/test_timeouts.py"]},
                    "final_receipt": ".loop/runs/r1/final-receipt.json",
                },
            }
        ],
    }

    result = validate_structured_plan(plan)

    assert result["valid"] is True
    assert result["issues"] == []


def test_prompt_compiler_extracts_explicit_loop_plan(tmp_path: Path) -> None:
    prompt = """Create a function that parses durations.

Call the coder subagent using model gpt-5.5 at medium reasoning.
Pass to the code-reviewer subagent using model gpt-5.5 at high reasoning.
Do this in a loop with a maximum of 2 tries until the reviewer passes.

Scope:
- duration_tool/**
- tests/**
- exclude .loop/**

Required checks:
- python -m unittest discover -s tests
- python -m duration_tool.cli "1h 30m"

final_receipt: .loop/runs/example/final-receipt.json
"""
    plan = compile_prompt(prompt, tmp_path)
    task = plan["tasks"][0]

    assert task["runner"] == "loop"
    assert task["mode"] == "artifact_transaction"
    assert task["loop"]["max_attempts"] == 2
    assert task["loop"]["producer"]["agent"] == "coder"
    assert task["loop"]["producer"]["model"] == "gpt-5.5"
    assert task["loop"]["producer"]["reasoning"] == "medium"
    assert task["loop"]["verifier"]["agent"] == "code-reviewer"
    assert task["loop"]["verifier"]["model"] == "gpt-5.5"
    assert task["loop"]["verifier"]["reasoning"] == "high"
    assert task["loop"]["scope"]["include"] == ["duration_tool/**", "tests/**"]
    assert task["loop"]["scope"]["exclude"] == [".loop/**"]
    assert task["loop"]["checks"] == [
        "python -m unittest discover -s tests",
        "python -m duration_tool.cli \"1h 30m\"",
    ]
    assert task["loop"]["final_receipt"] == ".loop/runs/example/final-receipt.json"


def test_prompt_compiler_cli_writes_interview_for_ambiguous_prompt(tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.txt"
    out_file = tmp_path / "plan.yaml"
    prompt_file.write_text("We need to create a function that does X where done means Y.\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "skills" / "orchestrate" / "loop_prompt_compiler.py"),
            str(prompt_file),
            "--repo",
            str(tmp_path),
            "--out",
            str(out_file),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    interview_path = Path(payload["interview_request"])
    interview = json.loads(interview_path.read_text(encoding="utf-8"))
    question_ids = {question["id"] for question in interview["questions"]}
    assert {"allowed_scope", "checks", "loop_runtime"}.issubset(question_ids)
    assert not out_file.exists()
