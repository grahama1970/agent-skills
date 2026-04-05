"""Cross-page table merger.

Detects tables split across consecutive pages and merges them.

Architecture (skill contract):
- Deterministic code gathers structured evidence (sensors)
- /table-lab agent makes the merge decision using that evidence
- Heuristic fallback ONLY when no agent is available (offline degradation)

Evidence signals (deterministic sensors — agent decides):
- section_header_between: bool — section header detected between tables
- continued_keyword: bool — "continued" found in title, cells, or page text
- continued_text: str — actual matched text (e.g. "Table 4.2 (Continued)")
- title_a/title_b: str — table titles (explicit, INFERRED:, or ai_title)
- title_source_a/b: str — "explicit" | "inferred" | "vlm" | None
- col_count_match: bool — same number of columns
- width_ratio: float — min(w_a, w_b) / max(w_a, w_b)
- x_overlap_ratio: float — horizontal overlap as fraction of narrower table
- header_match: bool — first rows identical
- rows_a/rows_b: int — row counts
- table_a_is_header_stub: bool — <=3 rows, likely just header
- table_a_at_page_bottom: bool — table A ends in bottom 15% of page
- table_b_at_page_top: bool — table B starts in top 15% of page
- text_between_tables: bool — non-table text between A bottom and page end
- font_size_match: bool — dominant font size identical
- font_style_match: bool — same bold/italic pattern
- col_boundary_match: bool — column edges align within 5pt
- col_boundary_rmse: float — RMS error between column boundaries
- edge_pattern_match: bool — same cell border pattern (LRTB flags)

All bboxes use top-left origin: (x0, y0, x1, y1).
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from loguru import logger
import polars as pl

try:
    from .models import Table
except ImportError:
    from models import Table


@dataclass
class MergeEvidence:
    """Structured evidence bundle for a cross-page table pair.

    All fields are deterministic sensor outputs. The agent decides.
    """
    table_a_page: int
    table_b_page: int
    table_a_bbox: tuple[float, float, float, float]
    table_b_bbox: tuple[float, float, float, float]
    # Signals
    section_header_between: bool = False
    header_text: Optional[str] = None
    continued_keyword: bool = False
    continued_text: Optional[str] = None  # actual continuation text found (e.g. "Table 4.2 (Continued)")
    title_a: Optional[str] = None  # table A title (for agent context)
    title_b: Optional[str] = None  # table B title (for agent context)
    title_source_a: Optional[str] = None  # "explicit" | "inferred" | "vlm" | None
    title_source_b: Optional[str] = None  # "explicit" | "inferred" | "vlm" | None
    col_count_match: bool = False
    col_count_a: int = 0
    col_count_b: int = 0
    width_ratio: float = 0.0
    x_overlap_ratio: float = 0.0
    header_match: bool = False  # first rows identical
    # Structural signals for agent decision
    rows_a: int = 0  # row count of table A
    rows_b: int = 0  # row count of table B
    table_a_is_header_stub: bool = False  # <=3 rows, likely just header
    table_b_at_page_top: bool = False  # table B starts near top of page
    table_a_at_page_bottom: bool = False  # table A ends near bottom of page
    text_between_tables: bool = False  # non-table text between A's bottom and page end
    # Font consistency signals
    font_size_match: bool = False  # dominant font size is the same
    font_size_a: float = 0.0  # dominant font size in table A region
    font_size_b: float = 0.0  # dominant font size in table B region
    font_style_match: bool = False  # same bold/italic pattern
    # Column boundary signals
    col_boundaries_a: list[float] = field(default_factory=list)  # sorted x-positions of cell boundaries
    col_boundaries_b: list[float] = field(default_factory=list)
    col_boundary_match: bool = False  # column edges align within tolerance
    col_boundary_rmse: float = 999.0  # RMS error between aligned column boundaries (pts)
    # Cell edge pattern signals
    edge_pattern_a: str = ""  # serialized edge flags pattern (e.g. "LRTB" for all borders)
    edge_pattern_b: str = ""
    edge_pattern_match: bool = False  # same cell border pattern

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _classify_title_source(table) -> Optional[str]:
    """Classify how a table's title was obtained.

    Returns: "explicit" | "inferred" | "vlm" | None
    """
    if table.title:
        if table.title.startswith("INFERRED:"):
            return "inferred"
        return "explicit"
    if table.ai_title:
        return "vlm"
    return None


def _extract_column_boundaries(cells: list) -> list[float]:
    """Extract sorted unique x-positions that define column boundaries from cells."""
    x_positions: set[float] = set()
    for c in cells:
        x_positions.add(round(c.x0, 1))
        x_positions.add(round(c.x1, 1))
    return sorted(x_positions)


def _column_boundary_rmse(bounds_a: list[float], bounds_b: list[float]) -> float:
    """Compute RMSE between two sets of column boundaries.

    Aligns boundaries by count — if counts differ, returns 999.
    """
    if len(bounds_a) != len(bounds_b) or len(bounds_a) == 0:
        return 999.0
    sq_sum = sum((a - b) ** 2 for a, b in zip(bounds_a, bounds_b))
    return math.sqrt(sq_sum / len(bounds_a))


def _cell_edge_pattern(cells: list) -> str:
    """Summarize cell edge flags into a compact pattern string.

    Returns something like "LRTB" if all cells have all 4 borders,
    or "LR" if only left/right borders are present. Uses majority vote.
    """
    if not cells:
        return ""
    total = len(cells)
    left_count = sum(1 for c in cells if c.left)
    right_count = sum(1 for c in cells if c.right)
    top_count = sum(1 for c in cells if c.top)
    bottom_count = sum(1 for c in cells if c.bottom)
    threshold = total * 0.5
    pattern = ""
    if left_count > threshold:
        pattern += "L"
    if right_count > threshold:
        pattern += "R"
    if top_count > threshold:
        pattern += "T"
    if bottom_count > threshold:
        pattern += "B"
    return pattern


def _dominant_font(
    pdf_path: str, page_index: int, bbox: tuple[float, float, float, float],
) -> tuple[float, bool, bool]:
    """Find dominant font size and style within a bbox region.

    Returns (font_size, is_bold, is_italic) for the most common font in the region.
    """
    try:
        from .pdf_bridge import extract_text_elements
    except ImportError:
        from pdf_bridge import extract_text_elements

    elements = extract_text_elements(pdf_path, page_index)
    # Filter to elements overlapping the bbox
    x0, y0, x1, y1 = bbox
    region_els = [
        e for e in elements
        if e.x0 < x1 and e.x1 > x0 and e.y0 < y1 and e.y1 > y0
        and e.text.strip()
    ]
    if not region_els:
        return (0.0, False, False)

    # Majority vote on font size (round to 0.5pt)
    size_counter: Counter[float] = Counter()
    for e in region_els:
        size_counter[round(e.font_size * 2) / 2] += 1
    dominant_size = size_counter.most_common(1)[0][0] if size_counter else 0.0

    # Majority vote on bold/italic
    bold_count = sum(1 for e in region_els if e.is_bold)
    italic_count = sum(1 for e in region_els if e.is_italic)
    is_bold = bold_count > len(region_els) * 0.5
    is_italic = italic_count > len(region_els) * 0.5

    return (dominant_size, is_bold, is_italic)


def _gather_evidence(
    a: Table,
    b: Table,
    pdf_path: str | None = None,
    password: str | None = None,
) -> Optional[MergeEvidence]:
    """Gather all deterministic evidence for a merge decision.

    Returns None if tables are not on consecutive pages (not a candidate).
    """
    if b.page_number != a.page_number + 1:
        return None

    ev = MergeEvidence(
        table_a_page=a.page_number,
        table_b_page=b.page_number,
        table_a_bbox=a.bbox,
        table_b_bbox=b.bbox,
    )

    # --- Section header between tables ---
    if pdf_path and a.bbox != (0.0, 0.0, 0.0, 0.0) and b.bbox != (0.0, 0.0, 0.0, 0.0):
        try:
            from .section_detector import has_header_between_tables
            has_header, header_info = has_header_between_tables(
                pdf_path, a.page_index, a.bbox, b.page_index, b.bbox, password,
            )
            ev.section_header_between = has_header
            if header_info:
                ev.header_text = header_info.text
        except Exception:
            pass

    # --- Table titles (for agent context) ---
    ev.title_a = a.title or a.ai_title
    ev.title_b = b.title or b.ai_title
    ev.title_source_a = _classify_title_source(a)
    ev.title_source_b = _classify_title_source(b)

    # --- "continued" keyword ---
    # Check title, cell text, and nearby page text for continuation markers
    _cont_patterns = ("continued", "cont'd", "cont.", "(cont)", "continuation")
    if b.title and any(p in b.title.lower() for p in _cont_patterns):
        ev.continued_keyword = True
        ev.continued_text = b.title
    # Check first row cell text of table B (some PDFs put "(Continued)" in a cell)
    if not ev.continued_keyword and b._data and len(b._data) > 0:
        first_row_text = " ".join(str(c).lower() for c in b._data[0])
        if any(p in first_row_text for p in _cont_patterns):
            ev.continued_keyword = True
            ev.continued_text = " ".join(str(c) for c in b._data[0])
    # Check text just above table B on its page for "(Continued)" captions
    if not ev.continued_keyword and pdf_path and b.bbox != (0.0, 0.0, 0.0, 0.0):
        try:
            from .pdf_bridge import extract_text_elements
            text_els = extract_text_elements(pdf_path, b.page_index)
            b_top = b.bbox[1]
            # Text within 30pt above table B
            above_text = [
                t for t in text_els
                if t.y1 <= b_top and t.y0 >= b_top - 30
            ]
            for t in above_text:
                if any(p in t.text.lower() for p in _cont_patterns):
                    ev.continued_keyword = True
                    ev.continued_text = t.text.strip()
                    break
        except Exception:
            pass

    # --- Column count ---
    ev.col_count_a = a.cols
    ev.col_count_b = b.cols
    ev.col_count_match = (a.cols > 0 and b.cols > 0 and a.cols == b.cols)

    # --- Width ratio and X-overlap ---
    a_width = a.bbox[2] - a.bbox[0]
    b_width = b.bbox[2] - b.bbox[0]
    if a_width > 0 and b_width > 0:
        ev.width_ratio = min(a_width, b_width) / max(a_width, b_width)
        overlap_x0 = max(a.bbox[0], b.bbox[0])
        overlap_x1 = min(a.bbox[2], b.bbox[2])
        if overlap_x1 > overlap_x0:
            ev.x_overlap_ratio = (overlap_x1 - overlap_x0) / min(a_width, b_width)

    # --- Header row match ---
    if a._data and b._data and len(a._data) > 0 and len(b._data) > 0:
        ev.header_match = (a._data[0] == b._data[0])

    # --- Row counts and header-stub detection ---
    ev.rows_a = len(a._data) if a._data else (a._rows or 0)
    ev.rows_b = len(b._data) if b._data else (b._rows or 0)
    ev.table_a_is_header_stub = ev.rows_a <= 3

    # --- Position on page (near top/bottom) ---
    # Table A near bottom of its page (bottom 15% of page)
    if pdf_path and a.bbox != (0.0, 0.0, 0.0, 0.0):
        try:
            from .pdf_bridge import get_page_dimensions
            _, page_h_a = get_page_dimensions(pdf_path, a.page_index)
            a_bottom = a.bbox[3]  # y1 in top-left coords
            ev.table_a_at_page_bottom = a_bottom > page_h_a * 0.85
        except Exception:
            pass

    # Table B near top of its page (top 15% of page)
    if pdf_path and b.bbox != (0.0, 0.0, 0.0, 0.0):
        try:
            from .pdf_bridge import get_page_dimensions
            _, page_h_b = get_page_dimensions(pdf_path, b.page_index)
            b_top = b.bbox[1]  # y0 in top-left coords
            ev.table_b_at_page_top = b_top < page_h_b * 0.15
        except Exception:
            pass

    # --- Text between table A bottom and page end ---
    # If there's body text between table A and the page bottom, less likely a split
    if pdf_path and a.bbox != (0.0, 0.0, 0.0, 0.0):
        try:
            from .pdf_bridge import extract_text_elements
            text_els = extract_text_elements(pdf_path, a.page_index)
            a_bottom = a.bbox[3]
            text_below = [
                t for t in text_els
                if t.y0 > a_bottom + 5  # at least 5pt below table
            ]
            ev.text_between_tables = len(text_below) > 0
        except Exception:
            pass

    # --- Font consistency between tables ---
    if pdf_path and a.bbox != (0.0, 0.0, 0.0, 0.0) and b.bbox != (0.0, 0.0, 0.0, 0.0):
        try:
            size_a, bold_a, italic_a = _dominant_font(pdf_path, a.page_index, a.bbox)
            size_b, bold_b, italic_b = _dominant_font(pdf_path, b.page_index, b.bbox)
            ev.font_size_a = size_a
            ev.font_size_b = size_b
            ev.font_size_match = (size_a > 0 and size_b > 0 and size_a == size_b)
            ev.font_style_match = (bold_a == bold_b and italic_a == italic_b)
        except Exception:
            pass

    # --- Column boundary alignment ---
    if a.cells and b.cells:
        ev.col_boundaries_a = _extract_column_boundaries(a.cells)
        ev.col_boundaries_b = _extract_column_boundaries(b.cells)
        rmse = _column_boundary_rmse(ev.col_boundaries_a, ev.col_boundaries_b)
        ev.col_boundary_rmse = rmse
        ev.col_boundary_match = (rmse < 5.0)  # within 5pt tolerance

    # --- Cell edge pattern (border lines) ---
    if a.cells and b.cells:
        ev.edge_pattern_a = _cell_edge_pattern(a.cells)
        ev.edge_pattern_b = _cell_edge_pattern(b.cells)
        ev.edge_pattern_match = (
            ev.edge_pattern_a != "" and ev.edge_pattern_a == ev.edge_pattern_b
        )

    return ev


def _decide_merge(
    ev: MergeEvidence,
    a: Table,
    b: Table,
    pdf_path: str | None = None,
) -> bool:
    """Delegate merge decision to /table-lab agent, with heuristic fallback.

    /table-lab receives the full evidence bundle and makes the call.
    The heuristic fallback only fires when /table-lab is unavailable.
    """
    # --- /table-lab agent decision (primary) ---
    if pdf_path:
        try:
            from table_lab.merge_tuner import should_merge_native
            should, confidence, method = should_merge_native(
                a.to_dict(), b.to_dict(), pdf_path,
            )
            logger.debug(
                f"table-lab decision: {should} (conf={confidence:.2f}, method={method}) "
                f"for p{ev.table_a_page}→p{ev.table_b_page}"
            )
            # Ambiguous zone: quarantine for human review
            if 0.3 <= confidence < 0.5:
                _quarantine_ambiguous_merge(ev, pdf_path, confidence, method)
                return False  # Don't merge when uncertain
            if confidence >= 0.5:
                return should
        except ImportError:
            pass  # table-lab not installed
        except Exception as e:
            logger.debug(f"table-lab error: {e}")

    # --- Offline heuristic fallback ---
    # Only used when no agent is available. Interprets evidence deterministically.
    logger.debug(
        f"Heuristic fallback for p{ev.table_a_page}→p{ev.table_b_page}: "
        f"header_between={ev.section_header_between}, continued={ev.continued_keyword}, "
        f"cols_match={ev.col_count_match}, width_ratio={ev.width_ratio:.2f}, "
        f"x_overlap={ev.x_overlap_ratio:.2f}, font_match={ev.font_size_match}, "
        f"col_bound_match={ev.col_boundary_match}(rmse={ev.col_boundary_rmse:.1f}), "
        f"edge_match={ev.edge_pattern_match}, stub={ev.table_a_is_header_stub}"
    )

    # Strong negatives
    if ev.section_header_between:
        return False

    # Strong positives
    if ev.continued_keyword:
        return True

    # Weak signals — require convergence of multiple signals
    if not ev.col_count_match:
        return False

    # Header-stub relaxation: when one table has <=3 rows (likely just a header
    # row split at page break), the header fragment is often narrower than the
    # data table because long cell values haven't stretched the columns yet.
    # Relax width_ratio from 0.9 to 0.5 in this case.
    min_rows = min(
        len(a._data) if a._data else a._rows or 999,
        len(b._data) if b._data else b._rows or 999,
    )
    width_threshold = 0.5 if min_rows <= 3 else 0.9

    if ev.width_ratio < width_threshold:
        return False
    if ev.x_overlap_ratio < 0.5:
        return False

    return True


def _quarantine_ambiguous_merge(
    ev: MergeEvidence,
    pdf_path: str,
    confidence: float,
    method: str,
) -> None:
    """Defer an ambiguous merge decision to /interview for human review.

    Called when table-lab confidence is in the 0.3-0.5 range — too uncertain
    to decide automatically but with enough signal to warrant human attention.
    """
    try:
        from .evidence_matrix import log_merge_evidence
        log_merge_evidence(ev, confidence=confidence, should_merge="needs_human")
    except Exception:
        pass

    try:
        # Import defer_pdf from learn-datalake
        import sys
        _ld_dir = str(Path(__file__).resolve().parent.parent.parent.parent.parent / "learn-datalake")
        if _ld_dir not in sys.path:
            sys.path.insert(0, _ld_dir)
        from pdf_discovery import defer_pdf

        questions = [
            {
                "id": f"merge_p{ev.table_a_page}_p{ev.table_b_page}",
                "text": (
                    f"Should the table on page {ev.table_a_page} be merged with "
                    f"the table on page {ev.table_b_page}? "
                    f"Columns match: {ev.col_count_match}, "
                    f"width ratio: {ev.width_ratio:.2f}, "
                    f"continued keyword: {ev.continued_keyword}"
                ),
                "type": "yes_no_refine",
                "recommendation": "no" if confidence < 0.4 else "yes",
                "reason": f"table-lab confidence={confidence:.2f} ({method})",
            }
        ]

        # Capture evidence screenshots if possible
        screenshots: list[str] = []
        try:
            from .pdf_bridge import render_page_image
            screenshot_dir = Path(__file__).resolve().parent.parent.parent / "state" / "quarantine_screenshots"
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            stem = Path(pdf_path).stem
            for page_num in (ev.table_a_page, ev.table_b_page):
                img = render_page_image(pdf_path, page_num - 1, dpi=150)
                fname = f"{stem}_p{page_num}_merge.png"
                img_path = screenshot_dir / fname
                img.save(str(img_path))
                screenshots.append(str(img_path))
        except Exception:
            pass

        defer_pdf(
            Path(pdf_path),
            reason="ambiguous_merge",
            detail=(
                f"Merge decision uncertain (conf={confidence:.2f}) for "
                f"p{ev.table_a_page}→p{ev.table_b_page}. "
                f"cols_match={ev.col_count_match}, width_ratio={ev.width_ratio:.2f}"
            ),
            questions=questions,
            screenshot_paths=screenshots if screenshots else None,
            metadata=ev.to_dict(),
        )
        logger.info(
            f"quarantine_merge p{ev.table_a_page}→p{ev.table_b_page} "
            f"conf={confidence:.2f} pdf={Path(pdf_path).name}"
        )
    except Exception as e:
        logger.debug(f"quarantine_merge_failed: {e}")


def merge_split_tables(
    tables: list[Table],
    pdf_path: str | None = None,
    password: str | None = None,
) -> list[Table]:
    """Merge tables that span across page breaks.

    Args:
        tables: List of tables sorted by (page_number, y0, x0)
        pdf_path: Path to PDF (needed for section detection + /table-lab)
        password: PDF password if encrypted

    Returns:
        Merged list (may be shorter than input)
    """
    if len(tables) <= 1:
        return tables

    merged = []
    skip = set()

    for i, table in enumerate(tables):
        if i in skip:
            continue

        current = table
        j = i + 1
        while j < len(tables):
            candidate = tables[j]
            evidence = _gather_evidence(current, candidate, pdf_path, password)
            if evidence is not None and _decide_merge(evidence, current, candidate, pdf_path):
                current = _merge_pair(current, candidate)
                skip.add(j)
                j += 1
            else:
                break

        merged.append(current)

    return merged


def _merge_pair(a: Table, b: Table) -> Table:
    """Merge table b into table a."""
    components = []
    if a.components:
        components.extend(a.components)
    else:
        components.append({"page_number": a.page_number, "bbox": a.bbox})
    components.append({"page_number": b.page_number, "bbox": b.bbox})

    # Merge data — skip duplicate header row
    merged_data = None
    if a._data and b._data:
        b_data = b._data
        if (len(a._data) > 0 and len(b_data) > 0
                and a._data[0] == b_data[0]):
            b_data = b_data[1:]
        merged_data = a._data + b_data
    elif a._data:
        merged_data = a._data
    elif b._data:
        merged_data = b._data

    # Merge DataFrames
    merged_df = None
    if a._df is not None and b._df is not None:
        try:
            if list(a._df.columns) == list(b._df.columns):
                merged_df = pl.concat([a._df, b._df])
            else:
                merged_df = a._df
        except Exception:
            merged_df = a._df
    elif a._df is not None:
        merged_df = a._df
    elif b._df is not None:
        merged_df = b._df

    merged_cells = list(a.cells) + list(b.cells)
    merged_bbox = a.bbox

    return Table(
        cells=merged_cells,
        page_number=a.page_number,
        page_index=a.page_index,
        bbox=merged_bbox,
        strategy=a.strategy,
        accuracy=min(a.accuracy, b.accuracy),
        whitespace=max(a.whitespace, b.whitespace),
        title=a.title,
        title_bbox=a.title_bbox,
        ai_title=a.ai_title,
        section_id=a.section_id,
        components=components,
        _data=merged_data,
        _df=merged_df,
        _rows=a._rows + b._rows,
        _cols=max(a._cols, b._cols),
    )
