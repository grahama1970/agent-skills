#!/usr/bin/env python3
"""Build an approved-reference canary manifest from Watch tracking crops.

This is a local canary for the Watch identity loop. It models the same shape
that human annotation approvals will produce, but it does not claim that public
search or ML labels alone prove identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_CROP_MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "architecture"
    / "generated"
    / "bad_santa_marcus_0248_tracking_crops"
    / "watch_tracking_crops.bad_santa_marcus.json"
)
DEFAULT_OUT = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "architecture"
    / "generated"
    / "bad_santa_marcus_0248_approved_reference_canary"
    / "watch_approved_reference_manifest.bad_santa_marcus.canary.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crop-manifest", type=Path, default=DEFAULT_CROP_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--entity-id", default="movie_domain_entities/marcus_bad_santa_2003")
    parser.add_argument("--character-name", default="Marcus")
    parser.add_argument("--actor-name", default="Tony Cox")
    args = parser.parse_args()

    crop_manifest = read_json(args.crop_manifest)
    crops = [
        crop for crop in crop_manifest.get("crops", [])
        if ((crop.get("candidate_entity") or {}).get("entity_id") == args.entity_id)
    ][: args.limit]
    if len(crops) < args.limit:
        raise SystemExit(f"not enough crops for reference canary: found={len(crops)} required={args.limit}")

    references = []
    for index, crop in enumerate(crops, start=1):
        crop_path = str(crop["crop_path"])
        references.append(
            {
                "reference_id": stable_id("watch_ref_canary", {"crop_path": crop_path, "entity_id": args.entity_id}),
                "entity_id": args.entity_id,
                "character_name": args.character_name,
                "actor_name": args.actor_name,
                "approval_status": "APPROVED",
                "approval_source": "watch_canary_existing_track_crop_reference",
                "approval_note": (
                    "Canary reference generated from an existing Watch tracking crop. "
                    "Use for pipeline proof only; production approval should come from "
                    "human annotation or reviewed external reference images."
                ),
                "local_path": crop_path,
                "source_overlay_id": crop.get("overlay_id"),
                "source_track_id": crop.get("track_id"),
                "source_media_time_seconds": crop.get("media_time_seconds"),
                "rank": index,
            }
        )

    manifest = {
        "schema": "watch.approved_reference_manifest.v1",
        "asset_id": crop_manifest.get("asset_uid") or "movie_bad_santa_2003_unrated",
        "entity_id": args.entity_id,
        "character_name": args.character_name,
        "actor_name": args.actor_name,
        "reference_source": "watch_tracking_crop_canary",
        "approval_boundary": (
            "Approved here means approved for local pipeline canary receipts only. "
            "This manifest does not by itself prove supported identity."
        ),
        "references": references,
        "counts": {"approved_reference_count": len(references)},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print("approved_reference_manifest_ok", args.out)
    print("approved_references", len(references))
    return 0


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_id(prefix: str, value: Any) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}:{hashlib.sha256(material.encode('utf-8')).hexdigest()[:32]}"


if __name__ == "__main__":
    raise SystemExit(main())
