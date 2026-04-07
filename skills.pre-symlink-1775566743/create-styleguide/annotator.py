"""Pillow annotation engine — leader lines + token callouts on screenshots."""

from __future__ import annotations

import json
import os
from pathlib import Path

from loguru import logger
from PIL import Image, ImageDraw, ImageFont


# --- Shared helpers (same as create-design-board) ---

def _get_font(size: int = 14) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# --- Constants ---

ANNOTATION_COL_WIDTH = 280
BG_COLOR = _hex_to_rgb("#0e0e1c")
HIGHLIGHT_FILL = (74, 158, 255, 40)  # accent blue, low alpha
HIGHLIGHT_OUTLINE = (74, 158, 255, 180)
LEADER_COLOR = (255, 255, 255, 120)
LABEL_COLOR = (255, 255, 255, 220)
MUTED_COLOR = (255, 255, 255, 120)


# --- Region types ---

def load_regions(regions_path: Path) -> list[dict]:
    """Load region definitions from JSON file."""
    with open(regions_path) as f:
        return json.load(f)


def _default_regions(img_width: int, img_height: int) -> list[dict]:
    """Fallback: divide image into 3 horizontal bands."""
    top_h = int(img_height * 0.15)
    mid_h = int(img_height * 0.70)
    return [
        {"name": "header", "rect": [0, 0, img_width, top_h],
         "tokens": ["layout.header", "colors.background", "typography.header"]},
        {"name": "content", "rect": [0, top_h, img_width, top_h + mid_h],
         "tokens": ["layout.content", "colors.text.primary", "typography.body"]},
        {"name": "footer", "rect": [0, top_h + mid_h, img_width, img_height],
         "tokens": ["layout.footer", "colors.border", "typography.caption"]},
    ]


def _resolve_token_value(token_path: str, tokens: dict) -> str:
    """Walk dotted path into token dict, return value or '?'."""
    parts = token_path.split(".")
    node = tokens
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return "?"
    return str(node) if not isinstance(node, dict) else "{...}"


# --- Main annotation function ---

def annotate_screenshot(
    img_path: Path,
    tokens: dict,
    output_path: Path,
    regions: list[dict] | None = None,
) -> Path:
    """Annotate a single screenshot with token callouts.

    Returns path to annotated image.
    """
    img = Image.open(img_path).convert("RGBA")
    w, h = img.size

    if regions is None:
        regions = _default_regions(w, h)

    # Create extended canvas
    canvas_w = w + ANNOTATION_COL_WIDTH
    canvas = Image.new("RGBA", (canvas_w, h), BG_COLOR + (255,))
    canvas.paste(img, (0, 0))

    overlay = Image.new("RGBA", (canvas_w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_label = _get_font(12)
    font_value = _get_font(10)

    y_cursor = 10  # vertical position in annotation column

    for region in regions:
        rect = region["rect"]  # [x1, y1, x2, y2]
        x1, y1, x2, y2 = rect

        # Draw highlight rectangle on the screenshot area
        draw.rectangle([x1, y1, x2, y2], fill=HIGHLIGHT_FILL, outline=HIGHLIGHT_OUTLINE, width=1)

        # Region name label in annotation column
        label_x = w + 12
        draw.text((label_x, y_cursor), region["name"], fill=LABEL_COLOR, font=font_label)
        y_cursor += 18

        # Leader line from region midpoint to annotation column
        mid_y = (y1 + y2) // 2
        draw.line([(x2, mid_y), (w + 4, y_cursor)], fill=LEADER_COLOR, width=1)

        # Token callouts
        for token_path in region.get("tokens", []):
            value = _resolve_token_value(token_path, tokens)
            text = f"  {token_path}: {value}"
            draw.text((label_x, y_cursor), text, fill=MUTED_COLOR, font=font_value)
            y_cursor += 14

        y_cursor += 10  # gap between regions

    # Composite overlay
    canvas = Image.alpha_composite(canvas, overlay)
    result = canvas.convert("RGB")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, "PNG")
    logger.info(f"Annotated: {output_path}")
    return output_path


def annotate_screenshots(
    screenshots_dir: Path,
    tokens: dict,
    output_dir: Path,
    regions: list[dict] | None = None,
) -> list[Path]:
    """Annotate all PNGs in a directory. Returns list of output paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for img_path in sorted(screenshots_dir.glob("*.png")):
        out = output_dir / f"annotated-{img_path.name}"
        annotate_screenshot(img_path, tokens, out, regions)
        results.append(out)
    return results
