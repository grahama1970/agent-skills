"""Materialize YOLO/ByteTrack person boxes for every Watch report row.

Watch uses YOLOAnalytics-style detector tracks as the first-stage person-box
source. This batch wrapper runs the existing per-clip YOLO/ByteTrack adapter
for each row in a Watch report and writes row-specific tracker logs into the
Watch generated artifacts tree, where the UX server already discovers them.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_WATCH_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = Path("/tmp/watch-wex5uxs_/report.json")
DEFAULT_OUT_ROOT = (
    DEFAULT_WATCH_DIR
    / "docs"
    / "architecture"
    / "generated"
    / "watch_yolo_bytetrack_rows"
)
DEFAULT_TRACK_SCRIPT = DEFAULT_WATCH_DIR / "scripts" / "track_yolo_bytetrack.py"
DEFAULT_PYTHON_BIN = (
    DEFAULT_WATCH_DIR / ".venv" / "bin" / "python"
    if (DEFAULT_WATCH_DIR / ".venv" / "bin" / "python").exists()
    else Path(sys.executable)
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--track-script", type=Path, default=DEFAULT_TRACK_SCRIPT)
    parser.add_argument("--python-bin", type=Path, default=DEFAULT_PYTHON_BIN)
    parser.add_argument("--asset-uid", help="Override report/run asset uid.")
    parser.add_argument("--rows", help="Comma-separated row indexes. Defaults to every report row.")
    parser.add_argument("--sample-fps", type=float, default=5.0)
    parser.add_argument("--max-events", type=int, default=500)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--model", default=str(DEFAULT_WATCH_DIR / "yolo11n.pt"))
    parser.add_argument("--force", action="store_true", help="Regenerate rows even when summary.json exists.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned row commands without running YOLO.")
    args = parser.parse_args()

    report = _read_json(args.report)
    rows = report.get("scene_elements")
    if not isinstance(rows, list):
        raise ValueError(f"report has no scene_elements list: {args.report}")

    requested_rows = _parse_rows(args.rows)
    asset_uid = args.asset_uid or _asset_uid_from_report(report)
    args.out_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_index = _as_int(row.get("index"))
        if row_index is None:
            continue
        if requested_rows is not None and row_index not in requested_rows:
            continue
        result = _materialize_row(args=args, row=row, row_index=row_index, asset_uid=asset_uid)
        results.append(result)

    summary = {
        "schema": "watch.yolo_bytetrack_report_materialization.v1",
        "report": str(args.report),
        "asset_uid": asset_uid,
        "out_root": str(args.out_root),
        "row_count": len(results),
        "generated_count": sum(1 for item in results if item["status"] in {"generated", "no_detections"}),
        "skipped_count": sum(1 for item in results if item["status"] == "skipped_existing"),
        "failed_count": sum(1 for item in results if item["status"] == "failed"),
        "no_detection_count": sum(1 for item in results if item["status"] == "no_detections"),
        "dry_run": args.dry_run,
        "rows": results,
    }
    summary_path = args.out_root / "materialization_summary.json"
    _write_json(summary_path, summary)
    print(json.dumps({
        "summary": str(summary_path),
        "row_count": summary["row_count"],
        "generated_count": summary["generated_count"],
        "skipped_count": summary["skipped_count"],
        "failed_count": summary["failed_count"],
    }, sort_keys=True))
    return 1 if summary["failed_count"] else 0


def _materialize_row(*, args: argparse.Namespace, row: dict[str, Any], row_index: int, asset_uid: str) -> dict[str, Any]:
    clip_path = row.get("video_clip_path")
    if not isinstance(clip_path, str) or not clip_path:
        return {"row_index": row_index, "status": "failed", "error": "missing video_clip_path"}
    if not Path(clip_path).exists():
        return {"row_index": row_index, "status": "failed", "error": f"clip does not exist: {clip_path}"}

    bounds = _segment_bounds(row)
    segment_start = bounds[0] if bounds else _timecode_seconds(row.get("timecode")) or 0.0
    # Keep the unpadded row token because the UX server's row matcher accepts
    # row_4-style segment ids and also falls back to media time bounds.
    segment_id = f"watch_row_{row_index}_yolo_bytetrack"
    row_dir = args.out_root / f"{_safe_part(asset_uid)}_row{row_index:04d}"
    summary_path = row_dir / "summary.json"
    event_log = row_dir / "watch_tracker_event_log.bad_santa_marcus.yolo_bytetrack.jsonl"
    if summary_path.exists() and event_log.exists() and not args.force:
        existing_summary = _read_json(summary_path)
        if existing_summary.get("status") == "NO_DETECTIONS":
            return {
                "row_index": row_index,
                "status": "no_detections",
                "clip": clip_path,
                "out_dir": str(row_dir),
                "event_log": str(event_log),
            }
        return {
            "row_index": row_index,
            "status": "skipped_existing",
            "clip": clip_path,
            "out_dir": str(row_dir),
            "event_log": str(event_log),
        }

    command = [
        str(args.python_bin),
        str(args.track_script),
        "--source",
        clip_path,
        "--out-dir",
        str(row_dir),
        "--asset-uid",
        asset_uid,
        "--segment-id",
        segment_id,
        "--start-seconds",
        str(segment_start),
        "--sample-fps",
        str(args.sample_fps),
        "--max-events",
        str(args.max_events),
        "--conf",
        str(args.conf),
        "--imgsz",
        str(args.imgsz),
        "--model",
        str(args.model),
    ]
    if args.dry_run:
        return {
            "row_index": row_index,
            "status": "planned",
            "clip": clip_path,
            "out_dir": str(row_dir),
            "command": command,
        }

    row_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        if "YOLO/ByteTrack produced no track events" in proc.stderr:
            row_dir.mkdir(parents=True, exist_ok=True)
            event_log.write_text("", encoding="utf-8")
            _write_json(summary_path, {
                "schema_version": "watch.yolo_bytetrack_event_log_summary.v1",
                "status": "NO_DETECTIONS",
                "posted": False,
                "source": clip_path,
                "event_log": str(event_log),
                "event_count": 0,
                "track_ids": [],
                "claim_boundary": (
                    "YOLO/ByteTrack emitted no person track events for this row. "
                    "This is an explicit empty detector artifact, not character evidence."
                ),
            })
            return {
                "row_index": row_index,
                "status": "no_detections",
                "clip": clip_path,
                "out_dir": str(row_dir),
                "event_log": str(event_log),
                "stderr": proc.stderr[-2000:],
            }
        return {
            "row_index": row_index,
            "status": "failed",
            "clip": clip_path,
            "out_dir": str(row_dir),
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "command": command,
        }
    return {
        "row_index": row_index,
        "status": "generated",
        "clip": clip_path,
        "out_dir": str(row_dir),
        "event_log": str(event_log),
        "stdout": proc.stdout[-2000:],
    }


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_rows(value: str | None) -> set[int] | None:
    if not value:
        return None
    rows = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        rows.add(int(part))
    return rows


def _asset_uid_from_report(report: dict[str, Any]) -> str:
    for key in ("asset_uid", "assetUid"):
        value = report.get(key)
        if isinstance(value, str) and value:
            return value
    for row in report.get("scene_elements", []) if isinstance(report.get("scene_elements"), list) else []:
        if isinstance(row, dict):
            value = row.get("asset_uid") or row.get("assetUid")
            if isinstance(value, str) and value:
                return value
    return "bad_santa_unrated_2003_brrip_xvidhd_720p_npw"


def _segment_bounds(row: dict[str, Any]) -> tuple[float, float] | None:
    value = row.get("movie_segment")
    if not isinstance(value, str) or "-" not in value:
        return None
    start_raw, end_raw = [part.strip() for part in value.split("-", 1)]
    start = _timecode_seconds(start_raw)
    end = _timecode_seconds(end_raw)
    if start is None or end is None:
        return None
    return start, end


def _timecode_seconds(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    parts = value.split(":")
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return None
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    if len(numbers) == 3:
        return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]
    return None


def _safe_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)
    return cleaned.strip("_") or "watch_asset"


def _as_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number


if __name__ == "__main__":
    raise SystemExit(main())
