"""Tool-use agent loop for code-runner v4.

The LLM calls tools (write_file, edit_file, read_file, run_command) and
code-runner executes them. No output parsing. No diff guessing.

This is how Cursor, Claude Code, Aider, and every working agent CLI works.

v4.1: Hermes-inspired reliability improvements:
  - Structured JSON tool results (consistent schema for all tools)
  - Strict invalid-args handling (no silent coercion to {})
  - Message sanitization (strip surrogates before API calls)
  - Duplicate-call suppression (block repeated identical failing calls)
  - Stronger mutation blocking (expanded destructive command patterns)

v4.2: Error classification and fallback parsing:
  - Smart error classifier (context overflow, billing, rate limit → recovery action)
  - Fallback tool call parser (Hermes, DeepSeek V3, generic XML formats)
  - Reasoning extraction (<think> blocks, reasoning_content fields)

v4.3: Hermes-inspired duplicate-call suppression and mutation blocking
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

# Common utilities
import sys
_skills_dir = Path(os.environ.get("SKILLS_DIR", str(Path(__file__).resolve().parent.parent)))
_common = str(_skills_dir / "common")
if _common not in sys.path:
    sys.path.insert(0, _common)

from json_utils import parse_json
from message_utils import sanitize_messages

# Local modules
from _error_classifier import classify_api_error
from _tool_call_parser import parse_tool_calls, to_openai_format


def normalize_scillm_chat_url(raw_url: str | None) -> str:
    """Return the concrete OpenAI-compatible chat completions endpoint."""
    url = (raw_url or "http://localhost:4001/v1/chat/completions").strip().rstrip("/")
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path in ("", "/"):
        return f"{url}/v1/chat/completions"
    if path == "/v1":
        return f"{url}/chat/completions"
    return url


SCILLM_URL = normalize_scillm_chat_url(os.environ.get("SCILLM_API_BASE"))
SCILLM_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

# Mock response function for testing. When set, bypasses HTTP calls and returns mock responses.
# Set to a callable(payload: dict) -> str that returns the LLM response text.
_mock_response_fn: Optional[callable] = None

# Valid tool names for this agent
VALID_TOOLS = {"write_file", "edit_file", "read_file", "run_command", "search_code"}


# Paths that should NEVER be written by an LLM
DENYLIST = {".git", ".gitignore", ".env", "SKILL.md", "run.sh", "sanity.sh", "pyproject.toml", "package.json"}

# Max iterations to prevent runaway tool loops
MAX_TOOL_ITERATIONS = 20


def _emit_backend_stream_event(
    event_emitter: Any,
    *,
    round_num: int,
    event: str,
    payload: dict[str, Any] | None = None,
) -> None:
    if event_emitter is None:
        return
    try:
        from models import EventType
        event_emitter.emit(
            EventType.backend_stream_event,
            round=round_num,
            payload={"event": event, **(payload or {})},
        )
    except Exception as exc:
        logger.debug("failed to emit backend stream event {}: {}", event, exc)


def _merge_stream_delta(message: dict[str, Any], delta: dict[str, Any]) -> None:
    if delta.get("role"):
        message["role"] = delta["role"]
    if delta.get("content"):
        message["content"] = message.get("content", "") + delta["content"]
    if delta.get("reasoning"):
        message["reasoning"] = message.get("reasoning", "") + str(delta["reasoning"])
    if delta.get("reasoning_content"):
        message["reasoning_content"] = message.get("reasoning_content", "") + str(delta["reasoning_content"])

    for tool_delta in delta.get("tool_calls") or []:
        raw_index = tool_delta.get("index")
        index = int(raw_index) if raw_index is not None else -1
        tool_calls = message.setdefault("_tool_calls_by_index", {})
        fn_delta = tool_delta.get("function") or {}
        if raw_index is None and not fn_delta.get("name"):
            named_indices = [
                existing_index
                for existing_index, existing_call in tool_calls.items()
                if existing_call.get("function", {}).get("name")
            ]
            if len(named_indices) == 1:
                index = named_indices[0]
            elif len(named_indices) > 1:
                index = max(named_indices)
        if raw_index is None and fn_delta.get("name"):
            index = max(tool_calls.keys(), default=-1) + 1
        if raw_index is not None and index not in tool_calls and not fn_delta.get("name"):
            named_indices = [
                existing_index
                for existing_index, existing_call in tool_calls.items()
                if existing_call.get("function", {}).get("name")
            ]
            if len(named_indices) == 1:
                index = named_indices[0]
            elif len(named_indices) > 1:
                index = max(named_indices)
        if raw_index is not None and index not in tool_calls and fn_delta.get("name"):
            unnamed_indices = [
                existing_index
                for existing_index, existing_call in tool_calls.items()
                if not existing_call.get("function", {}).get("name")
            ]
            if len(unnamed_indices) == 1:
                index = unnamed_indices[0]
            elif len(unnamed_indices) > 1:
                raise ValueError("ambiguous tool-call stream: name arrived on a new index with multiple unnamed calls pending")
        current = tool_calls.setdefault(
            index,
            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
        )
        if tool_delta.get("id"):
            current["id"] += tool_delta["id"]
        if tool_delta.get("type"):
            current["type"] = tool_delta["type"]
        if fn_delta.get("name"):
            current["function"]["name"] += fn_delta["name"]
        if fn_delta.get("arguments"):
            current["function"]["arguments"] += fn_delta["arguments"]


def _finalize_stream_message(message: dict[str, Any]) -> dict[str, Any]:
    tool_calls_by_index = message.pop("_tool_calls_by_index", {})
    if tool_calls_by_index:
        incomplete = [
            index
            for index, tool_call in tool_calls_by_index.items()
            if not tool_call.get("function", {}).get("name")
        ]
        if incomplete:
            raise ValueError(f"incomplete tool-call stream: missing function name for indices {incomplete}")
        message["tool_calls"] = [
            {**tool_call, "id": tool_call.get("id") or f"call_{index}"}
            for index, tool_call in sorted(tool_calls_by_index.items())
        ]
    message.setdefault("role", "assistant")
    message.setdefault("content", "")
    return message


def _stream_chat_completion(
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    event_emitter: Any,
    round_num: int,
    idle_timeout: float,
    hard_wall_timeout: float,
) -> dict[str, Any]:
    """Call /scillm with SSE and return one OpenAI-compatible chat response.

    Liveness is event-based: heartbeat comments, progress data, token deltas, and
    tool-call deltas all reset the read timeout. The caller still gets a hard
    wall-clock budget to prevent unbounded provider hangs.
    """
    stream_payload = {
        **payload,
        "stream": True,
        "stream_heartbeat_s": int(os.environ.get("CODE_RUNNER_STREAM_HEARTBEAT_S", "15")),
        "stream_progress_events": True,
        "timeout": hard_wall_timeout,
    }
    timeout = httpx.Timeout(
        connect=10.0,
        read=max(float(idle_timeout), 1.0),
        write=30.0,
        pool=30.0,
    )
    started = time.monotonic()
    finish_reason = ""
    message: dict[str, Any] = {"role": "assistant", "content": ""}
    chunks = 0
    saw_done = False
    saw_model_delta = False

    _emit_backend_stream_event(
        event_emitter,
        round_num=round_num,
        event="stream_started",
        payload={"idle_timeout": idle_timeout, "hard_wall_timeout": hard_wall_timeout},
    )
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", SCILLM_URL, headers=headers, json=stream_payload) as response:
                if response.status_code >= 400:
                    body = response.read().decode(errors="replace")
                    raise httpx.HTTPStatusError(
                        f"/scillm stream returned HTTP {response.status_code}: {body[:500]}",
                        request=response.request,
                        response=response,
                    )

                for line in response.iter_lines():
                    elapsed = time.monotonic() - started
                    if elapsed > hard_wall_timeout:
                        raise TimeoutError(
                            f"/scillm stream exceeded hard_wall_timeout={hard_wall_timeout:.1f}s"
                        )
                    if not line:
                        continue
                    if line.startswith(":"):
                        _emit_backend_stream_event(
                            event_emitter,
                            round_num=round_num,
                            event="heartbeat",
                            payload={"elapsed_seconds": round(elapsed, 3)},
                        )
                        continue
                    if not line.startswith("data:"):
                        _emit_backend_stream_event(
                            event_emitter,
                            round_num=round_num,
                            event="sse_line",
                            payload={"line": line[:200]},
                        )
                        continue

                    data_text = line[5:].strip()
                    if data_text == "[DONE]":
                        saw_done = True
                        break
                    if os.environ.get("CODE_RUNNER_DEBUG_SSE") == "1":
                        logger.debug("  SSE chunk: {}", data_text[:1000])
                    try:
                        event = json.loads(data_text)
                    except json.JSONDecodeError:
                        _emit_backend_stream_event(
                            event_emitter,
                            round_num=round_num,
                            event="invalid_json_chunk",
                            payload={"chunk": data_text[:200]},
                        )
                        continue

                    if event.get("event") and not event.get("choices"):
                        _emit_backend_stream_event(
                            event_emitter,
                            round_num=round_num,
                            event=str(event.get("event")),
                            payload={k: v for k, v in event.items() if k != "event"},
                        )
                        continue

                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    if delta.get("content") or delta.get("reasoning") or delta.get("reasoning_content") or delta.get("tool_calls"):
                        saw_model_delta = True
                    _merge_stream_delta(message, delta)
                    chunks += 1
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
    except httpx.ReadTimeout as exc:
        raise TimeoutError(f"/scillm stream idle_timeout={idle_timeout:.1f}s elapsed with no SSE event") from exc

    message = _finalize_stream_message(message)
    has_response_payload = bool(
        message.get("content")
        or message.get("tool_calls")
        or message.get("reasoning")
        or message.get("reasoning_content")
    )
    if not (saw_done or finish_reason):
        raise TimeoutError("/scillm stream ended without terminal [DONE] or finish_reason")
    if not saw_model_delta or not has_response_payload:
        raise TimeoutError("/scillm stream ended without assistant content, reasoning, or tool calls")
    _emit_backend_stream_event(
        event_emitter,
        round_num=round_num,
        event="stream_complete",
        payload={"chunks": chunks, "finish_reason": finish_reason or "stop"},
    )
    return {"choices": [{"message": message, "finish_reason": finish_reason or "stop"}]}

# Destructive command patterns for run_command blocking (Hermes-inspired)
# Each tuple is (compiled_regex, error_message)
DESTRUCTIVE_PATTERNS = [
    (re.compile(r'\bgit\s+reset\s+--hard'), "git reset --hard blocked — use git checkout for specific files"),
    (re.compile(r'\bgit\s+clean\s+-[fd]'), "git clean blocked — could delete untracked work"),
    (re.compile(r'\bsed\s+-i'), "sed -i blocked — use edit_file for modifications"),
    (re.compile(r'\btruncate\s'), "truncate blocked — use write_file instead"),
    (re.compile(r'\bdd\s+.*\bof='), "dd with output blocked — use write_file instead"),
    (re.compile(r'\bshred\s'), "shred blocked — files cannot be securely deleted"),
    (re.compile(r"<<['\"]?EOF"), "Heredoc to file blocked — use write_file instead"),
    (re.compile(r'\bchmod\s+[+0-7]*x'), "chmod +x blocked — code-runner manages execution"),
    (re.compile(r'\b(cat|echo)\s+.*>\s*\S+\.(py|ts|js|sh|json|yaml|yml)\b'), "Redirect to code file blocked — use write_file"),
]


# ── Structured Tool Results ────────────────────────────────────────────
# All tools return JSON with a consistent schema for reliable downstream parsing.


def _tool_result(
    ok: bool,
    tool: str,
    *,
    path: Optional[str] = None,
    exit_code: Optional[int] = None,
    stdout_preview: Optional[str] = None,
    stderr_preview: Optional[str] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    retryable: bool = True,
    lines_affected: Optional[int] = None,
    **extra: Any,
) -> str:
    """Return structured JSON tool result.

    Error types:
    - PERMISSION: Path not in allowlist or denylisted
    - SYNTAX: Python syntax error in written code
    - STALE: File modified since last read
    - TRUNCATION: Write would truncate existing file
    - INVALID_ARGS: Could not parse tool arguments
    - UNKNOWN_TOOL: Tool name not recognized
    - DUPLICATE_CALL: Same call already made this round
    - BLOCKED_COMMAND: Destructive command pattern detected
    - NOT_FOUND: File does not exist
    - LINE_RANGE: Invalid line range for edit
    - TIMEOUT: Command timed out
    - EXECUTION: Command execution failed
    """
    result: dict[str, Any] = {"ok": ok, "tool": tool}
    if path is not None:
        result["path"] = path
    if exit_code is not None:
        result["exit_code"] = exit_code
    if stdout_preview is not None:
        result["stdout_preview"] = stdout_preview
    if stderr_preview is not None:
        result["stderr_preview"] = stderr_preview
    if error_type is not None:
        result["error_type"] = error_type
    if error_message is not None:
        result["error_message"] = error_message
    if not ok:
        result["retryable"] = retryable
    if lines_affected is not None:
        result["lines_affected"] = lines_affected
    if extra:
        result.update(extra)
    return json.dumps(result)

def _retry_delay(attempt: int, max_delay: float = 32.0) -> float:
    """Exponential backoff with jitter. Prevents thundering herd."""
    base = min(0.5 * (2 ** attempt), max_delay)
    return base + random.random() * 0.25 * base


# Pattern for extracting <think>...</think> blocks from content
_THINK_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def _extract_reasoning(msg: dict) -> Optional[str]:
    """Extract reasoning from assistant message.

    Handles multiple provider formats:
    1. msg["reasoning_content"] field (Anthropic, some providers)
    2. msg["reasoning"] field (OpenRouter)
    3. <think>...</think> blocks in content (Qwen, DeepSeek)

    Returns:
        Extracted reasoning text, or None if not found
    """
    # Check dedicated reasoning fields
    if msg.get("reasoning_content"):
        return msg["reasoning_content"]
    if msg.get("reasoning"):
        return msg["reasoning"]

    # Check for <think> blocks in content
    content = msg.get("content", "")
    if content and "<think>" in content:
        matches = _THINK_PATTERN.findall(content)
        if matches:
            return "\n".join(m.strip() for m in matches)

    return None


# File staleness tracking: {path: (content_hash, mtime)}
_file_state: dict[str, tuple[str, float]] = {}


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode(errors="replace")).hexdigest()[:16]


def _track_file_read(path: Path) -> None:
    """Record file state on read for staleness detection."""
    try:
        content = path.read_text(errors="replace")
        _file_state[str(path)] = (_hash_content(content), path.stat().st_mtime)
    except OSError:
        pass


def _check_file_stale(path: Path) -> str | None:
    """Check if file changed since last read. Returns error message or None."""
    key = str(path)
    if key not in _file_state:
        return None  # Never tracked — allow write
    old_hash, old_mtime = _file_state[key]
    try:
        current_mtime = path.stat().st_mtime
    except OSError:
        return None  # File deleted — allow write (create_file case)
    if current_mtime == old_mtime:
        return None  # Unchanged
    # Mtime changed — compare content hash (avoids false positives from touch/cloud sync)
    try:
        current_hash = _hash_content(path.read_text(errors="replace"))
    except OSError:
        return None
    if current_hash == old_hash:
        # Content same, mtime different — update tracking and allow
        _file_state[key] = (current_hash, current_mtime)
        return None
    return (f"STALE: {path.name} was modified externally since last read "
            f"(hash {old_hash}→{current_hash}). Re-read before editing.")


# ── Repo Map ───────────────────────────────────────────────────────


def build_repo_map(files: list[str], cwd: str) -> str:
    """Repo maps are disabled in the minimal runner."""

    return ""


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
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search codebase for patterns using ripgrep. Use to find usages, implementations, or related code. Returns file:line matches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "glob": {"type": "string", "description": "File glob filter (e.g. '*.py', 'src/**/*.ts'). Optional."},
                },
                "required": ["pattern"],
            },
        },
    },
]
TOOLS = [tool for tool in TOOLS if tool["function"]["name"] in VALID_TOOLS]


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
    """Execute a tool call and return structured JSON result."""

    if name == "write_file":
        path = arguments.get("path", "")
        content = arguments.get("content", "")
        safe = _is_path_safe(path, cwd, allowlist)
        if not safe:
            return _tool_result(
                ok=False, tool="write_file", path=path,
                error_type="PERMISSION",
                error_message=f"Path not in allowlist or is denylisted. Allowlist: {allowlist}",
            )
        target = Path(cwd) / safe
        # Staleness check — reject if file changed since last read
        stale_msg = _check_file_stale(target)
        if stale_msg:
            return _tool_result(
                ok=False, tool="write_file", path=safe,
                error_type="STALE", error_message=stale_msg,
            )
        # Full-file rewrite guard — force edit_file for existing large files
        if target.exists():
            existing_lines = len(target.read_text(errors="replace").splitlines())
            new_lines = len(content.splitlines())
            if existing_lines > 500 and new_lines < existing_lines * 0.5:
                return _tool_result(
                    ok=False, tool="write_file", path=safe,
                    error_type="TRUNCATION",
                    error_message=f"Existing file has {existing_lines} lines, replacement has {new_lines}. Use edit_file for surgical changes.",
                )
            if existing_lines > 100:
                return _tool_result(
                    ok=False, tool="write_file", path=safe,
                    error_type="TRUNCATION",
                    error_message=f"File exists with {existing_lines} lines. Use read_file then edit_file for surgical changes.",
                )
        # Python lint gate
        if safe.endswith(".py"):
            try:
                compile(content, safe, "exec")
            except SyntaxError as e:
                return _tool_result(
                    ok=False, tool="write_file", path=safe,
                    error_type="SYNTAX", error_message=f"Python syntax error: {e}",
                )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        _track_file_read(target)  # Update tracking after write
        lines_written = len(content.splitlines())
        logger.info("  tool: write_file {} ({} lines)", safe, lines_written)
        return _tool_result(ok=True, tool="write_file", path=safe, lines_affected=lines_written)

    elif name == "edit_file":
        path = arguments.get("path", "")
        start = arguments.get("start_line", 1)
        end = arguments.get("end_line", 1)
        content = arguments.get("content", "")
        safe = _is_path_safe(path, cwd, allowlist)
        if not safe:
            return _tool_result(
                ok=False, tool="edit_file", path=path,
                error_type="PERMISSION",
                error_message=f"Path not in allowlist. Allowlist: {allowlist}",
            )
        target = Path(cwd) / safe
        if not target.exists():
            return _tool_result(
                ok=False, tool="edit_file", path=safe,
                error_type="NOT_FOUND",
                error_message="File does not exist. Use write_file to create it.",
            )
        # Staleness check
        stale_msg = _check_file_stale(target)
        if stale_msg:
            return _tool_result(
                ok=False, tool="edit_file", path=safe,
                error_type="STALE", error_message=stale_msg,
            )
        lines = target.read_text(errors="replace").splitlines(keepends=True)
        if start < 1 or end > len(lines) or start > end:
            return _tool_result(
                ok=False, tool="edit_file", path=safe,
                error_type="LINE_RANGE",
                error_message=f"Line range {start}-{end} invalid for file with {len(lines)} lines.",
            )
        replacement = content.splitlines(keepends=True)
        if replacement and not replacement[-1].endswith("\n"):
            replacement[-1] += "\n"
        # Truncation guard for edit_file
        replaced_lines = end - start + 1
        new_lines_count = len(replacement)
        if len(lines) > 500 and replaced_lines > len(lines) * 0.8 and new_lines_count < replaced_lines * 0.5:
            return _tool_result(
                ok=False, tool="edit_file", path=safe,
                error_type="TRUNCATION",
                error_message=f"Editing {replaced_lines}/{len(lines)} lines but replacement is only {new_lines_count} lines ({new_lines_count*100//replaced_lines}%). Use smaller edit ranges.",
            )

        lines[start - 1:end] = replacement
        new_content = "".join(lines)
        if safe.endswith(".py"):
            try:
                compile(new_content, safe, "exec")
            except SyntaxError as e:
                return _tool_result(
                    ok=False, tool="edit_file", path=safe,
                    error_type="SYNTAX",
                    error_message=f"Edit would create syntax error: {e}",
                )
        target.write_text(new_content)
        _track_file_read(target)  # Update tracking after edit
        logger.info("  tool: edit_file {} lines {}-{} → {} lines", safe, start, end, new_lines_count)
        return _tool_result(
            ok=True, tool="edit_file", path=safe,
            lines_affected=new_lines_count, start_line=start, end_line=end,
        )

    elif name == "read_file":
        path = arguments.get("path", "")
        clean = path.lstrip("/")
        target = Path(cwd) / clean
        if not target.exists():
            return _tool_result(
                ok=False, tool="read_file", path=clean,
                error_type="NOT_FOUND", error_message="File does not exist.",
            )
        content = target.read_text(errors="replace")
        _track_file_read(target)  # Track for staleness detection
        # Cap at 500 lines to prevent context flooding
        lines = content.splitlines()
        total_lines = len(lines)
        if total_lines > 500:
            preview = "\n".join(f"{i+1}: {l}" for i, l in enumerate(lines[:500]))
            return _tool_result(
                ok=True, tool="read_file", path=clean,
                lines_affected=total_lines, truncated=True,
                content=f"File: {clean} ({total_lines} lines — showing first 500)\n{preview}\n... ({total_lines - 500} more lines)",
            )
        file_content = "\n".join(f"{i+1}: {l}" for i, l in enumerate(lines))
        return _tool_result(
            ok=True, tool="read_file", path=clean,
            lines_affected=total_lines,
            content=f"File: {clean} ({total_lines} lines)\n{file_content}",
        )

    elif name == "run_command":
        command = arguments.get("command", "")

        # Check destructive patterns (expanded from Hermes-inspired analysis)
        for pattern, msg in DESTRUCTIVE_PATTERNS:
            if pattern.search(command):
                return _tool_result(
                    ok=False, tool="run_command",
                    error_type="BLOCKED_COMMAND", error_message=msg, retryable=False,
                    command=command[:100],
                )

        # Legacy rm/mv/redirect blocks (kept for completeness)
        if re.search(r'\brm\s', command) and not re.search(r'\brm\s+(-rf?\s+)?(\/tmp|__pycache__|\.pytest_cache|node_modules|dist|build)\b', command):
            return _tool_result(
                ok=False, tool="run_command",
                error_type="BLOCKED_COMMAND",
                error_message="rm blocked — use edit_file or write_file to modify files.",
                retryable=False, command=command[:100],
            )
        if re.search(r'\bmv\s.*\.(py|ts|tsx|js|jsx|sh)\b', command):
            return _tool_result(
                ok=False, tool="run_command",
                error_type="BLOCKED_COMMAND",
                error_message="mv of code files blocked — use write_file to create files at new paths.",
                retryable=False, command=command[:100],
            )

        source_cwd = os.environ.get("CODE_RUNNER_SOURCE_CWD", "")
        if source_cwd and source_cwd in command:
            return _tool_result(
                ok=False,
                tool="run_command",
                error_type="SOURCE_ESCAPE",
                error_message=(
                    "Command references the source repository path. "
                    "Commands must operate inside the disposable worktree."
                ),
                retryable=False,
                command=command[:100],
            )

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
            stdout = proc.stdout[:2500] if len(proc.stdout) > 2500 else proc.stdout
            stderr = proc.stderr[:2500] if len(proc.stderr) > 2500 else proc.stderr
            logger.info("  tool: run_command exit={} '{}'", proc.returncode, command[:80])
            return _tool_result(
                ok=(proc.returncode == 0), tool="run_command",
                exit_code=proc.returncode,
                stdout_preview=stdout if stdout else None,
                stderr_preview=stderr if stderr else None,
                command=command[:100],
            )
        except subprocess.TimeoutExpired:
            return _tool_result(
                ok=False, tool="run_command",
                error_type="TIMEOUT",
                error_message="Command timed out after 30 seconds.",
                command=command[:100],
            )
        except Exception as e:
            return _tool_result(
                ok=False, tool="run_command",
                error_type="EXECUTION",
                error_message=str(e),
                command=command[:100],
            )

    elif name == "search_code":
        pattern = arguments.get("pattern", "")
        glob_filter = arguments.get("glob", "")
        if not pattern:
            return _tool_result(
                ok=False, tool="search_code",
                error_type="MISSING_ARGS",
                error_message="'pattern' is required.",
            )

        source = "ripgrep"

        cmd = ["rg", "--line-number", "--no-heading", "--max-count=50", pattern]
        if glob_filter:
            cmd.extend(["--glob", glob_filter])
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15, cwd=cwd,
            )
            # rg returns 1 when no matches found (not an error)
            output = proc.stdout[:4000] if proc.stdout else ""
            match_count = len(output.strip().split("\n")) if output.strip() else 0
            logger.info("  tool: search_code '{}' → {} ripgrep matches", pattern[:40], match_count)
            return _tool_result(
                ok=True, tool="search_code",
                pattern=pattern, glob=glob_filter or None,
                source="ripgrep",
                match_count=match_count,
                content=output if output else "No matches found.",
            )
        except subprocess.TimeoutExpired:
            return _tool_result(
                ok=False, tool="search_code",
                error_type="TIMEOUT",
                error_message="Search timed out after 15 seconds.",
                pattern=pattern,
            )
        except FileNotFoundError:
            return _tool_result(
                ok=False, tool="search_code",
                error_type="TOOL_NOT_FOUND",
                error_message="ripgrep (rg) not installed. Install with: apt install ripgrep",
            )
        except Exception as e:
            return _tool_result(
                ok=False, tool="search_code",
                error_type="EXECUTION",
                error_message=str(e),
                pattern=pattern,
            )

    # Unknown tool — should not happen if VALID_TOOLS is checked first
    return _tool_result(
        ok=False, tool=name,
        error_type="UNKNOWN_TOOL",
        error_message=f"Unknown tool '{name}'. Available: {', '.join(sorted(VALID_TOOLS))}",
        retryable=False,
    )


# ── Agent Loop ──────────────────────────────────────────────────────


def run_tool_use_loop(
    system_prompt: str,
    user_prompt: str,
    model: str,
    cwd: str,
    allowlist: list[str] | None = None,
    read_context: list[str] | None = None,
    temperature: float = 0.2,
    reasoning: str = "low",
    max_tokens: int = 8000,
    dod_command: str = "",
    event_emitter: Any = None,
    round_num: int = 0,
    task_id: str = "",
    idle_timeout: float = 90.0,
    hard_wall_timeout: float = 600.0,
) -> tuple[list[str], list[dict]]:
    """Run the tool-use agent loop. Returns (files_written, messages).

    The LLM decides what to read, edit, and run. Code-runner just executes
    the tool calls and feeds results back. Loop ends when the LLM stops
    calling tools (sends a text response instead).

    If dod_command is provided, the LLM is instructed to run it after editing
    to verify its changes pass. This gives it in-conversation feedback.
    """
    # Strip JSON output format instructions — tool_use path uses tools, not JSON responses.
    # The system prompt template (code_runner_system_v3.txt) was designed for text-mode
    # which returns structured JSON. In tool_use mode, the LLM must call write_file/edit_file
    # tools instead. Without this strip, Codex follows the JSON instruction and returns
    # {"summary":...,"operations":[...]} instead of making tool calls.
    system_prompt = re.sub(
        r"(?s)Return ONLY a JSON object\..*?OPERATION RULES:.*?(?=\nSKILL DOCUMENTATION|\nSAFETY|\Z)",
        "You have tools: write_file, edit_file, read_file, run_command. "
        "Use these tools to make changes. Do NOT return JSON — call the tools directly.\n\n",
        system_prompt,
    )
    system_prompt = system_prompt.replace(
        "You are a code-fixing agent. Return ONLY a JSON object. No prose, no markdown, no explanations.",
        "You are a code-fixing agent. Use the provided tools to read, edit, and write files.",
    )

    # Inject DoD verification instruction into system prompt
    if dod_command:
        system_prompt += (
            "\n\nVERIFICATION: After making your edits, run this command with run_command "
            "to verify your changes work:\n"
            f"  {dod_command}\n"
            "If the command fails, read the output and fix the issue before stopping."
        )

    # Clear file staleness state for fresh round
    _file_state.clear()

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
    }
    # scillm rejects max_tokens by policy. Keep the argument for callers that
    # still pass a budget, but do not forward it to the proxy.
    if not model.startswith("gpt-"):
        payload_base["temperature"] = min(temperature, 1.0)

    # Duplicate-call suppression: track calls this loop to block repeated identical failing calls
    seen_calls: set[str] = set()

    for iteration in range(MAX_TOOL_ITERATIONS):
        # Message sanitization: strip surrogates before API call (Hermes-inspired)
        sanitize_messages(messages)

        payload = {**payload_base, "messages": messages}

        # Call LLM with smart retry using error classifier
        data = None
        max_retries = 3
        # Estimate tokens for context overflow detection
        # Note: m.get("content", "") returns None if key exists with None value, so use `or ""`
        approx_tokens = sum(len(m.get("content") or "") // 4 for m in messages)

        for attempt in range(1, max_retries + 1):
            try:
                if iteration == 0 and attempt == 1:
                    logger.debug("  Payload model={} system_len={} user_len={} tools={} approx_tokens={}",
                                 payload.get("model"), len(payload["messages"][0]["content"]),
                                 len(payload["messages"][1]["content"]), len(payload.get("tools", [])),
                                 approx_tokens)

                # Test mode: use mock response function if set
                env_mock_response = os.environ.get("CODE_RUNNER_MOCK_RESPONSE")
                if _mock_response_fn is not None or env_mock_response is not None:
                    mock_content = _mock_response_fn(payload) if _mock_response_fn is not None else env_mock_response
                    # Parse "### FILE:" format to extract file writes
                    import re as mock_re
                    file_matches = list(mock_re.finditer(r'### FILE: (\S+)\n```\w*\n(.*?)```', mock_content, mock_re.DOTALL))
                    if file_matches:
                        # Convert to write_file tool calls
                        tool_calls_list = []
                        for i, m in enumerate(file_matches):
                            tool_calls_list.append({
                                "id": f"mock_call_{i}",
                                "type": "function",
                                "function": {
                                    "name": "write_file",
                                    "arguments": json.dumps({"path": m.group(1), "content": m.group(2)}),
                                },
                            })
                        assistant_msg = {"role": "assistant", "content": "", "tool_calls": tool_calls_list}
                        # Create mock data structure that mimics HTTP response
                        data = {
                            "choices": [{
                                "message": assistant_msg,
                                "finish_reason": "tool_calls",
                            }]
                        }
                    else:
                        # No file blocks - return as content (final response)
                        assistant_msg = {"role": "assistant", "content": mock_content}
                        data = {
                            "choices": [{
                                "message": assistant_msg,
                                "finish_reason": "stop",
                            }]
                        }
                    break  # Exit retry loop with mock response

                # Build enhanced caller header: code-runner:{task_id}:{round}
                # Sanitize task_id to remove any chars that could break HTTP headers
                safe_task_id = "".join(c for c in task_id if c.isalnum() or c in "-_") if task_id else "unknown"
                caller_header = f"code-runner:{safe_task_id}:{round_num}"

                headers = {
                    "Authorization": f"Bearer {SCILLM_KEY}",
                    "X-Caller-Skill": caller_header,
                }
                data = _stream_chat_completion(
                    payload,
                    headers=headers,
                    event_emitter=event_emitter,
                    round_num=round_num,
                    idle_timeout=idle_timeout,
                    hard_wall_timeout=hard_wall_timeout,
                )
                break

            except httpx.TimeoutException as e:
                classified = classify_api_error(e, approx_tokens=approx_tokens)
                if attempt < max_retries and classified.retryable:
                    wait = _retry_delay(attempt)
                    logger.warning("/scillm timeout (attempt {}/{}) — retrying in {:.1f}s",
                                   attempt, max_retries, wait)
                    time.sleep(wait)
                    continue
                logger.error("/scillm timeout after {} attempts", max_retries)

            except (httpx.ConnectError, OSError) as e:
                classified = classify_api_error(e, approx_tokens=approx_tokens)
                if attempt < max_retries and classified.retryable:
                    wait = _retry_delay(attempt)
                    logger.warning("/scillm connection error (attempt {}/{}) — retrying in {:.1f}s: {}",
                                   attempt, max_retries, wait, e)
                    time.sleep(wait)
                    continue
                logger.error("/scillm connection failed after {} attempts: {}", max_retries, e)

            except Exception as e:
                classified = classify_api_error(e, approx_tokens=approx_tokens)
                logger.error("Tool loop LLM call failed: {} ({})", e, classified.reason.value)
                if not classified.retryable:
                    break
                if attempt < max_retries:
                    wait = _retry_delay(attempt)
                    time.sleep(wait)
                    continue
                break

        if data is None:
            logger.error("  Tool loop aborting — LLM unreachable after retries")
            break

        choice = data["choices"][0]
        msg = choice["message"]
        finish = choice.get("finish_reason", "stop")

        # Extract reasoning if present (for debugging)
        reasoning = _extract_reasoning(msg)
        if reasoning:
            logger.debug("  Reasoning (turn {}): {}", iteration + 1, reasoning[:200])

        # Append assistant message to conversation
        messages.append(msg)

        # If no tool calls — try fallback parsing for raw tags (Qwen, DeepSeek)
        tool_calls = msg.get("tool_calls")
        content = msg.get("content", "")

        # Fallback: parse raw tool call tags from content if no structured tool_calls
        if not tool_calls and content and ("<tool_call>" in content or "<｜tool" in content or "<function" in content):
            cleaned_content, parsed_calls = parse_tool_calls(content)
            if parsed_calls:
                # Inject parsed calls into the message
                tool_calls = to_openai_format(parsed_calls)
                msg["tool_calls"] = tool_calls
                if cleaned_content is not None:
                    msg["content"] = cleaned_content
                logger.info("  Fallback parser extracted {} tool calls from raw content", len(parsed_calls))

        if tool_calls and finish == "stop":
            logger.warning("  LLM returned {} tool_calls but finish_reason=stop — processing tool calls anyway", len(tool_calls))
            finish = "tool_calls"  # Fix: treat as tool_calls if tools present

        if not tool_calls:
            logger.info("  Tool loop complete after {} iterations (no tool_calls, finish={})", iteration + 1, finish)
            break

        # Execute each tool call and append results
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args_raw = tc["function"].get("arguments", "{}")
            tc_id = tc.get("id", f"call_{hashlib.sha256(fn_args_raw.encode()).hexdigest()[:8]}")

            # 1. Unknown tool check (before parsing args)
            if fn_name not in VALID_TOOLS:
                result = _tool_result(
                    ok=False, tool=fn_name,
                    error_type="UNKNOWN_TOOL",
                    error_message=f"Unknown tool '{fn_name}'. Available: {', '.join(sorted(VALID_TOOLS))}",
                    retryable=False,
                )
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})
                logger.warning("  Unknown tool '{}' — returning error", fn_name)
                continue

            # 2. Parse arguments with repair (uses json_utils.parse_json)
            fn_args = parse_json(fn_args_raw)
            if isinstance(fn_args, str):
                # parse_json returns original string if all parsing failed
                result = _tool_result(
                    ok=False, tool=fn_name,
                    error_type="INVALID_ARGS",
                    error_message=f"Could not parse arguments as JSON. Raw: {fn_args_raw[:200]}",
                    retryable=True,
                )
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})
                logger.warning("  Invalid JSON args for '{}' — returning error", fn_name)
                continue

            # 3. Duplicate-call suppression (same tool + args = blocked)
            call_hash = hashlib.sha256(f"{fn_name}:{fn_args_raw}".encode()).hexdigest()[:16]
            if call_hash in seen_calls:
                result = _tool_result(
                    ok=False, tool=fn_name,
                    error_type="DUPLICATE_CALL",
                    error_message="This exact tool call was already made this loop. Try a different approach.",
                    retryable=False,
                )
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})
                logger.warning("  Duplicate call to '{}' — blocked", fn_name)
                continue
            seen_calls.add(call_hash)

            # 4. Execute bounded tool
            result = execute_tool(fn_name, fn_args, cwd, allowlist)

            # 5. Track written files (parse JSON result to check success)
            if fn_name in ("write_file", "edit_file"):
                try:
                    result_data = json.loads(result)
                    if result_data.get("ok") and result_data.get("path"):
                        path = result_data["path"]
                        if path not in files_written:
                            files_written.append(path)
                except (json.JSONDecodeError, KeyError):
                    pass

            # 9. Feed result back to LLM
            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": result,
            })

    return files_written, messages
