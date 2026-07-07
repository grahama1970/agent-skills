#!/usr/bin/env python3
"""Generate PixiJS spritesheet JSON for a fixed BATTLE 8x14 runtime atlas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Final


ROWS: Final[tuple[tuple[str, int], ...]] = (
    ("idle", 4),
    ("walk", 6),
    ("run", 8),
    ("research", 6),
    ("payload", 6),
    ("mutate", 6),
    ("handoff", 6),
    ("spawn", 8),
    ("blocked", 6),
    ("hit", 3),
    ("killed", 8),
    ("victory", 8),
    ("promoted", 8),
    ("fastest_crash", 8),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sprite-id", required=True, help="Stable sprite id, e.g. space_pirate_hornbreaker.")
    parser.add_argument("--image", required=True, help="Runtime atlas PNG filename referenced by meta.image.")
    parser.add_argument("--out", required=True, type=Path, help="Output PixiJS spritesheet JSON path.")
    parser.add_argument("--frame-width", type=int, default=64, choices=(48, 64))
    parser.add_argument("--frame-height", type=int, default=64, choices=(48, 64))
    parser.add_argument("--columns", type=int, default=8)
    args = parser.parse_args()

    frames: dict[str, object] = {}
    animations: dict[str, list[str]] = {}

    for row_index, (animation_name, frame_count) in enumerate(ROWS):
        frame_names: list[str] = []
        for column_index in range(frame_count):
            frame_name = f"{args.sprite_id}_{animation_name}_{column_index}"
            frame_names.append(frame_name)
            frames[frame_name] = {
                "frame": {
                    "x": column_index * args.frame_width,
                    "y": row_index * args.frame_height,
                    "w": args.frame_width,
                    "h": args.frame_height,
                },
                "sourceSize": {
                    "w": args.frame_width,
                    "h": args.frame_height,
                },
                "spriteSourceSize": {
                    "x": 0,
                    "y": 0,
                    "w": args.frame_width,
                    "h": args.frame_height,
                },
            }
        animations[animation_name] = frame_names

    output = {
        "frames": frames,
        "animations": animations,
        "meta": {
            "image": args.image,
            "format": "RGBA8888",
            "scale": "1",
            "battle": {
                "variant_id": args.sprite_id,
                "frameWidth": args.frame_width,
                "frameHeight": args.frame_height,
                "columns": args.columns,
                "rows": len(ROWS),
                "margin": 0,
                "spacing": 0,
                "anchor": {"x": 0.5, "y": 0.85},
                "style": "original_16bit_grimdark_scifi_pixel_art",
                "usage": "pixijs-v8",
            },
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
