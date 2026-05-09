"""Canonical session-directory management for /subagent-runner."""
from __future__ import annotations

import json
import os
import socket
import time
import uuid
from pathlib import Path

try:
    from .models import SessionEvent, SessionPaths, SessionResult, SessionSpec, SessionState, SessionStatus
except ImportError:
    from models import SessionEvent, SessionPaths, SessionResult, SessionSpec, SessionState, SessionStatus


class SessionStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve_session_dir(self, session_id_or_dir: str | Path) -> Path:
        session_path = Path(session_id_or_dir)
        if session_path.is_dir():
            return session_path
        return self.session_dir(str(session_id_or_dir))

    def session_dir(self, session_id: str) -> Path:
        return self.root / session_id

    def paths(self, session_id: str) -> SessionPaths:
        session_dir = self.session_dir(session_id)
        return SessionPaths(
            session_dir=str(session_dir),
            spec_file=str(session_dir / "spec.json"),
            status_file=str(session_dir / "status.json"),
            events_file=str(session_dir / "events.jsonl"),
            commands_file=str(session_dir / "commands.jsonl"),
            transcript_file=str(session_dir / "transcript.log"),
            stdout_file=str(session_dir / "stdout.log"),
            stderr_file=str(session_dir / "stderr.log"),
            prompt_file=str(session_dir / "prompt.txt"),
            result_file=str(session_dir / "result.json"),
        )

    def create_session(self, spec: SessionSpec) -> SessionState:
        session_id = f"{spec.task_id}-{uuid.uuid4().hex[:8]}"
        paths = self.paths(session_id)
        session_dir = Path(paths.session_dir)
        session_dir.mkdir(parents=True, exist_ok=False)

        now = time.time()
        state = SessionState(
            session_id=session_id,
            task_id=spec.task_id,
            title=spec.title,
            backend=spec.backend,
            command=spec.command,
            cwd=spec.cwd,
            output_dir=spec.output_dir,
            timeout_seconds=spec.timeout_seconds,
            idle_timeout_seconds=spec.idle_timeout_seconds,
            status=SessionStatus.queued,
            started_at=now,
            updated_at=now,
            last_output_at=now,
            artifact_dir=paths.session_dir,
        )

        Path(paths.spec_file).write_text(spec.model_dump_json(indent=2))
        Path(paths.prompt_file).write_text(spec.prompt)
        Path(paths.transcript_file).touch()
        Path(paths.stdout_file).touch()
        Path(paths.stderr_file).touch()
        Path(paths.events_file).touch()
        Path(paths.commands_file).touch()
        self.write_status(state)
        return state

    def write_status(self, state: SessionState) -> None:
        paths = self.paths(state.session_id)
        Path(paths.status_file).write_text(state.model_dump_json(indent=2))

    def save_state(self, state: SessionState) -> None:
        self.write_status(state)

    def load_status(self, session_id_or_dir: str | Path) -> SessionState:
        status_file = self.resolve_session_dir(session_id_or_dir) / "status.json"
        return SessionState.model_validate_json(status_file.read_text())

    def append_event(self, event: SessionEvent) -> None:
        paths = self.paths(event.session_id)
        event_json = event.model_dump_json()
        with Path(paths.events_file).open("a", encoding="utf-8") as handle:
            handle.write(event_json)
            handle.write("\n")
        self._publish_event_socket(event_json)

    def _publish_event_socket(self, event_json: str) -> None:
        socket_path = os.environ.get("SUBAGENT_RUNNER_EVENT_SOCKET", "").strip()
        if not socket_path:
            return
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                client.connect(socket_path)
                client.sendall(event_json.encode("utf-8"))
        except OSError:
            return

    def write_result(self, result: SessionResult) -> None:
        paths = self.paths(result.session_id)
        Path(paths.result_file).write_text(result.model_dump_json(indent=2))

    def load_spec(self, session_id_or_dir: str | Path) -> SessionSpec:
        spec_file = self.resolve_session_dir(session_id_or_dir) / "spec.json"
        return SessionSpec.model_validate(json.loads(spec_file.read_text()))

    def update_status(self, state: SessionState, *, status: SessionStatus, updated_at: float | None = None) -> SessionState:
        new_state = state.model_copy(update={
            "status": status,
            "updated_at": updated_at or time.time(),
        })
        self.write_status(new_state)
        return new_state

    def patch_state(self, state: SessionState, **updates: object) -> SessionState:
        merged = state.model_copy(update={**updates, "updated_at": time.time()})
        self.write_status(merged)
        return merged
