"""Container/service rebuild-restart for containerized projects.

Many registered projects serve from a container or daemon that does NOT
auto-reload host source (memory: embry-memory docker; sparta/scillm/chatterbox:
systemd units). A repair that edits source is therefore not testable until the
service is rebuilt and restarted on the new code. This module gives the watchdog
that capability, driven by the registry ``service`` field:

    "service": {
        "kind": "docker+systemd" | "systemd" | "none",
        "restart_cmd": "<shell to rebuild+restart>",
        "health_check": "<shell that exits 0 when healthy>",
        "deps": [...],
        "proof_needs_restart": true | false
    }

It is fail-closed: a missing/failed restart or a health check that never passes
within the bounded window returns ok=False so the caller must BLOCK rather than
run the deterministic proof against stale (or dead) code.

WIRING NOTE (deliberately not called from the live dispatch yet): where this
runs is a policy decision, because the fix lives in an unmerged worktree while
the proof hits the live service. Two safe models — (a) hermetic ephemeral
instance built from the worktree, or (b) supervised install-from-worktree ->
restart -> proof -> rollback-on-fail — must be chosen before the repair flow
calls this. Until then this is a tested, dormant capability (see #1398).
"""
from __future__ import annotations

import time
from typing import Any

from .core import run_cmd


def service_config(project: dict[str, Any] | None) -> dict[str, Any]:
    """The project's ``service`` block, or a safe no-restart default."""
    if not project:
        return {"kind": "none", "proof_needs_restart": False}
    return project.get("service") or {"kind": "none", "proof_needs_restart": False}


def needs_restart(project: dict[str, Any] | None) -> bool:
    return bool(service_config(project).get("proof_needs_restart"))


def rebuild_restart_service(
    project: dict[str, Any] | None,
    *,
    cwd: str,
    health_timeout_s: int = 120,
    health_poll_s: float = 3.0,
    restart_timeout_s: int = 600,
    _now=time.monotonic,
    _sleep=time.sleep,
) -> dict[str, Any]:
    """Rebuild+restart the project's service, then wait for its health check.

    Returns a receipt fragment: {ok, kind, steps:[...], reason?}. Fail-closed —
    ok is False unless the restart command exits 0 AND the health check passes
    within the bounded window. A project with proof_needs_restart=False is a
    no-op success (ok=True, skipped).
    """
    svc = service_config(project)
    receipt: dict[str, Any] = {"kind": svc.get("kind", "none"), "steps": []}

    if not svc.get("proof_needs_restart"):
        receipt["ok"] = True
        receipt["skipped"] = "proof_needs_restart is false"
        return receipt

    restart_cmd = svc.get("restart_cmd")
    if not restart_cmd:
        receipt["ok"] = False
        receipt["reason"] = "service.proof_needs_restart is true but no restart_cmd is declared"
        return receipt

    restart = run_cmd(["bash", "-lc", restart_cmd], cwd=cwd, timeout_s=restart_timeout_s)
    receipt["steps"].append({"restart_cmd": restart_cmd, "exit_code": restart.get("exit_code")})
    if restart.get("exit_code") != 0:
        receipt["ok"] = False
        receipt["reason"] = "restart_cmd failed"
        return receipt

    health = svc.get("health_check")
    if not health:
        # Restart succeeded but we cannot prove liveness -> fail closed.
        receipt["ok"] = False
        receipt["reason"] = "restart succeeded but no health_check declared to prove liveness"
        return receipt

    deadline = _now() + health_timeout_s
    attempts = 0
    while True:
        attempts += 1
        check = run_cmd(["bash", "-lc", health], cwd=cwd, timeout_s=30)
        if check.get("exit_code") == 0:
            receipt["steps"].append({"health_check": health, "attempts": attempts, "healthy": True})
            receipt["ok"] = True
            return receipt
        if _now() >= deadline:
            receipt["steps"].append({"health_check": health, "attempts": attempts, "healthy": False})
            receipt["ok"] = False
            receipt["reason"] = f"health_check did not pass within {health_timeout_s}s"
            return receipt
        _sleep(health_poll_s)
