"""Cron capability preflight: probe dependencies before burning leases (#1644).

cron starts with a nearly empty environment. Two historical failures came from
that drift: provider auth failed under cron while working interactively, and
the triage-error runner was undiscoverable (2026-09-10). Both made a healthy
queue look intrinsically unrepairable and burned leases/DAG runs discovering it.

This module probes the dispatch-critical dependencies once, writes a capability
receipt per dependency, and answers whether NEW leases may be acquired. A failed
probe pauses new dispatch but never blocks recovery, native close, or release --
those must still drain in-flight work. Restored health auto-resumes because the
next probe rewrites the receipt.

Probes are cheap and deterministic; each returns (ok, detail). A probe that
raises is treated as a failure with the exception text, never a crash.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from . import config

RECEIPT_SCHEMA = "agent_skills.project_watchdog.capability_receipt.v1"
RECEIPT_FILE = "capability-preflight.json"
#: A receipt older than this is stale and cannot authorize new leases.
DEFAULT_MAX_AGE_SECONDS = 3600


def _run(argv: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def _probe_gh() -> tuple[bool, str]:
    if not shutil.which("gh"):
        return False, "gh_not_on_path"
    p = _run(["gh", "auth", "status"])
    return (p.returncode == 0, "authenticated" if p.returncode == 0 else "gh_auth_not_ready")


def _probe_triage_runner() -> tuple[bool, str]:
    runner = Path.home() / ".pi" / "agent" / "skills" / "triage-error" / "run.sh"
    if not runner.is_file():
        return False, "triage_runner_not_discoverable"
    p = _run([str(runner), "classify", "--text", "probe", "--layer", "tau", "--contract", "tau"])
    return (p.returncode == 0, "contract_ok" if p.returncode == 0 else "triage_contract_probe_failed")


def _probe_memory() -> tuple[bool, str]:
    runner = config.SKILL_DIR.parent / "memory" / "run.sh"
    if not runner.is_file():
        return False, "memory_runner_missing"
    return True, "runner_present"


def _probe_ask() -> tuple[bool, str]:
    runner = config.ask_run_sh()
    return (runner.is_file(), "entrypoint_present" if runner.is_file() else "ask_entrypoint_missing")


#: Named probes; tests monkeypatch this map to fault-inject a single dependency.
PROBES: dict[str, Callable[[], tuple[bool, str]]] = {
    "gh": _probe_gh,
    "triage_runner": _probe_triage_runner,
    "memory": _probe_memory,
    "ask": _probe_ask,
}


def run(output: Path | None = None) -> dict[str, Any]:
    """Probe every dependency and write the capability receipt."""
    deps: dict[str, Any] = {}
    for name, probe in PROBES.items():
        try:
            ok, detail = probe()
        except Exception as exc:  # noqa: BLE001 - a probe crash is a failed probe
            ok, detail = False, f"probe_raised:{str(exc)[:80]}"
        deps[name] = {"ok": ok, "detail": detail}
    dispatch_ready = all(d["ok"] for d in deps.values())
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "checked_at": time.time(),
        "checked_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dispatch_ready": dispatch_ready,
        "failed": [n for n, d in deps.items() if not d["ok"]],
        "dependencies": deps,
    }
    path = output or (config.state_root() / RECEIPT_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    receipt["receipt_path"] = str(path)
    return receipt


def dispatch_allowed(*, max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> tuple[bool, dict[str, Any]]:
    """Whether NEW leases may be acquired. Recovery/close are never gated here.

    Fail-closed: a missing or stale receipt refuses new dispatch (the fleet must
    prove capability recently), but the reason is reported so the supervisor can
    run the preflight rather than treating it as a human blocker.
    """
    path = config.state_root() / RECEIPT_FILE
    try:
        receipt = json.loads(path.read_text())
    except (OSError, ValueError):
        return False, {"reason": "no_capability_receipt", "next": "run capability_preflight.run()"}
    if os.environ.get("PROJECT_WATCHDOG_SKIP_CAPABILITY_PREFLIGHT"):
        return True, {"reason": "preflight_disabled_by_env"}
    age = time.time() - float(receipt.get("checked_at") or 0)
    if age > max_age_seconds:
        return False, {"reason": "capability_receipt_stale", "age_seconds": age}
    if not receipt.get("dispatch_ready"):
        return False, {"reason": "capability_dependency_down", "failed": receipt.get("failed")}
    return True, {"reason": "ready", "checked_at_iso": receipt.get("checked_at_iso")}
