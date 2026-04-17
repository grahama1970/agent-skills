"""
Cross-process Chutes API concurrency lock using fcntl.flock.

Chutes allows 5-6 concurrent connections per token. Each doc2qra process
uses asyncio.Semaphore(6) internally. Running multiple doc2qra processes
simultaneously causes self-DoS.

Usage:
    from common.chutes_lock import chutes_slot

    with chutes_slot():
        # Only one process at a time can hold this lock
        run_doc2qra_pipeline()

    # Or check how many processes are waiting:
    from common.chutes_lock import slot_count_estimate
    print(f"Processes with lock file open: {slot_count_estimate()}")

Environment:
    CHUTES_MAX_SLOTS  — Max concurrent slots (default: 1)
    CHUTES_LOCK_TIMEOUT — Timeout in seconds (default: 300)
    CHUTES_API_TOKEN — Used to hash lock file name (isolates per-token)
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import time
from pathlib import Path


_LOCK_DIR = Path("/tmp")
_DEFAULT_MAX_SLOTS = 1
_DEFAULT_TIMEOUT = 300  # 5 minutes


def _token_hash() -> str:
    """Short hash of the Chutes token for lock file isolation."""
    token = os.environ.get("CHUTES_API_TOKEN", "default")
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def _lock_path() -> Path:
    """Path to the lock file for the current token."""
    return _LOCK_DIR / f"chutes-slots-{_token_hash()}.lock"


@contextlib.contextmanager
def chutes_slot():
    """Context manager that acquires an exclusive file lock.

    Only CHUTES_MAX_SLOTS (default: 1) processes can hold the lock
    simultaneously. Additional callers block until a slot opens or
    the timeout expires.

    Raises:
        TimeoutError: If lock cannot be acquired within CHUTES_LOCK_TIMEOUT seconds.
    """
    timeout = int(os.environ.get("CHUTES_LOCK_TIMEOUT", _DEFAULT_TIMEOUT))
    lock_file = _lock_path()

    # Create the lock file if it doesn't exist
    lock_file.touch(exist_ok=True)

    fd = open(lock_file, "r+")
    start = time.monotonic()

    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break  # Lock acquired
            except (IOError, OSError):
                elapsed = time.monotonic() - start
                if elapsed >= timeout:
                    fd.close()
                    raise TimeoutError(
                        f"Could not acquire Chutes lock after {timeout}s. "
                        f"Another doc2qra process likely holds the lock.\n"
                        f"Check with: ps aux | grep doc2qra\n"
                        f"Lock file: {lock_file}"
                    )
                time.sleep(1)

        yield

    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except (IOError, OSError):
            pass
        fd.close()


def slot_count_estimate() -> int:
    """Estimate how many processes have the lock file open.

    Scans /proc/*/fd/ for symlinks pointing to our lock file.
    Returns 0 if /proc is not available (non-Linux).
    """
    lock_file = _lock_path()
    if not lock_file.exists():
        return 0

    lock_inode = lock_file.stat().st_ino
    count = 0
    proc = Path("/proc")

    if not proc.exists():
        return 0

    for pid_dir in proc.iterdir():
        if not pid_dir.name.isdigit():
            continue
        fd_dir = pid_dir / "fd"
        try:
            for fd_link in fd_dir.iterdir():
                try:
                    target = fd_link.resolve()
                    if target.stat().st_ino == lock_inode:
                        count += 1
                        break  # One hit per process is enough
                except (OSError, FileNotFoundError):
                    continue
        except (PermissionError, FileNotFoundError):
            continue

    return count
