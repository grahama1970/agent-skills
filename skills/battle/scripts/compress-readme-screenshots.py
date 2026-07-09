#!/usr/bin/env python3
"""Pillow-compress raw README captures to docs/assets/screenshots/*.webp."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

BATTLE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BATTLE_DIR / "docs/assets/screenshots/raw"
OUT_DIR = BATTLE_DIR / "docs/assets/screenshots"
QUALITY = 84


def compress_png_to_webp(png_path: Path, webp_path: Path) -> dict:
    with Image.open(png_path) as image:
        rgb = image.convert("RGB") if image.mode in {"RGBA", "P", "LA"} else image
        if image.mode == "RGBA":
            rgb = Image.new("RGB", image.size, (8, 12, 18))
            rgb.paste(image, mask=image.split()[-1])
        rgb.save(webp_path, format="WEBP", quality=QUALITY, method=6)
    return {
        "png_bytes": png_path.stat().st_size,
        "webp_bytes": webp_path.stat().st_size,
        "webp": str(webp_path.relative_to(BATTLE_DIR)),
    }


def main() -> None:
    manifest_path = RAW_DIR / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    outputs = []
    for entry in manifest.get("manifest", []):
        shot_id = entry["id"]
        png_path = Path(entry["pngPath"])
        webp_path = OUT_DIR / f"{shot_id}.webp"
        if not png_path.exists():
            raise SystemExit(f"missing capture: {png_path}")
        outputs.append({"id": shot_id, **compress_png_to_webp(png_path, webp_path)})

    print(json.dumps({"outputs": outputs}, indent=2))


if __name__ == "__main__":
    main()
