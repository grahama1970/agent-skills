"""Bounded tool implementations for the code-runner backend loop."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .worktree import path_allowed


TOOLS: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "edit_file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}, "content": {"type": "string"}}, "required": ["path", "start_line", "end_line", "content"]}}},
    {"type": "function", "function": {"name": "run_command", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "search_code", "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "glob": {"type": "string"}}, "required": ["pattern"]}}},
]

DENY = {".git", ".env", "SKILL.md", "pyproject.toml", "run.sh"}
BLOCKED = [re.compile(pattern) for pattern in (r"\bgit\s+reset\b", r"\bgit\s+clean\b", r"\brm\s+-rf\b", r"\bsed\s+-i\b")]


def result(ok: bool, **payload: Any) -> str:
    """Return a JSON tool result."""

    return json.dumps({"ok": ok, **payload})


def safe_path(cwd: Path, raw_path: str) -> Path:
    """Resolve a relative path under cwd."""

    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path escapes worktree: {raw_path}")
    if any(part in DENY for part in path.parts):
        raise ValueError(f"path is denylisted: {raw_path}")
    root = cwd.resolve()
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f"path escapes worktree: {raw_path}")
    return resolved


def execute(name: str, args: dict[str, Any], cwd: str | Path, allowlist: list[str], read_context: list[str]) -> str:
    """Execute one bounded tool call."""

    root = Path(cwd).resolve()
    try:
        if name == "read_file":
            path = str(args.get("path", ""))
            if not (path_allowed(path, allowlist) or path_allowed(path, read_context)):
                return result(False, error_type="PERMISSION", error=f"read not allowed: {path}")
            target = safe_path(root, path)
            return result(True, path=path, content=target.read_text(errors="replace")[:12000])
        if name == "write_file":
            path = str(args.get("path", ""))
            if not path_allowed(path, allowlist):
                return result(False, error_type="PERMISSION", error=f"write not allowed: {path}")
            target = safe_path(root, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(args.get("content", "")))
            return result(True, path=path)
        if name == "edit_file":
            path = str(args.get("path", ""))
            if not path_allowed(path, allowlist):
                return result(False, error_type="PERMISSION", error=f"edit not allowed: {path}")
            target = safe_path(root, path)
            lines = target.read_text(errors="replace").splitlines()
            start = int(args.get("start_line", 1))
            end = int(args.get("end_line", start))
            replacement = str(args.get("content", "")).splitlines()
            lines[start - 1:end] = replacement
            target.write_text("\n".join(lines) + "\n")
            return result(True, path=path)
        if name == "run_command":
            command = str(args.get("command", ""))
            source = os.environ.get("CODE_RUNNER_SOURCE_CWD", "")
            if source and source in command:
                command = command.replace(source, str(root))
            if any(pattern.search(command) for pattern in BLOCKED):
                return result(False, error_type="BLOCKED_COMMAND", error="destructive command blocked")
            env = {**os.environ, "CODE_RUNNER_SOURCE_CWD": str(root)}
            proc = subprocess.run(["bash", "-lc", command], cwd=root, text=True, capture_output=True, timeout=60, env=env)
            return result(True, exit_code=proc.returncode, stdout=proc.stdout[-4000:], stderr=proc.stderr[-4000:])
        if name == "search_code":
            cmd = ["rg", "--line-number", "--no-heading", "--max-count=50", str(args.get("pattern", ""))]
            if args.get("glob"):
                cmd.extend(["--glob", str(args["glob"])])
            proc = subprocess.run(cmd, cwd=root, text=True, capture_output=True, timeout=30)
            return result(True, exit_code=proc.returncode, stdout=proc.stdout[:8000], stderr=proc.stderr[:2000])
    except Exception as exc:
        return result(False, error_type="EXCEPTION", error=str(exc))
    return result(False, error_type="UNKNOWN_TOOL", error=f"unknown tool: {name}")
