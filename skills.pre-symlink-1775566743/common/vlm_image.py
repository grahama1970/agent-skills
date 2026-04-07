"""VLM image preprocessing — prepare screenshots for multimodal LLM analysis.

Shared utility for any skill that sends screenshots to a VLM (Gemini Flash,
GPT-4V, Claude Vision). Handles the common pipeline:
    auto-crop → sharpen → upscale → compress → stitch

Usage:
    from common.vlm_image import prepare_for_vlm, auto_crop, stitch_vertical

    # Single image
    processed = prepare_for_vlm(raw_bytes, min_width=1200)

    # Multiple screenshots → single stitched image
    stitched = stitch_vertical([img1_bytes, img2_bytes, img3_bytes])

    # Crop a known UI region from a full-page screenshot
    cropped = smart_crop(raw_bytes, region="detail_panel", layout="three_pane")
"""
from __future__ import annotations

import io
from typing import Literal

from PIL import Image, ImageFilter

# ── Core transforms ──────────────────────────────────────────────────


def auto_crop(img: Image.Image, threshold: int = 15, padding: int = 4) -> Image.Image:
    """Trim dark borders (common in headless Chrome captures).

    Pixels with all channels <= threshold are considered border.
    """
    gray = img.convert("L")
    bbox = gray.point(lambda x: 255 if x > threshold else 0).getbbox()
    if not bbox:
        return img
    x1 = max(0, bbox[0] - padding)
    y1 = max(0, bbox[1] - padding)
    x2 = min(img.width, bbox[2] + padding)
    y2 = min(img.height, bbox[3] + padding)
    return img.crop((x1, y1, x2, y2))


def sharpen_text(img: Image.Image) -> Image.Image:
    """Enhance text edges for better VLM OCR accuracy."""
    return img.filter(ImageFilter.SHARPEN)


def upscale(img: Image.Image, min_width: int = 1200, max_height: int = 2000) -> Image.Image:
    """Upscale small images (panel closeups) to min_width for text readability.

    Also caps height at max_height to avoid huge VLM payloads.
    """
    if img.width < min_width and img.width > 50:
        scale = min_width / img.width
        img = img.resize((min_width, int(img.height * scale)), Image.LANCZOS)

    if img.height > max_height:
        scale = max_height / img.height
        img = img.resize((int(img.width * scale), max_height), Image.LANCZOS)

    return img


def compress(data: bytes, max_bytes: int = 500_000, jpeg_quality: int = 85) -> bytes:
    """Compress to JPEG if PNG exceeds max_bytes. VLMs handle JPEG fine."""
    if len(data) <= max_bytes:
        return data
    img = Image.open(io.BytesIO(data)).convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=jpeg_quality, optimize=True)
    return out.getvalue()


def to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    """Convert PIL Image to bytes."""
    out = io.BytesIO()
    img.save(out, format=fmt, optimize=True)
    return out.getvalue()


# ── Composite operations ─────────────────────────────────────────────


def prepare_for_vlm(
    data: bytes,
    min_width: int = 1200,
    max_height: int = 2000,
    max_bytes: int = 500_000,
) -> bytes:
    """Full preprocessing pipeline: auto-crop → upscale → sharpen → compress.

    Args:
        data: Raw PNG/JPEG screenshot bytes.
        min_width: Upscale to this width if smaller (for text readability).
        max_height: Cap height to avoid huge payloads.
        max_bytes: Compress to JPEG if exceeds this size.

    Returns:
        Processed image bytes ready for VLM consumption.
    """
    img = Image.open(io.BytesIO(data))
    img = auto_crop(img)
    img = upscale(img, min_width=min_width, max_height=max_height)
    img = sharpen_text(img)
    return compress(to_bytes(img), max_bytes=max_bytes)


def stitch_vertical(
    images: list[bytes],
    separator: int = 4,
    max_total_height: int = 3000,
    bg_color: tuple[int, int, int] = (20, 20, 20),
) -> bytes:
    """Stack multiple screenshots vertically into a single image.

    When a VLM caps at N images per request, stitching lets it see all
    context in one frame. Normalizes widths and adds thin separators.

    Args:
        images: List of image bytes to stitch.
        separator: Pixel height of separator between images.
        max_total_height: Scale down if total height exceeds this.
        bg_color: Separator/padding color.

    Returns:
        Single stitched image bytes (PNG).
    """
    if not images:
        return b""
    if len(images) == 1:
        return images[0]

    pil_images = [Image.open(io.BytesIO(data)) for data in images]

    # Normalize all to the same width
    max_w = max(img.width for img in pil_images)
    normalized = []
    for img in pil_images:
        if img.width < max_w:
            scale = max_w / img.width
            img = img.resize((max_w, int(img.height * scale)), Image.LANCZOS)
        normalized.append(img)

    # Calculate total height
    total_h = sum(img.height for img in normalized) + separator * (len(normalized) - 1)

    # Scale down if too tall
    if total_h > max_total_height:
        scale = max_total_height / total_h
        normalized = [
            img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
            for img in normalized
        ]
        total_h = sum(img.height for img in normalized) + separator * (len(normalized) - 1)
        max_w = max(img.width for img in normalized)

    stitched = Image.new("RGB", (max_w, total_h), bg_color)
    y = 0
    for img in normalized:
        stitched.paste(img, (0, y))
        y += img.height + separator

    return to_bytes(stitched)


def smart_crop(
    data: bytes,
    region: Literal["graph", "detail", "toolbar", "right_pane", "table"],
    viewport: tuple[int, int] = (1440, 900),
    layout: Literal["three_pane"] = "three_pane",
    upscale_to: int = 1200,
) -> bytes:
    """Crop a known UI region from a full-page screenshot.

    Coordinates are based on the Binary Explorer three-pane layout
    at the given viewport size. Scale proportionally for other sizes.

    Args:
        data: Full-page screenshot bytes.
        region: Which UI region to crop.
        viewport: Expected viewport dimensions.
        layout: Layout type (currently only three_pane).
        upscale_to: Upscale cropped region to this width.

    Returns:
        Cropped + upscaled image bytes.
    """
    img = Image.open(io.BytesIO(data))
    sx = img.width / viewport[0]
    sy = img.height / viewport[1]

    # Binary Explorer three-pane layout at 1440x900:
    #   Sidebar: 0-220px
    #   Graph pane: 220-940px, with topbar 0-70px, graph 70-530px, detail 530-900px
    #   Right pane (chat/journal): 940-1440px
    regions = {
        "graph": (int(220 * sx), int(70 * sy), int(940 * sx), int(530 * sy)),
        "detail": (int(220 * sx), int(530 * sy), int(940 * sx), int(900 * sy)),
        "toolbar": (int(220 * sx), 0, int(940 * sx), int(70 * sy)),
        "right_pane": (int(940 * sx), 0, img.width, img.height),
        "table": (int(220 * sx), int(560 * sy), int(940 * sx), int(900 * sy)),
    }

    box = regions.get(region)
    if not box:
        return data

    cropped = img.crop(box)
    cropped = upscale(cropped, min_width=upscale_to)
    cropped = sharpen_text(cropped)
    return compress(to_bytes(cropped))
