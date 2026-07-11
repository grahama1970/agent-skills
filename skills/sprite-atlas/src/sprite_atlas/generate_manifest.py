"""Generate PixiJS spritesheet JSON from profile."""

from __future__ import annotations

import json
from pathlib import Path

from sprite_atlas.contracts import Profile


def build_manifest(*, sprite_id: str, image_name: str, profile: Profile) -> dict[str, object]:
    frames: dict[str, object] = {}
    animations: dict[str, list[str]] = {}
    fw = profile.atlas.frame_width
    fh = profile.atlas.frame_height
    for animation in profile.animations:
        names: list[str] = []
        for column in range(animation.frames):
            frame_name = f"{sprite_id}_{animation.name}_{column}"
            names.append(frame_name)
            frames[frame_name] = {
                "frame": {
                    "x": column * fw,
                    "y": animation.row * fh,
                    "w": fw,
                    "h": fh,
                },
                "sourceSize": {"w": fw, "h": fh},
                "spriteSourceSize": {"x": 0, "y": 0, "w": fw, "h": fh},
            }
        animations[animation.name] = names
    return {
        "frames": frames,
        "animations": animations,
        "meta": {
            "image": image_name,
            "format": "RGBA8888",
            "scale": "1",
            "battle": {
                "variant_id": sprite_id,
                "frameWidth": fw,
                "frameHeight": fh,
                "columns": profile.atlas.columns,
                "rows": profile.atlas.rows,
                "margin": profile.atlas.margin,
                "spacing": profile.atlas.spacing,
                "anchor": {"x": profile.anchor.x, "y": profile.anchor.y},
                "style": "original_16bit_grimdark_scifi_pixel_art",
                "usage": "pixijs-v8",
            },
        },
    }


def write_manifest(path: Path, *, sprite_id: str, image_name: str, profile: Profile) -> dict[str, object]:
    manifest = build_manifest(sprite_id=sprite_id, image_name=image_name, profile=profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
