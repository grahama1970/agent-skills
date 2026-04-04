"""Tool-use agent loop for code-runner v4.

The LLM calls tools (write_file, edit_file, read_file, run_command) and
code-runner executes them. No output parsing. No diff guessing.

This is how Cursor, Claude Code, Aider, and every working agent CLI works.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import httpx
from loguru import logger

SCILLM_URL = os.environ.get("SCILLM_API_BASE", "http://localhost:4001/v1/chat/completions")
SCILLM_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

# Paths that should NEVER be written by an LLM
DENYLIST = {".git", ".gitignore", ".env", "SKILL.md", "run.sh", "sanity.sh", "pyproject.toml", "package.json"}

# Max iterations to prevent runaway tool loops
MAX_TOOL_ITERATIONS = 20

TREESITTER_RUN = Path(__file__).resolve().parent.parent / "treesitter" / "run.sh"


# ── Repo Map (tree-sitter symbols for context) ─────────────────────


def build_repo_map(files: list[str], cwd: str) -> str:
    """Build a repo map of symbols from tree-sitter, like Aider's repomap.

    Gives the LLM a table of contents — function names, class names, signatures —
    so it knows what exists before editing. No need to read_file every file.
    """
    if not TREESITTER_RUN.exists():
        return ""

    sections = []
    for rel_path in files:
        target = Path(cwd) / rel_path
        if not target.exists():
            continue
        try:
            clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
            clean_env["PATH"] = os.pathsep.join(
                p for p in clean_env.get("PATH", "").split(os.pathsep)
                if ".venv" not in p
            )
            # Call treesitter via uvx directly — local install may be broken
            proc = subprocess.run(
                ["uvx", "--from", "git+https://github.com/grahama1970/treesitter-tools.git",
                 "treesitter-tools", "symbols", str(target)],
                capture_output=True, text=True, timeout=15,
                env=clean_env,
            )
            if proc.returncode != 0:
                continue
            symbols = json.loads(proc.stdout)
            if not symbols:
                continue
            lines = [f"\n{rel_path}:"]
            for sym in symbols:
                sig = sym.get("signature", "")
                if sig:
                    lines.append(f"  {sig}")
                else:
                    lines.append(f"  {sym.get('kind', '?')} {sym.get('name', '?')} (line {sym.get('start_line', '?')})")
            sections.append("\n".join(lines))
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            continue

    if not sections:
        return ""

    return "## Repo Map (symbols in scope)\n" + "\n".join(sections) + "\n"


# ── Tool Definitions (OpenAI format — scillm translates per backend) ─


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write complete content to a file. Creates parent directories. Use for new files or full rewrites of small files (<200 lines).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to working directory"},
                    "content": {"type": "string", "description": "Complete file content"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace a specific line range in an existing file. Use for surgical edits to larger files. Lines are 1-indexed, inclusive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to working directory"},
                    "start_line": {"type": "integer", "description": "First line to replace (1-indexed)"},
                    "end_line": {"type": "integer", "description": "Last line to replace (inclusive)"},
                    "content": {"type": "string", "description": "Replacement content for that line range"},
                },
                "required": ["path", "start_line", "end_line", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file's content. Use to check current state before editing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to working directory"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command and return stdout+stderr. Use to check tests, lint, or verify changes. Max 30 seconds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                },
                "required": ["command"],
            },
        },
    },
]


# ── Tool Execution ──────────────────────────────────────────────────


def _is_path_safe(path: str, cwd: str, allowlist: list[str] | None) -> str | None:
    """Check if path is authorized for writing. Returns cleaned path or None."""
    clean = path.lstrip("/")
    if any(clean == d or clean.startswith(d + "/") for d in DENYLIST):
        return None
    cwd_path = Path(cwd).resolve()
    target = (cwd_path / clean).resolve()
    try:
        target.relative_to(cwd_path)
    except ValueError:
        return None
    if allowlist is not None:
        # Exact match or directory scope
        stem = Path(clean).with_suffix("")
        for a in allowlist:
            if clean == a or clean == a.lstrip("/"):
                return clean
            if a.endswith("/") and clean.startswith(a.rstrip("/") + "/"):
                return clean
            # Fuzzy extension match
            if Path(a).with_suffix("") == stem:
                return a
        return None
    return clean


def execute_tool(
    name: str, arguments: dict, cwd: str, allowlist: list[str] | None,
) -> str:
    """Execute a tool call and return the result string."""

    if name == "write_file":
        path = arguments.get("path", "")
        content = arguments.get("content", "")
        safe = _is_path_safe(path, cwd, allowlist)
        if not safe:
            return f"ERROR: Path '{path}' not in allowlist or is denylisted. Allowlist: {allowlist}"
        target = Path(cwd) / safe
        # Truncation guard
        if target.exists():
            existing_lines = len(target.read_text(errors="replace").splitlines())
            new_lines = len(content.splitlines())
            if existing_lines > 500 and new_lines < existing_lines * 0.5:
                return (f"ERROR: Truncation guard — existing file has {existing_lines} lines, "
                        f"replacement has {new_lines}. Use edit_file for surgical changes.")
        # Python lint gate
        if safe.endswith(".py"):
            try:
                compile(content, safe, "exec")
            except SyntaxError as e:
                return f"ERROR: Python syntax error — {e}. Fix and retry."
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        logger.info("  tool: write_file {} ({} lines)", safe, len(content.splitlines()))
        return f"OK: Wrote {safe} ({len(content.splitlines())} lines)"

    elif name == "edit_file":
        path = arguments.get("path", "")
        start = arguments.get("start_line", 1)
        end = arguments.get("end_line", 1)
        content = arguments.get("content", "")
        safe = _is_path_safe(path, cwd, allowlist)
        if not safe:
            return f"ERROR: Path '{path}' not in allowlist. Allowlist: {allowlist}"
        target = Path(cwd) / safe
        if not target.exists():
            return f"ERROR: File '{safe}' does not exist. Use write_file to create it."
        lines = target.read_text(errors="replace").splitlines(keepends=True)
        if start < 1 or end > len(lines) or start > end:
            return f"ERROR: Line range {start}-{end} invalid for file with {len(lines)} lines."
        replacement = content.splitlines(keepends=True)
        if replacement and not replacement[-1].endswith("\n"):
            replacement[-1] += "\n"
        lines[start - 1:end] = replacement
        new_content = "".join(lines)
        if safe.endswith(".py"):
            try:
                compile(new_content, safe, "exec")
            except SyntaxError as e:
                return f"ERROR: Edit would create syntax error — {e}. Fix and retry."
        target.write_text(new_content)
        logger.info("  tool: edit_file {} lines {}-{} → {} lines", safe, start, end, len(replacement))
        return f"OK: Edited {safe} lines {start}-{end}"

    elif name == "read_file":
        path = arguments.get("path", "")
        clean = path.lstrip("/")
        target = Path(cwd) / clean
        if not target.exists():
            return f"ERROR: File '{clean}' does not exist."
        content = target.read_text(errors="replace")
        # Cap at 500 lines to prevent context flooding
        lines = content.splitlines()
        if len(lines) > 500:
            return f"File: {clean} ({len(lines)} lines — showing first 500)\n" + "\n".join(
                f"{i+1}: {l}" for i, l in enumerate(lines[:500])
            ) + f"\n... ({len(lines) - 500} more lines)"
        return f"File: {clean} ({len(lines)} lines)\n" + "\n".join(
            f"{i+1}: {l}" for i, l in enumerate(lines)
        )

    elif name == "run_command":
        command = arguments.get("command", "")
        # Strip .venv from PATH
        clean_env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        clean_env["PATH"] = os.pathsep.join(
            p for p in clean_env.get("PATH", "").split(os.pathsep)
            if ".venv" not in p
        )
        try:
            proc = subprocess.run(
                ["bash", "-lc", command],
                capture_output=True, text=True, timeout=30, cwd=cwd, env=clean_env,
            )
            output = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
            # Cap output
            if len(output) > 5000:
                output = output[:5000] + "\n... (truncated)"
            logger.info("  tool: run_command exit={} '{}'", proc.returncode, command[:80])
            return f"exit_code: {proc.returncode}\n{output}"
        except subprocess.TimeoutExpired:
            return "ERROR: Command timed out after 30 seconds."
        except Exception as e:
            return f"ERROR: {e}"

    return f"ERROR: Unknown tool '{name}'"


# ── Agent Loop ──────────────────────────────────────────────────────


def run_tool_use_loop(
    system_prompt: str,
    user_prompt: str,
    model: str,
    cwd: str,
    allowlist: list[str] | None = None,
    read_context: list[str] | None = None,
    temperature: float = 0.2,
    max_tokens: int = 8000,
) -> tuple[list[str], list[dict]]:
    """Run the tool-use agent loop. Returns (files_written, messages).

    The LLM decides what to read, edit, and run. Code-runner just executes
    the tool calls and feeds results back. Loop ends when the LLM stops
    calling tools (sends a text response instead).
    """
    # Build repo map from allowlist + read_context so LLM knows what exists
    all_files = list(allowlist or []) + list(read_context or [])
    repo_map = build_repo_map(all_files, cwd)
    if repo_map:
        system_prompt = system_prompt + "\n\n" + repo_map
        logger.info("  Repo map: {} files, {} symbols", len(all_files),
                     repo_map.count("\n  "))

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    files_written: list[str] = []

    payload_base: dict = {
        "model": model,
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": max_tokens,
    }
    if not model.startswith("gpt-"):
        payload_base["temperature"] = min(temperature, 1.0)

    for iteration in range(MAX_TOOL_ITERATIONS):
        payload = {**payload_base, "messages": messages}

        # Call LLM
        try:
            resp = httpx.post(
                SCILLM_URL,
                headers={"Authorization": f"Bearer {SCILLM_KEY}"},
                json=payload,
                timeout=180.0,
            )
            if resp.status_code in (500, 502, 503, 429):
                wait = 2 ** min(iteration, 3)
                logger.warning("/scillm {} — retrying in {}s", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("Tool loop LLM call failed: {}", e)
            break

        choice = data["choices"][0]
        msg = choice["message"]
        finish = choice.get("finish_reason", "stop")

        # Append assistant message to conversation
        messages.append(msg)

        # If no tool calls — LLM is done (text response or stop)
        tool_calls = msg.get("tool_calls")
        if not tool_calls or finish == "stop":
            logger.info("  Tool loop complete after {} iterations", iteration + 1)
            break

        # Execute each tool call and append results
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                fn_args = {}

            result = execute_tool(fn_name, fn_args, cwd, allowlist)

            # Track written files
            if fn_name in ("write_file", "edit_file") and result.startswith("OK:"):
                path = fn_args.get("path", "")
                safe = _is_path_safe(path, cwd, allowlist)
                if safe and safe not in files_written:
                    files_written.append(safe)

            # Feed result back to LLM
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

    return files_written, messages
