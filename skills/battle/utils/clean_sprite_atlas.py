#!/usr/bin/env python3
"""Build PixiJS-compatible BATTLE sprite atlases from generated contact sheets.

The runtime contract is an 8x14 atlas of 64x64 frames plus PixiJS spritesheet
JSON. The checkerboard path uses OpenCV/NumPy to mask near-white and light-gray
fake transparency, then removes only background components connected to the
edge of each frame cell.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Annotated

import cv2
import numpy as np
import typer
from PIL import Image


app = typer.Typer(no_args_is_help=True)

ROWS: tuple[tuple[str, int], ...] = (
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


def _build_manifest(*, sprite_id: str, image: str, frame_width: int, frame_height: int, columns: int) -> dict[str, object]:
    frames: dict[str, object] = {}
    animations: dict[str, list[str]] = {}
    for row_index, (animation_name, frame_count) in enumerate(ROWS):
        frame_names: list[str] = []
        for column_index in range(frame_count):
            frame_name = f"{sprite_id}_{animation_name}_{column_index}"
            frame_names.append(frame_name)
            frames[frame_name] = {
                "frame": {
                    "x": column_index * frame_width,
                    "y": row_index * frame_height,
                    "w": frame_width,
                    "h": frame_height,
                },
                "sourceSize": {"w": frame_width, "h": frame_height},
                "spriteSourceSize": {"x": 0, "y": 0, "w": frame_width, "h": frame_height},
            }
        animations[animation_name] = frame_names
    return {
        "frames": frames,
        "animations": animations,
        "meta": {
            "image": image,
            "format": "RGBA8888",
            "scale": "1",
            "battle": {
                "variant_id": sprite_id,
                "frameWidth": frame_width,
                "frameHeight": frame_height,
                "columns": columns,
                "rows": len(ROWS),
                "margin": 0,
                "spacing": 0,
                "anchor": {"x": 0.5, "y": 0.85},
                "style": "original_16bit_grimdark_scifi_pixel_art",
                "usage": "pixijs-v8",
            },
        },
    }


def _edge_connected_mask(mask: np.ndarray) -> np.ndarray:
    """Return mask components connected to any image edge."""

    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=np.uint8)
    out = np.zeros_like(mask, dtype=np.uint8)
    queue: deque[tuple[int, int]] = deque()

    def enqueue(x: int, y: int) -> None:
        if visited[y, x] or mask[y, x] == 0:
            return
        visited[y, x] = 1
        queue.append((x, y))

    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    for y in range(height):
        enqueue(0, y)
        enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        out[y, x] = 255
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or nx >= width or ny < 0 or ny >= height:
                continue
            if visited[ny, nx] or mask[ny, nx] == 0:
                continue
            visited[ny, nx] = 1
            queue.append((nx, ny))
    return out


def _remove_checkerboard_from_cell(cell: Image.Image, *, lower: int, upper: int, neutral_spread: int) -> Image.Image:
    rgba = np.array(cell.convert("RGBA"))
    rgb = rgba[:, :, :3]
    near_light = cv2.inRange(rgb, np.array([lower, lower, lower], dtype=np.uint8), np.array([upper, upper, upper], dtype=np.uint8))
    spread = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    neutral = (spread <= neutral_spread).astype(np.uint8) * 255
    mask = cv2.bitwise_and(near_light, neutral)
    kernel = np.ones((2, 2), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    background = _edge_connected_mask(mask)
    rgba[:, :, 3] = np.where(background > 0, 0, rgba[:, :, 3])
    return Image.fromarray(rgba, "RGBA")


def _is_dark_background(pixel: tuple[int, int, int, int]) -> bool:
    red, green, blue, alpha = pixel
    return alpha == 0 or (max(red, green, blue) <= 76 and max(red, green, blue) - min(red, green, blue) <= 30)


def _remove_dark_edge_background(cell: Image.Image) -> Image.Image:
    rgba = cell.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def enqueue(x: int, y: int) -> None:
        index = y * width + x
        if visited[index]:
            return
        visited[index] = 1
        if _is_dark_background(pixels[x, y]):
            queue.append((x, y))

    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    for y in range(height):
        enqueue(0, y)
        enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        red, green, blue, _alpha = pixels[x, y]
        pixels[x, y] = (red, green, blue, 0)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or nx >= width or ny < 0 or ny >= height:
                continue
            index = ny * width + nx
            if visited[index]:
                continue
            visited[index] = 1
            if _is_dark_background(pixels[nx, ny]):
                queue.append((nx, ny))
    return rgba


def _fit_frame(cell: Image.Image, *, frame_width: int, frame_height: int, gutter: int = 0) -> Image.Image:
    rgba = cell.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    out = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
    if bbox is None:
        return out
    sprite = rgba.crop(bbox)
    scale = min((frame_width - gutter * 2) / sprite.width, (frame_height - gutter * 2) / sprite.height)
    resized = sprite.resize((max(1, int(sprite.width * scale)), max(1, int(sprite.height * scale))), Image.Resampling.NEAREST)
    out.alpha_composite(resized, ((frame_width - resized.width) // 2, frame_height - resized.height - gutter))
    return out


def _write_json(out_json: Path, *, sprite_id: str, image_name: str, frame_width: int, frame_height: int, columns: int) -> None:
    manifest = _build_manifest(
        sprite_id=sprite_id,
        image=image_name,
        frame_width=frame_width,
        frame_height=frame_height,
        columns=columns,
    )
    out_json.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _grid_cell(image: Image.Image, *, row: int, column: int, rows: int, columns: int) -> Image.Image:
    width, height = image.size
    return image.crop(
        (
            round(column * width / columns),
            round(row * height / rows),
            round((column + 1) * width / columns),
            round((row + 1) * height / rows),
        )
    )


@app.command()
def clean_checkerboard(
    source: Annotated[Path, typer.Option(help="Input light checkerboard contact sheet.")],
    sprite_id: Annotated[str, typer.Option(help="Stable Pixi variant id.")],
    out_png: Annotated[Path, typer.Option(help="Output 512x896 transparent runtime atlas.")],
    out_json: Annotated[Path | None, typer.Option(help="Optional PixiJS spritesheet JSON.")] = None,
    frame_width: Annotated[int, typer.Option()] = 64,
    frame_height: Annotated[int, typer.Option()] = 64,
    columns: Annotated[int, typer.Option()] = 8,
    background_lower: Annotated[int, typer.Option(help="Lower RGB threshold for light fake transparency.")] = 200,
    background_upper: Annotated[int, typer.Option(help="Upper RGB threshold for light fake transparency.")] = 255,
    neutral_spread: Annotated[int, typer.Option(help="Max RGB spread for neutral checker/grid pixels.")] = 42,
) -> None:
    """Remove baked light checkerboard background and emit runtime atlas."""

    image = Image.open(source).convert("RGBA")
    target = Image.new("RGBA", (columns * frame_width, len(ROWS) * frame_height), (0, 0, 0, 0))
    for row_index, (_animation_name, frame_count) in enumerate(ROWS):
        for column in range(frame_count):
            cell = _grid_cell(image, row=row_index, column=column, rows=len(ROWS), columns=columns)
            if column == 0:
                cell = _strip_row_label(cell, label_strip_ratio=0.34)
            cell = _trim_presentation_gutter(cell)
            cell = _remove_checkerboard_from_cell(cell, lower=background_lower, upper=background_upper, neutral_spread=neutral_spread)
            frame = _fit_frame(cell, frame_width=frame_width, frame_height=frame_height, gutter=2)
            target.alpha_composite(frame, (column * frame_width, row_index * frame_height))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    target.save(out_png)
    if out_json:
        _write_json(out_json, sprite_id=sprite_id, image_name=out_png.name, frame_width=frame_width, frame_height=frame_height, columns=columns)
    typer.echo(str(out_png))


@app.command()
def clean_dark_grid(
    source: Annotated[Path, typer.Option(help="Input dark grid contact sheet.")],
    sprite_id: Annotated[str, typer.Option(help="Stable Pixi variant id.")],
    out_png: Annotated[Path, typer.Option(help="Output 512x896 transparent runtime atlas.")],
    out_json: Annotated[Path | None, typer.Option(help="Optional PixiJS spritesheet JSON.")] = None,
    frame_width: Annotated[int, typer.Option()] = 64,
    frame_height: Annotated[int, typer.Option()] = 64,
    columns: Annotated[int, typer.Option()] = 8,
) -> None:
    """Clean a dark presentation-grid sheet into the runtime row contract."""

    image = Image.open(source).convert("RGBA")
    source_rows = 13
    target = Image.new("RGBA", (columns * frame_width, len(ROWS) * frame_height), (0, 0, 0, 0))
    for source_row in range(source_rows):
        target_row = source_row if source_row < 9 else source_row + 1
        for column in range(columns):
            cell = _grid_cell(image, row=source_row, column=column, rows=source_rows, columns=columns)
            cell = _remove_dark_edge_background(cell)
            frame = _fit_frame(cell, frame_width=frame_width, frame_height=frame_height, gutter=2)
            target.alpha_composite(frame, (column * frame_width, target_row * frame_height))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    target.save(out_png)
    if out_json:
        _write_json(out_json, sprite_id=sprite_id, image_name=out_png.name, frame_width=frame_width, frame_height=frame_height, columns=columns)
    typer.echo(str(out_png))



def _content_mask(rgb: np.ndarray, kind: str) -> np.ndarray:
    """Boolean mask of sprite content vs background, keyed on background kind."""

    lum = rgb.mean(axis=2)
    spread = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    if kind == "dark":
        return lum > 60
    # checker / light grid: content is saturated OR clearly darker than the grid.
    return (spread > 28) | (lum < 150)


def _detect_background_kind(image: Image.Image) -> str:
    """Classify the sheet background from its corners: transparent / dark / checker."""

    rgba = np.array(image.convert("RGBA"))
    height, width, _ = rgba.shape
    corners = np.array(
        [rgba[0, 0], rgba[0, width - 1], rgba[height - 1, 0], rgba[height - 1, width - 1]],
        dtype=int,
    )
    if (corners[:, 3] < 16).all():
        return "transparent"
    if (corners[:, :3].mean(axis=1) < 60).all():
        return "dark"
    return "checker"


def _detect_row_bands(mask: np.ndarray) -> list[tuple[int, int]]:
    """Detect content bands via row projection so drifting (non-uniform) rows still slice cleanly."""

    height, width = mask.shape
    rowsum = mask.sum(axis=1)
    threshold = width * 0.01
    bands: list[tuple[int, int]] = []
    index = 0
    while index < height:
        if rowsum[index] > threshold:
            end = index
            while end < height and rowsum[end] > threshold:
                end += 1
            bands.append((index, end - 1))
            index = end
        else:
            index += 1
    return bands


def _uniform_bands(height: int, row_count: int) -> list[tuple[int, int]]:
    step = height / row_count
    return [(round(r * step), round((r + 1) * step) - 1) for r in range(row_count)]


def _isolate_main_subject(
    cell: Image.Image,
    *,
    edge_sliver_area_frac: float = 0.12,
    edge_sliver_width_frac: float = 0.18,
) -> Image.Image:
    """Drop thin fragments hugging a side edge — the neighbour-frame bleed sliver.

    Keeps the largest component and every substantial component (so attached
    VFX like dust, orbs, or projectiles survive); removes only small, narrow
    fragments touching the left/right edge, which is exactly the column-bleed
    artifact from slicing a slightly-misaligned generator grid.
    """

    rgba = np.array(cell.convert("RGBA"))
    alpha = (rgba[:, :, 3] > 16).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(alpha, connectivity=8)
    if num <= 2:
        return cell
    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = int(np.argmax(areas)) + 1
    largest_area = int(stats[largest, cv2.CC_STAT_AREA])
    _, width = alpha.shape
    drop_labels: list[int] = []
    for label in range(1, num):
        if label == largest:
            continue
        left = stats[label, cv2.CC_STAT_LEFT]
        cell_width = stats[label, cv2.CC_STAT_WIDTH]
        area = stats[label, cv2.CC_STAT_AREA]
        touches_edge = left == 0 or (left + cell_width) >= width
        very_narrow = cell_width <= 4  # a few-px-wide edge strip is bleed regardless of height
        smallish = area < largest_area * edge_sliver_area_frac and cell_width < width * edge_sliver_width_frac
        if touches_edge and (very_narrow or smallish):
            drop_labels.append(label)
    if not drop_labels:
        return cell
    rgba[np.isin(labels, drop_labels), 3] = 0
    return Image.fromarray(rgba, "RGBA")


@app.command("convert-autogrid")
def convert_autogrid(
    source: Annotated[Path, typer.Option(help="Input contact sheet (checker / dark / transparent bg).")],
    sprite_id: Annotated[str, typer.Option(help="Stable Pixi variant id.")],
    out_png: Annotated[Path, typer.Option(help="Output 512x896 transparent runtime atlas.")],
    out_json: Annotated[Path | None, typer.Option(help="Optional PixiJS spritesheet JSON.")] = None,
    frame_width: Annotated[int, typer.Option()] = 64,
    frame_height: Annotated[int, typer.Option()] = 64,
    columns: Annotated[int, typer.Option()] = 8,
    background: Annotated[str, typer.Option(help="Background kind: auto | checker | dark | transparent.")] = "auto",
    background_lower: Annotated[int, typer.Option()] = 200,
    background_upper: Annotated[int, typer.Option()] = 255,
    neutral_spread: Annotated[int, typer.Option()] = 42,
    row_pad: Annotated[int, typer.Option(help="Vertical padding around each detected band so tall sprites are not clipped.")] = 6,
    gutter: Annotated[int, typer.Option()] = 2,
    hold_last_frame: Annotated[bool, typer.Option(help="Fill a trailing empty canonical cell by holding the last drawn frame (generators often under-draw a row).")] = True,
) -> None:
    """One-shot: auto-detect row bands + background, de-sliver, emit the runtime atlas.

    Handles AI-generated contact sheets whose rows drift off a uniform grid (the
    common failure mode that makes `clean-checkerboard`/`convert-contact-sheet`
    clip tall sprites). Row bands are detected by content projection, columns are
    sliced by the canonical per-row frame counts, each cell is de-slivered, and
    every canonical frame is placed. Input image -> 512x896 canonical atlas.
    """

    image = Image.open(source)
    kind = _detect_background_kind(image) if background == "auto" else background
    if kind == "transparent":
        mask = np.array(image.convert("RGBA"))[:, :, 3] > 16
    else:
        mask = _content_mask(np.array(image.convert("RGB")), kind)

    bands = _detect_row_bands(mask)
    detected = len(bands) == len(ROWS)
    source_to_target = [(index, index) for index in range(len(bands))]
    if len(bands) == len(ROWS) - 1:
        # Some early contact sheets have 13 source rows and omit the canonical
        # hit row. Preserve detected bands and map rows after blocked forward,
        # matching clean_dark_grid; a forced 14-row uniform grid mis-slices VFX.
        source_to_target = [(index, index if index < 9 else index + 1) for index in range(len(bands))]
        detected = True
    if not detected:
        typer.echo(
            f"WARN: detected {len(bands)} row bands, expected {len(ROWS)}; using uniform grid",
            err=True,
        )
        bands = _uniform_bands(image.height, len(ROWS))
        source_to_target = [(index, index) for index in range(len(bands))]

    src = image.convert("RGBA")
    target = Image.new("RGBA", (columns * frame_width, len(ROWS) * frame_height), (0, 0, 0, 0))
    col_w = image.width / columns
    placed = 0
    for source_row_index, target_row_index in source_to_target:
        _name, count = ROWS[target_row_index]
        y0, y1 = bands[source_row_index]
        top = max(0, y0 - row_pad)
        bottom = min(image.height, y1 + row_pad)
        last_frame: Image.Image | None = None
        for column in range(count):
            cell = src.crop((round(column * col_w), top, round((column + 1) * col_w), bottom))
            if kind == "dark":
                cell = _remove_dark_edge_background(cell)
            elif kind != "transparent":
                cell = _remove_checkerboard_from_cell(
                    cell, lower=background_lower, upper=background_upper, neutral_spread=neutral_spread
                )
            cell = _isolate_main_subject(cell)
            frame = _fit_frame(cell, frame_width=frame_width, frame_height=frame_height, gutter=gutter)
            if _cell_has_sprite(frame):
                last_frame = frame
            elif hold_last_frame and last_frame is not None:
                frame = last_frame  # generator under-drew this row: hold the last frame, no gap
            target.alpha_composite(frame, (column * frame_width, target_row_index * frame_height))
            placed += 1

    out_png.parent.mkdir(parents=True, exist_ok=True)
    target.save(out_png)
    if out_json:
        _write_json(out_json, sprite_id=sprite_id, image_name=out_png.name, frame_width=frame_width, frame_height=frame_height, columns=columns)
    typer.echo(f"{out_png} rows={'detected' if detected else 'uniform'} source_rows={len(bands)} frames={placed} bg={kind}")


def _strip_row_label(cell: Image.Image, *, label_strip_ratio: float) -> Image.Image:
    """Remove the left presentation label band common in BATTLE contact sheets."""

    if label_strip_ratio <= 0:
        return cell
    width, height = cell.size
    cut = min(width - 8, max(0, int(width * label_strip_ratio)))
    if cut <= 0:
        return cell
    return cell.crop((cut, 0, width, height))


def _trim_presentation_gutter(cell: Image.Image, *, top: int = 3, right: int = 3, bottom: int = 4, left: int = 3) -> Image.Image:
    """Drop presentation grid borders that bleed into runtime frames."""

    width, height = cell.size
    if width <= left + right + 8 or height <= top + bottom + 8:
        return cell
    return cell.crop((left, top, width - right, height - bottom))


def _cell_has_sprite(cell: Image.Image) -> bool:
    alpha = cell.convert("RGBA").getchannel("A")
    return alpha.getbbox() is not None


@app.command("convert-contact-sheet")
def convert_contact_sheet(
    source: Annotated[Path, typer.Option(help="BATTLE contact sheet PNG (948x1659 checkerboard).")],
    sprite_id: Annotated[str, typer.Option(help="Stable Pixi variant id.")],
    out_png: Annotated[Path, typer.Option(help="Output 512x896 transparent runtime atlas.")],
    out_json: Annotated[Path, typer.Option(help="PixiJS spritesheet JSON.")],
    frame_width: Annotated[int, typer.Option()] = 64,
    frame_height: Annotated[int, typer.Option()] = 64,
    columns: Annotated[int, typer.Option()] = 8,
    source_rows: Annotated[int, typer.Option(help="Rows in the contact sheet image.")] = 14,
    label_strip_ratio: Annotated[float, typer.Option(help="Strip left label band from column 0 cells.")] = 0.34,
    background_lower: Annotated[int, typer.Option()] = 200,
    background_upper: Annotated[int, typer.Option()] = 255,
    neutral_spread: Annotated[int, typer.Option()] = 42,
) -> None:
    """Convert a labeled BATTLE contact sheet into a PixiJS runtime atlas."""

    image = Image.open(source).convert("RGBA")
    target = Image.new("RGBA", (columns * frame_width, len(ROWS) * frame_height), (0, 0, 0, 0))

    for target_row, (animation_name, frame_count) in enumerate(ROWS):
        source_row = target_row if source_rows == len(ROWS) else (target_row if target_row < 9 else target_row - 1)
        if source_row >= source_rows:
            continue
        for column in range(frame_count):
            cell = _grid_cell(image, row=source_row, column=column, rows=source_rows, columns=columns)
            if column == 0:
                cell = _strip_row_label(cell, label_strip_ratio=label_strip_ratio)
            cell = _trim_presentation_gutter(cell)
            cell = _remove_checkerboard_from_cell(
                cell,
                lower=background_lower,
                upper=background_upper,
                neutral_spread=neutral_spread,
            )
            frame = _fit_frame(cell, frame_width=frame_width, frame_height=frame_height, gutter=2)
            if not _cell_has_sprite(frame):
                typer.echo(
                    f"WARN: empty frame {animation_name}[{column}] from {source.name} row {source_row}",
                    err=True,
                )
            target.alpha_composite(frame, (column * frame_width, target_row * frame_height))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    target.save(out_png)
    _write_json(
        out_json,
        sprite_id=sprite_id,
        image_name=out_png.name,
        frame_width=frame_width,
        frame_height=frame_height,
        columns=columns,
    )
    typer.echo(str(out_png))
    typer.echo(str(out_json))

if __name__ == "__main__":
    app()
