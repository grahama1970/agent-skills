"""Render PDF pages and crop element bounding boxes."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from loguru import logger
from PIL import Image

_SCREENSHOT_DIR = Path("${HOME}/workspace/experiments/pi-mono/.pi/skills/pdf-screenshot")
if str(_SCREENSHOT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCREENSHOT_DIR))

from pdf_screenshot import screenshot_page  # noqa: E402


def render_page(pdf_path: Path, page_num: int, dpi: int = 150) -> Path:
    """Render a single PDF page to PNG via pdf-screenshot."""
    out = screenshot_page(str(pdf_path), page_num, dpi=dpi)
    logger.debug("Rendered page {} of {} -> {}", page_num, pdf_path.name, out)
    return Path(out)


def crop_element(
    page_image: Path,
    bbox: tuple[float, float, float, float],
    page_height: float,
    dpi: int = 150,
) -> Path:
    """Crop a PDF element bbox from a rendered page image.

    bbox is (x, y, width, height) in PDF coords (origin bottom-left).
    """
    img = Image.open(page_image)
    scale = dpi / 72.0
    pdf_x, pdf_y, pdf_w, pdf_h = bbox
    px_left = pdf_x * scale
    px_top = (page_height - pdf_y - pdf_h) * scale
    px_right = (pdf_x + pdf_w) * scale
    px_bottom = (page_height - pdf_y) * scale
    pad = 5
    crop_box = (
        max(0, int(px_left - pad)),
        max(0, int(px_top - pad)),
        min(img.width, int(px_right + pad)),
        min(img.height, int(px_bottom + pad)),
    )
    cropped = img.crop(crop_box)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    cropped.save(tmp.name)
    return Path(tmp.name)


def render_and_crop_elements(
    pdf_path: Path, page_num: int, blocks: list[dict], page_height: float
) -> list[dict]:
    """Render page once, crop each block that has a bbox. Returns enriched block dicts."""
    page_img = render_page(pdf_path, page_num)
    results = []
    for blk in blocks:
        bbox = blk.get("bbox")
        # Fast path: reuse existing image if available
        src = (blk.get("source_meta") or {}).get("image_path")
        if src and Path(src).exists():
            img_path = Path(src)
        elif bbox:
            img_path = crop_element(page_img, tuple(bbox), page_height)
        else:
            img_path = None
        results.append({
            "block_type": blk.get("block_type"),
            "text": blk.get("text", ""),
            "image_path": str(img_path) if img_path else None,
            "bbox": bbox,
        })
    return results
