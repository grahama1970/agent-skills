"""Section header detection for extract-tables.

PDF-specific wrappers around common.section_detector heuristics.
Uses pdf_bridge (wrapping pdf_oxide) for text extraction.

All bboxes are in top-left origin: (x0, y0, x1, y1).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

# Ensure common/ is importable
_skills_dir = str(Path.home() / ".pi" / "skills")
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

# Shared heuristics from common/
from common.section_detector import (
    HeaderInfo,
    is_section_header,
    estimate_body_font_size,
    group_elements_into_blocks,
    classify_blocks_as_headers,
)


def detect_headers_on_page(
    pdf_path: str,
    page_num: int,  # 0-indexed
    password: str | None = None,
) -> list[HeaderInfo]:
    """Detect section headers on a page using pdf_oxide via pdf_bridge.

    Returns list of HeaderInfo with bbox in top-left origin coordinates.
    """
    try:
        from .pdf_bridge import extract_text_elements
    except ImportError:
        return []

    try:
        elements = extract_text_elements(pdf_path, page_num, password=password)
    except Exception:
        return []

    if not elements:
        return []

    headers = classify_blocks_as_headers(elements)
    for h in headers:
        h.page_number = page_num + 1
    return headers


def has_header_between_tables(
    pdf_path: str,
    table_a_page: int,  # 0-indexed
    table_a_bbox: tuple[float, float, float, float],
    table_b_page: int,  # 0-indexed
    table_b_bbox: tuple[float, float, float, float],
    password: str | None = None,
) -> tuple[bool, Optional[HeaderInfo]]:
    """Check if a section header exists between two tables across pages.

    Looks for headers:
    - Below table_a on its page (between table_a bottom and page bottom)
    - Above table_b on its page (between page top and table_b top)

    Returns (has_header, header_info_or_none).
    """
    if table_b_page != table_a_page + 1:
        return False, None

    # Check below table A (on page A)
    headers_a = detect_headers_on_page(pdf_path, table_a_page, password)
    a_bottom = table_a_bbox[3]  # y1 of table A
    for h in headers_a:
        if h.bbox[1] > a_bottom:  # header top is below table A bottom
            return True, h

    # Check above table B (on page B)
    headers_b = detect_headers_on_page(pdf_path, table_b_page, password)
    b_top = table_b_bbox[1]  # y0 of table B
    for h in headers_b:
        if h.bbox[3] < b_top:  # header bottom is above table B top
            return True, h

    return False, None


def find_table_title(
    pdf_path: str,
    page_num: int,  # 0-indexed
    table_bbox: tuple[float, float, float, float],
    password: str | None = None,
) -> tuple[Optional[str], Optional[tuple[float, float, float, float]]]:
    """Search for a table title above the table bbox using pdf_oxide.

    Looks for "Table N:" patterns and bold/larger text in a 60pt
    window above the table.

    Returns (title_text, title_bbox) or (None, None).
    Bbox is in top-left origin coordinates (x0, y0, x1, y1).
    """
    try:
        from .pdf_bridge import extract_text_elements
    except ImportError:
        return None, None

    try:
        elements = extract_text_elements(pdf_path, page_num, password=password)
    except Exception:
        return None, None

    if not elements:
        return None, None

    x0, y0, x1, y1 = table_bbox
    search_top = max(0, y0 - 60)
    body_size = estimate_body_font_size(elements)

    # Filter elements above the table within the search window
    above = [e for e in elements
             if e.y1 <= y0 and e.y0 >= search_top
             and e.x0 >= x0 - 50 and e.x1 <= x1 + 50]

    if not above:
        return None, None

    blocks = group_elements_into_blocks(above)
    if not blocks:
        return None, None

    # Strategy 1: "Table N:" pattern
    table_re = re.compile(r'(?:table|tab\.?)\s*\d+[\s:.\-]', re.IGNORECASE)
    for block in blocks:
        if table_re.search(block["text"]):
            return block["text"], block["bbox"]

    # Strategy 2: bold or larger text closest to table (last block = closest)
    for block in reversed(blocks):
        if block["is_bold"] or (block["font_size"] > body_size * 1.15 and block["font_size"] > 0):
            return block["text"], block["bbox"]

    return None, None
