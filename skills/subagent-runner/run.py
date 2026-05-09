"""Typer CLI for /subagent-runner."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import typer

try:
    from .models import EventKind, InterventionSource, SessionEvent, SessionSpec, SessionState, SessionStatus
    from .pty_runtime import launch_subprocess, session_store_for_dir, signal_process_group
    from .result_watcher import attach_transcript, monitor_subprocess
    from .session_store import SessionStore
except ImportError:
    from models import EventKind, InterventionSource, SessionEvent, SessionSpec, SessionState, SessionStatus
    from pty_runtime import launch_subprocess, session_store_for_dir, signal_process_group
    from result_watcher import attach_transcript, monitor_subprocess
    from session_store import SessionStore

app = typer.Typer(add_completion=False)


@app.command()
def start(
    spec_file: str = typer.Argument(..., help="Path to SessionSpec JSON"),
) -> None:
    spec = SessionSpec.model_validate(json.loads(Path(spec_file).read_text()))
    store = SessionStore(spec.output_dir)
    state = store.create_session(spec)
    store.append_event(SessionEvent(
        session_id=state.session_id,
        task_id=state.task_id,
        ts=state.updated_at,
        kind=EventKind.session_created,
        status=state.status,
        source=InterventionSource.controller,
        payload={"backend": spec.backend, "cwd": spec.cwd},
    ))

    watcher = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "watch", state.artifact_dir],
        cwd=spec.cwd,
        env={**os.environ, **spec.env},
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=False,
    )
    state = store.patch_state(state, status=SessionStatus.starting, watcher_pid=watcher.pid)
    print(json.dumps({
        "session_id": state.session_id,
        "status": state.status.value,
        "artifact_dir": state.artifact_dir,
        "watcher_pid": watcher.pid,
    }, indent=2))


@app.command(hidden=True)
def watch(
    session_dir: str = typer.Argument(..., help="Session directory"),
) -> None:
    store = session_store_for_dir(session_dir)
    state = store.load_status(session_dir)
    spec = store.load_spec(session_dir)
    state = store.patch_state(state, status=SessionStatus.starting, watcher_pid=os.getpid())
    process, master_fd, state = launch_subprocess(spec, store, state)
    monitor_subprocess(store, state, spec, process, master_fd)


@app.command()
def status(
    session_dir: str = typer.Argument(..., help="Session directory or id"),
) -> None:
    store = session_store_for_dir(session_dir)
    state = store.load_status(session_dir)
    print(state.model_dump_json(indent=2))


@app.command("send-input")
def send_input_command(
    session_dir: str = typer.Argument(..., help="Session directory or id"),
    text: str = typer.Argument(..., help="Input to send to the session"),
    newline: bool = typer.Option(True, "--newline/--no-newline", help="Append newline"),
    source: InterventionSource = typer.Option(InterventionSource.controller, "--source", case_sensitive=False),
) -> None:
    store = session_store_for_dir(session_dir)
    state = store.load_status(session_dir)
    commands_path = Path(store.paths(state.session_id).commands_file)
    with commands_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"action": "input", "text": text, "newline": newline}))
        handle.write("\n")
    state = store.patch_state(state, intervention_state="input_sent")
    store.append_event(SessionEvent(
        session_id=state.session_id,
        task_id=state.task_id,
        ts=state.updated_at,
        kind=EventKind.input_sent,
        status=state.status,
        source=source,
        payload={"bytes": len(text.encode("utf-8", errors="replace")), "preview": text[:120]},
    ))
    print(state.model_dump_json(indent=2))


@app.command()
def attach(
    session_dir: str = typer.Argument(..., help="Session directory or id"),
    follow: bool = typer.Option(True, "--follow/--no-follow", help="Follow transcript output"),
    lines: int = typer.Option(200, "--lines", min=0, help="Tail this many lines before following"),
    source: InterventionSource = typer.Option(InterventionSource.controller, "--source", case_sensitive=False),
) -> None:
    store = session_store_for_dir(session_dir)
    state = store.load_status(session_dir)
    session_path = store.resolve_session_dir(session_dir)
    store.append_event(SessionEvent(
        session_id=state.session_id,
        task_id=state.task_id,
        ts=time.time(),
        kind=EventKind.session_attached,
        status=state.status,
        source=source,
        payload={"follow": follow, "lines": lines},
    ))
    attach_transcript(session_path, follow=follow, lines=lines)


@app.command()
def pause(
    session_dir: str = typer.Argument(..., help="Session directory or id"),
    source: InterventionSource = typer.Option(InterventionSource.controller, "--source", case_sensitive=False),
) -> None:
    store = session_store_for_dir(session_dir)
    state = store.load_status(session_dir)
    signal_process_group(state, signal.SIGSTOP)
    state = store.patch_state(state, status=SessionStatus.paused, intervention_state="paused")
    store.append_event(SessionEvent(
        session_id=state.session_id,
        task_id=state.task_id,
        ts=state.updated_at,
        kind=EventKind.session_paused,
        status=state.status,
        source=source,
        payload={},
    ))
    print(state.model_dump_json(indent=2))


@app.command()
def resume(
    session_dir: str = typer.Argument(..., help="Session directory or id"),
    source: InterventionSource = typer.Option(InterventionSource.controller, "--source", case_sensitive=False),
) -> None:
    store = session_store_for_dir(session_dir)
    state = store.load_status(session_dir)
    signal_process_group(state, signal.SIGCONT)
    state = store.patch_state(state, status=SessionStatus.running, intervention_state="resumed")
    store.append_event(SessionEvent(
        session_id=state.session_id,
        task_id=state.task_id,
        ts=state.updated_at,
        kind=EventKind.session_resumed,
        status=state.status,
        source=source,
        payload={},
    ))
    print(state.model_dump_json(indent=2))


@app.command()
def cancel(
    session_dir: str = typer.Argument(..., help="Session directory or id"),
    source: InterventionSource = typer.Option(InterventionSource.controller, "--source", case_sensitive=False),
) -> None:
    store = session_store_for_dir(session_dir)
    state = store.load_status(session_dir)
    signal_process_group(state, signal.SIGTERM)
    state = store.patch_state(state, intervention_state="cancel_requested")
    store.append_event(SessionEvent(
        session_id=state.session_id,
        task_id=state.task_id,
        ts=state.updated_at,
        kind=EventKind.session_cancelled,
        status=state.status,
        source=source,
        payload={"requested": True},
    ))
    print(state.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
