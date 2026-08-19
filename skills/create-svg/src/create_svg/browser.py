"""Real Chromium verification for SVGs embedded through a README-like img element.

The check uses Playwright and Pillow without mocks. It proves that Chromium loads the SVG
with intrinsic dimensions and that two sampled raster frames differ. Failures return typed
evidence rather than being silently downgraded.
"""

from __future__ import annotations

import base64
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from loguru import logger
from PIL import Image, ImageChops

from .models import BrowserEvidence


def _changed_ratio(first: Path, second: Path) -> float:
    with Image.open(first).convert("RGBA") as image_a, Image.open(second).convert("RGBA") as image_b:
        if image_a.size != image_b.size:
            return 1.0
        difference = ImageChops.difference(image_a, image_b)
        changed = sum(1 for pixel in difference.get_flattened_data() if pixel != (0, 0, 0, 0))
        total = image_a.width * image_a.height
        return changed / total if total else 0.0


def verify_readme_image(svg_path: Path) -> BrowserEvidence:
    """Load an SVG through img in real Chromium and compare two animation frames."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        logger.warning("browser verification dependency is unavailable: {}", exc)
        return BrowserEvidence(
            status="NOT_RUN",
            loaded=False,
            details="playwright is not installed",
        )

    executable = next(
        (
            value
            for value in (
                shutil.which("chromium"),
                shutil.which("chromium-browser"),
                shutil.which("google-chrome"),
            )
            if value
        ),
        None,
    )

    try:
        with TemporaryDirectory(prefix="readme-svg-browser-") as temporary:
            directory = Path(temporary)
            encoded_svg = base64.b64encode(svg_path.read_bytes()).decode("ascii")
            data_uri = f"data:image/svg+xml;base64,{encoded_svg}"
            document = (
                "<!doctype html><meta charset='utf-8'>"
                "<style>html,body{margin:0;background:#20252d}"
                "main{padding:20px}img{display:block;width:850px;height:auto}</style>"
                f"<main><img id='art' src='{data_uri}' alt='verification image'></main>"
            )
            frame_a = directory / "frame-a.png"
            frame_b = directory / "frame-b.png"
            with sync_playwright() as playwright:
                launch_args = {"headless": True}
                if executable:
                    launch_args["executable_path"] = executable
                browser = playwright.chromium.launch(**launch_args)
                page = browser.new_page(viewport={"width": 900, "height": 620})
                page.set_content(document, wait_until="load", timeout=15000)
                page.wait_for_function(
                    "document.querySelector('#art').complete && "
                    "document.querySelector('#art').naturalWidth > 0",
                    timeout=10000,
                )
                dimensions = page.locator("#art").evaluate(
                    "element => ({width: element.naturalWidth, height: element.naturalHeight})"
                )
                page.wait_for_timeout(250)
                page.locator("#art").screenshot(path=str(frame_a))
                page.wait_for_timeout(1000)
                page.locator("#art").screenshot(path=str(frame_b))
                browser.close()
            ratio = _changed_ratio(frame_a, frame_b)
            observed = ratio > 0.0001
            return BrowserEvidence(
                status="PASS" if observed else "FAIL",
                loaded=True,
                natural_width=int(dimensions["width"]),
                natural_height=int(dimensions["height"]),
                animation_observed=observed,
                changed_pixel_ratio=round(ratio, 8),
                details="two img-mode Chromium frames sampled 1000ms apart",
            )
    except Exception as exc:
        logger.error("real browser verification failed: {}", exc)
        return BrowserEvidence(
            status="FAIL",
            loaded=False,
            details=f"browser verification error: {exc}",
        )
