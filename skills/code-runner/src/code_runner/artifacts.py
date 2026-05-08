"""Artifact writing helpers for code-runner.

The runner writes append-only events and explicit JSON state so callers can
verify what happened without scraping terminal output.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def json_default(value: Any) -> str:
    """Serialize path-like values in result artifacts."""

    if isinstance(value, Path):
        return str(value)
    return str(value)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write formatted JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=json_default) + "\n")
    tmp.replace(path)


def append_event(path: Path, event: str, **payload: Any) -> None:
    """Append one event JSON line."""

    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"event": event, "ts": time.time(), **payload}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=json_default) + "\n")


class RunArtifacts:
    """Resolved artifact paths for one task."""

    def __init__(self, output_dir: str | Path, task_id: str) -> None:
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.task_id = task_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.request = self.output_dir / f"{task_id}.request.json"
        self.status = self.output_dir / f"{task_id}.status.json"
        self.events = self.output_dir / f"{task_id}.events.jsonl"
        self.rounds = self.output_dir / f"{task_id}.rounds.jsonl"
        self.response = self.output_dir / f"{task_id}.response.txt"
        self.result = self.output_dir / f"{task_id}.result.json"
        self.patch = self.output_dir / f"{task_id}.patch"
        self.hunk = self.output_dir / f"{task_id}.hunk.md"
        self.verifier = self.output_dir / f"{task_id}.verifier.log"

    def write_status(self, status: str, **payload: Any) -> None:
        """Write current task status."""

        write_json(self.status, {"task_id": self.task_id, "status": status, "updated_at": time.time(), **payload})
