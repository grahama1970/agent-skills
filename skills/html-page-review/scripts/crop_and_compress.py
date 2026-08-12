#!/usr/bin/env python3
"""Crop and compress section screenshots from a full-page screenshot.

Coordinates in review-map.json are CSS pixels. The script scales them to the
actual screenshot size, crops full-width section images, resizes to a VLM-friendly
width, splits very tall sections, and writes a manifest.

RECONSTRUCTED 2026-08-12 from the surviving compiled bytecode
(crop_and_compress.cpython-312.pyc) after the .py source was lost (never tracked
in git, no disk copy survived). Faithful to the 3.12 disassembly. Now TRACKED.
"""
from __future__ import annotations

import json
import math
import pathlib
import re
from dataclasses import dataclass
from typing import Any

import typer

try:
    from PIL import Image
except ImportError as exc:
    raise SystemExit("Pillow is required: pip install pillow") from exc


@dataclass
class CropConfig:
    max_width: int = 1400
    max_height: int = 1800
    quality: int = 82
    overlap: int = 120
    min_height: int = 80


def slugify(value: str, fallback: str) -> str:
    value = value.strip() or fallback
    value = re.sub("[^A-Za-z0-9._-]+", "-", value)
    value = re.sub("-+", "-", value).strip("-._")
    return (value or fallback)[:72]


def load_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resize_to_width(img: Image.Image, max_width: int) -> Image.Image:
    if img.width <= max_width:
        return img.copy()
    ratio = max_width / float(img.width)
    new_height = max(1, int(round(img.height * ratio)))
    return img.resize((max_width, new_height), Image.Resampling.LANCZOS)


def save_jpeg(img: Image.Image, out_path: pathlib.Path, quality: int) -> None:
    if img.mode not in ("RGB", "L"):
        bg = Image.new("RGB", img.size, "white")
        if img.mode == "RGBA":
            bg.paste(img, mask=img.getchannel("A"))
        else:
            bg.paste(img.convert("RGB"))
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img.save(out_path, "JPEG", quality=quality, optimize=True, progressive=True)


def split_and_save(img: Image.Image, base_path: pathlib.Path, cfg: CropConfig) -> list[pathlib.Path]:
    resized = resize_to_width(img, cfg.max_width)
    if resized.height <= cfg.max_height:
        save_jpeg(resized, base_path, cfg.quality)
        return [base_path]
    written: list[pathlib.Path] = []
    y = 0
    part = 1
    step = max(1, cfg.max_height - cfg.overlap)
    while y < resized.height:
        bottom = min(resized.height, y + cfg.max_height)
        tile = resized.crop((0, y, resized.width, bottom))
        out = base_path.with_name(f"{base_path.stem}-part-{part:02d}{base_path.suffix}")
        save_jpeg(tile, out, cfg.quality)
        written.append(out)
        if bottom >= resized.height:
            return written
        y += step
        part += 1
    return written


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def main(
    image: pathlib.Path = typer.Option(..., help="Full-page screenshot PNG"),
    review_map: pathlib.Path = typer.Option(..., help="review-map.json with section coordinates"),
    out: pathlib.Path = typer.Option(..., help="Output directory for cropped JPEGs"),
    manifest: pathlib.Path = typer.Option(..., help="Output manifest JSON path"),
    max_width: int = typer.Option(1400, help="Max pixel width after resize"),
    max_height: int = typer.Option(1800, help="Max pixel height per tile"),
    quality: int = typer.Option(82, help="JPEG quality (1-100)"),
):
    cfg = CropConfig(max_width=max_width, max_height=max_height, quality=quality)
    out.mkdir(parents=True, exist_ok=True)
    data = load_json(review_map)
    sections = data.get("sections", [])
    page = data.get("page", {})
    page_height = max(1, int(page.get("page_height") or 1))
    page_width = max(1, int(page.get("viewport_width") or page.get("page_width") or 1))
    full = Image.open(image)
    x_ratio = full.width / float(page_width)
    y_ratio = full.height / float(page_height)
    manifest_data = {
        "source_image": str(image),
        "source_size": [full.width, full.height],
        "page_css_size": [page_width, page_height],
        "scale": {"x": x_ratio, "y": y_ratio},
        "screenshots": [],
    }
    for section in sections:
        idx = int(section.get("index") or len(manifest_data["screenshots"]) + 1)
        heading = str(section.get("heading") or f"Section {idx}")
        top_css = max(0, float(section.get("top") or 0))
        bottom_css = min(float(section.get("bottom") or page_height), float(page_height))
        if bottom_css <= top_css:
            continue
        top_px = max(0, min(full.height - 1, int(math.floor(top_css * y_ratio))))
        bottom_px = max(top_px + 1, min(full.height, int(math.ceil(bottom_css * y_ratio))))
        if bottom_px - top_px < cfg.min_height:
            continue
        slug = slugify(heading, f"section-{idx}")
        base = out / f"{idx:02d}-{slug}.jpg"
        crop = full.crop((0, top_px, full.width, bottom_px))
        paths = split_and_save(crop, base, cfg)
        manifest_data["screenshots"].append({
            "section_index": idx,
            "heading": heading,
            "role_guess": section.get("role_guess"),
            "layer_guess": section.get("layer_guess"),
            "css_top": round(top_css),
            "css_bottom": round(bottom_css),
            "pixel_top": top_px,
            "pixel_bottom": bottom_px,
            "files": [str(p) for p in paths],
            "split_count": len(paths),
        })
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    app()
