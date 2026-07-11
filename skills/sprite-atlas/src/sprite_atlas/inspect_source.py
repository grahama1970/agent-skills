"""Inspect source sheets and emit analysis artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from sprite_atlas.contracts import Profile
from sprite_atlas.detect_layout import detect_layout, render_segmentation_overlay
from sprite_atlas.map_frames import detected_counts, propose_mapping
from sprite_atlas.receipts import sha256_file, write_json
from sprite_atlas.remove_background import crop_metadata_panel, remove_presentation_background


def classify_background(image: Image.Image) -> str:
    rgb = np.array(image.convert("RGB"))
    light = ((rgb.min(axis=2) >= 200) & (rgb.max(axis=2) - rgb.min(axis=2) <= 42)).mean()
    dark = (rgb.max(axis=2) <= 76).mean()
    if light > 0.2:
        return "light_checkerboard"
    if dark > 0.2:
        return "dark_presentation"
    alpha = np.array(image.convert("RGBA"))[:, :, 3]
    if (alpha == 0).mean() > 0.1:
        return "transparent_runtime_candidate"
    return "unknown"


def inspect_source(*, source: Path, profile: Profile, job_dir: Path) -> dict[str, Any]:
    job_dir.mkdir(parents=True, exist_ok=True)
    raw = Image.open(source)
    background_type = classify_background(raw)
    cleaned = remove_presentation_background(crop_metadata_panel(raw))
    detected_rows = detect_layout(cleaned, profile)
    source_sha = sha256_file(source)
    mapping = propose_mapping(profile, detected_rows, source_sha256=source_sha)
    gaps = detected_counts(profile, detected_rows)

    rgba = np.array(raw.convert("RGBA"))
    analysis: dict[str, Any] = {
        "schema": "sprite_atlas.source_analysis.v1",
        "source": str(source),
        "source_sha256": source_sha,
        "dimensions": {"width": raw.width, "height": raw.height},
        "mode": raw.mode,
        "background_type": background_type,
        "alpha_range": [int(rgba[:, :, 3].min()), int(rgba[:, :, 3].max())] if rgba.ndim == 3 else None,
        "corner_rgba": [list(raw.convert("RGBA").getpixel((0, 0)))],
        "detected_rows": [
            {
                "row_index": row.row_index,
                "y0": row.y0,
                "y1": row.y1,
                "frame_count": len(row.frames),
                "frames": [frame.bbox.as_list() for frame in row.frames],
            }
            for row in detected_rows
        ],
        "frame_gaps": gaps,
    }
    write_json(job_dir / "source-analysis.json", analysis)
    render_segmentation_overlay(cleaned, detected_rows).save(job_dir / "segmentation-overlay.png")
    write_json(job_dir / "mapping.proposed.json", mapping.to_dict())
    return analysis
