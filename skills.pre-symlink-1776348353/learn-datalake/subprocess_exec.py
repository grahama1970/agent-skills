"""Subprocess execution with watchdog monitoring for learn-datalake.

Purpose:
- Run shell commands with timeout and stall detection.
- Pump stdout/stderr asynchronously with output buffering.

Inputs:
- Shell command strings, timeout/watchdog parameters.

Outputs:
- CommandResult with captured output, timing, and failure flags.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from queue import Empty, Queue
from typing import Any, Callable, Dict, List, Optional

import typer
from loguru import logger

from config import CommandResult


def run(cmd: str, timeout: int = 7200) -> subprocess.CompletedProcess[str]:
    """Run a shell command via bash with timeout."""
    return subprocess.run(
        ["bash", "-lc", cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def terminate_process(proc: subprocess.Popen[str]) -> None:
    """Gracefully terminate a subprocess and its entire process group.

    Uses os.killpg to ensure all child processes (extractors, etc.) are
    killed — not just the immediate bash shell. This prevents orphaned
    grandchild processes from accumulating across supervisor restarts.
    """
    if proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        proc.wait(timeout=5)


def run_with_watchdog(
    cmd: str,
    *,
    timeout: int,
    watchdog_seconds: int,
    watchdog_poll_seconds: int,
    stream_stdout: bool = False,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> CommandResult:
    """Run a command with watchdog stall detection and optional stdout streaming.

    The watchdog terminates the process if no output is seen for watchdog_seconds.
    Hard timeout kills unconditionally after timeout seconds.
    """
    max_buffer_lines = 4000
    start = time.monotonic()
    proc = subprocess.Popen(
        ["bash", "-lc", cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,  # own process group so killpg cleans all children
    )
    queue: Queue[tuple[str, str]] = Queue()

    def pump(stream: Any, channel: str) -> None:
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                queue.put((channel, line))
        finally:
            try:
                stream.close()
            except OSError:
                logger.debug(f"stream_close_error channel={channel}")

    t_out = threading.Thread(target=pump, args=(proc.stdout, "stdout"), daemon=True)
    t_err = threading.Thread(target=pump, args=(proc.stderr, "stderr"), daemon=True)
    t_out.start()
    t_err.start()

    stdout_lines: List[str] = []
    stderr_lines: List[str] = []
    last_output = time.monotonic()
    last_report = 0.0
    last_heartbeat_print = 0.0
    timed_out = False
    stalled = False

    while True:
        now = time.monotonic()
        if now - start > timeout and proc.poll() is None:
            timed_out = True
            terminate_process(proc)
        elif watchdog_seconds > 0 and now - last_output > watchdog_seconds and proc.poll() is None:
            stalled = True
            terminate_process(proc)

        if progress_callback and now - last_report >= max(1, watchdog_poll_seconds):
            progress_callback(
                {
                    "elapsed_seconds": now - start,
                    "last_output_age_seconds": now - last_output,
                    "stdout_tail": "".join(stdout_lines[-20:]),
                    "stderr_tail": "".join(stderr_lines[-20:]),
                    "returncode": proc.poll(),
                }
            )
            last_report = now

        if stream_stdout and now - last_heartbeat_print >= max(30, watchdog_poll_seconds * 4):
            print(
                (
                    "[watchdog] running "
                    f"elapsed={int(now - start)}s "
                    f"last_output_age={int(now - last_output)}s "
                    f"cmd={cmd}"
                ),
                flush=True,
            )
            last_heartbeat_print = now

        if proc.poll() is not None and queue.empty():
            break

        try:
            channel, line = queue.get(timeout=max(1, watchdog_poll_seconds))
            last_output = time.monotonic()
            if channel == "stdout":
                stdout_lines.append(line)
                if len(stdout_lines) > max_buffer_lines:
                    del stdout_lines[: len(stdout_lines) - max_buffer_lines]
                if stream_stdout:
                    print(line, end="", flush=True)
            else:
                stderr_lines.append(line)
                if len(stderr_lines) > max_buffer_lines:
                    del stderr_lines[: len(stderr_lines) - max_buffer_lines]
        except Empty:
            continue

    t_out.join(timeout=1)
    t_err.join(timeout=1)

    if timed_out:
        stderr_lines.append(
            f"[watchdog] hard-timeout exceeded after {timeout}s for command: {cmd}\n"
        )
    if stalled:
        stderr_lines.append(
            f"[watchdog] no output for {watchdog_seconds}s; command terminated: {cmd}\n"
        )

    elapsed = time.monotonic() - start
    return CommandResult(
        cmd=cmd,
        returncode=proc.returncode if proc.returncode is not None else 1,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
        timed_out=timed_out,
        stalled=stalled,
        elapsed_seconds=elapsed,
    )


def ensure_not_stalled(result: CommandResult, label: str) -> None:
    """Raise typer.Exit(2) if a command result indicates stall or timeout."""
    if result.stalled or result.timed_out:
        logger.error(
            f"{label} watchdog failure rc={result.returncode} "
            f"stalled={result.stalled} timed_out={result.timed_out}"
        )
        if result.returncode != 0 and result.stderr.strip():
            logger.error(result.stderr.splitlines()[-1])
        raise typer.Exit(code=2)
