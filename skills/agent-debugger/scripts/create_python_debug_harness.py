#!/usr/bin/env python3
"""Create Python-first VS Code debug harness artifacts for agent-debugger."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import typer

APP = typer.Typer(add_completion=False, help="Create Python VS Code debug harness artifacts.")


@dataclass(frozen=True)
class BreakpointSpec:
    file: str
    line: int
    expressions: list[str]
    reason: str


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return slug or "debug-task"


def _parse_breakpoint(value: str) -> BreakpointSpec:
    """Parse file:line:expr,expr or file:line."""
    parts = value.split(":", 2)
    if len(parts) < 2:
        raise typer.BadParameter("breakpoint must be file:line or file:line:expr,expr")
    file_name, line_text = parts[0], parts[1]
    try:
        line = int(line_text)
    except ValueError as exc:
        raise typer.BadParameter(f"breakpoint line must be an integer: {line_text}") from exc
    if line < 1:
        raise typer.BadParameter("breakpoint line must be >= 1")
    expressions: list[str] = []
    if len(parts) == 3 and parts[2].strip():
        expressions = [item.strip() for item in parts[2].split(",") if item.strip()]
    return BreakpointSpec(
        file=file_name,
        line=line,
        expressions=expressions,
        reason=f"Inspect runtime state at {file_name}:{line}",
    )


def _parse_json_list(raw: str, field: str) -> list[str]:
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"{field} must be a JSON array of strings: {exc}") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise typer.BadParameter(f"{field} must be a JSON array of strings")
    return list(parsed)


def _strip_jsonc(text: str) -> str:
    """Best-effort JSONC comment stripper for VS Code launch.json files."""
    out: list[str] = []
    in_string = False
    escaped = False
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    cleaned = "".join(out)
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return cleaned


def _load_launch(path: Path) -> dict:
    if not path.exists():
        return {"version": "0.2.0", "configurations": []}
    try:
        data = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Could not parse existing launch.json as JSON/JSONC: {exc}") from exc
    if not isinstance(data, dict):
        raise typer.BadParameter("launch.json root must be an object")
    data.setdefault("version", "0.2.0")
    data.setdefault("configurations", [])
    if not isinstance(data["configurations"], list):
        raise typer.BadParameter("launch.json configurations must be a list")
    return data


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


@APP.command("init-python")
def init_python(
    task: Annotated[str, typer.Option(help="Task/debug-session id used under .plan-iterate/<task>/debug.")],
    target: Annotated[Path, typer.Option(help="Python script path relative to the workspace root.")],
    target_args_json: Annotated[str, typer.Option(help="JSON array of arguments passed to the target script.")] = "[]",
    breakpoint: Annotated[str | None, typer.Option(help="Single breakpoint as file:line or file:line:expr,expr.")] = None,
    breakpoints_json: Annotated[str, typer.Option(help="JSON array of breakpoint strings for multiple breakpoints.")] = "[]",
    root: Annotated[Path, typer.Option(help="Workspace root where artifacts should be created.")] = Path("."),
    plan_root: Annotated[str, typer.Option(help="Plan/evidence root under the workspace.")] = ".plan-iterate",
    launch_name: Annotated[str | None, typer.Option(help="Optional launch.json configuration name.")] = None,
) -> None:
    """Create a Python harness, manifest, and VS Code launch config."""
    target_args = _parse_json_list(target_args_json, "target_args_json")
    breakpoint_args = _parse_json_list(breakpoints_json, "breakpoints_json")
    if breakpoint:
        breakpoint_args.append(breakpoint)

    workspace = root.resolve()
    target_rel = target.as_posix()
    target_path = (workspace / target_rel).resolve()
    if not target_path.exists():
        raise typer.BadParameter(f"target does not exist: {target_rel}")
    if target_path.suffix != ".py":
        raise typer.BadParameter("v1 supports Python script targets ending in .py only")

    task_slug = _slug(task)
    debug_dir = workspace / plan_root / task_slug / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    harness_path = debug_dir / f"harness_{task_slug.replace('-', '_').replace('.', '_')}.py"
    launch_config_name = launch_name or f"Agent Debugger: {task_slug}"

    argv_literal = repr([target_rel, *target_args])
    harness = f'''#!/usr/bin/env python3
"""Generated by agent-debugger. Do not edit production code for debugging."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
os.chdir(WORKSPACE)
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

sys.argv = {argv_literal}
runpy.run_path(str(WORKSPACE / {target_rel!r}), run_name="__main__")
'''
    harness_path.write_text(harness, encoding="utf-8")
    harness_path.chmod(0o755)

    breakpoint_specs = [_parse_breakpoint(item) for item in breakpoint_args]
    breakpoints = [
        {
            "file": spec.file,
            "line": spec.line,
            "reason": spec.reason,
            "expressions": spec.expressions,
            "stop": True,
            "source": "agent",
        }
        for spec in breakpoint_specs
    ]

    commands_path = debug_dir / "debug_commands.jsonl"
    observations_path = debug_dir / "debug_observations.jsonl"
    state_path = debug_dir / "debug_session_state.json"
    notes_path = debug_dir / "notes.md"
    manifest_path = debug_dir / "debug_manifest.json"

    for jsonl_path in (commands_path, observations_path):
        if not jsonl_path.exists():
            jsonl_path.write_text("", encoding="utf-8")

    _write_json(
        state_path,
        {
            "schema": "agent_debugger_session_state.v1",
            "status": "not_started",
            "managed_session": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    manifest = {
        "schema": "agent_debugger_manifest.v1",
        "version": 1,
        "language": "python",
        "task": task_slug,
        "launch_config_name": launch_config_name,
        "harness": _relative(harness_path, workspace),
        "target": target_rel,
        "target_args": target_args,
        "breakpoints": breakpoints,
        "commands_path": _relative(commands_path, workspace),
        "observations_path": _relative(observations_path, workspace),
        "session_state_path": _relative(state_path, workspace),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lifecycle": {
            "replay_semantics": "stop_and_restart_same_launch_config",
            "managed_session_only": True,
        },
    }
    _write_json(manifest_path, manifest)

    vscode_dir = workspace / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    launch_path = vscode_dir / "launch.json"
    launch = _load_launch(launch_path)
    config = {
        "name": launch_config_name,
        "type": "debugpy",
        "request": "launch",
        "program": "${workspaceFolder}/" + _relative(harness_path, workspace),
        "cwd": "${workspaceFolder}",
        "console": "integratedTerminal",
        "justMyCode": False,
        "env": {"PYTHONUNBUFFERED": "1"},
    }
    launch["configurations"] = [
        existing for existing in launch["configurations"] if existing.get("name") != launch_config_name
    ]
    launch["configurations"].append(config)
    _write_json(launch_path, launch)

    notes_path.write_text(
        "# Agent Debugger Session\n\n"
        f"Task: `{task_slug}`\n\n"
        f"Launch config: `{launch_config_name}`\n\n"
        f"Target: `{target_rel} {shlex.join(target_args)}`\n\n"
        "Use the VS Code command `Agent Debugger: Run Current Manifest` after loading this manifest.\n",
        encoding="utf-8",
    )

    result = {
        "status": "created",
        "task": task_slug,
        "manifest": _relative(manifest_path, workspace),
        "harness": _relative(harness_path, workspace),
        "launch_json": _relative(launch_path, workspace),
        "launch_config_name": launch_config_name,
        "breakpoint_count": len(breakpoints),
    }
    typer.echo(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    APP()
