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


Image.init()

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


def _detect_row_bands(mask: np.ndarray) -> list[tuple[int, int]]:
    """Detect ordered content bands from a foreground mask."""

    rows = np.asarray(mask).astype(bool).any(axis=1)
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for index, present in enumerate(rows):
        if present and start is None:
            start = index
        elif not present and start is not None:
            if index - start > 1:
                bands.append((start, index))
            start = None
    if start is not None and len(rows) - start > 1:
        bands.append((start, len(rows)))
    return bands


def _isolate_main_subject(cell: Image.Image) -> Image.Image:
    """Drop tiny edge-connected slivers while preserving large edge VFX."""

    rgba = np.array(cell.convert("RGBA"))
    alpha = rgba[:, :, 3]
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats((alpha > 0).astype(np.uint8), 8)
    height, width = alpha.shape
    remove = np.zeros_like(alpha, dtype=bool)
    for label in range(1, count):
        x, y, w, h, area = stats[label]
        touches_edge = x == 0 or y == 0 or x + w >= width or y + h >= height
        thin_edge_sliver = touches_edge and (w <= max(4, int(width * 0.08)) or h <= max(4, int(height * 0.08)))
        tiny_edge_noise = touches_edge and area <= int(width * height * 0.04)
        if thin_edge_sliver or tiny_edge_noise:
            remove |= labels == label
    rgba[:, :, 3] = np.where(remove, 0, rgba[:, :, 3])
    return Image.fromarray(rgba, "RGBA")


def _detect_background_kind(image: Image.Image) -> str:
    rgba = np.array(image.convert("RGBA"))
    if not (rgba[:, :, 3] > 0).any():
        return "transparent"
    rgb = rgba[:, :, :3]
    if float(rgb.mean()) <= 85:
        return "dark"
    return "checker"


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


def _foreground_mask(image: Image.Image, *, background: str, lower: int, upper: int, neutral_spread: int) -> np.ndarray:
    rgba = np.array(image.convert("RGBA"))
    if background == "transparent":
        return rgba[:, :, 3] > 0
    rgb = rgba[:, :, :3]
    if background == "dark":
        brightness = rgb.max(axis=2)
        spread = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
        return ~((brightness <= 76) & (spread <= 30))
    near_light = (rgb >= lower).all(axis=2) & (rgb <= upper).all(axis=2)
    spread = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    neutral = spread <= neutral_spread
    return ~(near_light & neutral)


@app.command("convert-autogrid")
def convert_autogrid(
    source: Annotated[Path, typer.Option(help="Input generated sprite sheet with detectable row bands.")],
    sprite_id: Annotated[str, typer.Option(help="Stable Pixi variant id.")],
    out_png: Annotated[Path, typer.Option(help="Output transparent runtime atlas.")],
    out_json: Annotated[Path, typer.Option(help="PixiJS spritesheet JSON.")],
    frame_width: Annotated[int, typer.Option()] = 64,
    frame_height: Annotated[int, typer.Option()] = 64,
    columns: Annotated[int, typer.Option()] = 8,
    background: Annotated[str, typer.Option(help="auto, checker, dark, or transparent.")] = "auto",
    background_lower: Annotated[int, typer.Option()] = 200,
    background_upper: Annotated[int, typer.Option()] = 255,
    neutral_spread: Annotated[int, typer.Option()] = 42,
    row_pad: Annotated[int, typer.Option()] = 6,
    gutter: Annotated[int, typer.Option()] = 2,
    hold_last_frame: Annotated[bool, typer.Option()] = True,
) -> None:
    """Convert a loosely aligned generated sheet into the canonical 8x14 atlas."""

    image = Image.open(source).convert("RGBA")
    bg = _detect_background_kind(image) if background == "auto" else background
    mask = _foreground_mask(image, background=bg, lower=background_lower, upper=background_upper, neutral_spread=neutral_spread)
    bands = _detect_row_bands(mask)
    if len(bands) < len(ROWS):
        step = image.height / len(ROWS)
        bands = [(round(row * step), round((row + 1) * step)) for row in range(len(ROWS))]
    target = Image.new("RGBA", (columns * frame_width, len(ROWS) * frame_height), (0, 0, 0, 0))
    for row_index, (_animation_name, frame_count) in enumerate(ROWS):
        start, end = bands[row_index]
        start = max(0, start - row_pad)
        end = min(image.height, end + row_pad)
        previous: Image.Image | None = None
        for column in range(frame_count):
            left = round(column * image.width / columns)
            right = round((column + 1) * image.width / columns)
            cell = image.crop((left, start, right, end))
            if bg == "dark":
                cell = _remove_dark_edge_background(cell)
            elif bg == "checker":
                cell = _remove_checkerboard_from_cell(
                    cell,
                    lower=background_lower,
                    upper=background_upper,
                    neutral_spread=neutral_spread,
                )
            cell = _isolate_main_subject(cell)
            if not _cell_has_sprite(cell) and hold_last_frame and previous is not None:
                frame = previous.copy()
            else:
                frame = _fit_frame(cell, frame_width=frame_width, frame_height=frame_height, gutter=gutter)
                if _cell_has_sprite(frame):
                    previous = frame.copy()
            target.alpha_composite(frame, (column * frame_width, row_index * frame_height))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    target.save(out_png)
    _write_json(out_json, sprite_id=sprite_id, image_name=out_png.name, frame_width=frame_width, frame_height=frame_height, columns=columns)
    typer.echo(str(out_png))
    typer.echo(str(out_json))


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
