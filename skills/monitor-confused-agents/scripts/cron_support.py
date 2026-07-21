"""Cron and status helpers for monitor-confused-agents."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
STATE_ROOT = Path.home() / ".local" / "state" / "monitor-confused-agents"
LOG_DIR = STATE_ROOT / "logs"
RECEIPT_ROOT = STATE_ROOT / "receipts"
STATE_PATH = STATE_ROOT / "state.json"
CRON_MARKER = "# monitor-confused-agents herdr cron"


async def run_process(command: list[str], *, input_text: str | None = None) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE if input_text is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input_text.encode("utf-8") if input_text is not None else None)
    return {
        "command": command,
        "exit_code": proc.returncode,
        "stdout": stdout.decode("utf-8", "replace"),
        "stderr": stderr.decode("utf-8", "replace"),
    }


def run_process_sync(command: list[str], *, input_text: str | None = None) -> dict[str, Any]:
    return asyncio.run(run_process(command, input_text=input_text))


def status_payload() -> dict[str, Any]:
    receipts = sorted(RECEIPT_ROOT.glob("*/receipt.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    crontab_result = run_process_sync(["crontab", "-l"])
    cron_stdout = crontab_result["stdout"] if crontab_result["exit_code"] == 0 else ""
    return {
        "schema": "agent_skills.monitor_confused_agents.status.v1",
        "mocked": False,
        "live": True,
        "api": "herdr_socket",
        "state_root": str(STATE_ROOT),
        "cron_installed": CRON_MARKER in cron_stdout,
        "cron_marker": CRON_MARKER,
        "log_file": str(LOG_DIR / "monitor-confused-agents.log"),
        "state_path": str(STATE_PATH),
        "latest_receipts": [str(path) for path in receipts[:5]],
    }


def install_cron(*, apply: bool, minute: str, space: str, apply_prompts: bool, cwd_prefix: str) -> tuple[int, dict[str, Any]]:
    script_path = SKILL_DIR / "run.sh"
    cron_log = LOG_DIR / "cron.log"
    tick_args = "--apply" if apply_prompts else ""
    line = (
        f"{minute} * * * * cd {shell_quote(str(SKILL_DIR))} && "
        f"{shell_quote(str(script_path))} tick {tick_args} --space {shell_quote(space)} --cwd-prefix {shell_quote(cwd_prefix)} "
        f">> {shell_quote(str(cron_log))} 2>&1 {CRON_MARKER}"
    ).replace("  ", " ").strip()
    current = run_process_sync(["crontab", "-l"])
    existing = current["stdout"] if current["exit_code"] == 0 else ""
    filtered = [item for item in existing.splitlines() if CRON_MARKER not in item]
    next_crontab = "\n".join(filtered + [line]).strip() + "\n"
    payload = {
        "schema": "agent_skills.monitor_confused_agents.cron_install.v1",
        "mocked": False,
        "live": True,
        "apply": apply,
        "cron_marker": CRON_MARKER,
        "cron_line": line,
        "would_replace_existing": CRON_MARKER in existing,
        "log_file": str(cron_log),
    }
    if not apply:
        payload["status"] = "DRY_RUN"
        return 0, payload
    proc = run_process_sync(["crontab", "-"], input_text=next_crontab)
    payload["install_command"] = {"command": ["crontab", "-"], "exit_code": proc["exit_code"], "stderr": proc["stderr"]}
    payload["status"] = "INSTALLED" if proc["exit_code"] == 0 else "BLOCKED"
    return (0 if proc["exit_code"] == 0 else 1), payload


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
