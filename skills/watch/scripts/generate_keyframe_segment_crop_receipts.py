#!/usr/bin/env python3
"""Generate Watch keyframe ffmpeg segment-crop receipts.

This script proves the video side of the annotation loop: a human/ML keyframe
bbox is used to crop the actual movie segment with ffmpeg. It does not claim
identity recognition or interpolation across multiple keyframes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AGENT_SKILLS_ROOT = Path(__file__).resolve().parents[3]
MEMORY_ROOT = AGENT_SKILLS_ROOT.parent / "memory"
if str(MEMORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(MEMORY_ROOT / "src"))


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env(MEMORY_ROOT / ".env")

from graph_memory.arango_client import get_db  # noqa: E402


OUT_ROOT = (
    AGENT_SKILLS_ROOT
    / "skills"
    / "watch"
    / "docs"
    / "architecture"
    / "generated"
    / "watch_segment_crop_receipts"
)
VIDEO_ROOT = OUT_ROOT / "clips"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def slug(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned.strip("_") or "value"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return json.loads(proc.stdout)


def video_probe(path: Path) -> dict[str, Any]:
    data = run_json(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,duration,r_frame_rate",
            "-of",
            "json",
            str(path),
        ]
    )
    stream = (data.get("streams") or [{}])[0]
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "duration": float(stream.get("duration") or 0.0),
        "r_frame_rate": stream.get("r_frame_rate"),
    }


def even(value: int) -> int:
    return max(2, value - (value % 2))


def crop_filter_from_bbox(bbox: list[float], width: int, height: int) -> dict[str, Any]:
    x1, y1, x2, y2 = [float(v) for v in bbox]
    x1 = min(1.0, max(0.0, x1))
    y1 = min(1.0, max(0.0, y1))
    x2 = min(1.0, max(0.0, x2))
    y2 = min(1.0, max(0.0, y2))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    left = int(round(x1 * width))
    top = int(round(y1 * height))
    right = int(round(x2 * width))
    bottom = int(round(y2 * height))
    crop_w = even(max(2, right - left))
    crop_h = even(max(2, bottom - top))
    left = max(0, min(width - crop_w, left))
    top = max(0, min(height - crop_h, top))
    return {
        "pixel_bbox_xywh": [left, top, crop_w, crop_h],
        "filter": f"crop={crop_w}:{crop_h}:{left}:{top}",
    }


def fetch_keyframes(db: Any, character: str, limit: int) -> list[dict[str, Any]]:
    cursor = db.aql.execute(
        """
        FOR d IN watch_keyframe_annotations
          FILTER d.character_name == @character
          FILTER d.lifecycle_status != 'superseded'
          FILTER d.multimodal_sync_state == 'synced'
          FILTER IS_STRING(d.video_clip_path) AND d.video_clip_path != ''
          FILTER IS_ARRAY(d.bbox) AND LENGTH(d.bbox) == 4
          SORT d.lifecycle_status == 'current' DESC, d.updated_at DESC
          LIMIT @limit
          RETURN d
        """,
        bind_vars={"character": character, "limit": limit},
    )
    return list(cursor)


def update_keyframe_doc(db: Any, key: str, patch: dict[str, Any]) -> None:
    db.aql.execute(
        "UPDATE @key WITH @patch IN watch_keyframe_annotations",
        bind_vars={"key": key, "patch": patch},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", default="Willie")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--crf", type=int, default=23)
    args = parser.parse_args()

    db = get_db()
    docs = fetch_keyframes(db, args.character, args.limit)
    if not docs:
        raise SystemExit(f"no synced keyframe annotations with video_clip_path for character={args.character!r}")

    run_id = utc_stamp()
    run_dir = OUT_ROOT / run_id
    clip_dir = VIDEO_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    clip_dir.mkdir(parents=True, exist_ok=True)

    now_iso = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for doc in docs:
        source_clip = Path(str(doc.get("video_clip_path") or ""))
        if not source_clip.exists():
            skipped.append({"_key": doc.get("_key"), "reason": "video_clip_path_missing", "video_clip_path": str(source_clip)})
            continue
        probe = video_probe(source_clip)
        crop = crop_filter_from_bbox(doc["bbox"], probe["width"], probe["height"])
        output_clip = clip_dir / f"{slug(doc['_key'])}.mp4"
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_clip),
            "-vf",
            crop["filter"],
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            str(args.crf),
            "-c:a",
            "copy",
            str(output_clip),
        ]
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.returncode != 0:
            skipped.append(
                {
                    "_key": doc.get("_key"),
                    "reason": "ffmpeg_failed",
                    "stderr": proc.stderr[-2000:],
                    "command": " ".join(shlex.quote(part) for part in cmd),
                }
            )
            continue
        out_probe = video_probe(output_clip)
        segment_sha = sha256_file(output_clip)
        record = {
            "arango_key": doc["_key"],
            "asset_uid": doc.get("asset_uid"),
            "row_index": doc.get("row_index"),
            "character_name": doc.get("character_name"),
            "actor_name": doc.get("actor_name"),
            "timecode": doc.get("timecode"),
            "movie_segment": doc.get("movie_segment"),
            "source_video_clip_path": str(source_clip),
            "source_video_probe": probe,
            "bbox": doc.get("bbox"),
            "crop_filter": crop["filter"],
            "pixel_bbox_xywh": crop["pixel_bbox_xywh"],
            "segment_crop_path": str(output_clip),
            "segment_crop_sha256": segment_sha,
            "segment_crop_probe": out_probe,
        }
        records.append(record)

    if not records:
        raise SystemExit(f"no segment crops generated; skipped={skipped}")

    receipt_path = run_dir / "receipt.json"
    receipt = {
        "schema": "watch.keyframe_segment_crop_receipt.v1",
        "status": "SEGMENT_CROPS_SYNCED",
        "created_at": now_iso,
        "run_id": run_id,
        "character": args.character,
        "counts": {
            "candidate_docs": len(docs),
            "segment_crops_generated": len(records),
            "skipped": len(skipped),
        },
        "records": records,
        "skipped": skipped,
        "proof_scope": {
            "mocked": False,
            "live": True,
            "proves": [
                "synced Watch keyframe bbox records can crop the actual movie segment with ffmpeg",
                "the resulting segment crop is a playable MP4 artifact linked back to the Arango keyframe record",
            ],
            "does_not_prove": [
                "bbox interpolation across the entire segment is correct",
                "YOLO/ByteTrack is tracking the character live",
                "the cropped video segment has been embedded in Qdrant",
            ],
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    for record in records:
        update_keyframe_doc(
            db,
            record["arango_key"],
            {
                "segment_crop_path": record["segment_crop_path"],
                "segment_crop_sha256": record["segment_crop_sha256"],
                "segment_crop_filter": record["crop_filter"],
                "segment_crop_receipt_path": str(receipt_path),
                "segment_crop_sync_state": "synced",
                "updated_at": now_iso,
            },
        )

    print(
        json.dumps(
            {
                "receipt_path": str(receipt_path),
                "counts": receipt["counts"],
                "first_segment_crop_path": records[0]["segment_crop_path"],
                "first_segment_crop_sha256": records[0]["segment_crop_sha256"],
                "first_crop_filter": records[0]["crop_filter"],
                "first_segment_crop_probe": records[0]["segment_crop_probe"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
