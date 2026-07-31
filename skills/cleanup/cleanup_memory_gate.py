"""Pre-mutation gate for memory-mutating cleanup lanes (issue #1125).

Cleanup consumes receipts from the owning producers — the ops-arango nightly
backup lane and the monitor-sparta health scanner — and never re-runs their
checks itself. The gate is check-then-skip: a fresh verified backup receipt and
a fresh passing health receipt let the lane proceed citing the EXISTING
receipts; anything else fails the lane closed with a named blocker whose text
carries the exact producer command to re-run.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_BACKUP_RECEIPT = "/mnt/storage12tb/backups/arangodb/latest_backup_receipt.json"
DEFAULT_HEALTH_RECEIPT = "/mnt/storage12tb/media/agents/shared/monitor-sparta/state.json"

# Thresholds are tuned for a weekly cleanup consuming daily producers: accept
# the LATEST nightly backup (<48h) and the LATEST health receipt (<24h), never
# demand receipts generated at cleanup time.
DEFAULT_BACKUP_MAX_AGE_HOURS = 48.0
DEFAULT_HEALTH_MAX_AGE_HOURS = 24.0

BACKUP_REMEDIATION = (
    "run the owning backup lane: bash ~/.claude/skills/ops-arango/run.sh dump "
    "(cleanup never runs arangodump itself; the nightly lane retains ownership)"
)
HEALTH_REMEDIATION = (
    "run the owning monitor: bash skills/monitor-sparta/run.sh health "
    "(cleanup consumes the monitor verdict; it never re-implements the checks)"
)

_FAILING_VERDICTS = {"failed", "failing", "critical", "error", "stalled"}


def _parse_timestamp(value: Any) -> Optional[datetime]:
    # Producers disagree: ops-arango writes ISO strings, monitor-sparta
    # state.json writes UNIX epoch floats. Accept both.
    if isinstance(value, (int, float)) and value > 0:
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _age_hours(timestamp: Optional[datetime], now: datetime) -> Optional[float]:
    if timestamp is None:
        return None
    return (now - timestamp).total_seconds() / 3600.0


def _read_json(path: Path) -> Dict[str, Any]:
    import json

    return json.loads(path.read_text())


def check_backup_freshness(
    receipt_path: str | Path,
    *,
    max_age_hours: float = DEFAULT_BACKUP_MAX_AGE_HOURS,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Read back the ops-arango backup receipt and judge freshness."""
    now = now or datetime.now(timezone.utc)
    path = Path(receipt_path)
    result: Dict[str, Any] = {
        "receipt_path": str(path),
        "max_age_hours": max_age_hours,
        "fresh": False,
        "detail": "",
    }
    if not path.exists():
        result["detail"] = f"backup receipt missing: {path}"
        return result
    try:
        receipt = _read_json(path)
    except Exception as exc:
        result["detail"] = f"backup receipt unreadable: {exc}"
        return result

    completed = _parse_timestamp(receipt.get("completed_at"))
    age = _age_hours(completed, now)
    result["completed_at"] = receipt.get("completed_at")
    result["backup_dir"] = receipt.get("backup_dir")
    result["age_hours"] = age
    if age is None:
        result["detail"] = "backup receipt has no parseable completed_at"
        return result
    if age > max_age_hours:
        result["detail"] = (
            f"latest backup is {age:.1f}h old (threshold {max_age_hours:.0f}h)"
        )
        return result

    backup_dir = receipt.get("backup_dir")
    if backup_dir and not Path(str(backup_dir)).exists():
        result["detail"] = f"backup receipt cites missing backup_dir: {backup_dir}"
        return result

    result["fresh"] = True
    result["detail"] = f"backup is {age:.1f}h old, within {max_age_hours:.0f}h threshold"
    return result


def _failing_health_categories(state: Dict[str, Any]) -> List[str]:
    failing: List[str] = []
    top_status = str(state.get("status", "")).lower()
    if top_status in _FAILING_VERDICTS:
        failing.append(f"status={top_status}")
    for key, value in state.items():
        if not key.endswith("_health") or not isinstance(value, dict):
            continue
        verdict = str(value.get("status") or value.get("verdict") or "").lower()
        if verdict in _FAILING_VERDICTS:
            failing.append(key)
    return failing


def check_monitor_health(
    receipt_path: str | Path,
    *,
    max_age_hours: float = DEFAULT_HEALTH_MAX_AGE_HOURS,
    allowed_failing_categories: Optional[List[str]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Read back the owning monitor's health receipt: freshness then verdict."""
    now = now or datetime.now(timezone.utc)
    allowed = set(allowed_failing_categories or [])
    path = Path(receipt_path)
    result: Dict[str, Any] = {
        "receipt_path": str(path),
        "max_age_hours": max_age_hours,
        "fresh": False,
        "passing": False,
        "failing_categories": [],
        "detail": "",
    }
    if not path.exists():
        result["detail"] = f"monitor health receipt missing: {path}"
        return result
    try:
        state = _read_json(path)
    except Exception as exc:
        result["detail"] = f"monitor health receipt unreadable: {exc}"
        return result

    updated = _parse_timestamp(state.get("last_updated"))
    age = _age_hours(updated, now)
    result["last_updated"] = state.get("last_updated")
    result["age_hours"] = age
    if age is None or age > max_age_hours:
        result["detail"] = (
            "monitor health receipt has no parseable last_updated"
            if age is None
            else f"monitor health receipt is {age:.1f}h old (threshold {max_age_hours:.0f}h)"
        )
        return result
    result["fresh"] = True

    failing = [c for c in _failing_health_categories(state) if c not in allowed]
    result["failing_categories"] = failing
    if failing:
        result["detail"] = f"monitor reports failing categories: {', '.join(failing)}"
        return result

    result["passing"] = True
    result["detail"] = f"health receipt is {age:.1f}h old and passing"
    return result


def evaluate_memory_mutation_gate(
    *,
    backup_receipt_path: Optional[str] = None,
    health_receipt_path: Optional[str] = None,
    backup_max_age_hours: Optional[float] = None,
    health_max_age_hours: Optional[float] = None,
    allowed_failing_categories: Optional[List[str]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Evaluate every pre-mutation receipt gate for a memory-mutating lane.

    Returns ``allowed`` plus a blocker list where each blocker names the exact
    producer command to re-run, because a weekly-cadence consumer that blocks
    stays blocked until an operator acts.
    """
    backup = check_backup_freshness(
        backup_receipt_path
        or os.environ.get("CLEANUP_ARANGO_BACKUP_RECEIPT", DEFAULT_BACKUP_RECEIPT),
        max_age_hours=backup_max_age_hours
        if backup_max_age_hours is not None
        else float(os.environ.get("CLEANUP_BACKUP_MAX_AGE_HOURS", DEFAULT_BACKUP_MAX_AGE_HOURS)),
        now=now,
    )
    health = check_monitor_health(
        health_receipt_path
        or os.environ.get("CLEANUP_MONITOR_HEALTH_RECEIPT", DEFAULT_HEALTH_RECEIPT),
        max_age_hours=health_max_age_hours
        if health_max_age_hours is not None
        else float(os.environ.get("CLEANUP_HEALTH_MAX_AGE_HOURS", DEFAULT_HEALTH_MAX_AGE_HOURS)),
        allowed_failing_categories=allowed_failing_categories
        or [c for c in os.environ.get("CLEANUP_HEALTH_ALLOWED_FAILING", "").split(",") if c],
        now=now,
    )

    blockers: List[Dict[str, str]] = []
    if not backup["fresh"]:
        blockers.append({
            "blocker": "memory_backup_stale",
            "detail": backup["detail"],
            "remediation": BACKUP_REMEDIATION,
        })
    if not health["fresh"]:
        blockers.append({
            "blocker": "memory_health_stale",
            "detail": health["detail"],
            "remediation": HEALTH_REMEDIATION,
        })
    elif not health["passing"]:
        blockers.append({
            "blocker": "memory_health_failing",
            "detail": health["detail"],
            "remediation": HEALTH_REMEDIATION,
        })

    return {
        "schema": "cleanup.memory_mutation_gate.v1",
        "allowed": not blockers,
        "blockers": blockers,
        "backup": backup,
        "health": health,
        "backup_request_invocations": 0,
        "policy": (
            "check-then-skip: a fresh verified backup and fresh passing health "
            "receipt are cited as-is; cleanup never duplicates the nightly "
            "backup lane's work or re-runs monitor checks"
        ),
    }
