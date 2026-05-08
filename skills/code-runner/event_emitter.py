"""Event emitter for normalized events.jsonl output.

Writes append-only events that can be:
1. Tailed for live monitoring
2. Ingested into ArangoDB later
3. Used by _debug_dashboard.py for visualization

Usage:
    emitter = EventEmitter(output_dir, task_id)
    emitter.emit(EventType.run_started, state_after=RunState.running)
    emitter.emit(EventType.round_scored, round=1, payload={"score": 0.85})
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from loguru import logger

from models import EventType, ReasonCode, RunEvent, RunState


# Valid state transitions for the run state machine
# Maps (current_state) -> set of valid next states
VALID_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.queued: {RunState.preflight_failed, RunState.running},
    RunState.running: {RunState.blocked, RunState.timed_out, RunState.crashed, RunState.failed, RunState.passed},
    RunState.blocked: {RunState.running, RunState.failed, RunState.crashed},  # Can retry or give up
    RunState.timed_out: set(),  # Terminal
    RunState.crashed: set(),    # Terminal
    RunState.failed: set(),     # Terminal
    RunState.passed: set(),     # Terminal
    RunState.preflight_failed: set(),  # Terminal
}


class EventEmitter:
    """Append-only event emitter for code-runner execution."""

    def __init__(self, output_dir: str | Path, task_id: str):
        self.output_dir = Path(output_dir)
        self.run_id = task_id
        self.task_id = task_id
        self.events_file = self.output_dir / f"{task_id}.events.jsonl"
        self.status_file = self.output_dir / f"{task_id}.status.json"
        self.legacy_events_file = self.output_dir / "events.jsonl"
        self.legacy_run_file = self.output_dir / "run.json"
        self._current_state = RunState.queued
        self._current_round = 0
        self._best_score = 0.0
        self._reason_code: ReasonCode | None = None
        self._started_at = time.time()

        # Ensure output dir exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def emit(
        self,
        event: EventType,
        *,
        round: int | None = None,
        state_after: RunState | None = None,
        reason_code: ReasonCode | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Emit an event to events.jsonl and update run.json."""
        state_before = self._current_state

        # Validate state transition if changing state
        if state_after is not None and state_after != state_before:
            valid_next = VALID_TRANSITIONS.get(state_before, set())
            if state_after not in valid_next:
                logger.warning(
                    "Invalid state transition: {} -> {} (valid: {}). Event: {}",
                    state_before.value, state_after.value,
                    [s.value for s in valid_next], event.value
                )
                # Still allow the transition but log it for debugging
                # This helps identify logic bugs without breaking execution

        # Update internal state
        if state_after is not None:
            self._current_state = state_after
        if reason_code is not None:
            self._reason_code = reason_code
        if round is not None:
            self._current_round = round

        # Extract score from payload if present
        if payload and "score" in payload:
            score = payload["score"]
            if isinstance(score, (int, float)) and score > self._best_score:
                self._best_score = score

        # Create event record
        event_record = RunEvent(
            run_id=self.run_id,
            event=event,
            ts=time.time(),
            round=round,
            state_before=state_before if state_after else None,
            state_after=state_after,
            reason_code=reason_code,
            payload=payload or {},
        )

        # Append to task-scoped events.jsonl. Keep legacy events.jsonl for older dashboards.
        try:
            event_text = event_record.model_dump_json() + "\n"
            with self.events_file.open("a") as f:
                f.write(event_text)
            with self.legacy_events_file.open("a") as f:
                f.write(event_text)
        except IOError as e:
            logger.warning("Failed to write event: {}", e)

        # Update status snapshots
        self._write_run_snapshot()

    def _write_run_snapshot(self) -> None:
        """Write current run state to task-scoped status.json and legacy run.json."""
        snapshot = {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "state": self._current_state.value,
            "reason_code": self._reason_code.value if self._reason_code else None,
            "current_round": self._current_round,
            "best_score": self._best_score,
            "started_at": self._started_at,
            "updated_at": time.time(),
            "artifacts": {
                "request": str(self.output_dir / f"{self.task_id}.request.json"),
                "status": str(self.status_file),
                "events": str(self.events_file),
                "rounds": str(self.output_dir / f"{self.task_id}.rounds.jsonl"),
                "result": str(self.output_dir / f"{self.task_id}.result.json"),
                "response": str(self.output_dir / f"{self.task_id}.response.txt"),
                "hunk": str(self.output_dir / f"{self.task_id}.hunk.md"),
                "verifier_log": str(self.output_dir / f"{self.task_id}.verifier.log"),
            },
        }
        try:
            text = json.dumps(snapshot, indent=2) + "\n"
            _atomic_write(self.status_file, text)
            _atomic_write(self.legacy_run_file, text)
        except IOError as e:
            logger.warning("Failed to write run snapshot: {}", e)

    def set_score(self, score: float) -> None:
        """Update best score (called from evidence collection)."""
        if score > self._best_score:
            self._best_score = score
            self._write_run_snapshot()

    @property
    def current_state(self) -> RunState:
        return self._current_state

    @property
    def current_round(self) -> int:
        return self._current_round


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    tmp.replace(path)
