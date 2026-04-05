"""Text-to-cell assignment for lattice table extraction.

Implements Camelot-compatible text assignment: overlap-based column matching
with span splitting for pdf_oxide spans that cross column boundaries.
"""
from __future__ import annotations

from ..models import Cell
from ..pdf_bridge import TextElement


def _split_spanning_elements(
    text_elements: list[TextElement],
    col_boundaries: list[float],
    cells: list[Cell] | None = None,
) -> list[TextElement]:
    """Split text elements that span multiple columns at column boundaries.

    When pdf_oxide merges adjacent characters into a single span (e.g.,
    "1. 1967 " spanning the "Sl. No." and "Year" columns), this function
    splits the span at column boundaries so each piece can be assigned to
    the correct cell.

    Uses proportional text splitting: characters are allocated to sub-spans
    based on the fraction of the span width in each column.
    """
    if len(col_boundaries) < 2:
        return text_elements

    result: list[TextElement] = []
    for elem in text_elements:
        text = elem.text.rstrip()
        if not text:
            result.append(elem)
            continue

        # Find which column boundaries this span crosses
        crossed = []
        for bx in col_boundaries:
            if elem.x0 + 2.0 < bx < elem.x1 - 2.0:
                # Skip boundaries internal to a spanning cell
                if cells:
                    elem_cy = (elem.y0 + elem.y1) / 2.0
                    internal = False
                    for cell in cells:
                        # Check if boundary is within a wide cell
                        if (cell.x0 + 2 < bx < cell.x1 - 2
                                and cell.y0 - 2 <= elem_cy <= cell.y1 + 2):
                            internal = True
                            break
                        # Check if cell at boundary lacks left edge
                        # (part of a spanning group)
                        if (abs(cell.x0 - bx) < 2.0
                                and cell.y0 - 2 <= elem_cy <= cell.y1 + 2
                                and not cell.left):
                            internal = True
                            break
                    if internal:
                        continue
                crossed.append(bx)

        if not crossed:
            result.append(elem)
            continue

        # Split the text proportionally at each boundary
        splits = [elem.x0] + crossed + [elem.x1]
        total_width = elem.x1 - elem.x0
        if total_width <= 0:
            result.append(elem)
            continue

        char_width = total_width / max(len(text), 1)

        # Split text into (word, trailing_whitespace) tokens preserving
        # original spacing (including multi-space runs).
        import re
        tokens = re.findall(r'(\S+)(\s*)', text)

        # Pre-assign each word to exactly one segment (closest center)
        word_positions = []
        pos = elem.x0
        for word, ws in tokens:
            word_center = pos + len(word) * char_width / 2
            word_positions.append((word, ws, word_center))
            pos += (len(word) + len(ws)) * char_width

        for i in range(len(splits) - 1):
            seg_left = splits[i]
            seg_right = splits[i + 1]

            seg_parts = []
            for word, ws, word_center in word_positions:
                if seg_left - 2 <= word_center <= seg_right + 2:
                    # Check this word isn't closer to an adjacent segment
                    in_this = True
                    if word_center > seg_right:
                        # Near right edge — check if next segment is closer
                        if i + 1 < len(splits) - 1:
                            in_this = False
                    elif word_center < seg_left:
                        # Near left edge — check if prev segment is closer
                        if i > 0:
                            in_this = False
                    if in_this:
                        seg_parts.append(word + ws)

            seg_text = "".join(seg_parts).strip()
            if not seg_text:
                continue

            result.append(TextElement(
                text=seg_text,
                x0=seg_left,
                y0=elem.y0,
                x1=seg_right,
                y1=elem.y1,
                font_name=elem.font_name,
                font_size=elem.font_size,
                is_bold=elem.is_bold,
                is_italic=elem.is_italic,
            ))

    return result


def _find_best_row(cy: float, row_boundaries: list[float], tol: float) -> int:
    """Find which row a y-center belongs to using row boundaries.

    row_boundaries is sorted ascending: [y0, y1, y2, ...] where row i
    spans from row_boundaries[i] to row_boundaries[i+1].

    Returns row index, or -1 if not found.
    """
    for i in range(len(row_boundaries) - 1):
        y_lo = row_boundaries[i]
        y_hi = row_boundaries[i + 1]
        # Allow tolerance at grid edges
        if i == 0:
            y_lo -= tol
        if i == len(row_boundaries) - 2:
            y_hi += tol
        if y_lo <= cy <= y_hi:
            return i
    return -1


def _find_best_col(
    elem_x0: float, elem_x1: float, col_boundaries: list[float]
) -> int:
    """Find which column has maximum overlap with element x-range.

    col_boundaries is sorted ascending. Returns column index or -1.
    """
    best_col = -1
    best_overlap = -1.0
    for i in range(len(col_boundaries) - 1):
        c_lo = col_boundaries[i]
        c_hi = col_boundaries[i + 1]
        overlap_left = max(elem_x0, c_lo)
        overlap_right = min(elem_x1, c_hi)
        if overlap_right <= overlap_left:
            continue
        col_width = c_hi - c_lo
        if col_width <= 0:
            continue
        ratio = (overlap_right - overlap_left) / col_width
        if ratio > best_overlap:
            best_overlap = ratio
            best_col = i
    return best_col


def assign_text_to_cells(
    cells: list[Cell],
    text_elements: list[TextElement],
    strip_text: str = "",
    col_boundaries: list[float] | None = None,
    row_boundaries: list[float] | None = None,
) -> None:
    """Assign text elements to cells using overlap-based column matching.

    Mirrors Camelot's get_table_index: uses y-center for row matching and
    maximum overlap ratio for column matching. Spans crossing column
    boundaries are split first.

    When row_boundaries are provided, uses explicit row-index matching
    (like Camelot's row-based assignment) instead of cell-containment
    matching. This handles coordinate offsets between pdf_oxide and pdfminer.
    """
    if col_boundaries:
        text_elements = _split_spanning_elements(
            text_elements, col_boundaries, cells=cells,
        )

    # If we have both row and column boundaries, use grid-index-based
    # assignment (mirrors Camelot's get_table_index exactly)
    if row_boundaries and col_boundaries and len(row_boundaries) >= 2 and len(col_boundaries) >= 2:
        _assign_by_grid_index(
            cells, text_elements, row_boundaries, col_boundaries, strip_text
        )
        return

    # Fallback: cell-containment-based assignment
    _assign_by_cell_containment(cells, text_elements, strip_text)


def _estimate_y_offset(
    text_elements: list[TextElement],
    row_boundaries: list[float],
    col_boundaries: list[float],
) -> float:
    """Estimate systematic y-offset between text positions and grid.

    pdf_oxide may report text coordinates shifted relative to line-detected
    grid boundaries. This function detects the offset by checking how many
    text elements fall inside the grid vs above/below, and finds the shift
    that maximizes in-grid assignment.

    Returns the y-offset to ADD to text cy values for correct row matching.
    """
    if not text_elements or len(row_boundaries) < 2:
        return 0.0

    grid_top = row_boundaries[0]
    grid_bottom = row_boundaries[-1]
    x_lo = col_boundaries[0] if col_boundaries else 0
    x_hi = col_boundaries[-1] if col_boundaries else float("inf")

    # Collect cy values for text within the grid's x-range
    cys = []
    for e in text_elements:
        cx = (e.x0 + e.x1) / 2.0
        if x_lo - 5 <= cx <= x_hi + 5:
            cy = (e.y0 + e.y1) / 2.0
            cys.append(cy)

    if len(cys) < 3:
        return 0.0

    # Count how many fall inside the grid at different offsets
    best_offset = 0.0
    best_count = 0
    for offset_candidate in [0.0, 5.0, 10.0, 15.0, 20.0, -5.0]:
        count = sum(
            1 for cy in cys
            if grid_top - 3 <= cy + offset_candidate <= grid_bottom + 3
        )
        if count > best_count:
            best_count = count
            best_offset = offset_candidate

    # Only apply offset if it significantly improves matching
    base_count = sum(
        1 for cy in cys
        if grid_top - 3 <= cy <= grid_bottom + 3
    )
    if best_offset != 0.0 and best_count > base_count * 1.1:
        return best_offset
    return 0.0


def _gap_separator(last_x1: float, next_x0: float, font_size: float) -> str:
    """Choose separator based on x-gap between consecutive same-line spans.

    Justified text has wider word gaps that pdfminer renders as double
    spaces. pdf_oxide splits these into separate spans; we detect the
    wider gap and insert proportional spacing.
    """
    gap = next_x0 - last_x1
    space_w = max(font_size * 0.25, 2.0) if font_size > 0 else 2.5
    if gap < 0:
        return " "  # overlapping spans: separate words need a space
    if gap < space_w * 0.3:
        return ""   # zero-gap: adjacent spans, no space
    if gap > space_w * 1.3:
        return "  "  # wide gap: justified text, double space
    return " "       # normal gap: single space


def _assign_by_grid_index(
    cells: list[Cell],
    text_elements: list[TextElement],
    row_boundaries: list[float],
    col_boundaries: list[float],
    strip_text: str,
) -> None:
    """Assign text to cells using row/col index matching (Camelot-style)."""
    n_rows = len(row_boundaries) - 1
    n_cols = len(col_boundaries) - 1

    # Build cell lookup: (row_idx, col_idx) -> Cell
    cell_grid: dict[tuple[int, int], Cell] = {}
    for cell in cells:
        # Find this cell's grid position
        ri = -1
        ci = -1
        cell_cy = (cell.y0 + cell.y1) / 2.0
        cell_cx = (cell.x0 + cell.x1) / 2.0
        for r in range(n_rows):
            if row_boundaries[r] - 1 <= cell_cy <= row_boundaries[r + 1] + 1:
                ri = r
                break
        for c in range(n_cols):
            if col_boundaries[c] - 1 <= cell_cx <= col_boundaries[c + 1] + 1:
                ci = c
                break
        if ri >= 0 and ci >= 0:
            cell_grid[(ri, ci)] = cell


    # Detect and compensate for systematic y-offset (pdf_oxide vs grid coords)
    y_offset = _estimate_y_offset(text_elements, row_boundaries, col_boundaries)

    # Compute edge tolerance for border rows
    row_heights = [row_boundaries[i+1] - row_boundaries[i] for i in range(n_rows)]
    median_h = sorted(row_heights)[len(row_heights) // 2] if row_heights else 12.0
    edge_tol = min(median_h * 0.5, 8.0)

    # Track last y and x1 per cell for line separation and spacing
    cell_last_y: dict[tuple[int, int], float] = {}
    cell_last_x1: dict[tuple[int, int], float] = {}

    sorted_elems = sorted(text_elements, key=lambda e: (e.y0, e.x0))

    for elem in sorted_elems:
        cy = (elem.y0 + elem.y1) / 2.0 + y_offset
        if not elem.text.strip():
            continue

        ri = _find_best_row(cy, row_boundaries, edge_tol)
        ci = _find_best_col(elem.x0, elem.x1, col_boundaries)

        if ri < 0 or ci < 0:
            # Fallback: nearest cell within 5pt
            cx = (elem.x0 + elem.x1) / 2.0
            best_dist = float("inf")
            best_key = None
            for (r, c), cell in cell_grid.items():
                clamped_x = max(cell.x0, min(cx, cell.x1))
                clamped_y = max(cell.y0, min(cy, cell.y1))
                dist = ((cx - clamped_x) ** 2 + (cy - clamped_y) ** 2) ** 0.5
                if dist < best_dist and dist < 5.0:
                    best_dist = dist
                    best_key = (r, c)
            if best_key is None:
                continue
            ri, ci = best_key

        key = (ri, ci)
        cell = cell_grid.get(key)
        if cell is None:
            continue

        # Record first text element's y0 for spanning cell ordering
        if not cell.text and cell._text_y0 == 0.0:
            cell._text_y0 = elem.y0

        # Pdfminer text lines have trailing \n — just concatenate like
        # Camelot does (Cell.text setter is raw concat, no separator logic).
        # For pdf_oxide text (no trailing \n), fall back to y_thresh heuristic.
        if elem.text.endswith("\n"):
            # Pdfminer path: direct concatenation preserves natural line breaks
            if cell.text is None:
                cell.text = elem.text
            else:
                cell.text += elem.text
        else:
            text = elem.text.strip()
            if not text:
                continue
            if cell.text:
                last_y = cell_last_y.get(key, cy)
                y_thresh = max(elem.font_size * 0.6, 3.0) if elem.font_size > 0 else 3.0
                if abs(cy - last_y) > y_thresh:
                    sep = "\n"
                    # Strip trailing whitespace before newline to match Camelot
                    cell.text = cell.text.rstrip()
                else:
                    sep = _gap_separator(
                        cell_last_x1.get(key, elem.x0), elem.x0, elem.font_size
                    )
                cell.text += sep + text
            else:
                cell.text = text
        cell_last_y[key] = cy
        cell_last_x1[key] = elem.x1

    if strip_text:
        for cell in cells:
            if cell.text:
                for ch in strip_text:
                    cell.text = cell.text.replace(ch, "")


def _assign_by_cell_containment(
    cells: list[Cell],
    text_elements: list[TextElement],
    strip_text: str,
) -> None:
    """Assign text to cells using cell-containment matching (original approach)."""
    if cells:
        grid_y_min = min(c.y0 for c in cells)
        grid_y_max = max(c.y1 for c in cells)
        row_heights = sorted(set(c.y1 - c.y0 for c in cells))
        median_row_h = row_heights[len(row_heights) // 2] if row_heights else 12.0
        edge_tol = min(median_row_h * 0.4, 5.0)
    else:
        grid_y_min = grid_y_max = 0.0
        edge_tol = 3.0

    cell_last_y: dict[int, float] = {}
    cell_last_x1: dict[int, float] = {}
    sorted_elems = sorted(text_elements, key=lambda e: (e.y0, e.x0))

    for elem in sorted_elems:
        cy = (elem.y0 + elem.y1) / 2.0
        text = elem.text.strip()
        if not text:
            continue

        best = None
        best_overlap = -1.0
        best_area = float("inf")

        for cell in cells:
            y_lo = cell.y0 - (edge_tol if cell.y0 <= grid_y_min + 0.5 else 0)
            y_hi = cell.y1 + (edge_tol if cell.y1 >= grid_y_max - 0.5 else 0)
            if not (y_lo <= cy <= y_hi):
                continue

            overlap_left = max(elem.x0, cell.x0)
            overlap_right = min(elem.x1, cell.x1)
            if overlap_right <= overlap_left:
                continue

            cell_width = cell.x1 - cell.x0
            if cell_width <= 0:
                continue
            overlap_ratio = (overlap_right - overlap_left) / cell_width

            area = cell_width * (cell.y1 - cell.y0)
            if overlap_ratio > best_overlap or (
                overlap_ratio == best_overlap and area < best_area
            ):
                best = cell
                best_overlap = overlap_ratio
                best_area = area

        if best is None:
            cx = (elem.x0 + elem.x1) / 2.0
            best_dist = float("inf")
            for cell in cells:
                clamped_x = max(cell.x0, min(cx, cell.x1))
                clamped_y = max(cell.y0, min(cy, cell.y1))
                dist = ((cx - clamped_x) ** 2 + (cy - clamped_y) ** 2) ** 0.5
                if dist < best_dist and dist < 5.0:
                    best_dist = dist
                    best = cell

        if best is not None:
            cell_id = id(best)
            if best.text:
                last_y = cell_last_y.get(cell_id, cy)
                y_thresh = max(elem.font_size * 0.6, 3.0) if elem.font_size > 0 else 3.0
                if abs(cy - last_y) > y_thresh:
                    sep = "\n"
                    # Strip trailing whitespace before newline to match Camelot
                    best.text = best.text.rstrip()
                else:
                    sep = _gap_separator(
                        cell_last_x1.get(cell_id, elem.x0), elem.x0, elem.font_size
                    )
                best.text += sep + text
            else:
                best.text = text
            cell_last_y[cell_id] = cy
            cell_last_x1[cell_id] = elem.x1

    if strip_text:
        for cell in cells:
            if cell.text:
                for ch in strip_text:
                    cell.text = cell.text.replace(ch, "")
