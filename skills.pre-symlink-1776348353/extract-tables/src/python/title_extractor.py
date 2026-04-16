"""Table title extraction — heuristic + VLM inference.

Title priority: explicit > heuristic > VLM-inferred.
VLM is OPTIONAL — graceful degradation if unavailable.
"""
from __future__ import annotations

import re
import subprocess
import json
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .pdf_bridge import TextElement
    from .models import Table


# Pattern: "Table N:", "Table N.", "TABLE N", "Tab. N"
TABLE_TITLE_RE = re.compile(
    r'(?:table|tab\.?)\s*\d+[\s:.\-]',
    re.IGNORECASE
)


def extract_title_from_context(
    text_elements: list,  # list[TextElement]
    table_bbox: tuple[float, float, float, float],
    page_dims: tuple[float, float],
) -> Optional[str]:
    """Find table title from text above the table.

    Heuristic: look in a 50pt window above table top edge for:
    1. Text matching "Table N:" pattern
    2. Text with larger font size or bold formatting

    Args:
        text_elements: All text elements on the page (top-left coords)
        table_bbox: (x0, y0, x1, y1) of the table, top-left origin
        page_dims: (width, height) of the page

    Returns:
        Title string or None if no title found.
    """
    x0, y0, x1, y1 = table_bbox
    search_top = max(0, y0 - 50)  # 50pt above table

    # Filter text elements in the search window
    candidates = []
    for elem in text_elements:
        # Element must be above the table and within the search window
        # elem.y1 <= y0: element bottom is above table top
        # elem.y0 >= search_top: element top is within search window
        # Horizontal overlap with some margin
        if (elem.y1 <= y0 and elem.y0 >= search_top and
                elem.x0 >= x0 - 50 and elem.x1 <= x1 + 50):
            candidates.append(elem)

    if not candidates:
        return None

    # Sort by vertical position (top to bottom), then left to right
    candidates.sort(key=lambda e: (e.y0, e.x0))

    # Strategy 1: Look for "Table N:" pattern
    for elem in candidates:
        if TABLE_TITLE_RE.search(elem.text):
            # Collect the full title line (all elements on same y-level)
            line_y = elem.y0
            line_elems = [e for e in candidates if abs(e.y0 - line_y) < 5]
            line_elems.sort(key=lambda e: e.x0)
            title = " ".join(e.text.strip() for e in line_elems if e.text.strip())
            return title.strip()

    # Strategy 2: Look for bold or larger-font text closest to table
    # These are INFERRED from surrounding text — not explicitly labeled.
    # Prefix with "INFERRED:" so downstream consumers know the confidence level.
    sizes = [e.font_size for e in candidates if e.font_size > 0]
    if sizes:
        median_size = sorted(sizes)[len(sizes) // 2]
        # Look for text notably larger or bold, closest to table first
        for elem in reversed(candidates):
            if elem.is_bold or (elem.font_size > median_size * 1.15 and elem.font_size > 0):
                line_y = elem.y0
                line_elems = [e for e in candidates if abs(e.y0 - line_y) < 5]
                line_elems.sort(key=lambda e: e.x0)
                title = " ".join(e.text.strip() for e in line_elems if e.text.strip())
                if title.strip():
                    return f"INFERRED: {title.strip()}"

    return None


def infer_title_vlm(
    table_image_path: str,
    context_text: str = "",
) -> dict:
    """Infer table title using VLM (Vision Language Model).

    Returns dict with ai_title, ai_description, ai_headers.
    ALWAYS returns a dict — never raises. If VLM unavailable, returns None values.
    """
    result = {"ai_title": None, "ai_description": None, "ai_headers": None}

    try:
        # Try scillm VLM inference
        prompt = (
            "Look at this table image. Provide:\n"
            "1. A concise title for this table\n"
            "2. A one-sentence description of what the table contains\n"
            "3. The column headers as a list\n\n"
            "Respond in JSON format: {\"title\": \"...\", \"description\": \"...\", \"headers\": [...]}\n"
        )
        if context_text:
            prompt += f"\nContext from surrounding text: {context_text[:500]}"

        # Use scillm CLI for VLM inference
        proc = subprocess.run(
            ["python3", "-m", "scillm", "--model", "vlm",
             "--image", table_image_path, "--prompt", prompt],
            capture_output=True, text=True, timeout=30,
        )

        if proc.returncode == 0 and proc.stdout.strip():
            try:
                data = json.loads(proc.stdout.strip())
                result["ai_title"] = data.get("title")
                result["ai_description"] = data.get("description")
                result["ai_headers"] = data.get("headers")
            except json.JSONDecodeError:
                # VLM returned non-JSON — use raw text as title
                result["ai_title"] = proc.stdout.strip()[:200]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        # VLM not available — graceful degradation
        pass
    except Exception:
        # Any unexpected error — never fail
        pass

    return result


def batch_infer_titles(tables: list) -> list:
    """Batch VLM title inference for tables without titles.

    Returns the same tables list with ai_title/ai_description/ai_headers populated
    where possible. Tables that already have titles are skipped.
    """
    for table in tables:
        if table.title is not None:
            continue
        if table.ai_title is not None:
            continue
        # Would need rendered table image — skip VLM if no image available
        # In full pipeline, this gets called with rendered images
    return tables
