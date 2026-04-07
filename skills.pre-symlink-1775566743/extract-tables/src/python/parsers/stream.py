"""Stream table parser -- extracts tables from borderless/text-only tables.

Uses text positioning to detect columns and rows without relying on
ruled lines or image processing. Based on Camelot's stream parser and
Anssi Nurminen's table detection algorithm.

All coordinates are top-left origin: (x0, y0_top, x1, y1_bottom) where y=0 is top of page.
"""
from __future__ import annotations

import math
import warnings
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from ..models import Table, Cell
from ..pdf_bridge import TextElement, extract_text_elements, get_page_dimensions


@dataclass(slots=True)
class _TextProxy:
    """Lightweight wrapper so row/col logic can work with TextElement."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    font_size: float = 0.0

    def get_text(self) -> str:
        return self.text


def _elements_to_proxies(elements: list[TextElement]) -> list[_TextProxy]:
    return [
        _TextProxy(text=e.text, x0=e.x0, y0=e.y0, x1=e.x1, y1=e.y1,
                    font_size=e.font_size)
        for e in elements
    ]


class StreamParser:
    """Extract tables from borderless tables using text positioning.

    Algorithm:
        1. Get text elements from pdf_bridge
        2. Group text into rows by y-position proximity
        3. Detect column boundaries from text x-position clustering
        4. Build grid from rows x columns
        5. Assign text to cells

    Parameters
    ----------
    edge_tol : float
        Tolerance for edge detection (default 50).
    row_tol : float
        Tolerance for row grouping -- y-axis gap (default 2).
    column_tol : float
        Tolerance for column merging (default 0).
    """

    def __init__(
        self,
        edge_tol: float = 50,
        row_tol: float = 2,
        column_tol: float = 0,
    ):
        self.edge_tol = edge_tol
        self.row_tol = row_tol
        self.column_tol = column_tol

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_tables(
        self,
        pdf_path: str,
        page_num: int,
        *,
        table_areas: Optional[list[str]] = None,
        columns: Optional[list[str]] = None,
        **params,
    ) -> list[Table]:
        """Extract tables from *pdf_path* page *page_num* (0-indexed).

        Returns a list of Table objects with top-left-origin bboxes.
        """
        edge_tol = params.get("edge_tol", self.edge_tol)
        row_tol = params.get("row_tol", self.row_tol)
        column_tol = params.get("column_tol", self.column_tol)

        # --- 1. Extract text elements (already top-left origin) ---------
        try:
            elements = extract_text_elements(pdf_path, page_num)
        except Exception:
            return []

        if not elements:
            return []

        page_w, page_h = get_page_dimensions(pdf_path, page_num)
        proxies = _elements_to_proxies(elements)

        # --- 2. Determine table area(s) ---------------------------------
        if table_areas is not None:
            bboxes = [self._bbox_from_str(s) for s in table_areas]
        else:
            bboxes = [self._detect_table_area(proxies, page_w, page_h)]

        tables: list[Table] = []
        for idx, bbox in enumerate(bboxes):
            tbl = self._extract_one_table(
                proxies, bbox, page_w, page_h, page_num, row_tol, column_tol,
                user_cols=self._parse_user_cols(columns, idx) if columns else None,
            )
            if tbl is not None:
                tables.append(tbl)
        return tables

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bbox_from_str(s: str) -> tuple[float, float, float, float]:
        parts = [float(v) for v in s.split(",")]
        x0, y0, x1, y1 = parts
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    @staticmethod
    def _parse_user_cols(columns: list[str], idx: int) -> Optional[list[float]]:
        if idx >= len(columns):
            return None
        col_str = columns[idx]
        if not col_str:
            return None
        return [float(c) for c in col_str.split(",")]

    # ------------------------------------------------------------------
    # Table area detection
    # ------------------------------------------------------------------

    def _detect_table_area(
        self,
        proxies: list[_TextProxy],
        page_w: float,
        page_h: float,
    ) -> tuple[float, float, float, float]:
        """Return the bounding box of all text on the page as default table area."""
        if not proxies:
            return (0, 0, page_w, page_h)
        x0 = min(p.x0 for p in proxies)
        y0 = min(p.y0 for p in proxies)
        x1 = max(p.x1 for p in proxies)
        y1 = max(p.y1 for p in proxies)
        return (x0, y0, x1, y1)

    # ------------------------------------------------------------------
    # Row grouping  (top-left origin: smaller y0 = higher on page)
    # ------------------------------------------------------------------

    @staticmethod
    def _group_rows(
        proxies: list[_TextProxy], row_tol: float = 2,
    ) -> list[list[_TextProxy]]:
        """Group text objects into rows by y-position proximity.

        Sorted top-to-bottom (ascending y0 in top-left origin).
        """
        if not proxies:
            return []

        non_empty = [p for p in proxies if p.text.strip()]
        if not non_empty:
            return []

        # Sort top-to-bottom, then left-to-right
        non_empty.sort(key=lambda p: (p.y0, p.x0))

        rows: list[list[_TextProxy]] = []
        current_row: list[_TextProxy] = [non_empty[0]]
        row_y = non_empty[0].y0

        for p in non_empty[1:]:
            if math.isclose(p.y0, row_y, abs_tol=row_tol):
                current_row.append(p)
                # Update row_y to be forgiving of gradual drift
                row_y = p.y0
            else:
                rows.append(sorted(current_row, key=lambda t: t.x0))
                current_row = [p]
                row_y = p.y0

        if current_row:
            rows.append(sorted(current_row, key=lambda t: t.x0))

        return rows

    # ------------------------------------------------------------------
    # Row boundaries (continuous, top-left origin)
    # ------------------------------------------------------------------

    @staticmethod
    def _make_row_boundaries(
        rows_grouped: list[list[_TextProxy]],
        text_y_min: float,
        text_y_max: float,
    ) -> list[tuple[float, float]]:
        """Return continuous row boundaries as (top, bottom) tuples in top-left origin.

        top < bottom since y increases downward.
        """
        if not rows_grouped:
            return []

        # For each row group: (min_y0, max_y1) -- top-left origin
        bounds = [
            (min(t.y0 for t in r), max(t.y1 for t in r))
            for r in rows_grouped
        ]

        # Make boundaries continuous by splitting gaps
        for i in range(len(bounds) - 1):
            gap_mid = (bounds[i][1] + bounds[i + 1][0]) / 2.0
            bounds[i] = (bounds[i][0], gap_mid)
            bounds[i + 1] = (gap_mid, bounds[i + 1][1])

        # Extend first and last
        bounds[0] = (text_y_min, bounds[0][1])
        bounds[-1] = (bounds[-1][0], text_y_max)

        return bounds

    # ------------------------------------------------------------------
    # Column detection
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_columns(
        cl: list[tuple[float, float]], column_tol: float = 0,
    ) -> list[tuple[float, float]]:
        """Merge overlapping column boundary tuples."""
        merged: list[tuple[float, float]] = []
        for higher in cl:
            if not merged:
                merged.append(higher)
            else:
                lower = merged[-1]
                if column_tol >= 0:
                    if higher[0] <= lower[1] or math.isclose(
                        higher[0], lower[1], abs_tol=column_tol
                    ):
                        merged[-1] = (min(lower[0], higher[0]), max(lower[1], higher[1]))
                    else:
                        merged.append(higher)
                else:
                    if higher[0] <= lower[1]:
                        if math.isclose(higher[0], lower[1], abs_tol=abs(column_tol)):
                            merged.append(higher)
                        else:
                            merged[-1] = (min(lower[0], higher[0]), max(lower[1], higher[1]))
                    else:
                        merged.append(higher)
        return merged

    @staticmethod
    def _cluster_x_positions(
        positions: list[float], tol: float = 5.0,
    ) -> list[list[float]]:
        """Cluster sorted x-positions within tolerance into groups."""
        if not positions:
            return []
        positions = sorted(positions)
        clusters: list[list[float]] = [[positions[0]]]
        for p in positions[1:]:
            if p - clusters[-1][-1] <= tol:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        return clusters

    @staticmethod
    def _detect_columns(
        rows_grouped: list[list[_TextProxy]],
        column_tol: float = 0,
        row_tol: float = 2,
    ) -> list[tuple[float, float]]:
        """Detect column boundaries from text positions.

        Uses Camelot's mode-based approach: count elements per row,
        find the mode (most common count), then collect column bounds
        from rows with exactly that many elements. Text between/outside
        detected columns is handled by adding extra columns.
        """
        if not rows_grouped:
            return []

        all_text = [t for r in rows_grouped for t in r]
        if not all_text:
            return []

        # Count elements per row and find mode (Camelot's approach)
        elements = [len(r) for r in rows_grouped]
        if not elements:
            return [(min(t.x0 for t in all_text), max(t.x1 for t in all_text))]

        ncols = max(set(elements), key=elements.count)
        if ncols == 1:
            # If mode is 1, try removing all 1s and recalculate
            filtered = [c for c in elements if c != 1]
            if filtered:
                ncols = max(set(filtered), key=filtered.count)
            else:
                return [(min(t.x0 for t in all_text), max(t.x1 for t in all_text))]

        if ncols <= 1:
            return [(min(t.x0 for t in all_text), max(t.x1 for t in all_text))]

        # Collect column bounds from rows matching ncols
        cols = [
            (t.x0, t.x1) for r in rows_grouped if len(r) == ncols for t in r
        ]
        cols = StreamParser._merge_columns(sorted(cols), column_tol=column_tol)

        # Pick up text that falls between or outside detected columns
        inner_text: list[_TextProxy] = []
        for i in range(1, len(cols)):
            left = cols[i - 1][1]
            right = cols[i][0]
            inner_text.extend(
                t for t in all_text if t.x0 > left and t.x1 < right
            )

        outer_text = [
            t for t in all_text if t.x0 > cols[-1][1] or t.x1 < cols[0][0]
        ]
        inner_text.extend(outer_text)

        # Add columns for outlier text (Camelot's _add_columns)
        if inner_text:
            extra_rows = StreamParser._group_rows(inner_text, row_tol=row_tol)
            extra_counts = [len(r) for r in extra_rows]
            if extra_counts:
                new_cols = [
                    (t.x0, t.x1)
                    for r in extra_rows
                    if len(r) == max(extra_counts)
                    for t in r
                ]
                cols.extend(StreamParser._merge_columns(sorted(new_cols)))

        return cols

    @staticmethod
    def _join_columns(
        cols: list[tuple[float, float]],
        text_x_min: float,
        text_x_max: float,
    ) -> list[tuple[float, float]]:
        """Make column boundaries continuous."""
        if not cols:
            return []
        cols = sorted(cols)
        midpoints = [(cols[i][0] + cols[i - 1][1]) / 2 for i in range(1, len(cols))]
        boundaries = [text_x_min] + midpoints + [text_x_max]
        return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]

    # ------------------------------------------------------------------
    # Build table grid and assign text
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_title_footer_rows(
        rows_grouped: list[list[_TextProxy]],
    ) -> list[list[_TextProxy]]:
        """Remove title and footer rows that aren't part of the table.

        Camelot's Nurminen algorithm detects table boundaries to exclude
        non-table text. We approximate this by removing leading/trailing
        rows whose element count is much lower than the table's typical
        column count (mode). Title rows typically have 1-2 elements while
        data rows have ncols elements.
        """
        if len(rows_grouped) < 3:
            return rows_grouped

        # Find the mode of element counts
        counts = [len(r) for r in rows_grouped]
        ncols = max(set(counts), key=counts.count)
        if ncols == 1:
            filtered = [c for c in counts if c > 1]
            if filtered:
                ncols = max(set(filtered), key=filtered.count)
            else:
                return rows_grouped

        # Threshold: rows with fewer than half the mode elements
        # at leading/trailing positions are titles/footers
        threshold = max(ncols // 2, 2)

        # Strip leading rows below threshold
        start = 0
        while start < len(rows_grouped) and len(rows_grouped[start]) < threshold:
            start += 1

        # Strip trailing rows below threshold
        end = len(rows_grouped)
        while end > start and len(rows_grouped[end - 1]) < threshold:
            end -= 1

        if start >= end:
            return rows_grouped

        return rows_grouped[start:end]

    def _extract_one_table(
        self,
        proxies: list[_TextProxy],
        bbox: tuple[float, float, float, float],
        page_w: float,
        page_h: float,
        page_num: int,
        row_tol: float,
        column_tol: float,
        user_cols: Optional[list[float]] = None,
    ) -> Optional[Table]:
        """Build a single Table from proxies within bbox."""
        bx0, by0, bx1, by1 = bbox

        # Filter text within bbox (center must be inside, with 2pt tolerance)
        inside = [
            p for p in proxies
            if (bx0 - 2 <= (p.x0 + p.x1) / 2 <= bx1 + 2)
            and (by0 - 2 <= (p.y0 + p.y1) / 2 <= by1 + 2)
        ]

        if not inside:
            return None

        # Group into rows
        rows_grouped = self._group_rows(inside, row_tol=row_tol)
        if not rows_grouped:
            return None

        # Filter out title/footer rows before column detection
        rows_grouped = self._filter_title_footer_rows(rows_grouped)
        if not rows_grouped:
            return None

        # Text extent
        all_flat = [t for r in rows_grouped for t in r]
        text_x_min = min(t.x0 for t in all_flat)
        text_x_max = max(t.x1 for t in all_flat)
        text_y_min = min(t.y0 for t in all_flat)
        text_y_max = max(t.y1 for t in all_flat)

        # Columns
        if user_cols is not None:
            col_edges = [text_x_min] + user_cols + [text_x_max]
            cols = [(col_edges[i], col_edges[i + 1]) for i in range(len(col_edges) - 1)]
        else:
            cols_raw = self._detect_columns(rows_grouped, column_tol, row_tol)
            if not cols_raw:
                cols = [(text_x_min, text_x_max)]
            else:
                cols = self._join_columns(cols_raw, text_x_min, text_x_max)

        # Rows
        rows = self._make_row_boundaries(rows_grouped, text_y_min, text_y_max)

        if not cols or not rows:
            return None

        n_rows = len(rows)
        n_cols = len(cols)

        # Build 2D grid
        data: list[list[str]] = [["" for _ in range(n_cols)] for _ in range(n_rows)]
        cells: list[Cell] = []

        cell_last_x1: dict[tuple[int, int], float] = {}
        for p in all_flat:
            cx = (p.x0 + p.x1) / 2
            cy = (p.y0 + p.y1) / 2
            text = p.text.strip()
            if not text:
                continue

            # Find row
            r_idx = self._find_index(rows, cy, axis="row")
            # Find column
            c_idx = self._find_index(cols, cx, axis="col")

            if r_idx is not None and c_idx is not None:
                key = (r_idx, c_idx)
                if data[r_idx][c_idx]:
                    last_x1 = cell_last_x1.get(key, p.x0)
                    gap = p.x0 - last_x1
                    fs = p.font_size if p.font_size > 0 else 10.0
                    space_w = max(fs * 0.25, 2.0)
                    if gap < space_w * 0.3:
                        sep = ""
                    elif gap > space_w * 1.3:
                        sep = "  "
                    else:
                        sep = " "
                    data[r_idx][c_idx] += sep + text
                else:
                    data[r_idx][c_idx] = text
                cell_last_x1[key] = p.x1

        # Build Cell objects
        for ri, row_bounds in enumerate(rows):
            for ci, col_bounds in enumerate(cols):
                cells.append(Cell(
                    x0=col_bounds[0],
                    y0=row_bounds[0],
                    x1=col_bounds[1],
                    y1=row_bounds[1],
                    text=data[ri][ci],
                ))

        # Table bbox in top-left origin
        tbl_bbox = (text_x_min, text_y_min, text_x_max, text_y_max)

        table = Table(
            cells=cells,
            page_number=page_num + 1,
            page_index=page_num,
            bbox=tbl_bbox,
            strategy="stream",
            _data=data,
            _rows=n_rows,
            _cols=n_cols,
        )
        return table

    @staticmethod
    def _find_index(
        boundaries: list[tuple[float, float]], value: float, axis: str = "row"
    ) -> Optional[int]:
        """Find which boundary interval contains *value*."""
        for i, (lo, hi) in enumerate(boundaries):
            if lo - 1 <= value <= hi + 1:
                return i
        # Fallback: nearest
        best = None
        best_dist = float("inf")
        for i, (lo, hi) in enumerate(boundaries):
            mid = (lo + hi) / 2
            d = abs(value - mid)
            if d < best_dist:
                best_dist = d
                best = i
        return best
