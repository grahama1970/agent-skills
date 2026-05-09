"""Clean transcript entries into compact evidence for drift prompts."""
from __future__ import annotations

import re
from typing import Any

from .transcript_extract import TranscriptEntry
from .utils import first_present, parse_maybe_json, stable_hash, strip_private_text, truncate_text

ROUTINE_TOOLS = {"Read", "Grep", "Glob", "LS", "TodoWrite", "ListMcpResourcesTool", "Skill"}
NOISE_TOOL_NAMES = {"TodoWrite", "ListMcpResourcesTool", "AskUserQuestion"}

STRONG_COMMAND_PATTERNS = re.compile(
    r"\b(pytest|npm\s+test|npx\s+tsc|tsc\b|ruff\b|mypy\b|sanity\.sh|verify|verifier|healthcheck|health\s+check|docker\s+compose|git\s+commit|git\s+status|run\.sh\s+(scan|verify|test|sanity)|orchestrate|checkpoint)\b",
    re.IGNORECASE,
)
FILE_PATH_RE = re.compile(r"(?:[./~\w-]+/)+[\w.-]+")


def _role_from_entry(data: dict[str, Any]) -> str | None:
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
    if data.get("type") == "event_msg" and isinstance(payload, dict):
        payload_type = payload.get("type")
        if payload_type == "user_message":
            return "user"
        if payload_type == "agent_message":
            return "assistant"
    data = payload
    message = data.get("message")
    if isinstance(message, dict):
        role = message.get("role")
        if isinstance(role, str):
            return role
    role = data.get("role")
    if isinstance(role, str):
        return role
    typ = data.get("type")
    if typ in {"user", "assistant", "system"}:
        return str(typ)
    return None


def _text_from_content(content: Any, max_chars: int = 1200) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return truncate_text(content, max_chars=max_chars)
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") in {"text", "input_text", "output_text"} and isinstance(item.get("text"), str):
                    texts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    texts.append(item["content"])
            elif isinstance(item, str):
                texts.append(item)
        return truncate_text("\n".join(texts), max_chars=max_chars)
    return truncate_text(content, max_chars=max_chars)


def _message_text(data: dict[str, Any], max_chars: int = 1200) -> str:
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
    if data.get("type") == "event_msg" and isinstance(payload, dict):
        return _text_from_content(payload.get("message"), max_chars=max_chars)
    data = payload
    message = data.get("message")
    if isinstance(message, dict):
        return _text_from_content(message.get("content"), max_chars=max_chars)
    return _text_from_content(data.get("content") or data.get("text") or data.get("prompt"), max_chars=max_chars)


def _extract_tool_events_from_message(entry: TranscriptEntry) -> list[dict[str, Any]]:
    """Extract tool_use/tool_result blocks from Claude/Codex-style message content."""
    data = entry.data
    message = data.get("message") if isinstance(data.get("message"), dict) else data
    content = message.get("content") if isinstance(message, dict) else None
    events: list[dict[str, Any]] = []
    if not isinstance(content, list):
        return events
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "tool_use":
            events.append({
                "source": "message_block",
                "kind": "tool_use",
                "tool_use_id": block.get("id"),
                "tool_name": block.get("name"),
                "tool_input": block.get("input"),
                "tool_response": None,
                "timestamp": entry.timestamp,
                "line_number": entry.line_number,
                "path": entry.path,
            })
        elif block_type == "tool_result":
            events.append({
                "source": "message_block",
                "kind": "tool_result",
                "tool_use_id": block.get("tool_use_id"),
                "tool_name": block.get("name"),
                "tool_input": None,
                "tool_response": block.get("content"),
                "timestamp": entry.timestamp,
                "line_number": entry.line_number,
                "path": entry.path,
            })
    return events


def _extract_direct_tool_event(entry: TranscriptEntry) -> dict[str, Any] | None:
    data = entry.data
    tool_name = first_present(data, ["tool_name", "toolName", "name"])
    hook_event = first_present(data, ["hook_event_name", "hookEventName", "event", "type"])
    if not tool_name and hook_event not in {"PreToolUse", "PostToolUse", "tool_use", "tool_result"}:
        return None

    tool_input = first_present(data, ["tool_input", "toolInput", "input", "parameters"])
    tool_response = first_present(data, ["tool_response", "toolResponse", "tool_output", "toolOutput", "output", "result", "outcome"])
    return {
        "source": "direct_entry",
        "kind": "tool_result" if tool_response is not None else "tool_use",
        "tool_use_id": first_present(data, ["tool_use_id", "toolUseId", "id"]),
        "tool_name": tool_name,
        "tool_input": parse_maybe_json(tool_input),
        "tool_response": parse_maybe_json(tool_response),
        "timestamp": entry.timestamp,
        "line_number": entry.line_number,
        "path": entry.path,
    }


def _extract_codex_tool_event(entry: TranscriptEntry) -> dict[str, Any] | None:
    """Extract current Codex response_item function calls from payload records."""
    data = entry.data
    payload = data.get("payload")
    if data.get("type") != "response_item" or not isinstance(payload, dict):
        return None
    payload_type = payload.get("type")
    if payload_type == "function_call":
        arguments = payload.get("arguments")
        return {
            "source": "codex_payload",
            "kind": "tool_use",
            "tool_use_id": payload.get("call_id") or payload.get("id"),
            "tool_name": payload.get("name"),
            "tool_input": parse_maybe_json(arguments),
            "tool_response": None,
            "timestamp": entry.timestamp,
            "line_number": entry.line_number,
            "path": entry.path,
        }
    if payload_type == "function_call_output":
        return {
            "source": "codex_payload",
            "kind": "tool_result",
            "tool_use_id": payload.get("call_id") or payload.get("id"),
            "tool_name": payload.get("name"),
            "tool_input": None,
            "tool_response": parse_maybe_json(payload.get("output")),
            "timestamp": entry.timestamp,
            "line_number": entry.line_number,
            "path": entry.path,
        }
    return None


def _command_from_tool(tool_name: str | None, tool_input: Any) -> str | None:
    if tool_name not in {"Bash", "shell", "bash", "exec_command"}:
        return None
    if isinstance(tool_input, dict):
        cmd = first_present(tool_input, ["command", "cmd", "script"])
        return str(cmd) if cmd else None
    if isinstance(tool_input, str):
        return tool_input
    return None


def _success_from_response(response: Any) -> bool | None:
    if response is None:
        return None
    if isinstance(response, dict):
        for key in ("exit_code", "exitCode", "status_code", "statusCode", "returncode", "return_code"):
            if key in response:
                try:
                    return int(response[key]) == 0
                except Exception:
                    pass
        status = response.get("status") or response.get("outcome")
        if isinstance(status, str):
            if status.lower() in {"success", "succeeded", "ok", "passed", "pass"}:
                return True
            if status.lower() in {"failure", "failed", "error", "fail"}:
                return False
    text = str(response).lower()
    if "exit code: 0" in text or "passed" in text or "success" in text:
        return True
    if "exit code:" in text and "exit code: 0" not in text:
        return False
    return None


def _files_from_tool(tool_input: Any, tool_response: Any) -> list[str]:
    text = ""
    for value in (tool_input, tool_response):
        if value is None:
            continue
        if isinstance(value, dict):
            for key in ("file_path", "path", "filename"):
                if key in value and isinstance(value[key], str):
                    text += " " + value[key]
        text += " " + truncate_text(value, max_chars=3000)
    return sorted(set(FILE_PATH_RE.findall(text)))[:20]


def _evidence_strength(tool_name: str | None, command: str | None, success: bool | None, files: list[str]) -> str:
    if command and STRONG_COMMAND_PATTERNS.search(command) and success is True:
        return "strong"
    if tool_name in {"Edit", "Write", "apply_patch", "MultiEdit"} and files:
        return "medium"
    if success is True:
        return "weak"
    return "unknown"


def _is_routine(tool_name: str | None, command: str | None, strength: str) -> bool:
    if strength in {"strong", "medium"}:
        return False
    if tool_name in ROUTINE_TOOLS:
        return True
    if command:
        stripped = command.strip()
        if re.match(r"^(pwd|ls|cat|grep|rg|find|sed|awk)\b", stripped) and not STRONG_COMMAND_PATTERNS.search(stripped):
            return True
    return False


def clean_transcript_entries(
    entries: list[TranscriptEntry],
    *,
    max_events: int = 80,
    max_text_chars: int = 1600,
    include_routine: bool = False,
) -> dict[str, Any]:
    """Return compact cleaned evidence for the drift prompt."""
    observations: list[dict[str, Any]] = []
    routine_count = 0
    parse_errors = 0
    pending_tools: dict[str, dict[str, Any]] = {}

    def add_observation(obs: dict[str, Any]) -> None:
        nonlocal routine_count
        if len(observations) >= max_events:
            return
        tool_name = obs.get("tool_name")
        if tool_name in NOISE_TOOL_NAMES:
            routine_count += 1
            return
        command = obs.get("command")
        strength = obs.get("evidence_strength", "unknown")
        routine = _is_routine(tool_name, command, strength)
        obs["routine"] = routine
        if routine and not include_routine:
            routine_count += 1
            return
        observations.append(obs)

    for entry in entries:
        data = entry.data
        if "_parse_error" in data:
            parse_errors += 1
            continue

        role = _role_from_entry(data)
        if role in {"user", "assistant"}:
            text = _message_text(data, max_chars=max_text_chars)
            if text.strip():
                kind = "human_statement" if role == "user" else "assistant_conclusion"
                add_observation({
                    "id": stable_hash({"path": entry.path, "line": entry.line_number, "role": role}, prefix="obs"),
                    "kind": kind,
                    "timestamp": entry.timestamp,
                    "summary": text,
                    "source": {"path": entry.path, "line_number": entry.line_number},
                    "evidence_strength": "weak",
                })

        tool_events = _extract_tool_events_from_message(entry)
        direct_tool = _extract_direct_tool_event(entry)
        if direct_tool:
            tool_events.append(direct_tool)
        codex_tool = _extract_codex_tool_event(entry)
        if codex_tool:
            tool_events.append(codex_tool)

        for ev in tool_events:
            tool_id = ev.get("tool_use_id")
            if ev["kind"] == "tool_use" and tool_id:
                pending_tools[str(tool_id)] = ev
                continue
            if ev["kind"] == "tool_result" and tool_id and str(tool_id) in pending_tools:
                prior = pending_tools.pop(str(tool_id))
                tool_name = ev.get("tool_name") or prior.get("tool_name")
                tool_input = prior.get("tool_input") if prior.get("tool_input") is not None else ev.get("tool_input")
                tool_response = ev.get("tool_response")
            else:
                tool_name = ev.get("tool_name")
                tool_input = ev.get("tool_input")
                tool_response = ev.get("tool_response")

            command = _command_from_tool(str(tool_name) if tool_name else None, tool_input)
            success = _success_from_response(tool_response)
            files = _files_from_tool(tool_input, tool_response)
            strength = _evidence_strength(str(tool_name) if tool_name else None, command, success, files)
            output_excerpt = truncate_text(tool_response, max_chars=max_text_chars)
            summary_parts = [f"Tool {tool_name or 'unknown'}"]
            if command:
                summary_parts.append(f"command={truncate_text(command, max_chars=500)}")
            if success is not None:
                summary_parts.append(f"success={success}")
            if files:
                summary_parts.append("files=" + ", ".join(files[:5]))

            add_observation({
                "id": stable_hash({"path": ev.get("path"), "line": ev.get("line_number"), "tool": tool_name, "input": tool_input}, prefix="obs"),
                "kind": "command" if command else "tool_call",
                "timestamp": ev.get("timestamp"),
                "tool_name": str(tool_name) if tool_name else None,
                "success": success,
                "command": command,
                "files": files,
                "summary": "; ".join(summary_parts),
                "output_excerpt": output_excerpt,
                "source": {"path": ev.get("path"), "line_number": ev.get("line_number")},
                "evidence_strength": strength,
            })

    # Add unpaired tool uses only when they are non-routine and include useful data.
    for tool_id, ev in list(pending_tools.items())[:10]:
        tool_name = ev.get("tool_name")
        tool_input = ev.get("tool_input")
        command = _command_from_tool(str(tool_name) if tool_name else None, tool_input)
        files = _files_from_tool(tool_input, None)
        strength = _evidence_strength(str(tool_name) if tool_name else None, command, None, files)
        add_observation({
            "id": stable_hash({"tool_id": tool_id, "tool": tool_name, "input": tool_input}, prefix="obs"),
            "kind": "command" if command else "tool_call",
            "timestamp": ev.get("timestamp"),
            "tool_name": str(tool_name) if tool_name else None,
            "success": None,
            "command": command,
            "files": files,
            "summary": f"Unpaired tool_use {tool_name or 'unknown'}",
            "output_excerpt": "",
            "source": {"path": ev.get("path"), "line_number": ev.get("line_number")},
            "evidence_strength": strength,
        })

    return {
        "schema_version": 1,
        "entry_count": len(entries),
        "observation_count": len(observations),
        "routine_successful_tool_calls": routine_count,
        "parse_errors": parse_errors,
        "observations": observations,
    }
