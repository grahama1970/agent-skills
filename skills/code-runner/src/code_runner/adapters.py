"""Backend adapter dispatch for untrusted code-generating workers.

Adapters may propose tool calls, but they do not own filesystem mutation, DoD,
source apply, allowlist enforcement, artifacts, or rollback. Those remain in the
code-runner envelope.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
from typing import Any

from . import scillm
from .scillm import parse_tool_args
from .tools import execute


SCILLM_BACKENDS = {"codex", "claude", "gemini", "text", "deepseek", "test"}
COMMAND_ADAPTER_BACKENDS = {
    "codex-exec": "CODE_RUNNER_CODEX_EXEC_COMMAND",
    "claude-code": "CODE_RUNNER_CLAUDE_CODE_COMMAND",
    "gemini-cli": "CODE_RUNNER_GEMINI_CLI_COMMAND",
    "opencode": "CODE_RUNNER_OPENCODE_COMMAND",
}
ADAPTER_BACKENDS = {"native-fake"} | set(COMMAND_ADAPTER_BACKENDS)


def supported_backends() -> set[str]:
    return SCILLM_BACKENDS | ADAPTER_BACKENDS


def _file_blocks_to_message(content: str) -> dict[str, Any]:
    calls = []
    for index, match in enumerate(re.finditer(r"### FILE: (\S+)\n```\w*\n(.*?)```", content, re.DOTALL)):
        calls.append({
            "id": f"native_fake_{index}",
            "type": "function",
            "function": {
                "name": "write_file",
                "arguments": json.dumps({"path": match.group(1), "content": match.group(2)}),
            },
        })
    return {"role": "assistant", "content": content if not calls else "", "tool_calls": calls}


def _run_assistant_messages(
    assistant_messages: list[dict[str, Any]],
    cwd: str,
    allowlist: list[str],
    read_context: list[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    messages: list[dict[str, Any]] = []
    written: list[str] = []
    for message in assistant_messages:
        messages.append(message)
        for call in message.get("tool_calls") or []:
            name = str((call.get("function") or {}).get("name") or "")
            try:
                args = parse_tool_args((call.get("function") or {}).get("arguments") or "{}")
            except Exception as exc:
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", "call"),
                    "content": json.dumps({"ok": False, "error_type": "INVALID_ARGS", "error": str(exc)}),
                })
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


def _run_native_fake(cwd: str, allowlist: list[str], read_context: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    content = os.environ.get("CODE_RUNNER_NATIVE_FAKE_RESPONSE")
    if content is None:
        raise RuntimeError("native-fake adapter requires CODE_RUNNER_NATIVE_FAKE_RESPONSE")
    return _run_assistant_messages([_file_blocks_to_message(content)], cwd, allowlist, read_context)


def _native_command_prompt(system_prompt: str, user_prompt: str) -> str:
    return (
        f"SYSTEM:\n{system_prompt}\n\n"
        f"USER:\n{user_prompt}\n\n"
        "Return proposed file changes as one or more blocks exactly like:\n"
        "### FILE: path/inside/allowlist.py\n"
        "```python\n"
        "new file content\n"
        "```\n"
    )


def _run_native_command(
    backend: str,
    system_prompt: str,
    user_prompt: str,
    cwd: str,
    allowlist: list[str],
    read_context: list[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    env_name = COMMAND_ADAPTER_BACKENDS[backend]
    raw_command = os.environ.get(env_name)
    if not raw_command:
        raise RuntimeError(f"{backend} adapter requires {env_name}")

    command = shlex.split(raw_command)
    if not command:
        raise RuntimeError(f"{backend} adapter command is empty")

    timeout = float(os.environ.get("CODE_RUNNER_NATIVE_ADAPTER_TIMEOUT", "120"))
    prompt = _native_command_prompt(system_prompt, user_prompt)
    env = os.environ.copy()
    env["CODE_RUNNER_ADAPTER_BACKEND"] = backend
    env["CODE_RUNNER_ADAPTER_ALLOWLIST"] = json.dumps(allowlist)
    env["CODE_RUNNER_ADAPTER_READ_CONTEXT"] = json.dumps(read_context)

    with tempfile.TemporaryDirectory(prefix=f"code-runner-{backend}-") as adapter_cwd:
        proc = subprocess.run(
            command,
            cwd=adapter_cwd,
            env=env,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout)[-1000:]
        raise RuntimeError(f"{backend} adapter exited {proc.returncode}: {tail}")

    assistant = _file_blocks_to_message(proc.stdout)
    if proc.stderr.strip():
        assistant["adapter_stderr"] = proc.stderr[-1000:]
    return _run_assistant_messages([assistant], cwd, allowlist, read_context)


def run_backend_tool_loop(
    system_prompt: str,
    user_prompt: str,
    backend: str,
    cwd: str,
    allowlist: list[str],
    read_context: list[str],
    task_id: str,
    round_num: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    if backend in SCILLM_BACKENDS:
        return scillm.run_tool_loop(system_prompt, user_prompt, backend, cwd, allowlist, read_context, task_id, round_num)
    if backend == "native-fake":
        return _run_native_fake(cwd, allowlist, read_context)
    if backend in COMMAND_ADAPTER_BACKENDS:
        return _run_native_command(backend, system_prompt, user_prompt, cwd, allowlist, read_context)
    raise RuntimeError(f"unsupported code-runner adapter backend: {backend}")
