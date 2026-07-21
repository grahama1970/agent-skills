"""Submit text to Herdr terminals through the documented terminal.input bridge."""

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


async def run_process(command: list[str], *, input_text: str | None = None, timeout_s: float = 5.0) -> dict[str, Any]:
    started = datetime.now(UTC)
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE if input_text is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input_text.encode("utf-8") if input_text is not None else None),
            timeout=timeout_s,
        )
    except OSError as exc:
        logger.error("Process failed for {}: {}", command, exc)
        return {"command": command, "ok": False, "error": str(exc)}
    except TimeoutError:
        logger.error("Process timed out for {}", command)
        return {"command": command, "ok": False, "error": "timeout"}
    return {
        "command": command,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", "replace")[-1000:],
        "stderr": stderr.decode("utf-8", "replace")[-1000:],
        "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
    }


def run_process_sync(command: list[str], *, input_text: str | None = None, timeout_s: float = 5.0) -> dict[str, Any]:
    return asyncio.run(run_process(command, input_text=input_text, timeout_s=timeout_s))


def wait_for_agent_idle(target: str, timeout_ms: int = 1500) -> dict[str, Any]:
    command = [herdr_bin_path(), "agent", "wait", target, "--status", "idle", "--timeout", str(timeout_ms)]
    return run_process_sync(command, timeout_s=max(2, timeout_ms / 1000 + 1))


def terminal_control_submit(pane_id: str, prompt: str) -> dict[str, Any]:
    payload = {"type": "terminal.input", "text": prompt + "\r"}
    command = [herdr_bin_path(), "terminal", "session", "control", pane_id, "--takeover"]
    result = run_process_sync(command, input_text=json.dumps(payload) + "\n", timeout_s=5)
    result["attempted"] = True
    return result
