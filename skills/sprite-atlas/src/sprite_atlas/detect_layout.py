"""Detect row bands and frame clusters without equal-grid cropping."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from sprite_atlas.contracts import Profile, SourceBBox


@dataclass
class DetectedFrame:
    bbox: SourceBBox
    row_index: int
    column_index: int
    area: int


@dataclass
class DetectedRow:
    row_index: int
    y0: int
    y1: int
    frames: list[DetectedFrame]


def _alpha_mask(image: Image.Image) -> np.ndarray:
    rgba = np.array(image.convert("RGBA"))
    return (rgba[:, :, 3] > 0).astype(np.uint8) * 255


def discover_row_bands(mask: np.ndarray, *, expected_rows: int, min_band_height: int = 40) -> list[tuple[int, int]]:
    projection = (mask > 0).sum(axis=1)
    active = projection > projection.max() * 0.02 if projection.max() else projection > 0
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for y, is_active in enumerate(active):
        if is_active and start is None:
            start = y
        elif not is_active and start is not None:
            if y - start >= min_band_height:
                bands.append((start, y))
            start = None
    if start is not None and mask.shape[0] - start >= min_band_height:
        bands.append((start, mask.shape[0]))

    if len(bands) == expected_rows:
        return bands

    # Fallback: split active vertical span into expected row count.
    ys = np.where(active)[0]
    if ys.size == 0:
        return []
    y0, y1 = int(ys[0]), int(ys[-1]) + 1
    span = y1 - y0
    return [
        (int(y0 + row * span / expected_rows), int(y0 + (row + 1) * span / expected_rows))
        for row in range(expected_rows)
    ]


def cluster_frames_in_row(mask: np.ndarray, y0: int, y1: int, *, min_area: int = 80) -> list[SourceBBox]:
    row = mask[y0:y1, :]
    n, labels, stats, _ = cv2.connectedComponentsWithStats(row, connectivity=8)
    boxes: list[SourceBBox] = []
    for label_id in range(1, n):
        area = int(stats[label_id, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x, y, w, h, _ = stats[label_id]
        pad = 2
        boxes.append(
            SourceBBox(
                max(0, int(x) - pad),
                max(0, int(y) + y0 - pad),
                min(mask.shape[1], int(x + w) + pad),
                min(mask.shape[0], int(y + h) + y0 + pad),
            )
        )
    boxes.sort(key=lambda box: box.x0)
    merged: list[SourceBBox] = []
    for box in boxes:
        if not merged:
            merged.append(box)
            continue
        prev = merged[-1]
        if box.x0 - prev.x1 <= 14 and abs((box.y0 + box.y1) - (prev.y0 + prev.y1)) < 30:
            merged[-1] = SourceBBox(
                min(prev.x0, box.x0),
                min(prev.y0, box.y0),
                max(prev.x1, box.x1),
                max(prev.y1, box.y1),
            )
        else:
            merged.append(box)
    return merged


def detect_layout(image: Image.Image, profile: Profile, *, label_strip_ratio: float = 0.12) -> list[DetectedRow]:
    width, height = image.size
    label_cut = int(width * label_strip_ratio)
    mask = _alpha_mask(image)
    if label_cut > 0:
        mask[:, :label_cut] = 0
    if height > profile.atlas.rows * 80:
        bands = [
            (int(row * height / profile.atlas.rows), int((row + 1) * height / profile.atlas.rows))
            for row in range(profile.atlas.rows)
        ]
    else:
        bands = discover_row_bands(mask, expected_rows=profile.atlas.rows)
    rows: list[DetectedRow] = []
    for row_index, (y0, y1) in enumerate(bands[: profile.atlas.rows]):
        frame_boxes = cluster_frames_in_row(mask, y0, y1)
        frames = [
            DetectedFrame(bbox=bbox, row_index=row_index, column_index=column_index, area=bbox.width * bbox.height)
            for column_index, bbox in enumerate(frame_boxes)
        ]
        rows.append(DetectedRow(row_index=row_index, y0=y0, y1=y1, frames=frames))
    return rows


def render_segmentation_overlay(image: Image.Image, rows: list[DetectedRow]) -> Image.Image:
    rgba = np.array(image.convert("RGBA")).copy()
    for row in rows:
        cv2.line(rgba, (0, row.y0), (rgba.shape[1] - 1, row.y0), (255, 64, 64, 200), 1)
        cv2.line(rgba, (0, row.y1), (rgba.shape[1] - 1, row.y1), (255, 64, 64, 200), 1)
        for frame in row.frames:
            cv2.rectangle(
                rgba,
                (frame.bbox.x0, frame.bbox.y0),
                (frame.bbox.x1 - 1, frame.bbox.y1 - 1),
                (64, 200, 255, 220),
                1,
            )
    return Image.fromarray(rgba, "RGBA")
