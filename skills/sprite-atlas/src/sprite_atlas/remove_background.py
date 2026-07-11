"""Edge-connected background removal for presentation sheets."""

from __future__ import annotations

from collections import deque

import numpy as np
from PIL import Image


def _is_light_background(rgb: np.ndarray, *, lower: int = 200, spread: int = 42) -> np.ndarray:
    low = rgb.min(axis=2)
    high = rgb.max(axis=2)
    return (low >= lower) & ((high - low) <= spread)


def _is_dark_background(rgb: np.ndarray, *, max_channel: int = 76, spread: int = 30) -> np.ndarray:
    high = rgb.max(axis=2)
    low = rgb.min(axis=2)
    return (high <= max_channel) & ((high - low) <= spread)


def edge_connected_mask(mask: np.ndarray) -> np.ndarray:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=np.uint8)
    out = np.zeros_like(mask, dtype=np.uint8)
    queue: deque[tuple[int, int]] = deque()

    def enqueue(x: int, y: int) -> None:
        if visited[y, x] or not mask[y, x]:
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
            if visited[ny, nx] or not mask[ny, nx]:
                continue
            visited[ny, nx] = 1
            queue.append((nx, ny))
    return out


def remove_presentation_background(image: Image.Image) -> Image.Image:
    """Remove edge-connected light checkerboard and dark presentation backgrounds."""

    rgba = np.array(image.convert("RGBA"))
    rgb = rgba[:, :, :3]
    light = _is_light_background(rgb)
    dark = _is_dark_background(rgb)
    background = light | dark
    connected = edge_connected_mask(background)
    rgba[:, :, 3] = np.where(connected > 0, 0, rgba[:, :, 3])
    return Image.fromarray(rgba, "RGBA")


def crop_metadata_panel(image: Image.Image, *, min_width: int = 900) -> Image.Image:
    """Drop right-side metadata columns common on contact sheets."""

    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width < min_width:
        return rgba
    rgb = np.array(rgba)[:, :, :3]
    column_variance = rgb.var(axis=(0, 2))
    threshold = float(np.percentile(column_variance, 92))
    text_columns = np.where(column_variance > threshold * 0.35)[0]
    if text_columns.size == 0:
        return rgba
    grid_right = int(text_columns[0])
    if width - grid_right < 80 or grid_right < width * 0.7:
        return rgba
    return rgba.crop((0, 0, grid_right, height))
