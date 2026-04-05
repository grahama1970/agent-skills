"""Network table parser -- uses text alignment network analysis.

Handles complex merged cells, irregular table structures, and mixed
alignment patterns. Core alignment logic lives in network_core.py.

All coordinates use top-left origin: (x0, y0_top, x1, y1_bottom) where y=0
is the top of the page.
"""
from __future__ import annotations

import math
from typing import Optional

from ..models import Table, Cell
from ..pdf_bridge import TextElement, extract_text_elements, get_page_dimensions
from .network_core import (
    MINIMUM_TEXTLINES_IN_TABLE,
    TextNetworks,
    _bbox_from_textlines,
    _boundaries_to_split_lines,
    _find_columns_boundaries,
    _search_header_from_body_bbox,
    _text_in_bbox,
    _textlines_overlapping_bbox,
)


# ---------------------------------------------------------------------------
# Row grouping helpers
# ---------------------------------------------------------------------------

def _group_rows(text: list[TextElement], row_tol: float = 2.0) -> list[list[TextElement]]:
    """Group text elements into rows by y-position (top-left origin).

    Sorted top to bottom (ascending y0), then left to right.
    """
    sorted_text = sorted(
        [t for t in text if t.text.strip()],
        key=lambda t: (t.y0, t.x0),
    )
    rows: list[list[TextElement]] = []
    temp: list[TextElement] = []
    row_y: Optional[float] = None

    for t in sorted_text:
        if row_y is None:
            row_y = t.y0
        elif not math.isclose(row_y, t.y0, abs_tol=row_tol):
            rows.append(sorted(temp, key=lambda x: x.x0))
            temp = []
            row_y = t.y0
        temp.append(t)
        # Be forgiving: update row_y as we go
        if t.y0 < row_y + row_tol:
            row_y = min(row_y, t.y0)

    if temp:
        rows.append(sorted(temp, key=lambda x: x.x0))

    return rows


def _join_rows(
    rows_grouped: list[list[TextElement]], text_y_min: float, text_y_max: float
) -> list[list[float]]:
    """Make row coordinates continuous.

    Returns list of [y_top, y_bottom] for each row (top-left origin).
    """
    if not rows_grouped:
        return []

    row_boundaries = [
        [min(t.y0 for t in r), max(t.y1 for t in r)] for r in rows_grouped
    ]

    for i in range(len(row_boundaries) - 1):
        top_row = row_boundaries[i]
        next_row = row_boundaries[i + 1]
        midpoint = (top_row[1] + next_row[0]) / 2.0
        top_row[1] = midpoint
        next_row[0] = midpoint

    row_boundaries[0][0] = text_y_min
    row_boundaries[-1][1] = text_y_max

    return row_boundaries


# ---------------------------------------------------------------------------
# NetworkParser
# ---------------------------------------------------------------------------

class NetworkParser:
    """Extract tables using text alignment network analysis.

    Most sophisticated parser. Handles:
    - Complex merged cells
    - Irregular table structures
    - Tables with mixed alignment patterns

    All output bboxes use top-left origin: (x0, y0_top, x1, y1_bottom).
    """

    def __init__(
        self,
        row_tol: float = 2.0,
        edge_tol: Optional[float] = None,
        column_tol: float = 0.0,
        min_textlines: int = MINIMUM_TEXTLINES_IN_TABLE,
    ):
        self.row_tol = row_tol
        self.edge_tol = edge_tol
        self.column_tol = column_tol
        self.min_textlines = min_textlines

    def extract_tables(
        self,
        pdf_path: str,
        page_num: int,
        password: Optional[str] = None,
        **params,
    ) -> list[Table]:
        """Extract tables from a PDF page using network analysis.

        Parameters
        ----------
        pdf_path : str
            Path to the PDF file.
        page_num : int
            0-indexed page number.
        password : str, optional
            PDF password.

        Returns
        -------
        list[Table]
            Extracted tables with top-left origin coordinates.
        """
        textlines = extract_text_elements(pdf_path, page_num, password)
        page_width, page_height = get_page_dimensions(pdf_path, page_num)

        # Filter empty textlines
        textlines = [t for t in textlines if t.text.strip()]
        if not textlines:
            return []

        tables: list[Table] = []
        processed: set[int] = set()  # track by id
        remaining = list(textlines)

        while remaining:
            # Build network from remaining textlines
            text_network = TextNetworks()
            text_network.generate(remaining)
            text_network.remove_unconnected_edges()

            gaps_hv = text_network.compute_plausible_gaps()
            if gaps_hv is None:
                break

            edge_tol_hv = (
                gaps_hv[0],
                gaps_hv[1] if self.edge_tol is None else self.edge_tol,
            )

            bbox_body = text_network.search_table_body(edge_tol_hv)
            if bbox_body is None:
                break

            # Get textlines in the body bbox
            tls_in_bbox = _textlines_overlapping_bbox(bbox_body, remaining)
            if not tls_in_bbox:
                break

            # Find column structure
            cols_boundaries = _find_columns_boundaries(tls_in_bbox)
            cols_anchors = _boundaries_to_split_lines(cols_boundaries)

            # Try to expand bbox upward for headers
            bbox_from_tls = _bbox_from_textlines(tls_in_bbox)
            if bbox_from_tls is not None:
                bbox_full = _search_header_from_body_bbox(
                    bbox_from_tls, remaining, cols_anchors, gaps_hv[1]
                )
            else:
                bbox_full = tuple(bbox_body)

            # Build the table from the full bbox
            table = self._build_table(
                bbox_full,
                textlines,
                cols_anchors,
                page_num,
            )
            if table is not None:
                tables.append(table)

            # Mark processed
            processed_ids = {id(t) for t in tls_in_bbox}
            # Also include textlines in the full bbox
            full_tls = _textlines_overlapping_bbox(bbox_full, remaining)
            processed_ids.update(id(t) for t in full_tls)
            processed.update(processed_ids)

            remaining = [t for t in remaining if id(t) not in processed]

            if not remaining:
                break

        return tables

    def _build_table(
        self,
        bbox: tuple[float, float, float, float],
        all_textlines: list[TextElement],
        cols_anchors: list[float],
        page_num: int,
    ) -> Optional[Table]:
        """Build a Table object from a detected table bbox.

        bbox: (x0, y0_top, x1, y1_bottom) in top-left origin
        """
        # Get textlines in the full bbox
        tls_in_table = _text_in_bbox(bbox, all_textlines)
        tls_in_table = [t for t in tls_in_table if t.text.strip()]

        if not tls_in_table:
            return None

        # Build rows
        rows_grouped = _group_rows(tls_in_table, row_tol=self.row_tol)
        if not rows_grouped:
            return None

        tl_bounds = _bbox_from_textlines(tls_in_table)
        if tl_bounds is None:
            return None

        text_y_min, text_y_max = tl_bounds[1], tl_bounds[3]
        rows = _join_rows(rows_grouped, text_y_min, text_y_max)

        if not rows:
            return None

        # Build columns from anchors
        if len(cols_anchors) < 2:
            return None

        cols = [
            [cols_anchors[i], cols_anchors[i + 1]]
            for i in range(len(cols_anchors) - 1)
        ]

        # Build grid and assign text to cells
        n_rows = len(rows)
        n_cols = len(cols)
        grid: list[list[str]] = [[""] * n_cols for _ in range(n_rows)]
        cells: list[Cell] = []

        for tl in tls_in_table:
            tl_cy = (tl.y0 + tl.y1) / 2.0
            tl_cx = (tl.x0 + tl.x1) / 2.0

            # Find row
            r_idx = -1
            for ri, (rtop, rbot) in enumerate(rows):
                if rtop - 1 <= tl_cy <= rbot + 1:
                    r_idx = ri
                    break
            if r_idx == -1:
                # Try closest row
                dists = [abs((rtop + rbot) / 2 - tl_cy) for rtop, rbot in rows]
                r_idx = dists.index(min(dists))

            # Find column
            c_idx = -1
            for ci, (cleft, cright) in enumerate(cols):
                if cleft - 1 <= tl_cx <= cright + 1:
                    c_idx = ci
                    break
            if c_idx == -1:
                dists = [abs((cleft + cright) / 2 - tl_cx) for cleft, cright in cols]
                c_idx = dists.index(min(dists))

            r_idx = max(0, min(r_idx, n_rows - 1))
            c_idx = max(0, min(c_idx, n_cols - 1))

            existing = grid[r_idx][c_idx]
            if existing:
                grid[r_idx][c_idx] = existing + " " + tl.text.strip()
            else:
                grid[r_idx][c_idx] = tl.text.strip()

        # Build Cell objects
        for ri in range(n_rows):
            for ci in range(n_cols):
                cell = Cell(
                    x0=cols[ci][0],
                    y0=rows[ri][0],
                    x1=cols[ci][1],
                    y1=rows[ri][1],
                    text=grid[ri][ci],
                )
                cells.append(cell)

        # Detect spanning cells (cells with same text spanning multiple cols/rows)
        self._detect_spanning(cells, grid, rows, cols, n_rows, n_cols)

        table = Table(
            cells=cells,
            page_number=page_num + 1,
            page_index=page_num,
            bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
            strategy="network",
            _data=grid,
            _rows=n_rows,
            _cols=n_cols,
        )

        return table

    def _detect_spanning(
        self,
        cells: list[Cell],
        grid: list[list[str]],
        rows: list[list[float]],
        cols: list[list[float]],
        n_rows: int,
        n_cols: int,
    ):
        """Detect and mark spanning cells in the grid.

        Look for empty cells next to non-empty cells that might indicate
        a merged/spanning cell.
        """
        # Simple spanning detection: if a cell is non-empty and adjacent cells
        # in the same row are empty, it might span those columns.
        for ri in range(n_rows):
            for ci in range(n_cols):
                if not grid[ri][ci]:
                    continue
                # Check column spanning (right)
                col_span = 1
                while ci + col_span < n_cols and not grid[ri][ci + col_span]:
                    col_span += 1
                # Check row spanning (down)
                row_span = 1
                while ri + row_span < n_rows and not grid[ri + row_span][ci]:
                    row_span += 1

                if col_span > 1 or row_span > 1:
                    cell_idx = ri * n_cols + ci
                    if cell_idx < len(cells):
                        cells[cell_idx].col_span = col_span
                        cells[cell_idx].row_span = row_span
