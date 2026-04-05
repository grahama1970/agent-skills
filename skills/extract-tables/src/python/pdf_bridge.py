"""Bridge to pdf_oxide for text extraction and page rendering.

All coordinates output in top-left origin: (x0, y0_top, x1, y1_bottom).
pdf_oxide uses bottom-left origin (x, y, w, h) -- conversion happens HERE only.

Falls back to pdfminer when pdf_oxide produces incorrect text positions
(detected by clustering heuristic).
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from PIL import Image
import pdf_oxide


@dataclass(slots=True)
class TextElement:
    """A text span with position in top-left coordinates."""
    text: str
    x0: float
    y0: float  # top-left origin: y=0 is top of page
    x1: float
    y1: float  # y1 > y0 always
    font_name: str = ""
    font_size: float = 0.0
    is_bold: bool = False
    is_italic: bool = False


def _open_doc(pdf_path: str, password: Optional[str] = None) -> pdf_oxide.PdfDocument:
    """Open a PDF document, handling passwords."""
    doc = pdf_oxide.PdfDocument(pdf_path)
    if password:
        doc.authenticate(password)
    return doc


def get_page_count(pdf_path: str) -> int:
    """Get number of pages in the PDF."""
    doc = _open_doc(pdf_path)
    return doc.page_count()  # METHOD, not property


def get_page_dimensions(pdf_path: str, page_num: int) -> tuple[float, float]:
    """Get page width and height in PDF points.

    Returns (width, height) tuple.
    """
    doc = _open_doc(pdf_path)
    media_box = doc.page_media_box(page_num)
    # media_box returns (x0, y0, x1, y1) e.g. (0.0, 0.0, 612.0, 792.0)
    x0, y0, x1, y1 = media_box
    width = x1 - x0
    height = y1 - y0
    return (width, height)


def _extract_with_pdfminer(pdf_path: str, page_num: int) -> list[TextElement]:
    """Extract text elements using pdfminer as fallback.

    Used when pdf_oxide produces incorrect text positions (e.g., all text
    clusters in a narrow x-range instead of spanning the page).

    pdfminer uses bottom-left origin; we convert to top-left here.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTTextLineHorizontal, LTTextLineVertical, LTChar

    laparams = LAParams(
        line_overlap=0.5,
        char_margin=1.0,
        line_margin=0.5,
        word_margin=0.1,
        boxes_flow=0.5,
        detect_vertical=True,
        all_texts=True,
    )

    elements: list[TextElement] = []
    for i, page_layout in enumerate(extract_pages(pdf_path, laparams=laparams)):
        if i != page_num:
            continue
        page_height = page_layout.bbox[3]
        _textline_types = (LTTextLineHorizontal, LTTextLineVertical)
        for element in page_layout:
            if isinstance(element, _textline_types):
                _process_pdfminer_textline(element, page_height, elements)
            else:
                # Recurse into containers (LTTextBox, LTFigure, etc.)
                try:
                    for child in element:
                        if isinstance(child, _textline_types):
                            _process_pdfminer_textline(child, page_height, elements)
                except TypeError:
                    pass
        break
    return elements


def _process_pdfminer_textline(
    tl, page_height: float, out: list[TextElement]
) -> None:
    """Convert a pdfminer LTTextLineHorizontal to TextElement(s)."""
    from pdfminer.layout import LTChar

    # Keep trailing \n from pdfminer — Camelot relies on it for line breaks
    # within cells. Each LTTextLine.get_text() returns text + "\n"; Camelot's
    # Cell.text setter concatenates them, so the \n becomes the line separator.
    text = tl.get_text()
    if not text.strip():
        return
    x0, y0_bl, x1, y1_bl = tl.bbox
    y0_top = page_height - y1_bl
    y1_bottom = page_height - y0_bl

    # Extract font info from first LTChar child
    font_name = ""
    font_size = 0.0
    for child in tl:
        if isinstance(child, LTChar):
            font_name = child.fontname or ""
            font_size = child.size or 0.0
            break

    is_bold = "bold" in font_name.lower() if font_name else False
    is_italic = "italic" in font_name.lower() if font_name else False

    out.append(TextElement(
        text=text,
        x0=round(x0, 2),
        y0=round(y0_top, 2),
        x1=round(x1, 2),
        y1=round(y1_bottom, 2),
        font_name=font_name,
        font_size=round(font_size, 2),
        is_bold=is_bold,
        is_italic=is_italic,
    ))


def _is_suspicious_positioning(
    elements: list[TextElement], page_width: float
) -> bool:
    """Detect when pdf_oxide returns incorrect text positions.

    pdf_oxide sometimes returns wrong bounding boxes where text elements
    within the same row have x0 values clustered in a narrow range,
    when they should span the full table width across columns.

    Detects this by grouping elements by y-position (rows) and checking
    if rows with many elements have suspiciously narrow x0 spread.
    """
    if len(elements) < 5 or page_width < 100:
        return False

    # Group elements by y-position (within 3pt tolerance = same row)
    rows: dict[int, list[TextElement]] = {}
    for e in elements:
        row_key = round(e.y0 / 3.0)
        rows.setdefault(row_key, []).append(e)

    # Check rows with 3+ elements (likely table rows)
    suspicious_rows = 0
    multi_element_rows = 0
    for row_elements in rows.values():
        if len(row_elements) < 3:
            continue
        multi_element_rows += 1
        x0_vals = sorted(e.x0 for e in row_elements)
        x0_spread = x0_vals[-1] - x0_vals[0]
        # If 3+ elements fit within 15% of page width, they're clustered
        if x0_spread < page_width * 0.15:
            suspicious_rows += 1

    # If a significant fraction of multi-element rows are suspicious, flag it
    if multi_element_rows >= 2 and suspicious_rows >= 3:
        return True

    return False


def _has_merged_spans(elements: list[TextElement]) -> bool:
    """Detect when pdf_oxide merges text across column boundaries.

    pdf_oxide sometimes groups adjacent characters into a single span even
    when there's a significant gap between them (e.g., "9.5% 2" instead
    of separate "9.5%" and "2"). Detected by finding spans where the text
    width is much less than the bbox width, indicating internal gaps.
    """
    import re
    # Look for spans containing patterns like "value1 value2" where both
    # look like separate data values (numbers, percentages)
    merged_count = 0
    for e in elements:
        text = e.text.strip()
        if not text or len(text) < 3:
            continue
        # Pattern: "number% number" or "number number%" in one span
        if re.search(r'\d+\.?\d*%\s+\d', text) or re.search(r'\d\s+\d+\.?\d*%', text):
            merged_count += 1
    # If multiple spans show this pattern, pdf_oxide is merging across columns
    return merged_count >= 2


@lru_cache(maxsize=64)
def _cached_text_elements(pdf_path: str, page_num: int) -> tuple[TextElement, ...]:
    """Cache text elements per page (returns tuple for hashability).

    Uses pdf_oxide first; falls back to pdfminer if text positions look
    suspicious (clustered in narrow x-range) or if pdf_oxide merges text
    spans across what should be separate columns.
    """
    elements = _extract_with_pdf_oxide(pdf_path, page_num)

    doc = _open_doc(pdf_path)
    media_box = doc.page_media_box(page_num)
    page_width = media_box[2] - media_box[0]

    needs_fallback = _is_suspicious_positioning(elements, page_width)

    if not needs_fallback:
        needs_fallback = _has_merged_spans(elements)

    if needs_fallback:
        try:
            pdfminer_elements = _extract_with_pdfminer(pdf_path, page_num)
            if pdfminer_elements:
                elements = pdfminer_elements
        except Exception:
            pass  # Keep pdf_oxide results if pdfminer fails

    return tuple(elements)


def _extract_with_pdf_oxide(pdf_path: str, page_num: int) -> list[TextElement]:
    """Extract text elements using pdf_oxide."""
    doc = _open_doc(pdf_path)
    media_box = doc.page_media_box(page_num)
    page_h = media_box[3] - media_box[1]
    # pdf_oxide reports coordinates in absolute page space including
    # media_box origin. Subtract origin to normalize to (0,0)-based coords
    # before converting to top-left. Without this, PDFs with non-zero
    # media_box origins (e.g. row_span_1.pdf with y0=12) get shifted text.
    mb_x0 = media_box[0]
    mb_y0 = media_box[1]

    spans = doc.extract_spans(page_num)
    elements: list[TextElement] = []
    import re
    _trailing_dot_re = re.compile(r'\s+\.\s*$')
    for span in spans:
        ox, oy, ow, oh = span.bbox
        x0 = ox - mb_x0
        y0_top = page_h - (oy - mb_y0) - oh
        x1 = ox - mb_x0 + ow
        y1_bottom = page_h - (oy - mb_y0)

        font_name = getattr(span, "font_name", "") or ""
        font_size = getattr(span, "font_size", 0.0) or 0.0
        is_bold = getattr(span, "is_bold", False)
        if not is_bold and font_name:
            is_bold = "bold" in font_name.lower()
        is_italic = getattr(span, "is_italic", False)
        if not is_italic and font_name:
            is_italic = "italic" in font_name.lower()

        # Strip trailing isolated dots (PDF leader dots that pdfminer filters)
        text = _trailing_dot_re.sub(' ', span.text)

        elements.append(TextElement(
            text=text,
            x0=x0,
            y0=y0_top,
            x1=x1,
            y1=y1_bottom,
            font_name=font_name,
            font_size=font_size,
            is_bold=is_bold,
            is_italic=is_italic,
        ))

    return elements


def extract_text_elements(
    pdf_path: str, page_num: int, password: Optional[str] = None,
    backend: str = "auto",
) -> list[TextElement]:
    """Extract text elements with top-left coordinates.

    pdf_oxide returns spans with bbox = (x, y, w, h) in bottom-left origin.
    This function converts ALL coordinates to top-left origin.

    backend options:
      - "auto": pdf_oxide with pdfminer fallback on suspicious positioning
      - "pdfminer": force pdfminer (matches Camelot text output exactly)
      - "pdf_oxide": force pdf_oxide only
    """
    if backend == "pdfminer":
        try:
            elements = _extract_with_pdfminer(pdf_path, page_num)
            if elements:
                return elements
        except Exception:
            pass
        # Fall through to auto if pdfminer fails

    if password:
        # Can't cache password-protected docs safely; extract directly
        elements = _extract_with_pdf_oxide(pdf_path, page_num)
        doc = _open_doc(pdf_path, password)
        media_box = doc.page_media_box(page_num)
        page_width = media_box[2] - media_box[0]
        if _is_suspicious_positioning(elements, page_width) or _has_merged_spans(elements):
            try:
                pdfminer_elements = _extract_with_pdfminer(pdf_path, page_num)
                if pdfminer_elements:
                    elements = pdfminer_elements
            except Exception:
                pass
        return elements

    if backend == "pdf_oxide":
        return list(_extract_with_pdf_oxide(pdf_path, page_num))

    return list(_cached_text_elements(pdf_path, page_num))


@lru_cache(maxsize=32)
def _cached_render(pdf_path: str, page_num: int, dpi: int) -> bytes:
    """Cache rendered page bytes to avoid re-rendering."""
    doc = _open_doc(pdf_path)
    return doc.render_page(page_num, dpi=dpi)


def render_page_image(
    pdf_path: str, page_num: int, dpi: int = 150, password: Optional[str] = None
) -> Image.Image:
    """Render a PDF page as a PIL Image.

    Results are cached per (pdf_path, page_num, dpi) to avoid re-rendering.
    """
    if password:
        doc = _open_doc(pdf_path, password)
        img_bytes = doc.render_page(page_num, dpi=dpi)
    else:
        img_bytes = _cached_render(pdf_path, page_num, dpi)
    return Image.open(io.BytesIO(img_bytes))
