"""Cron and status helpers for monitor-herdr."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
STATE_ROOT = Path.home() / ".local" / "state" / "monitor-herdr"
LOG_DIR = STATE_ROOT / "logs"
RECEIPT_ROOT = STATE_ROOT / "receipts"
STATE_PATH = STATE_ROOT / "state.json"
CRON_MARKER = "# monitor-herdr herdr cron"
LEGACY_CRON_MARKERS = ("# monitor-confused-agents herdr cron",)


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


def status_payload(*, stale_after_seconds: int = 15 * 60) -> dict[str, Any]:
    receipts = sorted(RECEIPT_ROOT.glob("*/receipt.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    crontab_result = run_process_sync(["crontab", "-l"])
    cron_stdout = crontab_result["stdout"] if crontab_result["exit_code"] == 0 else ""
    latest = latest_receipt_summary(receipts[0]) if receipts else {}
    latest_cron = latest_cron_receipt_summary(receipts)
    health = scheduler_health(
        cron_installed=CRON_MARKER in cron_stdout,
        latest_receipt=latest_cron,
        stale_after_seconds=stale_after_seconds,
    )
    return {
        "schema": "agent_skills.monitor_herdr.status.v1",
        "mocked": False,
        "live": True,
        "api": "herdr_socket",
        "scheduler": health,
        "state_root": str(STATE_ROOT),
        "cron_installed": CRON_MARKER in cron_stdout,
        "cron_marker": CRON_MARKER,
        "log_file": str(LOG_DIR / "monitor-herdr.log"),
        "state_path": str(STATE_PATH),
        "latest_receipt": latest or None,
        "latest_cron_receipt": latest_cron or None,
        "latest_receipts": [str(path) for path in receipts[:5]],
    }


def latest_receipt_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "path": str(path),
            "readable": False,
            "error": type(exc).__name__,
        }
    age_seconds = max(0.0, time.time() - path.stat().st_mtime)
    prompts = payload.get("prompts") if isinstance(payload.get("prompts"), list) else []
    return {
        "path": str(path),
        "readable": True,
        "age_seconds": age_seconds,
        "run_id": payload.get("run_id"),
        "status": payload.get("status"),
        "ok": payload.get("ok"),
        "invocation_source": payload.get("invocation_source"),
        "mocked": payload.get("mocked"),
        "live": payload.get("live"),
        "observed_panes": payload.get("observed_panes"),
        "selected_panes": len(payload.get("selected_panes") or []),
        "prompts": len(prompts),
        "submit_confirmed": [item.get("submit_confirmed") for item in prompts if isinstance(item, dict)],
    }


def latest_cron_receipt_summary(receipts: list[Path]) -> dict[str, Any]:
    for path in receipts:
        summary = latest_receipt_summary(path)
        if summary.get("invocation_source") == "cron":
            return summary
    return {}


def scheduler_health(*, cron_installed: bool, latest_receipt: dict[str, Any], stale_after_seconds: int) -> dict[str, Any]:
    if stale_after_seconds < 1:
        stale_after_seconds = 1
    if not cron_installed:
        return {
            "status": "NOT_INSTALLED",
            "backend": "cron",
            "cron_installed": False,
            "stale_after_seconds": stale_after_seconds,
            "latest_receipt_age_seconds": latest_receipt.get("age_seconds"),
            "latest_receipt_path": latest_receipt.get("path"),
        }
    if not latest_receipt:
        return {
            "status": "NEEDS_ATTENTION",
            "backend": "cron",
            "cron_installed": True,
            "stale_after_seconds": stale_after_seconds,
            "latest_receipt_age_seconds": None,
            "latest_receipt_path": None,
            "reason": "cron_installed_but_no_cron_receipts",
        }
    if not latest_receipt.get("readable"):
        return {
            "status": "NEEDS_ATTENTION",
            "backend": "cron",
            "cron_installed": True,
            "stale_after_seconds": stale_after_seconds,
            "latest_receipt_age_seconds": latest_receipt.get("age_seconds"),
            "latest_receipt_path": latest_receipt.get("path"),
            "reason": "latest_receipt_unreadable",
        }
    latest_age = float(latest_receipt.get("age_seconds") or 0.0)
    if latest_age > stale_after_seconds:
        return {
            "status": "STALE",
            "backend": "cron",
            "cron_installed": True,
            "stale_after_seconds": stale_after_seconds,
            "latest_receipt_age_seconds": latest_age,
            "latest_receipt_path": latest_receipt.get("path"),
        }
    if latest_receipt.get("ok") is False or latest_receipt.get("status") == "NEEDS_ATTENTION":
        return {
            "status": "NEEDS_ATTENTION",
            "backend": "cron",
            "cron_installed": True,
            "stale_after_seconds": stale_after_seconds,
            "latest_receipt_age_seconds": latest_age,
            "latest_receipt_path": latest_receipt.get("path"),
            "latest_tick_status": latest_receipt.get("status"),
        }
    return {
        "status": "OK",
        "backend": "cron",
        "cron_installed": True,
        "stale_after_seconds": stale_after_seconds,
        "latest_receipt_age_seconds": latest_age,
        "latest_receipt_path": latest_receipt.get("path"),
        "latest_tick_status": latest_receipt.get("status"),
    }


def install_cron(
    *,
    apply: bool,
    minute: str,
    space: str,
    apply_prompts: bool,
    cwd_prefix: str,
    min_stopped_seconds: int = 600,
) -> tuple[int, dict[str, Any]]:
    validation_error = validate_cron_args(
        minute=minute,
        space=space,
        cwd_prefix=cwd_prefix,
        min_stopped_seconds=min_stopped_seconds,
    )
    if validation_error:
        return 2, {
            "schema": "agent_skills.monitor_herdr.cron_install.v1",
            "mocked": False,
            "live": True,
            "apply": apply,
            "status": "BLOCKED",
            "error": validation_error,
        }
    script_path = SKILL_DIR / "run.sh"
    cron_log = LOG_DIR / "cron.log"
    tick_args = "--apply" if apply_prompts else ""
    line = (
        f"{minute} * * * * cd {shell_quote(str(SKILL_DIR))} && "
        f"MONITOR_HERDR_INVOCATION_SOURCE=cron {shell_quote(str(script_path))} tick {tick_args} --space {shell_quote(space)} "
        f"--cwd-prefix {shell_quote(cwd_prefix)} --min-stopped-seconds {min_stopped_seconds} "
        f">> {shell_quote(str(cron_log))} 2>&1 {CRON_MARKER}"
    ).replace("  ", " ").strip()
    current = run_process_sync(["crontab", "-l"])
    no_crontab = current["exit_code"] != 0 and "no crontab for" in current["stderr"].lower()
    if current["exit_code"] != 0 and not no_crontab:
        return 1, {
            "schema": "agent_skills.monitor_herdr.cron_install.v1",
            "mocked": False,
            "live": True,
            "apply": apply,
            "status": "BLOCKED",
            "error": "crontab_read_failed",
            "read_command": {"command": ["crontab", "-l"], "exit_code": current["exit_code"], "stderr": current["stderr"]},
        }
    existing = current["stdout"] if current["exit_code"] == 0 else ""
    markers = (CRON_MARKER, *LEGACY_CRON_MARKERS)
    filtered = [item for item in existing.splitlines() if not any(marker in item for marker in markers)]
    next_crontab = "\n".join(filtered + [line]).strip() + "\n"
    payload = {
        "schema": "agent_skills.monitor_herdr.cron_install.v1",
        "mocked": False,
        "live": True,
        "apply": apply,
        "cron_marker": CRON_MARKER,
        "cron_line": line,
        "min_stopped_seconds": min_stopped_seconds,
        "would_replace_existing": any(marker in existing for marker in markers),
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


def validate_cron_args(*, minute: str, space: str, cwd_prefix: str, min_stopped_seconds: int = 600) -> str:
    if minute != "*/10":
        return "minute_must_be_exactly_every_10"
    if min_stopped_seconds < 0:
        return "min_stopped_seconds_must_be_non_negative"
    for name, value in {"space": space, "cwd_prefix": cwd_prefix}.items():
        if any(char in value for char in "\r\n%"):
            return f"{name}_contains_cron_control_character"
    return ""
