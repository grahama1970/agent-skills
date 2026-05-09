"""Typed task, session, event, and result models for /subagent-runner."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SessionStatus(str, Enum):
    queued = "queued"
    starting = "starting"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"
    stalled = "stalled"


class EventKind(str, Enum):
    session_created = "session_created"
    session_started = "session_started"
    session_attached = "session_attached"
    session_heartbeat = "session_heartbeat"
    transcript_delta = "transcript_delta"
    input_sent = "input_sent"
    session_paused = "session_paused"
    session_resumed = "session_resumed"
    session_cancelled = "session_cancelled"
    session_completed = "session_completed"
    session_failed = "session_failed"
    session_timed_out = "session_timed_out"
    session_stalled = "session_stalled"


class InterventionSource(str, Enum):
    controller = "controller"
    human = "human"
    watchdog = "watchdog"


class SessionPaths(BaseModel):
    session_dir: str
    spec_file: str
    status_file: str
    events_file: str
    commands_file: str
    transcript_file: str
    stdout_file: str
    stderr_file: str
    prompt_file: str
    result_file: str


class SessionSpec(BaseModel):
    task_id: str = Field(..., min_length=1)
    title: str = Field("", description="Human-readable task title")
    prompt: str = Field(..., min_length=1)
    backend: str = Field("codex")
    command: list[str] = Field(default_factory=list)
    cwd: str = Field(..., min_length=1)
    output_dir: str = Field("/tmp/subagent-runner")
    timeout_seconds: int = Field(1800, ge=1)
    idle_timeout_seconds: int = Field(300, ge=1)
    allowlist: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator("cwd")
    @classmethod
    def cwd_must_exist(cls, value: str) -> str:
        if not Path(value).exists():
            raise ValueError(f"cwd does not exist: {value}")
        return value

    @field_validator("backend")
    @classmethod
    def backend_must_be_known(cls, value: str) -> str:
        known = {"codex", "claude", "gemini", "deepseek"}
        if value not in known:
            raise ValueError(f"Unknown backend '{value}'. Valid: {', '.join(sorted(known))}")
        return value


class SessionState(BaseModel):
    session_id: str
    task_id: str
    title: str = ""
    backend: str
    command: list[str] = Field(default_factory=list)
    cwd: str
    output_dir: str
    timeout_seconds: int
    idle_timeout_seconds: int
    status: SessionStatus
    pid: int | None = None
    watcher_pid: int | None = None
    pty_device: str | None = None
    started_at: float
    updated_at: float
    last_output_at: float | None = None
    finished_at: float | None = None
    exit_code: int | None = None
    intervention_state: str = "idle"
    status_reason: str = ""
    artifact_dir: str


class SessionEvent(BaseModel):
    session_id: str
    task_id: str
    ts: float
    kind: EventKind
    status: SessionStatus
    source: InterventionSource | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SessionResult(BaseModel):
    session_id: str
    task_id: str
    backend: str
    status: SessionStatus
    exit_code: int | None = None
    started_at: float
    finished_at: float | None = None
    duration_seconds: float | None = None
    artifact_dir: str
    summary: str = ""
    final_message: str = ""
    final_message_source: str = ""
    final_message_status: str = "missing"
    final_message_file: str = ""
    final_message_warnings: list[str] = Field(default_factory=list)
