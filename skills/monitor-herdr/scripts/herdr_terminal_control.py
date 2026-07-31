"""Submit text to Herdr terminals through Herdr CLI input helpers.

The installed Herdr CLI may not expose the newer terminal session control
bridge. This module therefore keeps subprocess-based helpers small and explicit:
prefer pane.run for text plus Enter, and report the exact CLI result so the
caller can still fail closed on missing post-submit evidence.
"""

from __future__ import annotations

import json
import os
import shutil
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

DEFAULT_HERDR_BIN = Path.home() / ".local" / "share" / "mise" / "installs" / "herdr" / "latest" / "herdr"


def herdr_bin_path() -> str:
    return os.environ.get("HERDR_BIN") or str(
        DEFAULT_HERDR_BIN if DEFAULT_HERDR_BIN.exists() else (shutil.which("herdr") or "herdr")
    )


async def run_process(
    command: list[str],
    *,
    input_text: str | None = None,
    timeout_s: float = 5.0,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = datetime.now(UTC)
    proc_env = env or os.environ.copy()
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if input_text is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=proc_env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input_text.encode("utf-8") if input_text is not None else None),
                timeout=timeout_s,
            )
        except TimeoutError:
            logger.error("Process timed out for {}", command)
            proc.kill()
            stdout, stderr = await proc.communicate()
            return {
                "command": command,
                "ok": False,
                "error": "timeout",
                "exit_code": proc.returncode,
                "stdout": stdout.decode("utf-8", "replace")[-1000:],
                "stderr": stderr.decode("utf-8", "replace")[-1000:],
                "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
            }
    except OSError as exc:
        logger.error("Process failed for {}: {}", command, exc)
        return {"command": command, "ok": False, "error": str(exc)}
    return {
        "command": command,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", "replace")[-1000:],
        "stderr": stderr.decode("utf-8", "replace")[-1000:],
        "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
    }


def run_process_sync(command: list[str], *, input_text: str | None = None, timeout_s: float = 5.0, socket_path: Path | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    if socket_path:
        env["HERDR_SOCKET_PATH"] = str(socket_path)
    return asyncio.run(run_process(command, input_text=input_text, timeout_s=timeout_s, env=env))


def wait_for_agent_idle(target: str, timeout_ms: int = 1500, socket_path: Path | None = None) -> dict[str, Any]:
    command = [herdr_bin_path(), "agent", "wait", target, "--status", "idle", "--timeout", str(timeout_ms)]
    return run_process_sync(command, timeout_s=max(2, timeout_ms / 1000 + 1), socket_path=socket_path)


def terminal_control_submit(pane_id: str, prompt: str, socket_path: Path | None = None) -> dict[str, Any]:
    payload = {"type": "terminal.input", "text": prompt + "\r"}
    command = [herdr_bin_path(), "terminal", "session", "control", pane_id, "--takeover"]
    result = run_process_sync(command, input_text=json.dumps(payload) + "\n", timeout_s=5, socket_path=socket_path)
    result["attempted"] = True
    return result


def pane_run_submit(pane_id: str, prompt: str, socket_path: Path | None = None) -> dict[str, Any]:
    """Send prompt text through `herdr pane run`, which appends Enter."""
    command = [herdr_bin_path(), "pane", "run", pane_id, prompt]
    result = run_process_sync(command, timeout_s=5, socket_path=socket_path)
    result["attempted"] = True
    result["transport"] = "herdr_pane_run"
    return result
