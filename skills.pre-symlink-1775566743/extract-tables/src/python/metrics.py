"""Accuracy and whitespace metrics for extracted tables."""
from __future__ import annotations

try:
    from .models import Table
except ImportError:
    from models import Table

try:
    from extract_tables_rs import extract_tables_rs as _rs
except ImportError:
    _rs = None


def _try_rust_accuracy(table: Table) -> float | None:
    """Try computing accuracy via Rust. Returns None if unavailable."""
    if _rs is None or not table.cells:
        return None
    try:
        cells_tuples = [
            (c.x0, c.y0, c.x1, c.y1, c.text or "",
             getattr(c, 'left', False), getattr(c, 'right', False),
             getattr(c, 'top', False), getattr(c, 'bottom', False))
            for c in table.cells
        ]
        n_rows = getattr(table, '_rows', 0) or table.rows
        n_cols = getattr(table, '_cols', 0) or table.cols
        data_grid = table._data if table._data else None
        return _rs.compute_accuracy_rs(cells_tuples, n_rows, n_cols, data_grid)
    except Exception:
        return None


def compute_accuracy(table: Table) -> float:
    """Compute extraction accuracy based on cell alignment and structure.

    Returns a score 0-100. Uses cell fill ratio but excludes cells that are
    part of a span (interior cells lacking left/top edges) from the penalty,
    since they are expected to be empty.

    Also applies a structural penalty for degenerate tables (e.g. single-column
    or single-row), which often indicate the parser collapsed the grid.
    """
    # Try Rust path first (but skip for lattice mode with edge flags,
    # since the Rust path doesn't handle span-start exclusion yet)
    has_edge_flags = table.cells and any(
        getattr(c, 'left', False) or getattr(c, 'top', False)
        for c in table.cells[:min(10, len(table.cells))]
    )
    if not has_edge_flags:
        rust_result = _try_rust_accuracy(table)
        if rust_result is not None:
            return rust_result

    if not table.cells:
        return 0.0

    total = len(table.cells)
    if total == 0:
        return 0.0

    # Check if edge flags are available (lattice mode sets them)
    has_edges = any(
        getattr(cc, 'left', False) or getattr(cc, 'top', False)
        for cc in table.cells[:min(10, total)]
    )

    # Count cells, excluding interior spanning cells from the denominator
    effective_total = 0
    filled = 0

    if has_edges:
        # Lattice mode: use edge flags to detect spanning cells.
        # Exclude empty cells that are part of a span:
        # 1. Interior cells (missing left or top edge)
        # 2. Span-start cells (has top+left but missing bottom) that are empty
        #    — these are the top of a row span where content may be absent
        for c in table.cells:
            has_text = bool(c.text and c.text.strip())

            is_spanning_interior = (
                hasattr(c, 'left') and hasattr(c, 'top')
                and (not c.left or not c.top)
            )
            is_span_start = (
                hasattr(c, 'bottom') and not c.bottom
                and getattr(c, 'left', True) and getattr(c, 'top', True)
            )

            if not has_text and (is_spanning_interior or is_span_start):
                continue

            effective_total += 1
            if has_text:
                filled += 1
    elif table._data:
        # Stream mode: use _data grid to detect header spanning rows.
        # Header region = all rows before the first fully-filled row.
        # Empty cells in the header region are structural (spanning) and
        # shouldn't penalize accuracy.
        n_cols = len(table._data[0]) if table._data else 0
        header_end = 0  # index of first fully-filled row
        for ri, row in enumerate(table._data):
            if not isinstance(row, list):
                continue
            row_filled = sum(1 for cell in row if isinstance(cell, str) and cell.strip())
            if row_filled == len(row):
                header_end = ri
                break
        for ri, row in enumerate(table._data):
            if not isinstance(row, list):
                continue
            in_header = ri < header_end
            for cell in row:
                has_text = isinstance(cell, str) and bool(cell.strip())
                if in_header and not has_text:
                    # Structural empty cell in header — skip
                    continue
                effective_total += 1
                if has_text:
                    filled += 1
    else:
        for c in table.cells:
            effective_total += 1
            if c.text and c.text.strip():
                filled += 1

    if effective_total == 0:
        effective_total = total
        filled = sum(1 for c in table.cells if c.text and c.text.strip())

    fill_score = 100.0 * filled / effective_total

    # Structural penalty: single-column or single-row tables are
    # likely degenerate (parser collapsed the grid). Penalize unless
    # the table genuinely has very few cells.
    n_rows = getattr(table, '_rows', 0) or 0
    n_cols = getattr(table, '_cols', 0) or 0
    if n_rows == 0 and n_cols == 0:
        n_rows = table.rows
        n_cols = table.cols

    structural_factor = 1.0
    if n_cols == 1 and n_rows > 3:
        structural_factor = 0.5
    elif n_rows == 1 and n_cols > 3:
        structural_factor = 0.5

    return round(fill_score * structural_factor, 2)


def compute_whitespace(table: Table) -> float:
    """Compute whitespace ratio in table cells.

    Returns the percentage (0-100) of cells that are empty or whitespace-only.
    """
    if not table._data:
        if not table.cells:
            return 0.0
        total = len(table.cells)
        empty = sum(1 for c in table.cells if not c.text or not c.text.strip())
        if total == 0:
            return 0.0
        return round(100.0 * empty / total, 2)

    # Use _data (2D grid) if available
    total = 0
    empty = 0
    for row in table._data:
        if isinstance(row, list):
            total += len(row)
            for cell in row:
                if isinstance(cell, str) and cell.strip() == "":
                    empty += 1
    if total == 0:
        return 0.0
    return round(100.0 * empty / total, 2)
