#!/usr/bin/env python3
"""Lightweight operator wrapper for the local T'au project.

The wrapper reports current proof boundaries and runs bounded sanity checks.
It intentionally avoids mutating GitHub or changing cron state.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

TAU_ROOT = Path(
    os.environ.get("TAU_ROOT", str(Path.home() / "workspace/experiments/tau"))
).expanduser().resolve()
WATCHDOG_ROOT = Path.home() / ".local/state/project-watchdog"
WATCHDOG_RECEIPTS = WATCHDOG_ROOT / "receipts"
WATCHDOG_LOG = WATCHDOG_ROOT / "logs/project-watchdog.log"
WATCHDOG_CRON_LOG = WATCHDOG_ROOT / "logs/cron.log"
PROOFS_ROOT = TAU_ROOT / "experiments/goal-locked-subagents/proofs"
CHAT_CONTRACT = TAU_ROOT / "ui/tau-chat-contract.json"
UV_BIN = os.environ.get("UV_BIN") or shutil.which("uv") or str(Path.home() / ".local/bin/uv")

app = typer.Typer(add_completion=False, help="Operate and inspect the local T'au project.")


def now() -> str:
    """Return a UTC timestamp for receipts."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def emit(payload: dict[str, Any]) -> None:
    """Write JSON and use the payload ok field as the process result."""
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    if payload.get("ok") is False:
        raise typer.Exit(1)


def run(command: list[str], *, cwd: Path = TAU_ROOT, timeout_s: int = 120) -> dict[str, Any]:
    """Run a bounded command and capture stdout/stderr for receipts."""
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "command": command,
            "cwd": str(cwd),
            "exit_code": 127,
            "stdout": "",
            "stderr": str(exc),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "cwd": str(cwd),
            "exit_code": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    return {
        "command": command,
        "cwd": str(cwd),
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def uv_command(*parts: str) -> list[str]:
    return [UV_BIN, *parts]


def command_path(name: str) -> str | None:
    """Return the resolved executable path for a command, if available."""
    return shutil.which(name)


def doctor_payload() -> dict[str, Any]:
    """Report whether the Tau skill wrapper can find and invoke local Tau."""
    uv_path = command_path(UV_BIN) if "/" not in UV_BIN else (UV_BIN if Path(UV_BIN).exists() else None)
    git_path = command_path("git")
    gh_path = command_path("gh")
    herdr_path = command_path("herdr")
    tau_help = run(uv_command("run", "--project", str(TAU_ROOT), "tau", "--help"), timeout_s=60)
    git_status = run(["git", "status", "--short"], timeout_s=30) if TAU_ROOT.exists() else {
        "command": ["git", "status", "--short"],
        "cwd": str(TAU_ROOT),
        "exit_code": 1,
        "stdout": "",
        "stderr": "Tau root does not exist",
    }
    errors: list[str] = []
    if not TAU_ROOT.exists():
        errors.append("tau_root_missing")
    if not uv_path:
        errors.append("uv_missing")
    if tau_help["exit_code"] != 0:
        errors.append("tau_help_failed")
    if git_status["exit_code"] != 0:
        errors.append("git_status_failed")

    can_run_herdr_lane = bool(herdr_path)
    can_run_provider_live_lane = False
    can_run_github_apply_lane = False
    return {
        "schema": "agent_skills.tau.doctor.v1",
        "checked_at": now(),
        "ok": not errors,
        "mocked": False,
        "live": True,
        "provider_live": False,
        "command": "doctor",
        "tau_root": str(TAU_ROOT),
        "resolved_tau_root": str(TAU_ROOT),
        "uv": uv_path,
        "resolved_uv_bin": UV_BIN,
        "git": git_path,
        "gh": gh_path,
        "herdr": herdr_path,
        "memory_url": os.environ.get("MEMORY_URL", "http://127.0.0.1:7331"),
        "scillm_url": os.environ.get("SCILLM_URL", "http://127.0.0.1:4001"),
        "chat_contract_exists": CHAT_CONTRACT.exists(),
        "chat_contract": str(CHAT_CONTRACT),
        "can_call_tau_cli": tau_help["exit_code"] == 0,
        "can_run_local_sanity": tau_help["exit_code"] == 0,
        "can_run_herdr_lane": can_run_herdr_lane,
        "can_run_provider_live_lane": can_run_provider_live_lane,
        "can_run_github_dry_run_lane": bool(gh_path),
        "can_run_github_apply_lane": can_run_github_apply_lane,
        "can_run_browser_cdp_lane": False,
        "commands": {
            "tau_help": tau_help,
            "git_status": git_status,
        },
        "errors": errors,
        "proof_boundary": {
            "proves": [
                "Tau skill wrapper resolved the Tau root path",
                "Tau skill wrapper resolved uv or reported it missing",
                "Tau CLI help was invoked through the wrapper when available",
            ],
            "does_not_prove": [
                "Herdr provider DAG execution",
                "browser/CDP UI proof",
                "GitHub live mutation",
                "provider/model semantic quality",
            ],
        },
    }


def status_payload() -> dict[str, Any]:
    git_status = run(["git", "status", "--short"])
    head = run(["git", "log", "-1", "--oneline", "--decorate"])
    remote = run(["git", "ls-remote", "grahama1970", "refs/heads/main"])
    issues = run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            "grahama1970/tau",
            "--state",
            "open",
            "--limit",
            "20",
            "--json",
            "number,title,labels,url,state",
        ],
        cwd=TAU_ROOT,
    )
    issue_payload = json.loads(issues["stdout"] or "[]") if issues["exit_code"] == 0 else None
    return {
        "schema": "agent_skills.tau.status.v1",
        "checked_at": now(),
        "ok": all(item["exit_code"] == 0 for item in (git_status, head, remote, issues)),
        "mocked": False,
        "live": True,
        "tau_root": str(TAU_ROOT),
        "resolved_tau_root": str(TAU_ROOT),
        "resolved_uv_bin": UV_BIN,
        "git": {
            "head": head["stdout"].strip(),
            "remote_main": remote["stdout"].strip(),
            "status_short": git_status["stdout"].splitlines(),
        },
        "github_open_issues": issue_payload,
        "watchdog": watchdog_status_payload(),
        "proofs": latest_proofs_payload(),
    }


def watchdog_status_payload() -> dict[str, Any]:
    crontab = run(["crontab", "-l"], cwd=Path.cwd())
    latest_receipts = latest_watchdog_receipts(limit=5)
    cron_installed = "project-watchdog global issue cron" in crontab["stdout"]
    return {
        "schema": "agent_skills.tau.watchdog_status.v1",
        "ok": crontab["exit_code"] == 0,
        "mocked": False,
        "live": True,
        "cron_installed": cron_installed,
        "cron_log": str(WATCHDOG_CRON_LOG),
        "event_log": str(WATCHDOG_LOG),
        "latest_receipts": latest_receipts,
    }


def latest_watchdog_receipts(*, limit: int) -> list[dict[str, Any]]:
    if not WATCHDOG_RECEIPTS.exists():
        return []
    paths = sorted(WATCHDOG_RECEIPTS.glob("*/receipt.json"), key=lambda path: path.stat().st_mtime)
    rows: list[dict[str, Any]] = []
    for path in paths[-limit:]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            rows.append({"path": str(path), "error": str(exc)})
            continue
        except json.JSONDecodeError as exc:
            rows.append({"path": str(path), "error": str(exc)})
            continue
        rows.append(
            {
                "path": str(path),
                "schema": payload.get("schema"),
                "run_id": payload.get("run_id"),
                "status": payload.get("status"),
                "ok": payload.get("ok"),
                "handled_count": payload.get("handled_count"),
            }
        )
    return rows


def latest_proofs_payload() -> dict[str, Any]:
    manifests: list[dict[str, Any]] = []
    if PROOFS_ROOT.exists():
        paths = sorted(PROOFS_ROOT.glob("*/manifest.json"), key=lambda p: p.stat().st_mtime)
        for path in paths[-12:]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except OSError as exc:
                manifests.append({"path": str(path), "error": str(exc)})
                continue
            except json.JSONDecodeError as exc:
                manifests.append({"path": str(path), "error": str(exc)})
                continue
            manifests.append(
                {
                    "path": str(path),
                    "schema": payload.get("schema"),
                    "mocked": payload.get("mocked"),
                    "live": payload.get("live"),
                    "ok": payload.get("ok", payload.get("status")),
                }
            )
    return {
        "schema": "agent_skills.tau.latest_proofs.v1",
        "proofs_root": str(PROOFS_ROOT),
        "manifest_count": len(manifests),
        "manifests": manifests,
        "chat_contract_exists": CHAT_CONTRACT.exists(),
        "chat_contract": str(CHAT_CONTRACT),
    }


def sanity_payload() -> dict[str, Any]:
    test_command = run(
        uv_command(
            "run",
            "--project",
            str(TAU_ROOT),
            "pytest",
            "-q",
            "tests/test_subagent_receipt.py",
            "tests/test_agent_harness.py",
            "tests/test_tui_adapter.py",
            "tests/test_live_memory_chat_command_loop_proofs.py",
        ),
        timeout_s=180,
    )
    coder_spec = (
        TAU_ROOT
        / "experiments/goal-locked-subagents/agent-command-specs/coder/tau-dispatch-command.json"
    )
    json_ok = True
    json_error = None
    try:
        json.loads(coder_spec.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        json_ok = False
        json_error = str(exc)

    ok = test_command["exit_code"] == 0 and json_ok
    return {
        "schema": "agent_skills.tau.sanity_receipt.v1",
        "checked_at": now(),
        "ok": ok,
        "mocked": "mixed",
        "live": "mixed",
        "commands": [test_command],
        "json_checks": [
            {
                "path": str(coder_spec),
                "ok": json_ok,
                "error": json_error,
            }
        ],
        "proof_boundary": {
            "proves": [
                "targeted Tau receipt, harness, TUI adapter, and proof-manifest checks run",
                "coder command-spec JSON is readable",
            ],
            "does_not_prove": [
                "fresh browser chat UI rendering",
                "fresh live provider semantics",
                "production Sparta Chat readiness",
            ],
        },
    }


def proof_status_payload(*, command_name: str = "proof-status") -> dict[str, Any]:
    sanity_result = sanity_payload()
    status_result = status_payload()
    ok = sanity_result["ok"] and status_result["ok"]
    return {
        "schema": "agent_skills.tau.proof_status_receipt.v1",
        "checked_at": now(),
        "ok": ok,
        "mocked": "mixed",
        "live": "mixed",
        "provider_live": False,
        "command": command_name,
        "alias_for": "proof-status" if command_name == "e2e" else None,
        "deprecated_name": command_name == "e2e",
        "sanity": sanity_result,
        "status": status_result,
        "proof_boundary": {
            "proves": [
                "bounded Tau skill sanity checks ran",
                "Tau repository status and latest proof surfaces were inspected",
            ],
            "does_not_prove": [
                "Herdr provider DAG execution",
                "browser/CDP UI proof",
                "GitHub live mutation",
                "P1 schema enforcement",
                "issue #50 DAG context propagation fix",
            ],
        },
        "required_next_for_ui_claims": [
            "Run browser/CDP screenshot verification against the host chat route.",
            "Inspect screenshot for visible Memory stage trace and content rendering.",
        ],
    }


@app.command("doctor")
def doctor_command() -> None:
    """Check whether the Tau skill wrapper can find and invoke local Tau."""
    emit(doctor_payload())


@app.command("status")
def status_command() -> None:
    """Report Tau repo, GitHub issue, watchdog, and proof state."""
    emit(status_payload())


@app.command("watchdog-status")
def watchdog_status_command() -> None:
    """Report project-watchdog cron and latest receipt state."""
    emit(watchdog_status_payload())


@app.command("latest-proofs")
def latest_proofs_command() -> None:
    """List recent Tau proof manifests."""
    emit({"ok": True, **latest_proofs_payload()})


@app.command("sanity")
def sanity_command() -> None:
    """Run bounded non-mutating Tau checks."""
    emit(sanity_payload())


@app.command("proof-status")
def proof_status_command() -> None:
    """Run bounded Tau checks plus explicit proof-boundary status inspection."""
    emit(proof_status_payload())


@app.command("e2e")
def e2e_command(
    _note: Annotated[
        bool,
        typer.Option(
            "--ack-boundary",
            help="No-op flag documenting that this is not browser UI production proof.",
        ),
    ] = False,
) -> None:
    """Compatibility alias for proof-status; not full production E2E proof."""
    emit(proof_status_payload(command_name="e2e"))


if __name__ == "__main__":
    app()
