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
    - ``run_cmd`` never raises on a non-zero exit or timeout; it returns the
      exit code and captured streams so the caller can record them in a receipt.
      It *does* propagate ``FileNotFoundError``, which is a programming or
      environment error rather than a command result.
    - ``acquire_lock`` returns ``False`` when another tick holds the lock. Locks
      older than ``config.LOCK_STALE_SECONDS`` are reclaimed and the takeover is
      logged at WARNING.
    - ``release_lock`` logs at ERROR when the lock cannot be removed. It never
      raises, because it runs in a ``finally`` block where masking the original
      exception would lose the real failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
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
    proc = subprocess.Popen(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdin=subprocess.PIPE if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(input=input_text, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        descendants = _process_descendants(proc.pid)
        stdout, stderr, cleanup = _terminate_process_group(
            proc,
            timeout_s=timeout_s,
            descendants=descendants,
        )
        return {
            "command": command,
            "cwd": str(cwd) if cwd else None,
            "exit_code": 124,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
            "timed_out": True,
            "timeout_seconds": timeout_s,
            "process_group": {
                "pid": proc.pid,
                "pgid": proc.pid,
                "descendants_before_kill": descendants,
                **cleanup,
            },
        }
    return {
        "command": command,
        "cwd": str(cwd) if cwd else None,
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "duration_seconds": (datetime.now(UTC) - started).total_seconds(),
    }


def _terminate_process_group(
    proc: subprocess.Popen[str],
    *,
    timeout_s: int,
    descendants: list[dict[str, Any]] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Terminate the command's whole process group after a timeout."""
    cleanup: dict[str, Any] = {
        "terminated": False,
        "kill_sent": False,
        "termination_signal": "SIGTERM",
    }
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        cleanup["terminated"] = True
    except ProcessLookupError:
        pass
    except OSError as exc:
        cleanup["termination_error"] = str(exc)
    try:
        stdout, stderr = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        cleanup["descendant_cleanup_after_term"] = _terminate_recorded_descendants(descendants or [])
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            cleanup["kill_sent"] = True
        except ProcessLookupError:
            pass
        except OSError as exc:
            cleanup["kill_error"] = str(exc)
        cleanup["descendant_cleanup_after_kill"] = _terminate_recorded_descendants(descendants or [])
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            cleanup["communicate_after_kill_timeout"] = True
            stdout, stderr = "", ""
    cleanup["descendant_cleanup"] = _terminate_recorded_descendants(descendants or [])
    cleanup["return_code_after_timeout"] = proc.returncode
    cleanup["timeout_seconds"] = timeout_s
    return stdout or "", stderr or "", cleanup


def _pid_cmdline(pid: int) -> str | None:
    try:
        return (
            (Path("/proc") / str(pid) / "cmdline")
            .read_bytes()
            .replace(b"\0", b" ")
            .decode(errors="replace")
            .strip()
        )
    except OSError:
        return None


def _terminate_recorded_descendants(descendants: list[dict[str, Any]]) -> dict[str, Any]:
    """Terminate timeout descendants that escaped the launched process group."""
    cleanup: dict[str, Any] = {
        "checked": [],
        "term_sent": [],
        "kill_sent": [],
        "still_alive": [],
    }
    recorded: list[tuple[int, str]] = []
    for item in descendants:
        try:
            pid = int(item.get("pid"))
        except (TypeError, ValueError):
            continue
        cmdline = str(item.get("cmdline") or "")
        recorded.append((pid, cmdline))

    for pid, expected_cmdline in recorded:
        current_cmdline = _pid_cmdline(pid)
        cleanup["checked"].append({"pid": pid, "cmdline": current_cmdline})
        if current_cmdline is None:
            continue
        if expected_cmdline and current_cmdline != expected_cmdline:
            cleanup.setdefault("skipped_cmdline_mismatch", []).append(
                {
                    "pid": pid,
                    "expected": expected_cmdline,
                    "actual": current_cmdline,
                }
            )
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            cleanup["term_sent"].append(pid)
        except ProcessLookupError:
            continue
        except OSError as exc:
            cleanup.setdefault("term_errors", []).append({"pid": pid, "error": str(exc)})

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not any(_pid_cmdline(pid) is not None for pid, _ in recorded):
            break
        time.sleep(0.05)

    for pid, expected_cmdline in recorded:
        current_cmdline = _pid_cmdline(pid)
        if current_cmdline is None:
            continue
        if expected_cmdline and current_cmdline != expected_cmdline:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            cleanup["kill_sent"].append(pid)
        except ProcessLookupError:
            continue
        except OSError as exc:
            cleanup.setdefault("kill_errors", []).append({"pid": pid, "error": str(exc)})

    time.sleep(0.05)
    for pid, _ in recorded:
        current_cmdline = _pid_cmdline(pid)
        if current_cmdline is not None:
            cleanup["still_alive"].append({"pid": pid, "cmdline": current_cmdline})
    cleanup["ok"] = not cleanup["still_alive"]
    return cleanup


def _process_descendants(root_pid: int) -> list[dict[str, Any]]:
    """Best-effort snapshot of descendants before timeout cleanup."""
    children: dict[int, list[int]] = {}
    commands: dict[int, str] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            rparen = stat.rfind(")")
            ppid = int(stat[rparen + 2 :].split()[1])
            cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                errors="replace"
            ).strip()
        except (OSError, ValueError, IndexError):
            continue
        children.setdefault(ppid, []).append(pid)
        commands[pid] = cmdline or stat[:120]

    found: list[dict[str, Any]] = []
    stack = list(children.get(root_pid, []))
    seen: set[int] = set()
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        found.append({"pid": pid, "cmdline": commands.get(pid, "")})
        stack.extend(children.get(pid, []))
    return sorted(found, key=lambda item: int(item["pid"]))


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
    return _acquire_dir_lock(config.lock_dir(), run_id, {})


def execution_lock_key(targets: set[str] | list[str] | tuple[str, ...]) -> str:
    """Stable filesystem-safe key for one target set."""
    normalized = sorted({str(target).strip().rstrip("/") for target in targets if str(target).strip()})
    if not normalized:
        normalized = ["__unknown__"]
    digest = hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()[:16]
    label = normalized[0].replace("/", "_").replace(":", "_")[:80]
    return f"{label}-{digest}"


def acquire_execution_lock(run_id: str, targets: set[str] | list[str] | tuple[str, ...]) -> Path | None:
    """Take a per-target execution lock for a selected repair lane."""
    key = execution_lock_key(targets)
    lock = config.execution_lock_root() / key
    normalized = sorted({str(target).strip().rstrip("/") for target in targets if str(target).strip()})
    if _acquire_dir_lock(lock, run_id, {"targets": normalized, "kind": "execution"}):
        return lock
    return None


def release_execution_lock(lock: Path | None) -> None:
    if lock is not None:
        _remove_lock(lock)


def execution_lock_holder_alive(lock: Path) -> bool:
    owner_path = lock / "owner.json"
    try:
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        logger.error("could not read execution lock owner: {}", exc)
        return False
    return _owner_pid_alive(owner)


def _acquire_dir_lock(lock: Path, run_id: str, extra_owner_fields: dict[str, Any]) -> bool:
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
            {
                "run_id": run_id,
                "pid": os.getpid(),
                "ts": timestamp(),
                "epoch": time.time(),
                **extra_owner_fields,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return True


def lock_holder_alive() -> bool:
    """Whether a live process currently holds the tick lock.

    A tick that steps aside for another tick that is genuinely working is not a
    failure. Reporting it as one made every minute of a multi-minute audit log
    BLOCKED and exit 1, so a healthy long-running lane looked like a broken one.
    """
    owner_path = config.lock_dir() / "owner.json"
    try:
        owner = json.loads(owner_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        logger.error("could not read lock owner: {}", exc)
        return False
    return _owner_pid_alive(owner)


def _owner_pid_alive(owner: dict[str, Any]) -> bool:
    try:
        pid = int(owner.get("pid", 0))
    except (ValueError, TypeError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
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
    if _owner_pid_alive(owner):
        logger.warning(
            "watchdog lock held by live pid={} exceeded stale age_s={:.0f}; refusing takeover",
            owner.get("pid"),
            age,
        )
        log_event(
            run_id,
            "stale_lock_owner_still_alive",
            previous_run_id=owner.get("run_id"),
            pid=owner.get("pid"),
            age_seconds=age,
        )
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
