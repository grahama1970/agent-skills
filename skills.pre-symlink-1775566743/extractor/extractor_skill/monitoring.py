#!/usr/bin/env python3
"""
Monitoring module for extractor skill.

Provides NDJSON event streaming and task-monitor integration.

Usage:
    from extractor_skill.monitoring import EventEmitter, TaskClient, BatchProgress

    # NDJSON events
    emitter = EventEmitter("extract-batch")
    emitter.init(total=100)
    emitter.item_complete(0, ok=True, item="doc.pdf")
    emitter.done(success=True)

    # Task client (combines NDJSON + file state)
    client = TaskClient("extract-batch", total=100)
    for i, f in enumerate(files):
        result = extract(f)
        client.item_complete(i, ok=result.get("success"), item=f.name)
    client.finish(success=True)

    # Batch progress wrapper
    for f in BatchProgress(files, name="extract"):
        extract(f)
"""
from __future__ import annotations

from loguru import logger

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, TextIO, TypeVar

T = TypeVar("T")

# Task monitor registry location
TASK_MONITOR_REGISTRY = Path.home() / ".pi" / "task-monitor" / "registry.json"


class EventType(str, Enum):
    """Task-monitor compatible event types."""

    INIT = "init"
    PROGRESS = "progress"
    ITEM_COMPLETE = "item_complete"
    RETRY = "retry"
    ERROR = "error"
    DONE = "done"


class EventEmitter:
    """Emit NDJSON events to stderr.

    Each event is a single JSON line with:
    - event: Event type (init, progress, item_complete, etc.)
    - task_id: Unique identifier for this task run
    - task_name: Human-readable task name
    - timestamp: Unix timestamp (float)
    - elapsed_ms: Milliseconds since task start
    - Additional fields based on event type

    Args:
        task_name: Human-readable name for the task
        stream: Output stream (default: stderr)
        task_id: Unique identifier (default: auto-generated)
        project: Project name for grouping (default: "extractor")
    """

    def __init__(
        self,
        task_name: str,
        stream: TextIO = sys.stderr,
        task_id: Optional[str] = None,
        project: str = "extractor",
    ):
        self.task_name = task_name
        self.task_id = task_id or f"{task_name}-{int(time.time())}"
        self.project = project
        self.stream = stream
        self._start_time = time.time()
        self._count = 0
        self._total = 0

    def _emit(self, event_type: EventType, **data: Any) -> None:
        """Emit a single NDJSON line."""
        record = {
            "event": event_type.value,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "project": self.project,
            "timestamp": time.time(),
            "elapsed_ms": int((time.time() - self._start_time) * 1000),
            **data,
        }
        line = json.dumps(record, ensure_ascii=False)
        self.stream.write(line + "\n")
        self.stream.flush()

    def init(self, total: int, description: str = "", **meta: Any) -> None:
        """Emit task initialization event."""
        self._total = total
        self._emit(EventType.INIT, total=total, description=description, meta=meta)

    def progress(self, completed: int, total: Optional[int] = None, **data: Any) -> None:
        """Emit periodic progress update."""
        total = total or self._total
        pct = (completed / total * 100) if total > 0 else 0
        self._emit(
            EventType.PROGRESS,
            completed=completed,
            total=total,
            pct=round(pct, 1),
            **data,
        )

    def item_complete(self, index: int, ok: bool, **data: Any) -> None:
        """Emit item completion event."""
        self._count += 1
        self._emit(
            EventType.ITEM_COMPLETE,
            index=index,
            ok=ok,
            count=self._count,
            **data,
        )

    def retry(
        self,
        index: int,
        attempt: int,
        max_attempts: int,
        error: str,
        **data: Any,
    ) -> None:
        """Emit retry event."""
        self._emit(
            EventType.RETRY,
            index=index,
            attempt=attempt,
            max_attempts=max_attempts,
            error=error[:200],
            **data,
        )

    def error(
        self,
        index: Optional[int],
        error: str,
        recoverable: bool = False,
        **data: Any,
    ) -> None:
        """Emit error event."""
        self._emit(
            EventType.ERROR,
            index=index,
            error=error[:500],
            recoverable=recoverable,
            **data,
        )

    def done(self, success: bool, summary: Optional[Dict[str, Any]] = None) -> None:
        """Emit task completion event."""
        self._emit(
            EventType.DONE,
            success=success,
            summary=summary or {},
            total_count=self._count,
        )

    @property
    def count(self) -> int:
        """Number of items completed."""
        return self._count

    @property
    def elapsed_ms(self) -> int:
        """Milliseconds since task start."""
        return int((time.time() - self._start_time) * 1000)


@dataclass
class TaskMetrics:
    """Accumulated metrics for a task."""

    success: int = 0
    failed: int = 0
    retries: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "failed": self.failed,
            "retries": self.retries,
        }


@dataclass
class FailureRecord:
    """Record of a task item failure."""

    index: int
    item_id: str
    error: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "index": self.index,
            "item_id": self.item_id[:50],
            "error": self.error[:100],
            "timestamp": self.timestamp,
        }


class TaskClient:
    """Unified task client for extractor batch operations.

    Combines:
    - File-based state for task-monitor TUI display
    - NDJSON event streaming for real-time monitoring
    - Registry integration for task discovery

    Args:
        task_name: Human-readable task name
        total: Total number of items to process
        project: Project name (default: "extractor")
        state_dir: Directory for state file (default: cwd)
        emit_ndjson: Whether to emit NDJSON events (default: True)
        register: Whether to register with task-monitor (default: True)
        description: Optional task description
    """

    def __init__(
        self,
        task_name: str,
        total: int,
        project: str = "extractor",
        state_dir: Optional[Path] = None,
        emit_ndjson: bool = True,
        register: bool = True,
        description: Optional[str] = None,
    ):
        self.task_name = task_name
        self.total = total
        self.project = project
        self.description = description or f"{project}: {task_name}"
        self.state_dir = Path(state_dir) if state_dir else Path.cwd()
        self.state_file = self.state_dir / f".{task_name}_state.json"

        # Metrics tracking
        self.metrics = TaskMetrics()
        self.completed = 0
        self.start_time = time.time()
        self.last_update = 0.0
        self.current_item = ""
        self.consecutive_errors = 0

        # Failure tracking (keep last N)
        self.failures: List[FailureRecord] = []
        self._max_failures = 50

        # NDJSON emitter
        self.emitter: Optional[EventEmitter] = None
        if emit_ndjson:
            self.emitter = EventEmitter(task_name=task_name, project=project)
            self.emitter.init(total=total, description=self.description)

        # Register with task-monitor
        if register:
            self._register()

        # Write initial state
        self._write_state()

    def _register(self) -> None:
        """Register with task-monitor registry."""
        try:
            TASK_MONITOR_REGISTRY.parent.mkdir(parents=True, exist_ok=True)

            registry = {}
            if TASK_MONITOR_REGISTRY.exists():
                try:
                    registry = json.loads(TASK_MONITOR_REGISTRY.read_text())
                except Exception:
                    registry = {}

            registry[f"{self.project}:{self.task_name}"] = {
                "state_file": str(self.state_file),
                "total": self.total,
                "description": self.description,
                "project": self.project,
                "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Atomic write
            tmp = TASK_MONITOR_REGISTRY.with_suffix(".tmp")
            tmp.write_text(json.dumps(registry, indent=2))
            os.replace(tmp, TASK_MONITOR_REGISTRY)
        except Exception as e:
            logger.debug("extractor task monitor registry write failed: {}", e)

    def _write_state(self, final: bool = False) -> None:
        """Write state file for task-monitor TUI."""
        now = time.time()

        # Throttle updates (except final)
        if not final and (now - self.last_update) < 0.5:
            return
        self.last_update = now

        elapsed = now - self.start_time
        pct = (self.completed / self.total * 100) if self.total > 0 else 0

        # Calculate ETA
        eta_s = None
        if self.completed > 0 and self.completed < self.total:
            rate = self.completed / elapsed
            remaining = self.total - self.completed
            eta_s = remaining / rate if rate > 0 else None

        state = {
            "completed": self.completed,
            "total": self.total,
            "description": self.description,
            "current_item": self.current_item,
            "progress_pct": round(pct, 1),
            "elapsed_seconds": round(elapsed, 1),
            "eta_seconds": round(eta_s, 1) if eta_s else None,
            "stats": self.metrics.to_dict(),
            "failures": [f.to_dict() for f in self.failures[-20:]],
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "completed" if final else "running",
        }

        try:
            # Atomic write
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2))
            os.replace(tmp, self.state_file)
        except Exception as e:
            logger.debug("extractor task monitor state write failed: {}", e)

    def item_complete(
        self,
        index: int,
        ok: bool,
        item: str = "",
        error: Optional[str] = None,
        **data: Any,
    ) -> None:
        """Record item completion."""
        self.completed += 1
        self.current_item = item[:50] if item else f"item-{index}"

        if ok:
            self.metrics.success += 1
            self.consecutive_errors = 0
        else:
            self.metrics.failed += 1
            self.consecutive_errors += 1
            if error:
                self.failures.append(
                    FailureRecord(index=index, item_id=item, error=error)
                )
                # Trim to max
                if len(self.failures) > self._max_failures:
                    self.failures = self.failures[-self._max_failures:]

        if self.emitter:
            self.emitter.item_complete(index=index, ok=ok, item=item, **data)

        self._write_state()

    def retry(
        self,
        index: int,
        attempt: int,
        max_attempts: int,
        error: str,
    ) -> None:
        """Record a retry attempt."""
        self.metrics.retries += 1

        if self.emitter:
            self.emitter.retry(
                index=index,
                attempt=attempt,
                max_attempts=max_attempts,
                error=error,
            )

    def error(
        self,
        index: Optional[int],
        error: str,
        recoverable: bool = False,
    ) -> None:
        """Record an error."""
        if self.emitter:
            self.emitter.error(index=index, error=error, recoverable=recoverable)

    def finish(self, success: bool = True) -> Dict[str, Any]:
        """Mark task as complete and return summary."""
        summary = {
            "task_name": self.task_name,
            "project": self.project,
            "total": self.total,
            "completed": self.completed,
            "success": success,
            **self.metrics.to_dict(),
            "elapsed_seconds": round(time.time() - self.start_time, 1),
        }

        if self.emitter:
            self.emitter.done(success=success, summary=summary)

        self._write_state(final=True)

        return summary

    def get_summary(self) -> Dict[str, Any]:
        """Get current summary without finishing."""
        return {
            "task_name": self.task_name,
            "project": self.project,
            "total": self.total,
            "completed": self.completed,
            **self.metrics.to_dict(),
            "elapsed_seconds": round(time.time() - self.start_time, 1),
            "progress_pct": round(
                (self.completed / self.total * 100) if self.total > 0 else 0, 1
            ),
        }


class BatchProgress:
    """NDJSON-streaming progress wrapper (tqdm alternative).

    Wraps an iterable and emits NDJSON events for each item.

    Args:
        iterable: Items to iterate
        name: Task name for monitoring
        total: Total count (auto-detected if iterable has len)
        project: Project name (default: "extractor")
        register: Register with task-monitor (default: True)

    Example:
        for f in BatchProgress(files, name="extract"):
            extract(f)
    """

    def __init__(
        self,
        iterable: Iterable[T],
        name: str = "batch",
        total: Optional[int] = None,
        project: str = "extractor",
        register: bool = True,
    ):
        self.iterable = iterable
        self.name = name
        self.total = total or (len(iterable) if hasattr(iterable, "__len__") else 0)
        self.project = project
        self.register = register

        self._client: Optional[TaskClient] = None
        self._current_index = 0
        self._last_error: Optional[str] = None

    def __iter__(self) -> Iterator[T]:
        """Iterate with progress tracking."""
        self._client = TaskClient(
            task_name=self.name,
            total=self.total,
            project=self.project,
            emit_ndjson=True,
            register=self.register,
        )

        for i, item in enumerate(self.iterable):
            self._current_index = i
            self._last_error = None

            yield item

            # Record completion (ok unless fail() was called)
            ok = self._last_error is None
            self._client.item_complete(
                index=i,
                ok=ok,
                item=str(item)[:50] if item else f"item-{i}",
                error=self._last_error,
            )

        # Final completion
        success = self._client.metrics.failed == 0
        self._client.finish(success=success)

    def fail(self, error: str) -> None:
        """Mark current item as failed."""
        self._last_error = error

    @property
    def client(self) -> Optional[TaskClient]:
        """Get the underlying TaskClient."""
        return self._client
