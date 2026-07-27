#!/usr/bin/env python3
"""Run opt-in live Herdr E2E checks for monitor-herdr.

This eval exercises the real monitor-herdr CLI against the active Herdr socket.
It is intentionally outside the default sanity suite because it depends on a
running Herdr session and, with --allow-apply, may type into selected agent panes.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = Path("/mnt/storage12tb/skills/monitor-herdr/outputs/live-e2e")

app = typer.Typer(add_completion=False)


@app.callback()
def main() -> None:
    """Live Herdr E2E eval commands."""


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def run_command(command: list[str], *, timeout_seconds: int) -> dict[str, Any]:
    started = datetime.now(UTC)
    try:
        proc = subprocess.run(command, cwd=SKILL_DIR, text=True, capture_output=True, timeout=timeout_seconds, check=False)
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


def parse_json_stdout(result: dict[str, Any]) -> dict[str, Any] | None:
    try:
        payload = json.loads(str(result.get("stdout") or ""))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def api_methods(receipt: dict[str, Any]) -> list[str]:
    methods: list[str] = []
    for record in receipt.get("api_trace", []):
        method = record.get("request", {}).get("method")
        if isinstance(method, str):
            methods.append(method)
    return methods


def herdr_idle_fields_seen(receipt: dict[str, Any]) -> list[str]:
    hits: set[str] = set()
    idle_tokens = ("idle_seconds", "idle_since", "stopped_seconds", "stopped_since", "state_since")
    for record in receipt.get("api_trace", []):
        result = record.get("response", {}).get("result", {})
        panes = result.get("panes") if isinstance(result, dict) else None
        if isinstance(panes, list):
            for pane in panes:
                if isinstance(pane, dict):
                    hits.update(key for key in pane if any(token in key for token in idle_tokens))
        explain = result.get("explain") if isinstance(result, dict) else None
        if isinstance(explain, dict):
            hits.update(key for key in explain if any(token in key for token in idle_tokens))
    return sorted(hits)


def build_report(
    *,
    run_id: str,
    tick: dict[str, Any],
    receipt: dict[str, Any] | None,
    allow_apply: bool,
    require_prompt: bool,
) -> dict[str, Any]:
    methods = api_methods(receipt or {})
    prompts = (receipt or {}).get("prompts") or []
    selected = (receipt or {}).get("selected_panes") or []
    observed = (receipt or {}).get("observed_panes")
    stopped = (receipt or {}).get("stopped_panes") or []
    failures: list[str] = []
    if tick.get("exit_code") != 0:
        failures.append("tick_exit_nonzero")
    if not receipt:
        failures.append("tick_stdout_not_json")
    else:
        if receipt.get("mocked") is not False:
            failures.append("receipt_not_marked_non_mocked")
        if receipt.get("live") is not True:
            failures.append("receipt_not_marked_live")
        if "ping" not in methods or "workspace.list" not in methods or "pane.list" not in methods:
            failures.append("missing_core_herdr_api_methods")
        if not isinstance(observed, int) or observed <= 0:
            failures.append("no_live_panes_observed")
        if require_prompt and not prompts:
            failures.append("required_prompt_not_exercised")
        if allow_apply and prompts and any(not item.get("submit_confirmed") for item in prompts):
            failures.append("apply_prompt_not_confirmed")
    return {
        "schema": "agent_skills.monitor_herdr.live_e2e_report.v1",
        "run_id": run_id,
        "mocked": False,
        "live": True,
        "allow_apply": allow_apply,
        "require_prompt": require_prompt,
        "ok": not failures,
        "status": "PASS" if not failures else "NEEDS_ATTENTION",
        "failures": failures,
        "tick_command": tick.get("command"),
        "tick_exit_code": tick.get("exit_code"),
        "tick_duration_seconds": tick.get("duration_seconds"),
        "receipt_path": (receipt or {}).get("receipt_path"),
        "observed_panes": observed,
        "stopped_panes": len(stopped) if isinstance(stopped, list) else stopped,
        "selected_panes": len(selected) if isinstance(selected, list) else selected,
        "prompts": len(prompts) if isinstance(prompts, list) else prompts,
        "prompt_submit_confirmed": [item.get("submit_confirmed") for item in prompts] if isinstance(prompts, list) else [],
        "api_methods": sorted(set(methods)),
        "herdr_idle_fields_seen": herdr_idle_fields_seen(receipt or {}),
        "tick_stdout_excerpt": str(tick.get("stdout") or "")[-2000:],
        "tick_stderr_excerpt": str(tick.get("stderr") or "")[-2000:],
    }


@app.command("run")
def run_live_e2e(
    allow_live: bool = typer.Option(False, "--allow-live", help="Required guard for live Herdr access."),
    allow_apply: bool = typer.Option(False, "--allow-apply", help="Allow typing prompts into selected panes."),
    require_prompt: bool = typer.Option(False, "--require-prompt", help="Fail if no pane is selected and prompted."),
    space: str = typer.Option("codex", "--space", help="Herdr workspace label/id/number."),
    cwd_prefix: str = typer.Option(str(Path.home() / "workspace" / "experiments"), "--cwd-prefix", help="Monitor scope."),
    min_stopped_seconds: int = typer.Option(600, "--min-stopped-seconds", min=0, help="Minimum stopped age for prompt selection."),
    output_root: Path = typer.Option(DEFAULT_OUTPUT_ROOT, "--output-root", help="Directory for live eval reports."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=5, help="Tick timeout."),
) -> None:
    if not allow_live:
        print(json.dumps({
            "schema": "agent_skills.monitor_herdr.live_e2e_report.v1",
            "mocked": False,
            "live": False,
            "ok": False,
            "status": "BLOCKED",
            "failures": ["missing_allow_live"],
        }, indent=2, sort_keys=True))
        raise typer.Exit(2)

    run_id = f"live-e2e-{timestamp()}"
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(SKILL_DIR / "run.sh"),
        "tick",
        "--space",
        space,
        "--cwd-prefix",
        cwd_prefix,
        "--min-stopped-seconds",
        str(min_stopped_seconds),
        "--max-prompts",
        "1",
        "--json",
    ]
    if allow_apply:
        command.insert(2, "--apply")
    tick = run_command(command, timeout_seconds=timeout_seconds)
    receipt = parse_json_stdout(tick)
    report = build_report(
        run_id=run_id,
        tick=tick,
        receipt=receipt,
        allow_apply=allow_apply,
        require_prompt=require_prompt,
    )
    report_path = output_dir / "report.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise typer.Exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    app()
