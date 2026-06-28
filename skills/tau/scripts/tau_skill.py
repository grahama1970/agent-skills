#!/usr/bin/env python3
"""Lightweight operator wrapper for the local T'au project.

The wrapper reports current proof boundaries and runs bounded sanity checks.
It intentionally avoids mutating GitHub or changing cron state.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

TAU_ROOT = Path("/home/graham/workspace/experiments/tau")
UX_LAB_ROOT = Path("/home/graham/workspace/experiments/pi-mono/packages/ux-lab")
WATCHDOG_ROOT = Path.home() / ".local/state/project-watchdog"
WATCHDOG_RECEIPTS = WATCHDOG_ROOT / "receipts"
WATCHDOG_LOG = WATCHDOG_ROOT / "logs/project-watchdog.log"
WATCHDOG_CRON_LOG = WATCHDOG_ROOT / "logs/cron.log"
PROOFS_ROOT = TAU_ROOT / "experiments/goal-locked-subagents/proofs"
CHAT_CONTRACT = TAU_ROOT / "ui/tau-chat-contract.json"
UV_BIN = "/home/graham/.local/bin/uv"

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
    all_paths: list[Path] = []
    if PROOFS_ROOT.exists():
        all_paths = sorted(PROOFS_ROOT.glob("*/manifest.json"), key=lambda p: p.stat().st_mtime)
        manifests = [manifest_summary(path) for path in all_paths[-12:]]
    return {
        "schema": "agent_skills.tau.latest_proofs.v1",
        "proofs_root": str(PROOFS_ROOT),
        "manifest_count": len(manifests),
        "total_manifest_count": len(all_paths),
        "manifests": manifests,
        "goal_objective_manifests": goal_objective_manifests(all_paths),
        "chat_contract_exists": CHAT_CONTRACT.exists(),
        "chat_contract": str(CHAT_CONTRACT),
    }


def manifest_summary(path: Path) -> dict[str, Any]:
    """Return a compact manifest row, preserving parse errors."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {"path": str(path), "error": str(exc)}
    except json.JSONDecodeError as exc:
        return {"path": str(path), "error": str(exc)}
    return {
        "path": str(path),
        "schema": payload.get("schema"),
        "mocked": payload.get("mocked"),
        "live": payload.get("live"),
        "ok": payload.get("ok", payload.get("status")),
    }


def goal_objective_manifests(paths: list[Path]) -> list[dict[str, Any]]:
    """Surface older manifests that directly prove the active Tau hardening goal."""
    required_names = {
        "live-memory-route-failclosed-20260628T140048Z": "route_specific_memory_failclosed",
        "fresh-answer-browser-route-20260628T152045Z": "answer_browser_route",
        "fresh-research-brave-command-loop-20260628T152651Z": "research_brave_command_loop",
        "fresh-compliance-memory-browser-clean-20260628T212908Z": "compliance_memory_browser",
        "tau-same-run-compliance-20260628T222531Z": "same_run_chat_to_command_loop",
        "project-watchdog-same-run-compliance-apply-20260628T224349Z": "watchdog_apply_transport",
        "fresh-current-multistep-command-loop-20260628T225412Z": "current_multistep_command_loop",
        "fresh-current-multistep-github-apply-20260628T225904Z": "current_multistep_github_apply",
        "ux-lab-repeatable-same-message-tui-mirror-20260628T232614Z": "repeatable_chat_tui_mirror",
        "skill-chat-ui-proof-command-20260628T233232Z": "skill_chat_ui_proof_command",
        "skill-e2e-include-chat-ui-20260628T233739Z": "e2e_include_chat_ui",
    }
    rows: list[dict[str, Any]] = []
    for path in paths:
        key = required_names.get(path.parent.name)
        if key is None:
            continue
        row = manifest_summary(path)
        row["goal_evidence_key"] = key
        rows.append(row)
    return rows


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


def chat_ui_proof_payload(
    *,
    url: str,
    prompt: str,
    out_dir: Path | None,
    timeout_s: int,
) -> dict[str, Any]:
    """Run the repeatable UX Lab Tau same-message chat/TUI mirror proof."""
    proof_out_dir = out_dir or Path(f"/tmp/tau-skill-chat-ui-proof-{datetime.now(UTC):%Y%m%dT%H%M%SZ}")
    command = [
        "node",
        "scripts/tau-same-message-visible-tui-mirror-proof.mjs",
    ]
    run_env = {
        "TAU_CHAT_URL": url,
        "TAU_CHAT_PROMPT": prompt,
        "TAU_PROOF_OUT_DIR": str(proof_out_dir),
    }
    try:
        completed = subprocess.run(
            command,
            cwd=str(UX_LAB_ROOT),
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
            env={**os.environ, **run_env},
        )
    except FileNotFoundError as exc:
        return {
            "schema": "agent_skills.tau.chat_ui_proof_receipt.v1",
            "checked_at": now(),
            "ok": False,
            "mocked": False,
            "live": True,
            "command": command,
            "cwd": str(UX_LAB_ROOT),
            "error": str(exc),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "schema": "agent_skills.tau.chat_ui_proof_receipt.v1",
            "checked_at": now(),
            "ok": False,
            "mocked": False,
            "live": True,
            "command": command,
            "cwd": str(UX_LAB_ROOT),
            "exit_code": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "proof_out_dir": str(proof_out_dir),
        }

    proof_json = proof_out_dir / "proof.json"
    proof: dict[str, Any] | None = None
    proof_error = None
    try:
        proof = json.loads(proof_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        proof_error = str(exc)

    ok = completed.returncode == 0 and proof is not None and proof.get("ok") is True
    return {
        "schema": "agent_skills.tau.chat_ui_proof_receipt.v1",
        "checked_at": now(),
        "ok": ok,
        "mocked": False,
        "live": True,
        "command": command,
        "cwd": str(UX_LAB_ROOT),
        "exit_code": completed.returncode,
        "proof_out_dir": str(proof_out_dir),
        "proof_json": str(proof_json),
        "proof_error": proof_error,
        "proof_schema": proof.get("schema") if proof else None,
        "assertions": proof.get("assertions") if proof else {},
        "memory_request_count": len(proof.get("memoryRequests", [])) if proof else 0,
        "screenshot": proof.get("screenshot") if proof else None,
        "stderr": completed.stderr,
        "proof_boundary": {
            "proves": [
                "the checked-in UX Lab Tau chat UI proof runner executed",
                "a live browser COMPLIANCE turn rendered the same-message chat/TUI mirror assertions when ok is true",
            ],
            "does_not_prove": [
                "interactive Textual TUI embedding",
                "PersonaPlex audio synthesis",
                "applied GitHub mutation for this browser turn",
                "semantic correctness of the evidence case",
                "final Sparta Chat readiness",
            ],
        },
    }


def e2e_payload(*, include_chat_ui: bool, chat_ui_timeout_s: int) -> dict[str, Any]:
    sanity_result = sanity_payload()
    status_result = status_payload()
    chat_ui_result = (
        chat_ui_proof_payload(
            url="http://127.0.0.1:3002/#tau",
            prompt="How does Tau handle a CWE-287 SPARTA evidence case?",
            out_dir=None,
            timeout_s=chat_ui_timeout_s,
        )
        if include_chat_ui
        else None
    )
    ok = sanity_result["ok"] and status_result["ok"] and (
        chat_ui_result is None or chat_ui_result["ok"]
    )
    return {
        "schema": "agent_skills.tau.e2e_receipt.v1",
        "checked_at": now(),
        "ok": ok,
        "mocked": "mixed",
        "live": "mixed",
        "sanity": sanity_result,
        "status": status_result,
        "chat_ui": chat_ui_result,
        "required_next_for_ui_claims": []
        if include_chat_ui
        else [
            "Run browser/CDP screenshot verification against the host chat route.",
            "Inspect screenshot for visible Memory stage trace and content rendering.",
        ],
    }


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


@app.command("chat-ui-proof")
def chat_ui_proof_command(
    url: Annotated[
        str,
        typer.Option("--url", help="Tau UX Lab URL to exercise."),
    ] = "http://127.0.0.1:3002/#tau",
    prompt: Annotated[
        str,
        typer.Option("--prompt", help="Prompt to submit through the Tau chat composer."),
    ] = "How does Tau handle a CWE-287 SPARTA evidence case?",
    out_dir: Annotated[
        Path | None,
        typer.Option("--out-dir", help="Output directory for proof.json and screenshot."),
    ] = None,
    timeout_s: Annotated[
        int,
        typer.Option("--timeout-s", help="Maximum seconds for the browser proof command."),
    ] = 90,
) -> None:
    """Run the repeatable live Tau chat/TUI mirror browser proof."""
    emit(chat_ui_proof_payload(url=url, prompt=prompt, out_dir=out_dir, timeout_s=timeout_s))


@app.command("e2e")
def e2e_command(
    _note: Annotated[
        bool,
        typer.Option(
            "--ack-boundary",
            help="No-op flag documenting that this is not browser UI production proof.",
        ),
    ] = False,
    include_chat_ui: Annotated[
        bool,
        typer.Option(
            "--include-chat-ui",
            help="Also run the live UX Lab Tau chat/TUI mirror browser proof.",
        ),
    ] = False,
    chat_ui_timeout_s: Annotated[
        int,
        typer.Option("--chat-ui-timeout-s", help="Maximum seconds for the optional chat UI proof."),
    ] = 90,
) -> None:
    """Run bounded Tau checks plus live status/proof inspection."""
    emit(e2e_payload(include_chat_ui=include_chat_ui, chat_ui_timeout_s=chat_ui_timeout_s))


if __name__ == "__main__":
    app()
