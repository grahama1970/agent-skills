"""Durable ping-pong protocol state for the review-code skill.

This module is intentionally isolated from the existing review and loop commands.  It
provides small, transport-neutral primitives for recording reviewer/parent
coordination as append-only JSONL plus a compact ``state.json`` snapshot.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal, Optional, TypedDict

EventType = Literal[
    "run_started",
    "reviewer_started",
    "reviewer_event",
    "clarification_requested",
    "parent_response",
    "reviewer_completed",
    "recommendation",
    "error",
    "run_completed",
]

CommandType = Literal["parent_response", "course_correction"]
RunStatus = Literal[
    "created",
    "running",
    "waiting_for_parent",
    "reviewer_running",
    "completed",
    "error",
]


class EventRecord(TypedDict, total=False):
    """Common JSON shape for every protocol event."""

    event: EventType
    run_id: str
    at: str
    sequence: int
    data: dict[str, Any]


class RunStartedEvent(EventRecord):
    event: Literal["run_started"]


class ReviewerStartedEvent(EventRecord):
    event: Literal["reviewer_started"]


class ReviewerEvent(EventRecord):
    event: Literal["reviewer_event"]


class ClarificationRequestedEvent(EventRecord):
    event: Literal["clarification_requested"]


class ParentResponseEvent(EventRecord):
    event: Literal["parent_response"]


class ReviewerCompletedEvent(EventRecord):
    event: Literal["reviewer_completed"]


class RecommendationEvent(EventRecord):
    event: Literal["recommendation"]


class ErrorEvent(EventRecord):
    event: Literal["error"]


class RunCompletedEvent(EventRecord):
    event: Literal["run_completed"]


class CommandRecord(TypedDict, total=False):
    """Transport-neutral command sent by a parent/controller."""

    command: CommandType
    run_id: str
    at: str
    sequence: int
    data: dict[str, Any]


class ParentResponseCommand(CommandRecord):
    command: Literal["parent_response"]


class CourseCorrectionCommand(CommandRecord):
    command: Literal["course_correction"]


@dataclass
class RunState:
    """Compact durable snapshot stored as ``state.json``."""

    run_id: str
    status: RunStatus = "created"
    last_event_at: Optional[str] = None
    idle_timeout_seconds: Optional[float] = None
    max_wall_clock_seconds: Optional[float] = None
    rounds_completed: int = 0
    requested_model: Optional[str] = None
    actual_model: Optional[str] = None
    requested_reasoning: Optional[str] = None
    actual_reasoning: Optional[str] = None
    bundle_path: Optional[str] = None
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "RunState":
        allowed = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        return cls(**{key: value for key, value in data.items() if key in allowed})


@dataclass(frozen=True)
class StreamBatch:
    """Result returned by polling helpers that can back SSE or other streams."""

    records: list[dict[str, Any]]
    next_offset: int


def utc_now() -> str:
    """Return a compact UTC timestamp suitable for state and event records."""

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_run_id(prefix: str = "review") -> str:
    """Create an opaque run id."""

    return f"{prefix}-{uuid.uuid4().hex}"


def make_event(
    event: EventType,
    run_id: str,
    *,
    sequence: int = 0,
    at: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
    **fields: Any,
) -> EventRecord:
    """Build a typed event record.

    Extra keyword arguments are folded into ``data`` so callers can keep the
    top-level event schema stable while still attaching provider-specific detail.
    """

    payload = dict(data or {})
    payload.update(fields)
    return {
        "event": event,
        "run_id": run_id,
        "at": at or utc_now(),
        "sequence": sequence,
        "data": payload,
    }


def make_command(
    command: CommandType,
    run_id: str,
    *,
    sequence: int = 0,
    at: Optional[str] = None,
    data: Optional[dict[str, Any]] = None,
    **fields: Any,
) -> CommandRecord:
    """Build a transport-neutral parent command record."""

    payload = dict(data or {})
    payload.update(fields)
    return {
        "command": command,
        "run_id": run_id,
        "at": at or utc_now(),
        "sequence": sequence,
        "data": payload,
    }


def append_jsonl(path: Path | str, record: dict[str, Any], *, fsync: bool = True) -> int:
    """Append one JSON object as a JSONL record and return the ending byte offset.

    The line is encoded and written with a single ``os.write`` to a file opened with
    ``O_APPEND``.  Watchers should still tolerate a final partial line (for example
    after a crash); the readers in this module do so.
    """

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(str(target), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, encoded)
        if fsync:
            os.fsync(fd)
        return os.lseek(fd, 0, os.SEEK_END)
    finally:
        os.close(fd)


def read_jsonl(path: Path | str, *, start_offset: int = 0) -> StreamBatch:
    """Read complete JSONL records from ``path`` starting at ``start_offset``.

    Invalid or unterminated final lines are ignored and ``next_offset`` points to
    the start of that partial line so a future poll can retry it.
    """

    target = Path(path)
    if not target.exists():
        return StreamBatch([], start_offset)

    records: list[dict[str, Any]] = []
    with target.open("rb") as handle:
        handle.seek(start_offset)
        offset = start_offset
        while True:
            line_start = offset
            line = handle.readline()
            if not line:
                return StreamBatch(records, offset)
            offset += len(line)
            if not line.endswith(b"\n"):
                return StreamBatch(records, line_start)
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # Treat malformed complete lines as damaged records and continue;
                # this keeps stream consumers moving after external/manual edits.
                continue


def iter_jsonl(path: Path | str, *, start_offset: int = 0) -> Iterator[dict[str, Any]]:
    """Yield currently available complete JSONL records."""

    yield from read_jsonl(path, start_offset=start_offset).records


def write_state(path: Path | str, state: RunState | dict[str, Any]) -> None:
    """Atomically replace ``state.json`` with ``state``."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = state.to_json_dict() if isinstance(state, RunState) else dict(state)
    text = json.dumps(data, sort_keys=True, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
        try:
            dir_fd = os.open(str(target.parent), os.O_DIRECTORY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def read_state(path: Path | str) -> RunState:
    """Load a ``RunState`` from JSON."""

    with Path(path).open("r", encoding="utf-8") as handle:
        return RunState.from_json_dict(json.load(handle))


class PingPongRun:
    """Convenience wrapper around one run directory.

    Files created under ``root``:
      * ``events.jsonl`` for append-only protocol events
      * ``commands.jsonl`` for parent/controller commands
      * ``state.json`` for compact current state
    """

    def __init__(
        self,
        root: Path | str,
        *,
        run_id: Optional[str] = None,
        idle_timeout_seconds: Optional[float] = None,
        max_wall_clock_seconds: Optional[float] = None,
        requested_model: Optional[str] = None,
        requested_reasoning: Optional[str] = None,
        bundle_path: Optional[str] = None,
        artifact_paths: Optional[dict[str, str]] = None,
    ) -> None:
        self.root = Path(root)
        self.events_path = self.root / "events.jsonl"
        self.commands_path = self.root / "commands.jsonl"
        self.state_path = self.root / "state.json"
        self.state = RunState(
            run_id=run_id or new_run_id(),
            idle_timeout_seconds=idle_timeout_seconds,
            max_wall_clock_seconds=max_wall_clock_seconds,
            requested_model=requested_model,
            requested_reasoning=requested_reasoning,
            bundle_path=str(bundle_path) if bundle_path is not None else None,
            artifact_paths=dict(artifact_paths or {}),
        )
        self._event_sequence = 0
        self._command_sequence = 0

    def initialize(self) -> "PingPongRun":
        self.root.mkdir(parents=True, exist_ok=True)
        self.state.status = "created"
        write_state(self.state_path, self.state)
        return self

    def append_event(self, event: EventType, **data: Any) -> EventRecord:
        self._event_sequence += 1
        record = make_event(event, self.state.run_id, sequence=self._event_sequence, data=data)
        append_jsonl(self.events_path, record)
        self._apply_event_to_state(record)
        write_state(self.state_path, self.state)
        return record

    def append_command(self, command: CommandType, **data: Any) -> CommandRecord:
        self._command_sequence += 1
        record = make_command(command, self.state.run_id, sequence=self._command_sequence, data=data)
        append_jsonl(self.commands_path, record)
        return record

    def events_since(self, offset: int = 0) -> StreamBatch:
        return read_jsonl(self.events_path, start_offset=offset)

    def commands_since(self, offset: int = 0) -> StreamBatch:
        return read_jsonl(self.commands_path, start_offset=offset)

    def update_state(self, **changes: Any) -> RunState:
        for key, value in changes.items():
            if not hasattr(self.state, key):
                raise AttributeError(f"unknown RunState field: {key}")
            setattr(self.state, key, value)
        write_state(self.state_path, self.state)
        return self.state

    def _apply_event_to_state(self, record: EventRecord) -> None:
        self.state.last_event_at = record.get("at")
        event = record["event"]
        data = record.get("data", {})
        if event == "run_started":
            self.state.status = "running"
        elif event == "reviewer_started":
            self.state.status = "reviewer_running"
            if data.get("actual_model") is not None:
                self.state.actual_model = data["actual_model"]
            if data.get("actual_reasoning") is not None:
                self.state.actual_reasoning = data["actual_reasoning"]
        elif event == "clarification_requested":
            self.state.status = "waiting_for_parent"
        elif event == "parent_response":
            self.state.status = "running"
        elif event == "reviewer_completed":
            self.state.status = "running"
            if isinstance(data.get("rounds_completed"), int):
                self.state.rounds_completed = data["rounds_completed"]
            else:
                self.state.rounds_completed += 1
        elif event == "error":
            self.state.status = "error"
        elif event == "run_completed":
            self.state.status = "completed"


def create_run(root: Path | str, **kwargs: Any) -> PingPongRun:
    """Create and initialize a ``PingPongRun``."""

    return PingPongRun(root, **kwargs).initialize()


def iter_events_since(events_path: Path | str, offset: int = 0) -> StreamBatch:
    """Polling helper for future streaming transports."""

    return read_jsonl(events_path, start_offset=offset)


def iter_commands_since(commands_path: Path | str, offset: int = 0) -> StreamBatch:
    """Polling helper for future command transports."""

    return read_jsonl(commands_path, start_offset=offset)


def sse_lines(records: Iterable[dict[str, Any]], *, id_start: int = 0) -> Iterator[str]:
    """Format records as Server-Sent Events lines without opening a socket."""

    for index, record in enumerate(records, start=id_start):
        name = record.get("event") or record.get("command") or "message"
        yield f"id: {index}\n"
        yield f"event: {name}\n"
        yield f"data: {json.dumps(record, sort_keys=True, separators=(',', ':'))}\n\n"
