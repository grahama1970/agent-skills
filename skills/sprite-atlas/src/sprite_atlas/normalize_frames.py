"""Common-scale and baseline normalization."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from sprite_atlas.contracts import MappingDocument, Profile, SourceBBox


@dataclass
class NormalizedFrame:
    animation: str
    target_row: int
    target_column: int
    image: Image.Image
    body_height: int
    baseline_y: int


def _body_bbox(image: Image.Image) -> SourceBBox | None:
    alpha = image.getchannel("A")
    box = alpha.getbbox()
    if box is None:
        return None
    return SourceBBox(box[0], box[1], box[2], box[3])


def normalize_frames(
    source: Image.Image,
    profile: Profile,
    mapping: MappingDocument,
) -> tuple[list[NormalizedFrame], list[dict[str, object]]]:
    bodies: list[tuple[NormalizedFrame, SourceBBox]] = []
    overflow: list[dict[str, object]] = []
    guard = profile.normalization.edge_guard_px
    frame_w = profile.atlas.frame_width
    frame_h = profile.atlas.frame_height
    usable_w = frame_w - guard * 2
    usable_h = frame_h - guard * 2

    for row in mapping.rows:
        for frame in row.frames:
            crop = source.crop(frame.source_bbox.as_list())
            bbox = _body_bbox(crop)
            if bbox is None:
                continue
            bodies.append(
                (
                    NormalizedFrame(
                        animation=row.animation,
                        target_row=row.target_row,
                        target_column=frame.target_column,
                        image=crop,
                        body_height=bbox.height,
                        baseline_y=bbox.y1,
                    ),
                    bbox,
                )
            )

    if not bodies:
        return [], overflow

    median_height = int(np.median([item[1].height for item in bodies]))
    target_body_h = max(1, usable_h - 4)
    global_scale = target_body_h / max(1, median_height)

    normalized: list[NormalizedFrame] = []
    target_baseline = frame_h - guard - 2

    for item, bbox in bodies:
        crop = item.image
        if global_scale <= 0:
            continue
        new_w = max(1, int(crop.width * global_scale))
        new_h = max(1, int(crop.height * global_scale))
        if new_w > usable_w or new_h > usable_h:
            overflow.append(
                {
                    "animation": item.animation,
                    "row": item.target_row,
                    "column": item.target_column,
                    "reason": "BLOCKED_FRAME_OVERFLOW",
                    "size": [new_w, new_h],
                    "usable": [usable_w, usable_h],
                }
            )
            continue
        resized = crop.resize((new_w, new_h), Image.Resampling.NEAREST)
        canvas = Image.new("RGBA", (frame_w, frame_h), (0, 0, 0, 0))
        x = (frame_w - new_w) // 2
        y = target_baseline - new_h
        if y < guard:
            overflow.append(
                {
                    "animation": item.animation,
                    "row": item.target_row,
                    "column": item.target_column,
                    "reason": "BLOCKED_FRAME_OVERFLOW",
                }
            )
            continue
        canvas.alpha_composite(resized, (x, y))
        normalized.append(
            NormalizedFrame(
                animation=item.animation,
                target_row=item.target_row,
                target_column=item.target_column,
                image=canvas,
                body_height=int(new_h),
                baseline_y=target_baseline,
            )
        )
    return normalized, overflow
