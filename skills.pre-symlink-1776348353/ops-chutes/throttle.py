"""Cross-process concurrency semaphore for Chutes.ai via fcntl.flock.

Uses 5 slot files at ~/.pi/ops-chutes/semaphore/slot_{0..4}.
Lock auto-releases on process crash (fd closes). Visible with lsof.
Same pattern as Stream Deck's DeckWriter for atomic config mutation.

Inputs: max_slots (int), timeout (float seconds).
Outputs: slot index (int) on acquire; nothing on release.
Failure modes: TimeoutError if all slots held past timeout; OSError on fs issues.
"""
from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path

from loguru import logger


SEMAPHORE_DIR = Path.home() / ".pi" / "ops-chutes" / "semaphore"
DEFAULT_MAX_SLOTS = 5
DEFAULT_TIMEOUT = 90.0  # Matches Chutes 429 recovery period
POLL_INTERVAL = 0.5


class ChutesSemaphore:
    """Cross-process semaphore via fcntl.flock on slot files.

    Usage as context manager (Python callers):
        with ChutesSemaphore() as slot:
            print(f"Acquired slot {slot}")
            # ... make Chutes API calls ...

    Usage from CLI:
        slot = ChutesSemaphore()
        slot_id = slot.acquire()
        # ... do work ...
        slot.release()
    """

    def __init__(self, max_slots: int = DEFAULT_MAX_SLOTS, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.max_slots = max_slots
        self.timeout = timeout
        self._fd: int | None = None
        self._slot_id: int | None = None

        # Ensure slot files exist
        SEMAPHORE_DIR.mkdir(parents=True, exist_ok=True)
        for i in range(max_slots):
            slot_path = SEMAPHORE_DIR / f"slot_{i}"
            if not slot_path.exists():
                slot_path.touch()

    def acquire(self) -> int:
        """Try each slot with LOCK_EX|LOCK_NB. Poll every 0.5s until timeout.

        Returns the slot index acquired. Prints slot index to stdout for bash callers.
        Raises TimeoutError if no slot becomes available within timeout.
        """
        deadline = time.monotonic() + self.timeout

        while True:
            for i in range(self.max_slots):
                slot_path = SEMAPHORE_DIR / f"slot_{i}"
                try:
                    fd = os.open(str(slot_path), os.O_RDWR)
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        # Write PID for debugging
                        os.ftruncate(fd, 0)
                        os.lseek(fd, 0, os.SEEK_SET)
                        os.write(fd, f"{os.getpid()}\n".encode())
                        self._fd = fd
                        self._slot_id = i
                        logger.debug("Acquired semaphore slot {} (pid={})", i, os.getpid())
                        return i
                    except OSError:
                        # Slot already locked by another process
                        os.close(fd)
                        continue
                except OSError:
                    continue

            if time.monotonic() >= deadline:
                logger.warning("Semaphore timeout after {}s — all {} slots in use", self.timeout, self.max_slots)
                raise TimeoutError(
                    f"Could not acquire Chutes semaphore slot within {self.timeout}s "
                    f"(all {self.max_slots} slots in use)"
                )

            time.sleep(POLL_INTERVAL)

    def release(self) -> None:
        """Release the acquired slot (LOCK_UN + close fd)."""
        if self._fd is not None:
            slot = self._slot_id
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            self._slot_id = None
            logger.debug("Released semaphore slot {}", slot)

    def __enter__(self) -> int:
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    @classmethod
    def slots_in_use(cls, max_slots: int = DEFAULT_MAX_SLOTS) -> int:
        """Probe all slot files to count how many are locked.

        Non-destructive: acquires then immediately releases test locks.
        """
        SEMAPHORE_DIR.mkdir(parents=True, exist_ok=True)
        in_use = 0
        for i in range(max_slots):
            slot_path = SEMAPHORE_DIR / f"slot_{i}"
            if not slot_path.exists():
                continue
            try:
                fd = os.open(str(slot_path), os.O_RDONLY)
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    # We got the lock, so it wasn't in use — release immediately
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    # Lock held by another process
                    in_use += 1
                finally:
                    os.close(fd)
            except OSError:
                pass
        return in_use
