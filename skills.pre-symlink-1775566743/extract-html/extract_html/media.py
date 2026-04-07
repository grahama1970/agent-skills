"""media - extract_html.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
import io

import httpx
from bs4 import BeautifulSoup
from loguru import logger
from PIL import Image


@dataclass
class MediaItem:
    src_raw: str
    src_resolved: str
    alt: Optional[str]
    width: Optional[int]
    height: Optional[int]
    area: Optional[int]
    kind: str  # "image" | "video" (we only process images here)
    status: str  # "ok" | "skipped" | "error"
    reason: Optional[str] = None


def _is_remote(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in ("http", "https")


def discover_images(html: str, *, html_path: Path) -> List[Dict[str, Any]]:
    """
    Returns list of dicts: {src_raw, src_resolved, alt}
    - Resolves relative paths against the HTML file directory.
    - Keeps original src as seen in the HTML.
    """
    soup = BeautifulSoup(html, "lxml")
    base_dir = html_path.parent

    out: List[Dict[str, Any]] = []
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src:
            continue
        alt = img.get("alt")
        alt = alt.strip() if isinstance(alt, str) else None

        # Resolve:
        if _is_remote(src):
            resolved = src
        else:
            # local relative path
            # Handle potential absolute paths or complex joins if needed, 
            # but for now assume strict relative to HTML dir if not http
            try:
                resolved = str((base_dir / src).resolve())
            except Exception:
                resolved = src # Fallback

        out.append({"src_raw": src, "src_resolved": resolved, "alt": alt})
    return out


def load_image_bytes(
    src_resolved: str,
    *,
    fetch_remote: bool,
    timeout_s: float = 30.0,
) -> Optional[bytes]:
    """
    Loads image bytes from:
    - local file path
    - remote http(s) if fetch_remote=True
    """
    try:
        if _is_remote(src_resolved):
            if not fetch_remote:
                return None
            with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
                r = client.get(src_resolved)
                r.raise_for_status()
                return r.content
        else:
            p = Path(src_resolved)
            if not p.exists():
                return None
            return p.read_bytes()
    except Exception as e:
        logger.warning("Failed to load image {}: {}", src_resolved, e)
        return None


def image_dimensions(image_bytes: bytes) -> tuple[Optional[int], Optional[int]]:
    try:
        im = Image.open(io.BytesIO(image_bytes))
        return int(im.width), int(im.height)
    except Exception:
        return None, None


def filter_media_by_pixels(
    discovered: List[Dict[str, Any]],
    *,
    fetch_remote: bool,
    min_area: int,
    max_area: int,
    min_dim: int,
) -> List[MediaItem]:
    """
    Loads images to measure pixel size; returns MediaItems with status.
    """
    items: List[MediaItem] = []

    for d in discovered:
        src_raw = d["src_raw"]
        src_resolved = d["src_resolved"]
        alt = d.get("alt")

        b = load_image_bytes(src_resolved, fetch_remote=fetch_remote)
        if b is None:
            items.append(
                MediaItem(
                    src_raw=src_raw,
                    src_resolved=src_resolved,
                    alt=alt,
                    width=None,
                    height=None,
                    area=None,
                    kind="image",
                    status="skipped",
                    reason="remote_fetch_disabled_or_load_failed",
                )
            )
            continue

        w, h = image_dimensions(b)
        if not w or not h:
            items.append(
                MediaItem(
                    src_raw=src_raw,
                    src_resolved=src_resolved,
                    alt=alt,
                    width=w,
                    height=h,
                    area=None,
                    kind="image",
                    status="skipped",
                    reason="cannot_read_dimensions",
                )
            )
            continue

        area = w * h
        if w < min_dim or h < min_dim:
            items.append(
                MediaItem(
                    src_raw=src_raw,
                    src_resolved=src_resolved,
                    alt=alt,
                    width=w,
                    height=h,
                    area=area,
                    kind="image",
                    status="skipped",
                    reason=f"below_min_dim({min_dim})",
                )
            )
            continue

        if area < min_area:
            items.append(
                MediaItem(
                    src_raw=src_raw,
                    src_resolved=src_resolved,
                    alt=alt,
                    width=w,
                    height=h,
                    area=area,
                    kind="image",
                    status="skipped",
                    reason=f"below_min_area({min_area})",
                )
            )
            continue

        if area > max_area:
            items.append(
                MediaItem(
                    src_raw=src_raw,
                    src_resolved=src_resolved,
                    alt=alt,
                    width=w,
                    height=h,
                    area=area,
                    kind="image",
                    status="skipped",
                    reason=f"above_max_area({max_area})",
                )
            )
            continue

        items.append(
            MediaItem(
                src_raw=src_raw,
                src_resolved=src_resolved,
                alt=alt,
                width=w,
                height=h,
                area=area,
                kind="image",
                status="ok",
            )
        )

    return items


def to_media_context(items: List[MediaItem], extracted_text: Dict[str, str]) -> Dict[str, Any]:
    """
    Builds JSON context for Schematron:
    includes src_raw, src_resolved, alt, dims, and extracted text (if any).
    """
    out = []
    for it in items:
        entry = {
            "src": it.src_raw,                 # original URL/path as in HTML
            "resolved_src": it.src_resolved,   # resolved local path or remote URL
            "alt": it.alt,
            "width": it.width,
            "height": it.height,
            "area": it.area,
            "status": it.status,
            "reason": it.reason,
        }
        if it.status == "ok":
            entry["text"] = extracted_text.get(it.src_resolved)
        
        out.append(entry)
    return {"media_text": out}
