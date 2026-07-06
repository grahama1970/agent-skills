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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dir", type=Path, default=DEFAULT_LABEL_DIR)
    parser.add_argument("--asset-uid")
    parser.add_argument("--row-index", type=int)
    parser.add_argument("--track-id")
    parser.add_argument("--action")
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
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
