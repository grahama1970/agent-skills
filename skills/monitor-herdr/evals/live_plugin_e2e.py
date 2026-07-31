#!/usr/bin/env python3
"""Opt-in live Herdr plugin wrapper eval for monitor-herdr."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer


SKILL_DIR = Path(__file__).resolve().parents[1]
PLUGIN_DIR = SKILL_DIR / "herdr-plugin"
DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/monitor-herdr/outputs/live-plugin-e2e")
PLUGIN_ID = "agent-skills.monitor-herdr"

app = typer.Typer(add_completion=False)


@app.callback()
def main() -> None:
    """Live Herdr plugin eval commands."""


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def run_command(command: list[str], *, timeout_seconds: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = datetime.now(UTC)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        proc = subprocess.run(command, cwd=SKILL_DIR, text=True, capture_output=True, timeout=timeout_seconds, check=False, env=merged_env)
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "exit_code": None,
            "timeout": True,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
        }
    return {
        "command": command,
        "exit_code": proc.returncode,
        "timeout": False,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
    }


def parse_json_stdout(result: dict[str, Any]) -> Any:
    try:
        return json.loads(str(result.get("stdout") or ""))
    except json.JSONDecodeError:
        return None


def latest_plugin_log(log_payload: Any, action_id: str, *, log_id: str = "") -> dict[str, Any]:
    if not isinstance(log_payload, dict):
        return {}
    result = log_payload.get("result")
    if not isinstance(result, dict):
        return {}
    logs = result.get("logs")
    if not isinstance(logs, list):
        return {}
    matches = [item for item in logs if isinstance(item, dict) and item.get("action_id") == action_id]
    if log_id:
        for item in matches:
            if item.get("log_id") == log_id:
                return item
        return {}
    return max(matches, key=lambda item: int(item.get("started_unix_ms") or 0), default={})


def action_log_id(invoke_result: dict[str, Any]) -> str:
    payload = parse_json_stdout(invoke_result)
    if not isinstance(payload, dict):
        return ""
    result = payload.get("result")
    if not isinstance(result, dict):
        return ""
    log = result.get("log")
    if not isinstance(log, dict):
        return ""
    return str(log.get("log_id") or "")


def wait_for_action_log(action_id: str, *, log_id: str, timeout_seconds: int) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = datetime.now(UTC).timestamp() + timeout_seconds
    latest_result: dict[str, Any] = {}
    latest_log: dict[str, Any] = {}
    while datetime.now(UTC).timestamp() < deadline:
        latest_result = run_command(["herdr", "plugin", "log", "list", "--plugin", PLUGIN_ID, "--limit", "10"], timeout_seconds=5)
        latest_log = latest_plugin_log(parse_json_stdout(latest_result), action_id, log_id=log_id)
        if latest_log.get("status") and latest_log.get("status") != "running":
            return latest_result, latest_log
        time.sleep(0.25)
    return latest_result, latest_log


@app.command("run")
def run_live_plugin_e2e(
    allow_live: bool = typer.Option(False, "--allow-live", help="Required guard for live Herdr plugin access."),
    output_root: Path = typer.Option(DEFAULT_OUTPUT_ROOT, "--output-root", help="Directory for live plugin eval reports."),
    timeout_seconds: int = typer.Option(30, "--timeout-seconds", min=5, help="Command timeout."),
) -> None:
    if not allow_live:
        print(json.dumps({
            "schema": "agent_skills.monitor_herdr.live_plugin_e2e_report.v1",
            "mocked": False,
            "live": False,
            "ok": False,
            "status": "BLOCKED",
            "failures": ["missing_allow_live"],
        }, indent=2, sort_keys=True))
        raise typer.Exit(2)

    run_id = f"live-plugin-e2e-{timestamp()}"
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    commands = {
        "link": run_command(["herdr", "plugin", "link", str(PLUGIN_DIR)], timeout_seconds=timeout_seconds),
        "list": run_command(["herdr", "plugin", "list", "--plugin", PLUGIN_ID, "--json"], timeout_seconds=timeout_seconds),
        "actions": run_command(["herdr", "plugin", "action", "list", "--plugin", PLUGIN_ID], timeout_seconds=timeout_seconds),
        "status_action": run_command(
            ["herdr", "plugin", "action", "invoke", f"{PLUGIN_ID}.status"],
            timeout_seconds=timeout_seconds,
            env={"MONITOR_HERDR_SKILL_DIR": str(SKILL_DIR)},
        ),
    }
    status_log_id = action_log_id(commands["status_action"])
    log_result, status_log = wait_for_action_log("status", log_id=status_log_id, timeout_seconds=timeout_seconds)
    commands["logs"] = log_result
    plugin_list = parse_json_stdout(commands["list"])
    actions = commands["actions"]["stdout"]
    failures: list[str] = []
    if commands["link"]["exit_code"] not in {0} and "already" not in (commands["link"]["stderr"] + commands["link"]["stdout"]).lower():
        failures.append("plugin_link_failed")
    if commands["list"]["exit_code"] != 0:
        failures.append("plugin_list_failed")
    if PLUGIN_ID not in json.dumps(plugin_list, sort_keys=True):
        failures.append("plugin_not_listed")
    for action_id in ("status", "tick-dry-run", "tick-apply", "probe-current-pane"):
        if action_id not in actions:
            failures.append(f"missing_action:{action_id}")
    if commands["status_action"]["exit_code"] != 0:
        failures.append("status_action_invoke_failed")
    if not status_log_id:
        failures.append("status_action_log_id_missing")
    if not status_log:
        failures.append("status_action_log_missing")
    elif status_log.get("status") != "succeeded" or status_log.get("exit_code") != 0:
        failures.append(f"status_action_not_succeeded:{status_log.get('status')}")

    report = {
        "schema": "agent_skills.monitor_herdr.live_plugin_e2e_report.v1",
        "run_id": run_id,
        "mocked": False,
        "live": True,
        "ok": not failures,
        "status": "PASS" if not failures else "NEEDS_ATTENTION",
        "failures": failures,
        "plugin_id": PLUGIN_ID,
        "plugin_dir": str(PLUGIN_DIR),
        "status_action_log_id": status_log_id,
        "status_action_log": status_log,
        "commands": commands,
    }
    report_path = output_dir / "report.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise typer.Exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    app()
