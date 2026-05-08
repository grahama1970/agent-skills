"""Minimal `/scillm` SSE client and tool loop."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from json_repair import repair_json

from .tools import TOOLS, execute


MODEL_BY_BACKEND = {
    "codex": os.environ.get("CODE_RUNNER_CODEX_MODEL", "gpt-5.5"),
    "claude": "claude-sonnet",
    "gemini": "gemini-flash",
    "text": "text",
    "deepseek": "text",
    "test": "test",
}


def model_name(backend: str) -> str:
    """Map backend to scillm model name."""

    if backend not in MODEL_BY_BACKEND:
        raise ValueError(f"unknown backend: {backend}")
    return MODEL_BY_BACKEND[backend]


def normalize_chat_url(raw_url: str | None) -> str:
    """Normalize a scillm base URL to the chat completions endpoint."""

    url = (raw_url or "http://localhost:4001/v1/chat/completions").strip().rstrip("/")
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path in {"", "/"}:
        return f"{url}/v1/chat/completions"
    if path == "/v1":
        return f"{url}/chat/completions"
    return url


def _merge_delta(message: dict[str, Any], delta: dict[str, Any]) -> None:
    if delta.get("role"):
        message["role"] = delta["role"]
    if delta.get("content"):
        message["content"] = message.get("content", "") + delta["content"]
    for item in delta.get("tool_calls") or []:
        raw_index = item.get("index")
        index = int(raw_index) if raw_index is not None else -1
        calls = message.setdefault("_tool_calls", {})
        fn = item.get("function") or {}
        if raw_index is None and fn.get("name"):
            index = max(calls.keys(), default=-1) + 1
        if raw_index is None and not fn.get("name"):
            named = [key for key, call in calls.items() if call["function"]["name"]]
            index = named[-1] if named else max(calls.keys(), default=-1) + 1
        if raw_index is not None and index not in calls and not fn.get("name"):
            named = [key for key, call in calls.items() if call["function"]["name"]]
            if len(named) == 1:
                index = named[0]
        if raw_index is not None and index not in calls and fn.get("name"):
            unnamed = [key for key, call in calls.items() if not call["function"]["name"]]
            if len(unnamed) == 1:
                index = unnamed[0]
        current = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
        if item.get("id"):
            current["id"] += item["id"]
        if fn.get("name"):
            current["function"]["name"] += fn["name"]
        if fn.get("arguments"):
            current["function"]["arguments"] += fn["arguments"]


def _finalize(message: dict[str, Any]) -> dict[str, Any]:
    calls = message.pop("_tool_calls", {})
    if calls:
        finalized = []
        for index, call in sorted(calls.items()):
            if not call["function"]["name"]:
                continue
            call["id"] = call.get("id") or f"call_{index}"
            finalized.append(call)
        if finalized:
            message["tool_calls"] = finalized
    message.setdefault("role", "assistant")
    message.setdefault("content", "")
    return message


def stream_chat(payload: dict[str, Any], task_id: str, round_num: int) -> dict[str, Any]:
    """Call scillm with SSE and return one assistant message."""

    url = normalize_chat_url(os.environ.get("SCILLM_API_BASE"))
    headers = {
        "Authorization": f"Bearer {os.environ.get('SCILLM_PROXY_KEY', 'sk-dev-proxy-123')}",
        "X-Caller-Skill": f"code-runner:{task_id}:{round_num}",
    }
    timeout_s = float(os.environ.get("CODE_RUNNER_BACKEND_TIMEOUT", "840"))
    body = {
        **payload,
        "stream": True,
        "stream_progress_events": True,
        "stream_heartbeat_s": int(os.environ.get("CODE_RUNNER_STREAM_HEARTBEAT_S", "5")),
        "timeout": timeout_s,
    }
    started = time.monotonic()
    message: dict[str, Any] = {"role": "assistant", "content": ""}
    saw_terminal = False
    saw_delta = False
    with httpx.Client(timeout=httpx.Timeout(connect=10, read=90, write=30, pool=30)) as client:
        with client.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code >= 400:
                raise RuntimeError(f"scillm HTTP {response.status_code}: {response.read().decode(errors='replace')[:500]}")
            for line in response.iter_lines():
                if time.monotonic() - started > timeout_s:
                    raise TimeoutError("scillm hard timeout")
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    saw_terminal = True
                    break
                event = json.loads(data)
                choice = (event.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                if delta:
                    saw_delta = True
                    _merge_delta(message, delta)
                if choice.get("finish_reason"):
                    saw_terminal = True
    if not saw_terminal:
        raise TimeoutError("scillm stream ended without terminal event")
    if not saw_delta:
        raise TimeoutError("scillm stream ended without assistant delta")
    finalized = _finalize(message)
    if not str(finalized.get("content") or "").strip() and not finalized.get("tool_calls"):
        raise TimeoutError("scillm stream ended without assistant content or tool calls")
    return {"choices": [{"message": finalized, "finish_reason": "stop"}]}


def mock_message_from_env() -> dict[str, Any] | None:
    """Convert CODE_RUNNER_MOCK_RESPONSE file blocks to tool calls."""

    content = os.environ.get("CODE_RUNNER_MOCK_RESPONSE")
    if content is None:
        return None
    calls = []
    for index, match in enumerate(re.finditer(r"### FILE: (\S+)\n```\w*\n(.*?)```", content, re.DOTALL)):
        calls.append({"id": f"mock_{index}", "type": "function", "function": {"name": "write_file", "arguments": json.dumps({"path": match.group(1), "content": match.group(2)})}})
    return {"role": "assistant", "content": content if not calls else "", "tool_calls": calls}


def parse_tool_args(raw: str) -> dict[str, Any]:
    """Parse provider tool-call arguments with conservative repair."""

    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        try:
            data, _end = json.JSONDecoder().raw_decode(raw or "{}")
        except json.JSONDecodeError:
            data = json.loads(repair_json(raw or "{}"))
    if not isinstance(data, dict):
        raise ValueError("tool arguments must decode to an object")
    return data


def run_tool_loop(system_prompt: str, user_prompt: str, backend: str, cwd: str, allowlist: list[str], read_context: list[str], task_id: str, round_num: int) -> tuple[list[str], list[dict[str, Any]]]:
    """Run a small tool loop until the backend stops calling tools."""

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
    written: list[str] = []
    for _iteration in range(24):
        mock = mock_message_from_env()
        if mock is None:
            payload = {
                "model": model_name(backend),
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "required",
                "reasoning_effort": "high",
            }
            last_error = ""
            for attempt in range(5):
                try:
                    data = stream_chat(payload, task_id, round_num)
                    break
                except TimeoutError as exc:
                    last_error = str(exc)
                    time.sleep(1 + attempt)
            else:
                messages.append({"role": "assistant", "content": f"backend_error: {last_error}"})
                break
            message = data["choices"][0]["message"]
        else:
            message = mock
        messages.append(message)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            break
        for call in tool_calls:
            name = call["function"]["name"]
            try:
                args = parse_tool_args(call["function"].get("arguments") or "{}")
            except Exception as exc:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", "call"),
                        "content": json.dumps({"ok": False, "error_type": "INVALID_ARGS", "error": str(exc)}),
                    }
                )
                continue
            output = execute(name, args, cwd, allowlist, read_context)
            try:
                data = json.loads(output)
                if data.get("ok") and name in {"write_file", "edit_file"} and data.get("path"):
                    written.append(data["path"])
            except json.JSONDecodeError:
                pass
            messages.append({"role": "tool", "tool_call_id": call.get("id", "call"), "content": output})
    return sorted(set(written)), messages
