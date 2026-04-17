"""Tier 5: Infrastructure probes (lightweight).

P13 embedding-service     — HTTP health check on embedding FastAPI
P17 disk-usage-12tb       — Check /mnt/storage12tb usage
P18 scheduler-audit       — Check scheduler ran all jobs in last 24h
P19 security-freshness    — Check security-scan last-run (weekly)

Inputs: httpx for HTTP, shutil for disk, filesystem for state files.
Outputs: ProbeResult per probe.
"""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

import config
from probes import ProbeResult, ProbeStatus, register_probe


# ── P13: embedding-service ───────────────────────────────────────────────────


@register_probe("P13", "embedding-service", tier=5)
def probe_embedding_service(autofix: bool = False) -> ProbeResult:
    """HTTP health check on embedding FastAPI service."""
    try:
        import httpx
    except ImportError:
        return ProbeResult(
            probe_id="P13", name="embedding-service", tier=5,
            status=ProbeStatus.SKIP,
            message="httpx not installed",
            details={},
        )

    url = f"{config.EMBEDDING_SERVICE_URL}/health"
    try:
        resp = httpx.get(url, timeout=5)
        if resp.status_code == 200:
            return ProbeResult(
                probe_id="P13", name="embedding-service", tier=5,
                status=ProbeStatus.PASS,
                message=f"Embedding service healthy ({url})",
                details={"status_code": resp.status_code},
            )
        return ProbeResult(
            probe_id="P13", name="embedding-service", tier=5,
            status=ProbeStatus.WARN,
            message=f"Embedding service returned {resp.status_code}",
            details={"status_code": resp.status_code},
        )
    except httpx.ConnectError:
        return ProbeResult(
            probe_id="P13", name="embedding-service", tier=5,
            status=ProbeStatus.WARN,
            message=f"Embedding service unreachable at {url}",
            details={"url": url},
        )
    except httpx.HTTPError as e:
        return ProbeResult(
            probe_id="P13", name="embedding-service", tier=5,
            status=ProbeStatus.WARN,
            message=f"Embedding service error: {e}",
            details={"error": str(e)},
        )


# ── P17: disk-usage-12tb ─────────────────────────────────────────────────────


@register_probe("P17", "disk-usage-12tb", tier=5)
def probe_disk_usage(autofix: bool = False) -> ProbeResult:
    """Check disk usage on /mnt/storage12tb."""
    mount_path = config.STORAGE_12TB
    if not mount_path.exists():
        return ProbeResult(
            probe_id="P17", name="disk-usage-12tb", tier=5,
            status=ProbeStatus.SKIP,
            message=f"{mount_path} not mounted",
            details={"path": str(mount_path)},
        )

    try:
        usage = shutil.disk_usage(str(mount_path))
    except OSError as e:
        return ProbeResult(
            probe_id="P17", name="disk-usage-12tb", tier=5,
            status=ProbeStatus.FAIL,
            message=f"Cannot read disk usage: {e}",
            details={"error": str(e)},
        )

    used_pct = (usage.used / usage.total * 100) if usage.total > 0 else 0
    free_gb = usage.free / (1024 ** 3)

    status = ProbeStatus.PASS if used_pct < config.DISK_WARN_PCT else ProbeStatus.WARN

    return ProbeResult(
        probe_id="P17", name="disk-usage-12tb", tier=5,
        status=status,
        message=f"{used_pct:.1f}% used, {free_gb:.0f} GB free",
        details={
            "used_pct": round(used_pct, 1),
            "free_gb": round(free_gb, 1),
            "total_gb": round(usage.total / (1024 ** 3), 1),
        },
    )


# ── P18: scheduler-audit ─────────────────────────────────────────────────────


@register_probe("P18", "scheduler-audit", tier=5)
def probe_scheduler_audit(autofix: bool = False) -> ProbeResult:
    """Check if all scheduled jobs ran in the last 24 hours."""
    state_dir = Path.home() / ".pi/scheduler"
    if not state_dir.exists():
        return ProbeResult(
            probe_id="P18", name="scheduler-audit", tier=5,
            status=ProbeStatus.SKIP,
            message="Scheduler state directory not found",
            details={"state_dir": str(state_dir)},
        )

    state_file = state_dir / "state.json"
    if not state_file.exists():
        return ProbeResult(
            probe_id="P18", name="scheduler-audit", tier=5,
            status=ProbeStatus.SKIP,
            message="Scheduler state file not found",
            details={},
        )

    try:
        data = json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return ProbeResult(
            probe_id="P18", name="scheduler-audit", tier=5,
            status=ProbeStatus.FAIL,
            message=f"Cannot read scheduler state: {e}",
            details={"error": str(e)},
        )

    jobs = data.get("jobs", {})
    if not jobs:
        return ProbeResult(
            probe_id="P18", name="scheduler-audit", tier=5,
            status=ProbeStatus.WARN,
            message="No scheduled jobs found",
            details={},
        )

    threshold = 24 * 3600
    now = time.time()
    stale_jobs = []
    ok_jobs = []

    for name, info in jobs.items():
        last_run = info.get("last_run", "")
        if last_run:
            try:
                dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                age_s = (datetime.now(timezone.utc) - dt).total_seconds()
                if age_s > threshold:
                    stale_jobs.append(name)
                else:
                    ok_jobs.append(name)
            except ValueError:
                stale_jobs.append(name)
        else:
            stale_jobs.append(name)

    status = ProbeStatus.PASS if not stale_jobs else ProbeStatus.WARN

    return ProbeResult(
        probe_id="P18", name="scheduler-audit", tier=5,
        status=status,
        message=f"{len(ok_jobs)} jobs ran, {len(stale_jobs)} stale/missing",
        details={"ok": ok_jobs, "stale": stale_jobs},
    )


# ── P19: security-freshness ──────────────────────────────────────────────────


@register_probe("P19", "security-freshness", tier=5)
def probe_security_freshness(autofix: bool = False) -> ProbeResult:
    """Check security-scan last-run timestamp (weekly threshold)."""
    state_file = Path.home() / ".pi/security-scan/last_run.json"
    if not state_file.exists():
        return ProbeResult(
            probe_id="P19", name="security-freshness", tier=5,
            status=ProbeStatus.WARN,
            message="security-scan last_run.json not found",
            details={"state_file": str(state_file)},
        )

    try:
        data = json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return ProbeResult(
            probe_id="P19", name="security-freshness", tier=5,
            status=ProbeStatus.FAIL,
            message=f"Cannot read security state: {e}",
            details={"error": str(e)},
        )

    last_run = data.get("timestamp", data.get("last_run", ""))
    if not last_run:
        return ProbeResult(
            probe_id="P19", name="security-freshness", tier=5,
            status=ProbeStatus.WARN,
            message="No timestamp in security-scan state",
            details={},
        )

    try:
        dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except ValueError:
        age_days = float("inf")

    status = ProbeStatus.PASS if age_days <= config.SECURITY_MAX_AGE_DAYS else ProbeStatus.WARN

    return ProbeResult(
        probe_id="P19", name="security-freshness", tier=5,
        status=status,
        message=f"Last security scan {age_days:.1f} days ago",
        details={"age_days": round(age_days, 1), "last_run": last_run},
    )
