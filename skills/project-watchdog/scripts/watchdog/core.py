"""Logging, subprocess execution, JSON IO, locking, and receipt helpers.

Purpose
    The shared primitives every watchdog command needs. Kept separate from
    routing and dispatch so a change to how the watchdog logs or locks cannot
    silently alter which issues it selects.

Inputs
    Callers supply run ids, command argv lists, and receipt dictionaries.

Outputs
    - A structured JSONL event stream at ``config.event_log_path()``, written
      through a Loguru sink so diagnostics and the durable event log share one
      configuration.
    - ``receipt.json`` files under ``config.receipt_root()/<run_id>/``.

Failure modes
    - ``run_cmd`` never raises on a non-zero exit; it returns the exit code and
      captured streams so the caller can record them in a receipt. It *does*
      propagate ``subprocess.TimeoutExpired`` and ``FileNotFoundError``, which
      are programming or environment errors rather than command results.
    - ``acquire_lock`` returns ``False`` when another tick holds the lock. Locks
      older than ``config.LOCK_STALE_SECONDS`` are reclaimed and the takeover is
      logged at WARNING.
    - ``release_lock`` logs at ERROR when the lock cannot be removed. It never
      raises, because it runs in a ``finally`` block where masking the original
      exception would lose the real failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from . import config
from .dotenv_helper import load_env

load_env()

_LOGGING_CONFIGURED = False


def configure_logging(*, verbose: bool = False) -> None:
    """Install the stderr and JSONL sinks. Idempotent across repeated calls."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "INFO")
    log_path = config.event_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path,
        level="DEBUG",
        serialize=True,
        rotation="20 MB",
        retention=10,
        enqueue=False,
    )
    _LOGGING_CONFIGURED = True


def ensure_dirs() -> None:
    config.log_dir().mkdir(parents=True, exist_ok=True)
    config.receipt_root().mkdir(parents=True, exist_ok=True)


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def log_event(run_id: str, message: str, **fields: Any) -> None:
    """Record one structured watchdog event."""
    logger.bind(run_id=run_id, **fields).info(message)


def run_cmd(
    command: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout_s: int = 120,
) -> dict[str, Any]:
    """Run one subprocess and return a receipt-shaped record of the result."""
    started = datetime.now(UTC)
    env = os.environ.copy()
    uv_parent = str(Path(config.resolve_uv_bin()).parent)
    env["PATH"] = f"{uv_parent}:{env.get('PATH', '')}"
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout_s,
        check=False,
    )
    return {
        "command": command,
        "cwd": str(cwd) if cwd else None,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
    }


def load_json(path: Path) -> dict[str, Any]:
    """Read a JSON object, rejecting any non-object root."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def acquire_lock(run_id: str) -> bool:
    """Take the single-tick lock, reclaiming it when the holder is stale."""
    lock = config.lock_dir()
    try:
        lock.mkdir(parents=True)
    except FileExistsError:
        if not _reclaim_stale_lock(run_id, lock):
            return False
        try:
            lock.mkdir(parents=True)
        except FileExistsError:
            logger.error("lock reclaim raced with another tick; backing off")
            return False
    (lock / "owner.json").write_text(
        json.dumps(
            {"run_id": run_id, "pid": os.getpid(), "ts": timestamp(), "epoch": time.time()},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return True


def _reclaim_stale_lock(run_id: str, lock: Path) -> bool:
    owner_path = lock / "owner.json"
    try:
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
        age = time.time() - float(owner.get("epoch", 0.0))
    except (OSError, ValueError, TypeError) as exc:
        logger.error("unreadable lock owner file {}: {}", owner_path, exc)
        age = float("inf")
        owner = {}
    if age < config.LOCK_STALE_SECONDS:
        return False
    logger.warning(
        "reclaiming stale watchdog lock held by run_id={} pid={} age_s={:.0f}",
        owner.get("run_id"),
        owner.get("pid"),
        age,
    )
    log_event(run_id, "stale_lock_reclaimed", previous_run_id=owner.get("run_id"), age_seconds=age)
    _remove_lock(lock)
    return True


def release_lock() -> None:
    """Drop the tick lock. Logs and swallows errors; never masks a live exception."""
    _remove_lock(config.lock_dir())


def _remove_lock(lock: Path) -> None:
    try:
        (lock / "owner.json").unlink(missing_ok=True)
        lock.rmdir()
    except FileNotFoundError:
        logger.debug("lock directory already gone: {}", lock)
    except OSError as exc:
        logger.error("failed to release watchdog lock {}: {}", lock, exc)


def base_receipt(run_id: str, receipt_dir: Path, apply: bool) -> dict[str, Any]:
    return {
        "schema": "agent_skills.project_watchdog.tick_receipt.v1",
        "run_id": run_id,
        "mocked": False,
        "live": True,
        "apply": apply,
        "receipt_dir": str(receipt_dir),
        "log_file": str(config.event_log_path()),
        "cron_log_file": str(config.cron_log_path()),
        "handled_issues": [],
        "errors": [],
    }


#: Statuses whose receipts carry no evidence worth keeping on disk. Writing one
#: directory per minute for these produced 41,682 dirs / 329 MB by 2026-07-27.
UNEVENTFUL_STATUSES = frozenset({"NOOP", "SKIPPED"})


def finish(
    run_id: str,
    receipt_dir: Path,
    receipt: dict[str, Any],
    exit_code: int,
    *,
    persist: bool | None = None,
) -> int:
    """Emit the receipt to stdout, optionally persist it, and return ``exit_code``.

    Uneventful ticks (``NOOP``/``SKIPPED``) are not persisted by default: they
    carry no evidence, and one directory per minute is pure disk churn. The
    receipt is still printed and still logged.
    """
    if persist is None:
        persist = receipt.get("status") not in UNEVENTFUL_STATUSES
    if persist:
        receipt_path = receipt_dir / "receipt.json"
        receipt["receipt_path"] = str(receipt_path)
        write_json(receipt_path, receipt)
    else:
        receipt["receipt_path"] = None
        receipt["receipt_persisted"] = False
        _discard_empty_dir(receipt_dir)
    log_event(
        run_id,
        "tick_finish",
        status=receipt.get("status"),
        ok=receipt.get("ok"),
        receipt_path=receipt.get("receipt_path"),
        exit_code=exit_code,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return exit_code


def _discard_empty_dir(path: Path) -> None:
    try:
        path.rmdir()
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.debug("receipt dir not empty, keeping {}: {}", path, exc)
