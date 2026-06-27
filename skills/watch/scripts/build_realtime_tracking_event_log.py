"""Build a deterministic Watch live-track JSONL log from a manifest frame.

This is a non-ML harness. It reads the accepted Watch tracking manifest, opens
the representative frame referenced by the first observation, derives frame
dimensions, and emits schema-valid ``watch.live_track_update.v1`` events. The
events are deliberately marked as fixture/harness output and should not be used
as identity proof.
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from PIL import Image, ImageOps


DEFAULT_ARCH_DIR = Path(__file__).resolve().parents[1] / "docs" / "architecture"
DEFAULT_MANIFEST = DEFAULT_ARCH_DIR / "watch_realtime_tracking_memory_upsert_manifest.bad_santa_marcus.json"
DEFAULT_SCHEMA = DEFAULT_ARCH_DIR / "watch_track_observations.schema.json"
DEFAULT_OUT_DIR = DEFAULT_ARCH_DIR / "generated" / "bad_santa_marcus_0248_tracker_events"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    manifest = _read_json(args.manifest)
    observation = manifest["collections"]["watch_track_observations"][0]
    frame_path = Path(observation["evidence_basis"]["frame_refs"][0]["path"])
    frame_size = _frame_size(frame_path)
    events = _build_events(manifest, observation, frame_size)
    _validate_events(events, args.schema)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    frame_copy = args.out_dir / "source_frame.jpg"
    shutil.copy2(frame_path, frame_copy)
    events_path = args.out_dir / "watch_tracker_event_log.bad_santa_marcus.frame_harness.jsonl"
    events_path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )
    summary = {
        "schema_version": "watch.realtime_tracking_event_log_summary.v1",
        "status": "DRY_RUN_ONLY",
        "provenance": "deterministic_frame_harness_not_ml",
        "source_manifest": _display_path(args.manifest),
        "source_frame": str(frame_path),
        "source_frame_copy": _display_path(frame_copy),
        "frame_size": {"width": frame_size[0], "height": frame_size[1]},
        "event_log": _display_path(events_path),
        "event_count": len(events),
        "track_ids": sorted({event["track_id"] for event in events}),
        "time_bounds_seconds": {
            "start": min(event["media_time_seconds"] for event in events),
            "end": max(event["media_time_seconds"] for event in events),
        },
        "claim_boundary": (
            "This harness proves only that frame-backed inputs can emit the live "
            "track JSONL contract. It does not prove person detection, "
            "ByteTrack continuity, character identity, memory writes, or recall."
        ),
    }
    summary_path = args.out_dir / "summary.json"
    _write_json(summary_path, summary)

    print("frame_harness_events_ok", len(events))
    print("frame_size", frame_size[0], frame_size[1])
    print("track_ids", summary["track_ids"])
    print("event_log", events_path)
    return 0


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object: {path}")
    return data


def _frame_size(path: Path) -> tuple[int, int]:
    if not path.exists():
        raise FileNotFoundError(f"manifest frame does not exist: {path}")
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        return image.size


def _build_events(
    manifest: dict[str, Any],
    observation: dict[str, Any],
    frame_size: tuple[int, int],
) -> list[dict[str, Any]]:
    width, height = frame_size
    start = float(observation["time_range"]["start_seconds"])
    end = float(observation["time_range"]["end_seconds"])
    media_times = [round(start + 0.42, 2), round(start + 3.08, 2), round(end - 0.28, 2)]
    created_at = _parse_datetime(manifest.get("created_at", "2026-06-27T16:45:00Z"))
    base_bbox = [
        round(width * 0.43),
        round(height * 0.08),
        round(width * 0.74),
        round(height * 0.84),
    ]
    candidate = observation.get("candidate_entity")
    candidate_entities = []
    if candidate:
        candidate_entities.append(
            {
                "entity_id": candidate["entity_id"],
                "name": candidate["name"],
                "kind": candidate["kind"],
                "actor_name": candidate.get("actor_name"),
                "confidence": min(float(candidate.get("confidence", 0.0)), 0.5),
                "status": "PROVISIONAL",
                "basis": [
                    "movie_domain_memory",
                    "vlm_scene_text",
                ],
            }
        )

    events: list[dict[str, Any]] = []
    for index, media_time in enumerate(media_times):
        dx = index * max(1, round(width * 0.01))
        dy = index * max(1, round(height * 0.01))
        events.append(
            {
                "event_type": "track_update",
                "schema_version": "watch.live_track_update.v1",
                "stream_id": observation["stream_id"],
                "asset_uid": observation["asset_uid"],
                "segment_id": observation["segment_id"],
                "media_time_seconds": media_time,
                "track_id": observation["track_id"],
                "bbox_xyxy": [
                    base_bbox[0] + dx,
                    base_bbox[1] + dy,
                    min(width, base_bbox[2] + dx),
                    min(height, base_bbox[3] + dy),
                ],
                "detected_class": "person",
                "candidate_entities": candidate_entities,
                "status": "BOUNDARY_CANDIDATE" if index == len(media_times) - 1 else "PROVISIONAL",
                "emitted_at": (created_at + timedelta(seconds=index * 2.66)).isoformat().replace("+00:00", "Z"),
            }
        )
    return events


def _validate_events(events: list[dict[str, Any]], schema_path: Path) -> None:
    schema = _read_json(schema_path)
    event_schema = dict(schema["$defs"]["live_track_update_event"])
    event_schema["$defs"] = schema["$defs"]
    validator = Draft202012Validator(event_schema)
    for index, event in enumerate(events, start=1):
        errors = sorted(validator.iter_errors(event), key=lambda error: error.path)
        if errors:
            details = "; ".join(
                f"{list(error.path)}: {error.message}" for error in errors
            )
            raise ValueError(f"event {index} failed schema validation: {details}")


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
