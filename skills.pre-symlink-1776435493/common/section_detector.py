"""Shared section header detection heuristics.

Pure-Python module (no PDF library dependency). Provides header classification
from text + font metadata. Used by both /extract-tables and extractor pipeline.

All bboxes are in top-left origin: (x0, y0, x1, y1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# --- Header detection regexes (from extractor s03/s04 heuristics) ---

_RE_DECIMAL = re.compile(
    r"""^\s*
        (?P<num>\d+(?:\.\d+)*(?:\.[a-z])?)
        (?:[.:)\-\u2013\u2014]\s*|\s+)
        (?P<title>\S.*)$
    """,
    re.IGNORECASE | re.VERBOSE,
)
_RE_LABELED = re.compile(
    r"""^\s*
        (?:Appendix|Annex|Section|Chapter|Part)
        \s+[A-Za-z0-9IVXLCDM.]+
        \s*(?:[:.\\-\u2013\u2014])?\s+
        \S.*$
    """,
    re.IGNORECASE | re.VERBOSE,
)
_RE_ROMAN = re.compile(
    r"^\s*[IVXLCDM]+(?:\.[IVXLCDM]+)*\.\s+\S.*$",
    re.IGNORECASE,
)
_RE_CAPTION = re.compile(
    r"^\s*(?:Table|Figure|Exhibit|Listing)\s+\d+",
    re.IGNORECASE,
)
_RE_CONTINUED = re.compile(
    r"\bcontinued\b|\(cont(?:\.|inued)?\)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class HeaderInfo:
    """A detected section header with its bbox."""
    text: str
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1) top-left origin
    font_size: float = 0.0
    is_bold: bool = False
    confidence: float = 0.0
    page_number: int = 0  # 1-indexed


def is_section_header(
    text: str,
    font_size: float = 0.0,
    is_bold: bool = False,
    body_font_size: float = 11.0,
) -> tuple[bool, float]:
    """Determine if text is a section header.

    Returns (is_header, confidence).
    """
    t = (text or "").strip()
    if not t or len(t) < 2:
        return False, 0.0

    # --- Negatives ---
    if _RE_CAPTION.match(t):
        return False, 0.0
    if _RE_CONTINUED.search(t):
        return False, 0.0
    if len(t) > 180:
        return False, 0.0
    if len(t) <= 40 and t.endswith(":"):
        return False, 0.0
    if re.match(r"^\s*[\u2022\u25CF\u25AA\u2023\u2043\u2013\u2014\-\*\+\u00B7]", t):
        return False, 0.0
    if t.rstrip().endswith(".") or t.rstrip().endswith(";"):
        if len(t.split()) > 6:
            return False, 0.0
    words = t.split()
    if len(words) > 15:
        return False, 0.0
    if re.search(r"\([A-Z][a-z]+ et al\.", t):
        return False, 0.0

    # --- Positives ---
    confidence = 0.0

    m_decimal = _RE_DECIMAL.match(t)
    if m_decimal:
        title_part = m_decimal.group("title").strip()
        if len(title_part.split()) <= 12 and not title_part[0:1].islower():
            confidence = max(confidence, 0.85)

    if _RE_LABELED.match(t):
        confidence = max(confidence, 0.90)
    if _RE_ROMAN.match(t):
        confidence = max(confidence, 0.80)

    # Font-based evidence — only for short, title-like text
    if len(words) <= 8:
        if font_size > 0 and body_font_size > 0:
            if font_size >= body_font_size + 2.0:
                confidence = max(confidence, 0.70)
            if is_bold and font_size >= body_font_size + 1.0:
                confidence = max(confidence, 0.65)

    # ALL CAPS medium-length text
    if t.isupper() and 5 <= len(t) <= 60 and not re.search(r"\d", t):
        confidence = max(confidence, 0.60)

    return confidence >= 0.50, confidence


def estimate_body_font_size(elements: list) -> float:
    """Estimate the most common (body) font size from text elements.

    Elements must have .font_size and .text attributes.
    """
    sizes: dict[float, int] = {}
    for elem in elements:
        sz = round(elem.font_size, 1)
        text = elem.text.strip()
        if sz > 0 and len(text) > 5:
            sizes[sz] = sizes.get(sz, 0) + len(text)
    if not sizes:
        return 11.0
    return max(sizes, key=sizes.get)


def group_elements_into_blocks(
    elements: list,
    y_tolerance: float = 3.0,
) -> list[dict]:
    """Group text elements into logical blocks (lines at same y).

    Elements must have .x0, .y0, .x1, .y1, .text, .font_size, .is_bold.
    Returns list of dicts with keys: text, bbox, font_size, is_bold.
    """
    if not elements:
        return []

    sorted_elems = sorted(elements, key=lambda e: (e.y0, e.x0))
    blocks: list[dict] = []
    current_line: list = [sorted_elems[0]]
    line_y = sorted_elems[0].y0

    for elem in sorted_elems[1:]:
        if abs(elem.y0 - line_y) < y_tolerance:
            current_line.append(elem)
        else:
            if current_line:
                blocks.append(_line_to_block(current_line))
            current_line = [elem]
            line_y = elem.y0

    if current_line:
        blocks.append(_line_to_block(current_line))

    return blocks


def _line_to_block(line_elems: list) -> dict:
    """Convert elements on the same line to a block dict."""
    line_elems.sort(key=lambda e: e.x0)
    text = " ".join(e.text.strip() for e in line_elems if e.text.strip())
    x0 = min(e.x0 for e in line_elems)
    y0 = min(e.y0 for e in line_elems)
    x1 = max(e.x1 for e in line_elems)
    y1 = max(e.y1 for e in line_elems)
    first = next((e for e in line_elems if e.text.strip()), line_elems[0])
    return {
        "text": text,
        "bbox": (x0, y0, x1, y1),
        "font_size": first.font_size,
        "is_bold": first.is_bold,
    }


def classify_blocks_as_headers(
    elements: list,
    body_font_size: float | None = None,
) -> list[HeaderInfo]:
    """Classify text elements into section headers.

    Generic entry point — works with any element list that has
    .x0, .y0, .x1, .y1, .text, .font_size, .is_bold attributes.

    Returns list of HeaderInfo for detected headers.
    """
    if not elements:
        return []

    if body_font_size is None:
        body_font_size = estimate_body_font_size(elements)

    blocks = group_elements_into_blocks(elements)
    headers: list[HeaderInfo] = []

    for block in blocks:
        text = block["text"]
        if not text:
            continue

        is_hdr, conf = is_section_header(
            text,
            font_size=block["font_size"],
            is_bold=block["is_bold"],
            body_font_size=body_font_size,
        )

        if is_hdr:
            headers.append(HeaderInfo(
                text=text,
                bbox=block["bbox"],
                font_size=block["font_size"],
                is_bold=block["is_bold"],
                confidence=conf,
            ))

    return headers
