"""Extract representative crop images from a Watch UI overlay payload.

The output is evidence material for a later identity-verification pass. A crop
does not prove character identity by itself; it only gives the re-ID/human
review stage a bounded image tied to a track, time range, and source clip.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2


DEFAULT_ARCH_DIR = Path(__file__).resolve().parents[1] / "docs" / "architecture"
DEFAULT_OVERLAY_PAYLOAD = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_yolo_overlay_payload"
    / "watch_ui_overlay_payload.bad_santa_marcus.json"
)
DEFAULT_EVENT_SUMMARY = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_yolo_bytetrack"
    / "summary.json"
)
DEFAULT_OUT_DIR = (
    DEFAULT_ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_tracking_crops"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overlay-payload", type=Path, default=DEFAULT_OVERLAY_PAYLOAD)
    parser.add_argument("--event-summary", type=Path, default=DEFAULT_EVENT_SUMMARY)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    payload = _read_json(args.overlay_payload)
    summary = _read_json(args.event_summary)
    source = Path(summary["source"])
    if not source.exists():
        raise FileNotFoundError(f"source clip missing: {source}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = args.out_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    clip_start_seconds = float(summary["time_bounds_seconds"]["start"])
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError(f"could not open source clip: {source}")

    crop_records = []
    try:
        for overlay in payload.get("overlays", []):
            crop_records.append(
                _extract_crop(
                    cap=cap,
                    overlay=overlay,
                    clip_start_seconds=clip_start_seconds,
                    crops_dir=crops_dir,
                )
            )
    finally:
        cap.release()

    manifest = {
        "schema_version": "watch.tracking_crop_manifest.v1",
        "status": "DRY_RUN_ONLY",
        "posted": False,
        "source_overlay_payload": _display_path(args.overlay_payload),
        "source_event_summary": _display_path(args.event_summary),
        "source_clip": str(source),
        "proof_scope": ["track_crop_extraction"],
        "excluded_proofs": [
            "identity",
            "person_reid",
            "frame_crop_embedding",
            "memory_write",
            "qdrant_write",
            "recall",
        ],
        "crop_count": len(crop_records),
        "crops": crop_records,
        "claim_boundary": (
            "This manifest proves representative crop extraction from existing "
            "track boxes only. Crops are evidence inputs for re-identification "
            "or human review; they do not prove character identity by themselves."
        ),
    }
    manifest_path = args.out_dir / "watch_tracking_crops.bad_santa_marcus.json"
    _write_json(manifest_path, manifest)
    inspection_path = args.out_dir / "inspection.md"
    inspection_path.write_text(_inspection(manifest_path, manifest), encoding="utf-8")

    print("tracking_crops_ok", len(crop_records))
    print("source_clip", source)
    print("manifest", manifest_path)
    return 0


def _extract_crop(
    *,
    cap: cv2.VideoCapture,
    overlay: dict[str, Any],
    clip_start_seconds: float,
    crops_dir: Path,
) -> dict[str, Any]:
    anchor_media_time = float(overlay["valid_at_media_time_seconds"])
    local_time_seconds = max(0.0, anchor_media_time - clip_start_seconds)
    cap.set(cv2.CAP_PROP_POS_MSEC, local_time_seconds * 1000.0)
    ok, frame = cap.read()
    if not ok:
        raise RuntimeError(
            f"could not read frame for {overlay['overlay_id']} at {local_time_seconds:.3f}s"
        )

    height, width = frame.shape[:2]
    x1, y1, x2, y2 = [int(value) for value in overlay["bbox_xyxy"]]
    x1 = max(0, min(width - 1, x1))
    y1 = max(0, min(height - 1, y1))
    x2 = max(x1 + 1, min(width, x2))
    y2 = max(y1 + 1, min(height, y2))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        raise RuntimeError(f"empty crop for {overlay['overlay_id']}")

    crop_path = crops_dir / f"{overlay['overlay_id']}.png"
    if not cv2.imwrite(str(crop_path), crop):
        raise RuntimeError(f"failed writing crop: {crop_path}")

    candidate = overlay.get("identity_candidate") or {}
    return {
        "overlay_id": overlay["overlay_id"],
        "track_id": overlay["track_id"],
        "asset_uid": overlay["asset_uid"],
        "segment_id": overlay["segment_id"],
        "media_time_seconds": anchor_media_time,
        "clip_local_time_seconds": round(local_time_seconds, 3),
        "bbox_xyxy": [x1, y1, x2, y2],
        "crop_path": _display_path(crop_path),
        "crop_size": {"width": x2 - x1, "height": y2 - y1},
        "candidate_entity": {
            "name": candidate.get("name"),
            "entity_id": candidate.get("entity_id"),
            "status": candidate.get("status"),
        }
        if candidate
        else None,
        "identity_evidence_status": "CROP_ONLY_NOT_IDENTITY",
    }


def _inspection(manifest_path: Path, manifest: dict[str, Any]) -> str:
    crop_lines = "\n".join(
        "- `{track}` `{candidate}` `{path}` at `{time}`s bbox `{bbox}`".format(
            track=crop["track_id"],
            candidate=(
                crop["candidate_entity"]["name"]
                if crop.get("candidate_entity")
                else "unresolved"
            ),
            path=crop["crop_path"],
            time=crop["media_time_seconds"],
            bbox=crop["bbox_xyxy"],
        )
        for crop in manifest["crops"]
    )
    return f"""# Watch Tracking Crop Extraction Inspection

Status: `DRY_RUN_ONLY`

Manifest: `{_display_path(manifest_path)}`

This artifact extracts representative crop images from live-YOLO-derived Watch
overlay geometry. It creates inspectable image evidence for the next
re-identification or human-review step.

## Counts

- Crops extracted: `{manifest['crop_count']}`
- Source clip: `{manifest['source_clip']}`

## Crops

{crop_lines}

## Claim Boundary

{manifest['claim_boundary']}
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
