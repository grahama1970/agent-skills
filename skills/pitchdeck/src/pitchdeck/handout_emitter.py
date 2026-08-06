"""Speaker-handout PDF: rendered slide images beside full speaker notes.

Server-side adaptation of the client handoutPdfExporter spec: consumes the
REAL rendered slide PNGs (from `render`, i.e. the LibreOffice pipeline — not
an approximated DOM re-render), lays out two slides per A4 page with wrapped
speaker notes beside each, and writes a multi-page PDF via Pillow (no jsPDF/
html2canvas). Notes carry required qualifiers, so the handout preserves the
claim boundary's context. Hidden slides are excluded (render already skips
them). Failure modes: missing render PNGs raise before writing.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from loguru import logger
from PIL import Image, ImageDraw, ImageFont

from .models import (
    DeckManifest,
    OperationClaims,
    OperationReceipt,
    Readiness,
    SeamValidation,
)

A4 = (1240, 1754)  # ~150dpi portrait
MARGIN = 70
SLIDE_W = 480


def _font(size: int, bold: bool = False):
    for name in (
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans-{'Bold' if bold else 'Regular'}.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def emit_handout(
    deck: DeckManifest,
    render_dir: Path,
    output_path: Path,
) -> OperationReceipt:
    """Compose 2-slides-per-page A4 handout from rendered PNGs + notes."""
    visible = [s for s in sorted(deck.slides, key=lambda x: x.order) if not s.hidden]
    slide_images: list[tuple[object, Path]] = []
    for position, spec in enumerate(visible, start=1):
        png = render_dir / f"slide-{position}.png"
        if not png.exists():
            raise ValueError(f"missing rendered slide image: {png} (run `render` first)")
        slide_images.append((spec, png))

    pages: list[Image.Image] = []
    title_font = _font(22, bold=True)
    note_font = _font(16)
    small_font = _font(13)

    for start in range(0, len(slide_images), 2):
        page = Image.new("RGB", A4, "white")
        draw = ImageDraw.Draw(page)
        for row, (spec, png) in enumerate(slide_images[start : start + 2]):
            top = MARGIN + row * (A4[1] // 2 - 30)
            with Image.open(png) as img:
                ratio = SLIDE_W / img.width
                thumb = img.resize((SLIDE_W, round(img.height * ratio)), Image.LANCZOS)
                page.paste(thumb, (MARGIN, top))
                thumb_h = thumb.height
            text_x = MARGIN + SLIDE_W + 40
            title_line = f"Slide {spec.order}: {spec.title}"
            if len(title_line) > 48:
                title_line = title_line[:47] + "…"
            draw.text((text_x, top), title_line, font=title_font, fill=(20, 20, 20))
            notes = spec.notes.strip() or "No speaker notes recorded for this slide."
            wrapped: list[str] = []
            for paragraph in notes.splitlines():
                wrapped.extend(textwrap.wrap(paragraph, width=52) or [""])
            y = top + 40
            for line in wrapped[:28]:
                draw.text((text_x, y), line, font=note_font, fill=(70, 70, 70))
                y += 24
            if spec.claim_ids:
                draw.text(
                    (MARGIN, top + thumb_h + 10),
                    f"claims: {', '.join(spec.claim_ids[:3])}{'…' if len(spec.claim_ids) > 3 else ''}",
                    font=small_font,
                    fill=(120, 120, 120),
                )
        pages.append(page)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(output_path, format="PDF", save_all=True, append_images=pages[1:], resolution=150)
    logger.info("handout written: {} ({} pages, {} slides)", output_path, len(pages), len(slide_images))

    return OperationReceipt(
        schema="pitchdeck.handout_receipt.v1",
        operation="emit-handout",
        readiness=Readiness.READY,
        mocked=False,
        live=False,
        inputs={"render_dir": str(render_dir.resolve()), "slides": str(len(slide_images))},
        outputs={"handout_pdf": str(output_path.resolve())},
        counts={"pages": len(pages), "slides": len(slide_images)},
        gaps=[],
        claims=OperationClaims(
            proves=["The handout was composed from the real rendered slide images and manifest notes."],
            does_not_prove=["Notes accuracy or claim approval; the deck's review state is unchanged."],
        ),
        seam_validation=SeamValidation(kind="handout_receipt"),
    )
