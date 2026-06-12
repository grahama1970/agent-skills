"""Compile `/orchestrate` loop tasks into prompts and Scillm exec graphs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item).strip()]


def loop_ambiguities(task: Any) -> list[dict[str, Any]]:
    loop = task.loop if hasattr(task, "loop") else {}
    scope = loop.get("scope") if isinstance(loop.get("scope"), dict) else {}
    questions: list[dict[str, Any]] = []
    if not str(task.prompt or "").strip():
        questions.append(
            {
                "id": "objective",
                "header": "Goal",
                "text": "What exact artifact or code behavior should this loop produce?",
                "options": [
                    {
                        "label": "Use task title and implementation (Recommended)",
                        "description": "Compile the existing plan fields into the loop objective.",
                    },
                    {
                        "label": "Specify manually",
                        "description": "Provide a concrete objective before execution.",
                    },
                ],
            }
        )
    if not _string_list(scope.get("include")):
        questions.append(
            {
                "id": "allowed_scope",
                "header": "Scope",
                "text": "Which files may the loop modify?",
                "options": [
                    {
                        "label": "Infer from target paths (Recommended)",
                        "description": "Use files named in the request or tests as the allowlist.",
                    },
                    {
                        "label": "Specify manually",
                        "description": "Provide exact allowed file globs before execution.",
                    },
                ],
            }
        )
    checks = _string_list(loop.get("checks")) or _string_list(task.definition_of_done.get("command"))
    if not checks:
        questions.append(
            {
                "id": "checks",
                "header": "Checks",
                "text": "What deterministic checks prove this loop result?",
                "options": [
                    {
                        "label": "Use existing test command (Recommended)",
                        "description": "Use the repository's focused test command for this artifact.",
                    },
                    {
                        "label": "Specify manually",
                        "description": "Provide exact commands before execution.",
                    },
                ],
            }
        )
    if not (loop.get("launch_command") or loop.get("final_receipt")):
        questions.append(
            {
                "id": "loop_runtime",
                "header": "Runtime",
                "text": "How should Scillm execute or locate the `$loop` transaction?",
                "options": [
                    {
                        "label": "Use launch_command (Recommended)",
                        "description": "Run a concrete command that launches `$loop` and writes a receipt.",
                    },
                    {
                        "label": "Use existing receipt",
                        "description": "Consume a known final-receipt.json for proof/replay.",
                    },
                ],
            }
        )
    return questions


def build_interview_request(task: Any) -> dict[str, Any]:
    return {
        "title": f"Clarify loop task: {task.task_id}",
        "context": (
            "The task is not executable as a `$loop` artifact transaction until these fields are resolved."
        ),
        "questions": loop_ambiguities(task),
    }


def compile_loop_prompt(task: Any) -> str:
    loop = task.loop
    producer = loop.get("producer") or {}
    verifier = loop.get("verifier") or {}
    scope = loop.get("scope") if isinstance(loop.get("scope"), dict) else {}
    checks = _string_list(loop.get("checks")) or _string_list(task.definition_of_done.get("command"))
    max_attempts = int(loop.get("max_attempts") or task.max_rounds or 3)
    producer_agent = str(producer.get("agent") or "coder")
    verifier_agent = str(verifier.get("agent") or "code-reviewer")
    producer_model = str(producer.get("model") or task.backend or "gpt-5.5")
    verifier_model = str(verifier.get("model") or task.backend or "gpt-5.5")
    producer_reasoning = str(producer.get("reasoning") or "medium")
    verifier_reasoning = str(verifier.get("reasoning") or "high")

    lines = [
        f"$loop {task.prompt.strip()}",
        "",
        f"Use {producer_agent} as the producer subagent:",
        f"- model: {producer_model}",
        f"- reasoning: {producer_reasoning}",
        "",
        f"Use {verifier_agent} as the fresh read-only verifier:",
        f"- model: {verifier_model}",
        f"- reasoning: {verifier_reasoning}",
        "",
        f"Repair until {verifier_agent} returns PASS or {max_attempts} attempts are used.",
        "Stop early if blocked or if scope becomes unclear.",
        "",
        "Scope:",
    ]
    for pattern in _string_list(scope.get("include")):
        lines.append(f"- allowed: {pattern}")
    for pattern in _string_list(scope.get("exclude")):
        lines.append(f"- forbidden: {pattern}")
    if checks:
        lines.extend(["", "Required checks:"])
        lines.extend(f"- {check}" for check in checks)
    lines.extend(
        [
            "",
            "Done means:",
            f"- {verifier_agent} returns PASS",
            "- final receipt validates",
            "- changed-file scope check passes",
            "- required checks pass",
            "- final receipt lists changed files, checks run, stop reason, attempts used, verifier verdict, and remaining risks",
        ]
    )
    return "\n".join(lines) + "\n"


def build_scillm_exec_graph(task: Any, session_dir: Path, prompt_path: Path) -> dict[str, Any]:
    loop = task.loop
    scope = loop.get("scope") if isinstance(loop.get("scope"), dict) else {}
    checks = _string_list(loop.get("checks")) or _string_list(task.definition_of_done.get("command"))
    adapter = Path(__file__).resolve().parent / "loop_node_adapter.py"
    proof_out = session_dir / f"{task.task_id}.loop-node-result.json"
    timeout_s = int(getattr(task, "timeout_seconds", 0) or 1800)
    command = [
        sys.executable,
        str(adapter),
        "--repo",
        str(task.cwd),
        "--prompt",
        str(prompt_path),
        "--validator",
        str(task.cwd / ".agents" / "skills" / "loop" / "scripts" / "validate_loop_receipt.py"),
    ]
    if loop.get("launch_command"):
        command.extend(["--launch-command", str(loop["launch_command"])])
    if loop.get("final_receipt"):
        command.extend(["--receipt", str(loop["final_receipt"])])
    if loop.get("scope_checker"):
        command.extend(["--scope-checker", str(loop["scope_checker"])])
    else:
        command.extend(["--scope-checker", str(task.cwd / ".agents" / "skills" / "loop" / "scripts" / "check_changed_files.py")])
    if loop.get("scope_from_file"):
        command.extend(["--scope-from-file", str(loop["scope_from_file"])])
    for pattern in _string_list(scope.get("include")):
        command.extend(["--scope-include", pattern])
    for pattern in _string_list(scope.get("exclude")):
        command.extend(["--scope-exclude", pattern])
    for check in checks:
        command.extend(["--check-command", check])
    command.extend(["--proof-out", str(proof_out)])

    return {
        "exec_graph_version": "scillm.exec.graph.v1",
        "graph_id": f"orchestrate-loop-{task.task_id}",
        "graph_goal": f"Execute one `$loop` artifact transaction for task {task.task_id}: {task.title}",
        "max_concurrency": 1,
        "cwd": str(task.cwd),
        "metadata": {
            "compiled_from": "orchestrate.runner.loop",
            "task_id": task.task_id,
            "loop_prompt_path": str(prompt_path),
            "node_result_path": str(proof_out),
        },
        "nodes": [
            {
                "id": f"{task.task_id}_loop",
                "type": "local_command",
                "node_goal": "Launch or consume one `$loop` transaction and validate its final receipt.",
                "command": command,
                "timeout_s": timeout_s,
                "idle_timeout_s": timeout_s,
                "allow_failure": False,
                "metadata": {
                    "node_type": "loop/artifact-transaction",
                    "loop_prompt_path": str(prompt_path),
                },
            }
        ],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
