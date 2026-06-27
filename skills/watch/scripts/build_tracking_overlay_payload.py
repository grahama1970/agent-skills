"""Build Watch UI overlay payloads from live-track JSONL events.

This is the bridge between the streaming tracker contract and the browser
overlay/modal contract. It does not run ML, infer identity, or write memory.
It reads ``watch.live_track_update.v1`` events, validates them against the
Watch tracking schema, converts pixel boxes to percentage boxes, and emits a
UI-ready payload that a player/modal can render without hard-coded regions.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from jsonschema import Draft202012Validator


DEFAULT_ARCH_DIR = Path(__file__).resolve().parents[1] / "docs" / "architecture"
DEFAULT_EVENTS = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_tracker_events"
    / "watch_tracker_event_log.bad_santa_marcus.frame_harness.jsonl"
)
DEFAULT_EVENT_SUMMARY = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_tracker_events"
    / "summary.json"
)
DEFAULT_SCHEMA = DEFAULT_ARCH_DIR / "watch_track_observations.schema.json"
DEFAULT_OUT_DIR = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_overlay_payload"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--event-summary", type=Path, default=DEFAULT_EVENT_SUMMARY)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    events = _read_events(args.events, args.schema)
    frame_size = _frame_size(args.event_summary)
    overlays = _build_overlays(events, frame_size)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "watch.ui_overlay_payload.v1",
        "status": "DRY_RUN_ONLY",
        "posted": False,
        "proof_scope": ["geometry_plumbing"],
        "excluded_proofs": [
            "live_ml",
            "identity",
            "memory_write",
            "qdrant_write",
            "recall",
        ],
        "coordinate_space": {
            "source": "video_frame_pixels",
            "frame_width": frame_size[0],
            "frame_height": frame_size[1],
            "normalized_basis": "percent_of_source_frame",
        },
        "source_events": _display_path(args.events),
        "source_event_summary": _display_path(args.event_summary),
        "frame_size": {"width": frame_size[0], "height": frame_size[1]},
        "overlay_count": len(overlays),
        "overlays": overlays,
        "claim_boundary": (
            "This payload proves only that validated Watch track events can drive "
            "browser overlay geometry without hard-coded boxes. It does not prove "
            "live YOLO/ByteTrack inference, person re-identification, character "
            "identity, memory writes, Qdrant writes, or recall."
        ),
    }
    payload_path = args.out_dir / "watch_ui_overlay_payload.bad_santa_marcus.json"
    _write_json(payload_path, payload)
    inspection_path = args.out_dir / "inspection.md"
    inspection_path.write_text(_inspection(payload_path, payload), encoding="utf-8")

    print("overlay_payload_ok", len(overlays))
    print("frame_size", frame_size[0], frame_size[1])
    print(
        "identity_candidates",
        sorted(
            {
                overlay["identity_candidate"]["name"]
                for overlay in overlays
                if overlay.get("identity_candidate")
            }
        ),
    )
    print("payload", payload_path)
    return 0


def _read_events(events_path: Path, schema_path: Path) -> list[dict[str, Any]]:
    schema = _read_json(schema_path)
    event_schema = dict(schema["$defs"]["live_track_update_event"])
    event_schema["$defs"] = schema["$defs"]
    validator = Draft202012Validator(event_schema)
    events: list[dict[str, Any]] = []
    for index, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        event = json.loads(line)
        errors = sorted(validator.iter_errors(event), key=lambda error: error.path)
        if errors:
            details = "; ".join(
                f"{list(error.path)}: {error.message}" for error in errors
            )
            raise ValueError(f"event {index} failed schema validation: {details}")
        events.append(event)
    if not events:
        raise ValueError(f"no events found: {events_path}")
    return events


def _frame_size(summary_path: Path) -> tuple[int, int]:
    summary = _read_json(summary_path)
    frame_size = summary.get("frame_size", {})
    width = int(frame_size.get("width", 0))
    height = int(frame_size.get("height", 0))
    if width <= 0 or height <= 0:
        raise ValueError(f"missing frame_size width/height in {summary_path}")
    return width, height


def _build_overlays(
    events: list[dict[str, Any]],
    frame_size: tuple[int, int],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[
            (
                event["stream_id"],
                event["asset_uid"],
                event["segment_id"],
                event["track_id"],
            )
        ].append(event)

    overlays: list[dict[str, Any]] = []
    for (stream_id, asset_uid, segment_id, track_id), track_events in sorted(grouped.items()):
        first = track_events[0]
        boundary = next(
            (event for event in reversed(track_events) if event.get("status") == "BOUNDARY_CANDIDATE"),
            track_events[-1],
        )
        candidate = _best_candidate(track_events)
        bbox_xyxy = _median_bbox(track_events)
        latest_time = max(event["media_time_seconds"] for event in track_events)
        overlay = {
            "overlay_id": f"watch_overlay_{asset_uid}_{segment_id}_{track_id}",
            "stream_id": stream_id,
            "asset_uid": asset_uid,
            "segment_id": segment_id,
            "track_id": track_id,
            "time_range": {
                "start_seconds": min(event["media_time_seconds"] for event in track_events),
                "end_seconds": latest_time,
            },
            "anchor_media_time_seconds": boundary["media_time_seconds"],
            "valid_at_media_time_seconds": boundary["media_time_seconds"],
            "bbox_policy": "median_source_events",
            "representative_event": {
                "media_time_seconds": boundary["media_time_seconds"],
                "status": boundary["status"],
                "emitted_at": boundary["emitted_at"],
            },
            "track_lifecycle_status": _track_lifecycle_status(boundary),
            "last_seen_media_time_seconds": latest_time,
            "stale_after_ms": 1000,
            "detected_class": first["detected_class"],
            "classification": _classification(candidate),
            "bbox_xyxy": bbox_xyxy,
            "bbox_percent": _bbox_percent(bbox_xyxy, frame_size),
            "identity_candidate": candidate,
            "identity_status": _identity_status(candidate),
            "visibility_proof": False,
            "source_event_count": len(track_events),
            "source_event_refs": [
                {
                    "media_time_seconds": event["media_time_seconds"],
                    "status": event["status"],
                    "bbox_xyxy": event["bbox_xyxy"],
                }
                for event in track_events
            ],
            "render_policy": {
                "stroke": "solid",
                "stroke_color": "#03dac6" if candidate else "#ffb300",
                "fill_opacity": 0.1,
                "pointer_events": "none",
                "label_position": "top-left",
            },
        }
        overlays.append(overlay)
    return overlays


def _track_lifecycle_status(event: dict[str, Any]) -> str:
    if event.get("status") == "BOUNDARY_CANDIDATE":
        return "boundary_candidate"
    if event.get("status") == "DROPPED":
        return "dropped"
    return "active"


def _best_candidate(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for event in events:
        candidates.extend(event.get("candidate_entities") or [])
    if not candidates:
        return None
    candidate = max(candidates, key=lambda item: float(item.get("confidence", 0.0)))
    return {
        "entity_id": candidate.get("entity_id"),
        "name": candidate.get("name"),
        "kind": candidate.get("kind"),
        "actor_name": candidate.get("actor_name"),
        "confidence": candidate.get("confidence"),
        "status": candidate.get("status", "PROVISIONAL"),
        "basis": candidate.get("basis", []),
    }


def _classification(candidate: dict[str, Any] | None) -> str:
    if not candidate:
        return "unresolved_track"
    status = str(candidate.get("status", "")).lower()
    if status == "provisional":
        return "provisional_identity"
    return status or "candidate_identity"


def _identity_status(candidate: dict[str, Any] | None) -> str:
    if not candidate:
        return "UNRESOLVED"
    status = str(candidate.get("status", "PROVISIONAL")).upper()
    if status in {"VERIFIED", "REFUTED", "HUMAN_OVERRIDE"}:
        return status
    return "PROVISIONAL"


def _median_bbox(events: list[dict[str, Any]]) -> list[int]:
    boxes = [event["bbox_xyxy"] for event in events]
    return [int(round(median(box[index] for box in boxes))) for index in range(4)]


def _bbox_percent(bbox_xyxy: list[int], frame_size: tuple[int, int]) -> dict[str, float]:
    width, height = frame_size
    x1, y1, x2, y2 = bbox_xyxy
    return {
        "left": round((x1 / width) * 100.0, 3),
        "top": round((y1 / height) * 100.0, 3),
        "width": round(((x2 - x1) / width) * 100.0, 3),
        "height": round(((y2 - y1) / height) * 100.0, 3),
    }


def _inspection(payload_path: Path, payload: dict[str, Any]) -> str:
    overlays = payload["overlays"]
    overlay_lines = "\n".join(
        f"- `{overlay['overlay_id']}`: `{overlay['identity_candidate']['name'] if overlay['identity_candidate'] else 'unresolved'}` "
        f"from `{overlay['source_event_count']}` events, bbox percent `{overlay['bbox_percent']}`"
        for overlay in overlays
    )
    return f"""# Watch UI Overlay Payload Inspection

Status: `DRY_RUN_ONLY`

Payload: `{_display_path(payload_path)}`

This artifact adapts validated `watch.live_track_update.v1` events into UI
overlay geometry for the Watch table/modal. It is intended to remove hard-coded
annotation boxes from the browser layer.

## Counts

- Overlay count: `{payload['overlay_count']}`
- Frame size: `{payload['frame_size']['width']}x{payload['frame_size']['height']}`
- Source events: `{payload['source_events']}`

## Overlays

{overlay_lines}

## Claim Boundary

{payload['claim_boundary']}
"""


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
