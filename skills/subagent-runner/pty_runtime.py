"""PTY subprocess lifecycle helpers for /subagent-runner."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

try:
    from .models import EventKind, InterventionSource, SessionEvent, SessionSpec, SessionState, SessionStatus
    from .session_store import SessionStore
except ImportError:
    from models import EventKind, InterventionSource, SessionEvent, SessionSpec, SessionState, SessionStatus
    from session_store import SessionStore

DEFAULT_BACKEND_COMMANDS: dict[str, list[str]] = {
    "codex": ["codex"],
    "claude": ["claude"],
    "gemini": ["gemini"],
    "deepseek": ["deepseek"],
}


def resolve_command(spec: SessionSpec) -> list[str]:
    if spec.command:
        return spec.command
    return list(DEFAULT_BACKEND_COMMANDS[spec.backend])


def write_master(master_fd: int, text: str, *, append_newline: bool = True) -> None:
    payload = text + ("\n" if append_newline else "")
    os.write(master_fd, payload.encode("utf-8", errors="replace"))


def launch_subprocess(spec: SessionSpec, store: SessionStore, state: SessionState) -> tuple[subprocess.Popen[bytes], int, SessionState]:
    master_fd, slave_fd = os.openpty()
    slave_name = os.ttyname(slave_fd)
    command = resolve_command(spec)
    env = os.environ.copy()
    env.update(spec.env)
    env["SUBAGENT_RUNNER_SESSION_DIR"] = state.artifact_dir
    env["SUBAGENT_RUNNER_TASK_ID"] = state.task_id

    process = subprocess.Popen(
        command,
        cwd=spec.cwd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        text=False,
        close_fds=True,
        start_new_session=True,
    )
    os.close(slave_fd)

    state = store.patch_state(
        state,
        status=SessionStatus.running,
        pid=process.pid,
        pty_device=slave_name,
        command=command,
        intervention_state="idle",
    )
    store.append_event(SessionEvent(
        session_id=state.session_id,
        task_id=state.task_id,
        ts=state.updated_at,
        kind=EventKind.session_started,
        status=state.status,
        source=InterventionSource.controller,
        payload={"pid": process.pid, "command": command, "pty_device": slave_name},
    ))

    if spec.prompt.strip():
        write_master(master_fd, spec.prompt, append_newline=True)

    return process, master_fd, state


def send_input(state: SessionState, text: str, *, append_newline: bool = True) -> None:
    raise RuntimeError("direct send_input is not available outside the watcher process")


def signal_process_group(state: SessionState, sig: int) -> None:
    if state.pid is None:
        raise RuntimeError("session has no child pid")
    os.killpg(state.pid, sig)


def terminate_process_group(state: SessionState, *, grace_seconds: float = 5.0) -> None:
    signal_process_group(state, signal.SIGTERM)
    try:
        os.killpg(state.pid, 0)
    except OSError:
        return

    deadline = time.time() + grace_seconds
    while time.time() < deadline:
        try:
            os.killpg(state.pid, 0)
        except OSError:
            return
        time.sleep(0.2)
    signal_process_group(state, signal.SIGKILL)


def session_store_for_dir(session_dir: str | Path) -> SessionStore:
    return SessionStore(Path(session_dir).resolve().parent)
