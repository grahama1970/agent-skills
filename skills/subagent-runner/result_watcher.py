"""Session watcher and transcript follower for /subagent-runner."""
from __future__ import annotations

import errno
import json
import os
import select
import time
from pathlib import Path

try:
    from .models import EventKind, InterventionSource, SessionEvent, SessionResult, SessionSpec, SessionState, SessionStatus
    from .pty_runtime import terminate_process_group, write_master
    from .session_store import SessionStore
except ImportError:
    from models import EventKind, InterventionSource, SessionEvent, SessionResult, SessionSpec, SessionState, SessionStatus
    from pty_runtime import terminate_process_group, write_master
    from session_store import SessionStore

TERMINAL_STATUSES = {
    SessionStatus.completed,
    SessionStatus.failed,
    SessionStatus.cancelled,
    SessionStatus.timed_out,
    SessionStatus.stalled,
}

_EVENT_KIND_BY_STATUS = {
    SessionStatus.completed: EventKind.session_completed,
    SessionStatus.failed: EventKind.session_failed,
    SessionStatus.cancelled: EventKind.session_cancelled,
    SessionStatus.timed_out: EventKind.session_timed_out,
    SessionStatus.stalled: EventKind.session_stalled,
}


def append_output(store: SessionStore, state: SessionState, data: bytes) -> SessionState:
    paths = store.paths(state.session_id)
    text = data.decode("utf-8", errors="replace")
    for file_path in [paths.transcript_file, paths.stdout_file]:
        with Path(file_path).open("a", encoding="utf-8") as handle:
            handle.write(text)
    updated = store.patch_state(state, last_output_at=time.time())
    store.append_event(SessionEvent(
        session_id=updated.session_id,
        task_id=updated.task_id,
        ts=updated.updated_at,
        kind=EventKind.transcript_delta,
        status=updated.status,
        source=InterventionSource.controller,
        payload={
            "bytes": len(data),
            "transcript_bytes": Path(paths.transcript_file).stat().st_size,
        },
    ))
    return updated


def _idle_mode(spec: SessionSpec) -> str:
    return spec.env.get("SUBAGENT_RUNNER_IDLE_MODE", "stall").strip().lower()


def _heartbeat_interval(spec: SessionSpec) -> float:
    raw = spec.env.get("SUBAGENT_RUNNER_HEARTBEAT_INTERVAL", "30")
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 30.0


def append_heartbeat(
    store: SessionStore,
    state: SessionState,
    *,
    process,
    idle_for_seconds: float,
) -> None:
    store.append_event(SessionEvent(
        session_id=state.session_id,
        task_id=state.task_id,
        ts=time.time(),
        kind=EventKind.session_heartbeat,
        status=state.status,
        source=InterventionSource.watchdog,
        payload={
            "pid": state.pid,
            "process_alive": process.poll() is None,
            "idle_for_seconds": round(idle_for_seconds, 3),
        },
    ))


def finalize_session(
    store: SessionStore,
    state: SessionState,
    *,
    spec: SessionSpec | None = None,
    status: SessionStatus,
    exit_code: int | None,
    summary: str,
    source: InterventionSource,
) -> SessionState:
    finished_at = time.time()
    state = store.patch_state(
        state,
        status=status,
        exit_code=exit_code,
        finished_at=finished_at,
        intervention_state="idle" if status in TERMINAL_STATUSES else state.intervention_state,
        status_reason=summary,
    )
    final_message = extract_final_message(store, state, spec)
    store.append_event(SessionEvent(
        session_id=state.session_id,
        task_id=state.task_id,
        ts=finished_at,
        kind=_EVENT_KIND_BY_STATUS[status],
        status=status,
        source=source,
        payload={
            "exit_code": exit_code,
            "summary": summary,
            "final_message_status": final_message["status"],
            "final_message_source": final_message["source"],
        },
    ))
    duration = finished_at - state.started_at
    store.write_result(SessionResult(
        session_id=state.session_id,
        task_id=state.task_id,
        backend=state.backend,
        status=status,
        exit_code=exit_code,
        started_at=state.started_at,
        finished_at=finished_at,
        duration_seconds=duration,
        artifact_dir=state.artifact_dir,
        summary=summary,
        final_message=final_message["message"],
        final_message_source=final_message["source"],
        final_message_status=final_message["status"],
        final_message_file=final_message["file"],
        final_message_warnings=final_message["warnings"],
    ))
    return state


def extract_final_message(
    store: SessionStore,
    state: SessionState,
    spec: SessionSpec | None,
) -> dict[str, object]:
    """Resolve the final agent message into the typed result artifact."""
    paths = store.paths(state.session_id)
    warnings: list[str] = []
    configured_path = _configured_final_message_file(spec)
    transcript = _read_text(Path(paths.transcript_file))
    if configured_path:
        raw = _read_text(configured_path).strip()
        if raw:
            if _looks_like_terminal_hook_output(raw):
                warnings.append("configured final-message file looked like terminal hook output")
                fallback = _extract_pre_hook_content(transcript).strip()
                if fallback:
                    return {
                        "message": fallback,
                        "source": "transcript_pre_hook",
                        "status": "degraded",
                        "file": str(configured_path),
                        "warnings": warnings,
                    }
                return {
                    "message": "",
                    "source": "configured_file",
                    "status": "polluted",
                    "file": str(configured_path),
                    "warnings": warnings,
                }
            return {
                "message": raw,
                "source": "configured_file",
                "status": "ok",
                "file": str(configured_path),
                "warnings": warnings,
            }
        warnings.append("configured final-message file was missing or empty")
    fallback = _extract_pre_hook_content(transcript).strip()
    if fallback:
        return {
            "message": fallback,
            "source": "transcript",
            "status": "degraded",
            "file": str(configured_path or ""),
            "warnings": warnings,
        }
    return {
        "message": "",
        "source": "",
        "status": "missing",
        "file": str(configured_path or ""),
        "warnings": warnings,
    }


def drain_command_queue(store: SessionStore, state: SessionState, master_fd: int, position: int) -> tuple[SessionState, int]:
    commands_path = Path(store.paths(state.session_id).commands_file)
    if not commands_path.exists():
        return state, position

    with commands_path.open("r", encoding="utf-8") as handle:
        handle.seek(position)
        for line in handle:
            record = json.loads(line)
            if record.get("action") == "input":
                write_master(
                    master_fd,
                    str(record.get("text", "")),
                    append_newline=bool(record.get("newline", True)),
                )
        return state, handle.tell()


def monitor_subprocess(
    store: SessionStore,
    state: SessionState,
    spec: SessionSpec,
    process,
    master_fd: int,
) -> SessionState:
    command_position = 0
    idle_mode = _idle_mode(spec)
    heartbeat_interval = _heartbeat_interval(spec)
    next_heartbeat_at = 0.0
    try:
        while True:
            current_state = store.load_status(state.artifact_dir)
            current_state, command_position = drain_command_queue(store, current_state, master_fd, command_position)
            now = time.time()
            if current_state.status not in TERMINAL_STATUSES:
                if now - current_state.started_at > spec.timeout_seconds:
                    terminate_process_group(current_state)
                    state = finalize_session(
                        store,
                        current_state,
                        spec=spec,
                        status=SessionStatus.timed_out,
                        exit_code=process.poll(),
                        summary=f"session exceeded timeout_seconds={spec.timeout_seconds}",
                        source=InterventionSource.watchdog,
                    )
                    break
                if current_state.status != SessionStatus.paused and current_state.last_output_at is not None:
                    idle_for_seconds = now - current_state.last_output_at
                    if idle_mode == "stall" and idle_for_seconds > spec.idle_timeout_seconds:
                        terminate_process_group(current_state)
                        state = finalize_session(
                            store,
                            current_state,
                            spec=spec,
                            status=SessionStatus.stalled,
                            exit_code=process.poll(),
                            summary=f"no transcript growth for {spec.idle_timeout_seconds}s",
                            source=InterventionSource.watchdog,
                        )
                        break
                    if idle_mode == "heartbeat" and now >= next_heartbeat_at:
                        append_heartbeat(
                            store,
                            current_state,
                            process=process,
                            idle_for_seconds=idle_for_seconds,
                        )
                        next_heartbeat_at = now + heartbeat_interval

            ready, _, _ = select.select([master_fd], [], [], 0.5)
            if ready:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    chunk = b""
                if chunk:
                    current_state = append_output(store, current_state, chunk)

            if process.poll() is not None:
                while True:
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        chunk = b""
                    if not chunk:
                        break
                    current_state = append_output(store, current_state, chunk)

                terminal_state = store.load_status(current_state.artifact_dir)
                exit_code = process.returncode
                if terminal_state.status in TERMINAL_STATUSES:
                    state = store.patch_state(terminal_state, exit_code=exit_code, finished_at=time.time())
                elif terminal_state.intervention_state == "cancel_requested":
                    state = finalize_session(
                        store,
                        terminal_state,
                        spec=spec,
                        status=SessionStatus.cancelled,
                        exit_code=exit_code,
                        summary="session cancelled by controller or human",
                        source=InterventionSource.controller,
                    )
                elif exit_code == 0:
                    state = finalize_session(
                        store,
                        terminal_state,
                        spec=spec,
                        status=SessionStatus.completed,
                        exit_code=exit_code,
                        summary="session completed successfully",
                        source=InterventionSource.controller,
                    )
                else:
                    state = finalize_session(
                        store,
                        terminal_state,
                        spec=spec,
                        status=SessionStatus.failed,
                        exit_code=exit_code,
                        summary=f"session exited with code {exit_code}",
                        source=InterventionSource.controller,
                    )
                break
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass
    return state


def _configured_final_message_file(spec: SessionSpec | None) -> Path | None:
    if spec is None:
        return None
    for key in ("SUBAGENT_RUNNER_FINAL_MESSAGE_FILE", "ASK_ORACLE_ANSWER_FILE"):
        value = spec.env.get(key, "").strip()
        if value:
            return Path(value)
    return None


def _read_text(path: Path) -> str:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return ""


def _looks_like_terminal_hook_output(content: str) -> bool:
    lowered = content.lower()
    return any(
        marker in lowered
        for marker in (
            "cdp verification",
            "ui cdp verification",
            ".codex/ui-verification",
            "no rendered ui target",
            "no real target url",
            "ui verification marker",
            "hook: stop",
            "hook script",
            "<target-url>",
        )
    )


def _extract_pre_hook_content(transcript: str) -> str:
    if not transcript:
        return ""
    hook_markers = ("\nhook: Stop", "\nHook: Stop", "\n[hook: Stop")
    hook_index = -1
    for marker in hook_markers:
        hook_index = transcript.find(marker)
        if hook_index >= 0:
            break
    before_hook = transcript[:hook_index].rstrip() if hook_index >= 0 else transcript.rstrip()
    marker_index = before_hook.rfind("\ncodex\n")
    if marker_index >= 0:
        return before_hook[marker_index + len("\ncodex\n"):].strip()
    return before_hook.strip()


def attach_transcript(session_dir: str | Path, *, follow: bool = True, lines: int = 200) -> None:
    session_dir = Path(session_dir)
    transcript = session_dir / "transcript.log"
    status_file = session_dir / "status.json"
    if transcript.exists():
        data = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
        snippet = data[-lines:] if lines > 0 else data
        if snippet:
            print("\n".join(snippet))
    if not follow:
        return

    last_size = transcript.stat().st_size if transcript.exists() else 0
    while True:
        if transcript.exists():
            current_size = transcript.stat().st_size
            if current_size > last_size:
                with transcript.open("r", encoding="utf-8", errors="replace") as handle:
                    handle.seek(last_size)
                    chunk = handle.read()
                    if chunk:
                        print(chunk, end="")
                last_size = current_size
        if status_file.exists():
            state = SessionState.model_validate_json(status_file.read_text())
            if state.status in TERMINAL_STATUSES and (not transcript.exists() or transcript.stat().st_size == last_size):
                break
        time.sleep(0.5)
