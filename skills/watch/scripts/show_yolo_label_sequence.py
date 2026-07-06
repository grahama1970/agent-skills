#!/usr/bin/env python3
"""Print persisted Watch YOLO label/rejection event sequences."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


WATCH_DIR = Path(__file__).resolve().parents[1]
DEFAULT_LABEL_DIR = WATCH_DIR / "docs" / "architecture" / "generated" / "watch_yolo_track_labels"


def load_receipts(label_dir: Path) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    if not label_dir.exists():
        return receipts
    for path in sorted(label_dir.glob("*.json")):
        try:
            receipt = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            receipts.append(
                {
                    "schema": "watch.yolo_label_sequence_receipt_error.v1",
                    "receipt_path": str(path),
                    "error": f"json_decode_error: {exc}",
                    "events": [],
                }
            )
            continue
        receipt.setdefault("receipt_path", str(path))
        receipts.append(receipt)
    return receipts


def matches(receipt: dict[str, Any], asset_uid: str | None, row_index: int | None) -> bool:
    if asset_uid and receipt.get("asset_uid") != asset_uid:
        return False
    if row_index is not None and int(receipt.get("row_index", -1)) != row_index:
        return False
    return True


def event_time(event: dict[str, Any]) -> float | None:
    try:
        return float(event.get("time_seconds"))
    except (TypeError, ValueError):
        return None


def event_state(event: dict[str, Any]) -> dict[str, Any]:
    action = event.get("action")
    status = event.get("status")
    if action in {"reject_box", "reset_box", "reset", "reject"} or status in {"rejected_box", "reset", "reject"}:
        return {
            "state": "unassigned",
            "character_name": None,
            "reason": "sequence_stop",
        }
    character_name = event.get("character_name")
    if character_name:
        return {
            "state": "assigned",
            "character_name": character_name,
            "actor_name": event.get("actor_name"),
            "confidence": event.get("confidence"),
        }
    return {
        "state": "unknown",
        "character_name": None,
        "reason": "event_has_no_character",
    }


def sequence_states(events: list[dict[str, Any]], state_times: list[float]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    track_ids = sorted({str(event.get("track_id")) for event in events if event.get("track_id")})
    for track_id in track_ids:
        track_events = [
            event for event in events
            if event.get("track_id") == track_id and event_time(event) is not None
        ]
        track_events.sort(key=lambda event: (event_time(event) or 0, str(event.get("created_at") or "")))
        for state_time in state_times:
            prior = [event for event in track_events if (event_time(event) or 0) <= state_time + 0.011]
            if not prior:
                states.append(
                    {
                        "track_id": track_id,
                        "time_seconds": state_time,
                        "state": "unknown",
                        "character_name": None,
                        "source_event": None,
                    }
                )
                continue
            latest = prior[-1]
            states.append(
                {
                    "track_id": track_id,
                    "time_seconds": state_time,
                    **event_state(latest),
                    "source_event": {
                        "action": latest.get("action"),
                        "status": latest.get("status"),
                        "box_key": latest.get("box_key"),
                        "time_seconds": latest.get("time_seconds"),
                        "created_at": latest.get("created_at"),
                    },
                }
            )
    return states


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--asset-uid")
    parser.add_argument("--row-index", type=int)
    parser.add_argument("--track-id")
    parser.add_argument("--action")
    parser.add_argument("--state-at", type=float, action="append", default=[], help="Report interpolated identity state at this segment second. May be repeated.")
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    for receipt in load_receipts(args.label_dir):
        if not matches(receipt, args.asset_uid, args.row_index):
            continue
        for event in receipt.get("events", []):
            if args.track_id and event.get("track_id") != args.track_id:
                continue
            if args.action and event.get("action") != args.action:
                continue
            rows.append(
                {
                    "receipt_path": receipt.get("receipt_path"),
                    "asset_uid": receipt.get("asset_uid"),
                    "row_index": receipt.get("row_index"),
                    "track_id": event.get("track_id"),
                    "box_key": event.get("box_key"),
                    "action": event.get("action"),
                    "status": event.get("status"),
                    "character_name": event.get("character_name"),
                    "actor_name": event.get("actor_name"),
                    "confidence": event.get("confidence"),
                    "time_seconds": event.get("time_seconds"),
                    "created_at": event.get("created_at"),
                }
            )

    rows.sort(key=lambda row: (str(row.get("asset_uid")), int(row.get("row_index") or -1), float(row.get("time_seconds") or 0), str(row.get("created_at"))))
    report = {
        "schema": "watch.yolo_label_sequence_report.v1",
        "label_dir": str(args.label_dir),
        "filters": {
            "asset_uid": args.asset_uid,
            "row_index": args.row_index,
            "track_id": args.track_id,
            "action": args.action,
        },
        "event_count": len(rows),
        "events": rows,
    }
    if args.state_at:
        report["states"] = sequence_states(rows, args.state_at)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
