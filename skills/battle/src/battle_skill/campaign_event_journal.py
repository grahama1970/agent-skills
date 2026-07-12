"""Append receipt-backed events to one monotonic Battle campaign journal."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class CampaignEventJournal:
    """Write ordered public-safe events only after their source receipt exists."""

    def __init__(self, *, root: Path, battle_id: str, run_id: str) -> None:
        self.root = root
        self.path = root / "events.jsonl"
        self.clock_path = root / "campaign-clock.json"
        self.battle_id = battle_id
        self.run_id = run_id
        self.clock_id = f"{run_id}-clock"
        self.started_ns = time.monotonic_ns()
        self.seq = 0
        root.mkdir(parents=True, exist_ok=True)
        self.clock_path.write_text(
            json.dumps(
                {
                    "schema": "battle.campaign_clock.v1",
                    "campaign_clock_id": self.clock_id,
                    "battle_id": battle_id,
                    "run_id": run_id,
                    "started_at": _now(),
                    "monotonic_epoch_process_id": os.getpid(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        self.path.write_text("", encoding="utf-8")

    def append(
        self,
        *,
        event_type: str,
        source_receipt: Path,
        generation: int | None = None,
        team: str | None = None,
        lane_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not source_receipt.is_file():
            raise ValueError(f"source receipt missing: {source_receipt}")
        source = _read_json(source_receipt)
        self.seq += 1
        observed_ns = time.monotonic_ns()
        event = {
            "schema": "battle.campaign_event.v1",
            "seq": self.seq,
            "event_id": f"{self.run_id}-event-{self.seq:04d}",
            "battle_id": self.battle_id,
            "run_id": self.run_id,
            "campaign_clock_id": self.clock_id,
            "generation": generation,
            "team": team,
            "lane_id": lane_id,
            "event_type": event_type,
            "timing": {
                "observed_monotonic_ns": observed_ns,
                "elapsed_seconds": round(
                    (observed_ns - self.started_ns) / 1_000_000_000, 6
                ),
                "committed_at": _now(),
                "source_created_at": source.get("created_at"),
            },
            "source_receipt": {
                "receipt_id": source.get("receipt_id")
                or source.get("fitness_id")
                or source.get("request_id")
                or source.get("delta_id")
                or source.get("selection_id")
                or source.get("evaluation_id"),
                "schema": source.get("schema"),
                "sha256": _sha(source_receipt),
                "status": source.get("status"),
                "verdict": source.get("verdict"),
            },
            "payload": payload or {},
            "claims": {
                "proves": [
                    "Battle observed the cited committed receipt at this campaign time."
                ],
                "does_not_prove": [
                    "The journal independently establishes the receipt semantics."
                ],
            },
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
