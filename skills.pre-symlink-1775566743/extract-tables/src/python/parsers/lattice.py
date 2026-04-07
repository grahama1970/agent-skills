"""Lattice table parser: detects tables with visible borders/gridlines.

Pipeline: render_page -> adaptive_threshold -> find_lines -> find_contours
          -> find_joints -> build_cells -> assign_text

Multi-config probe architecture (skill contract):
- Deterministic code runs multiple parameter configs and gathers structured evidence
- /table-lab agent selects the best config based on evidence
- Heuristic fallback picks config with best grid structure when agent unavailable

All output bboxes use top-left origin: (x0, y0_top, x1, y1_bottom) where y=0 is top of page.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import numpy as np
from loguru import logger

from ..models import Cell, Table
from ..pdf_bridge import TextElement, extract_text_elements, get_page_dimensions, render_page_image
from .lattice_backend import (
    adaptive_threshold as _adaptive_threshold,
    find_lines as _find_lines,
    erode_dilate_open as _erode_dilate_open,
    find_contours as _find_contours,
    merge_close_lines as _merge_close_lines,
    pil_to_png_bytes as _pil_to_png_bytes,
    png_bytes_to_array as _png_bytes_to_array,
    array_to_png_bytes as _array_to_png_bytes,
    HAS_RUST as _HAS_RUST,
)


# ---------------------------------------------------------------------------
# Probe evidence: structured output for one parameter configuration
# ---------------------------------------------------------------------------

@dataclass
class LatticeProbeResult:
    """Evidence from running one lattice parameter configuration.

    All fields are deterministic sensor outputs. The agent decides which is best.
    """
    config_name: str
    line_scale: int
    threshold_blocksize: int
    threshold_constant: int
    resolution: int
    iterations: int
    # Evidence signals
    table_count: int = 0
    total_joints: int = 0
    total_cells: int = 0
    grid_dims: list[tuple[int, int]] = field(default_factory=list)
    table_bboxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    h_line_count: int = 0
    v_line_count: int = 0
    # Quality indicators
    has_spurious: bool = False
    max_grid_area: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Default probe configurations: covers the common parameter space
PROBE_CONFIGS = [
    {"name": "camelot_default", "line_scale": 15, "threshold_blocksize": 15, "threshold_constant": -2, "resolution": 300, "iterations": 0},
    {"name": "strong_lines",    "line_scale": 40, "threshold_blocksize": 15, "threshold_constant": -2, "resolution": 300, "iterations": 0},
    {"name": "sensitive",       "line_scale": 5,  "threshold_blocksize": 15, "threshold_constant": -2, "resolution": 300, "iterations": 0},
    {"name": "high_contrast",   "line_scale": 15, "threshold_blocksize": 21, "threshold_constant": -5, "resolution": 300, "iterations": 0},
    {"name": "low_res",         "line_scale": 15, "threshold_blocksize": 15, "threshold_constant": -2, "resolution": 150, "iterations": 0},
]


# ---------------------------------------------------------------------------
# Adaptive line tolerance for thick-line PDFs
# ---------------------------------------------------------------------------

def _adaptive_line_tol(sorted_vals: list[float], base_tol: float) -> float:
    """Compute adaptive merge tolerance from joint coordinate gaps."""
    if len(sorted_vals) < 4:
        return base_tol
    gaps = [sorted_vals[i+1] - sorted_vals[i] for i in range(len(sorted_vals)-1)]
    small_gaps = [g for g in gaps if base_tol < g <= base_tol * 5]
    if len(small_gaps) >= 2:
        return max(small_gaps) + 1.0
    return base_tol


# ---------------------------------------------------------------------------
# Scale helpers (image coords <-> PDF coords, all top-left origin)
# ---------------------------------------------------------------------------

def _scale_image_to_pdf(
    img_x: float, img_y: float, pdf_w: float, pdf_h: float, img_w: float, img_h: float
) -> tuple[float, float]:
    """Convert image pixel coords (top-left origin) to PDF points (top-left origin)."""
    return img_x * (pdf_w / img_w), img_y * (pdf_h / img_h)


# ---------------------------------------------------------------------------
# Core: build table grid from joints
# ---------------------------------------------------------------------------

def _joints_to_grid(
    joints: list[tuple[float, float]], line_tol: float = 2.0
) -> tuple[list[float], list[float]]:
    """Extract sorted, merged column (x) and row (y) coordinates from joints."""
    if not joints:
        return [], []
    xs = sorted(set(j[0] for j in joints))
    ys = sorted(set(j[1] for j in joints))
    cols = _merge_close_lines(xs, line_tol)
    rows = _merge_close_lines(ys, line_tol)
    return cols, rows


def _find_table_contours(
    h_mask_bytes: bytes,
    v_mask_bytes: bytes,
    min_joints: int = 4,
    min_dim_fraction: float = 0.02,
) -> dict[tuple[float, float, float, float], list[tuple[float, float]]]:
    """Find table regions via contour detection on combined H+V mask."""
    h_arr = _png_bytes_to_array(h_mask_bytes)
    v_arr = _png_bytes_to_array(v_mask_bytes)

    mask = np.clip(h_arr.astype(np.uint16) + v_arr.astype(np.uint16), 0, 255).astype(np.uint8)
    joints_mask = np.minimum(h_arr, v_arr)

    if _HAS_RUST:
        contour_bboxes = _find_contours(_array_to_png_bytes(mask))
    else:
        import cv2
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
        contour_bboxes = []
        for c in contours:
            c_poly = cv2.approxPolyDP(c, 3, True)
            x, y, w, h = cv2.boundingRect(c_poly)
            if w > 0 and h > 0:
                contour_bboxes.append((float(x), float(y), float(w), float(h)))

    img_h_px, img_w_px = h_arr.shape[:2]
    min_w = max(int(img_w_px * min_dim_fraction), 10)
    min_h = max(int(img_h_px * min_dim_fraction), 10)

    table_data: dict[tuple[float, float, float, float], list[tuple[float, float]]] = {}
    for cx, cy, cw, ch in contour_bboxes:
        x, y, w, h = int(cx), int(cy), int(cw), int(ch)
        if w < min_w or h < min_h:
            continue

        roi = joints_mask[y:y + h, x:x + w]

        if _HAS_RUST:
            roi_bytes = _array_to_png_bytes(roi)
            roi_contours = _find_contours(roi_bytes)
            joint_coords = []
            for jx, jy, jw, jh in roi_contours:
                gx = x + jx + jw / 2.0
                gy = y + jy + jh / 2.0
                joint_coords.append((gx, gy))
        else:
            import cv2
            jc, _ = cv2.findContours(roi.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
            joint_coords = []
            for j in jc:
                jx, jy, jw, jh = cv2.boundingRect(j)
                gx = x + (2 * jx + jw) / 2.0
                gy = y + (2 * jy + jh) / 2.0
                joint_coords.append((gx, gy))

        if len(joint_coords) < min_joints:
            continue

        xs = [j[0] for j in joint_coords]
        ys = [j[1] for j in joint_coords]
        unique_x = len(set(round(v, 1) for v in xs))
        unique_y = len(set(round(v, 1) for v in ys))
        if unique_x < 2 or unique_y < 2:
            continue

        contour_bbox = (float(x), float(y), float(x + w), float(y + h))
        table_data[contour_bbox] = joint_coords

    return table_data


def _build_cells_from_grid(cols: list[float], rows: list[float]) -> list[Cell]:
    """Build Cell objects from column and row boundaries."""
    cells = []
    for j in range(len(rows) - 1):
        for i in range(len(cols) - 1):
            cells.append(Cell(x0=cols[i], y0=rows[j], x1=cols[i + 1], y1=rows[j + 1]))
    return cells


def _assign_text_to_cells(
    cells: list[Cell],
    text_elements: list[TextElement],
    strip_text: str = "",
    col_boundaries: list[float] | None = None,
    row_boundaries: list[float] | None = None,
) -> None:
    """Assign text elements to cells. Delegates to text_assignment module."""
    from .text_assignment import assign_text_to_cells
    assign_text_to_cells(cells, text_elements, strip_text, col_boundaries, row_boundaries)


def _build_data_grid(cells: list[Cell], cols: list[float], rows: list[float]) -> list[list[str]]:
    """Build a 2D string grid from cells, matching row/col order."""
    n_rows = len(rows) - 1
    n_cols = len(cols) - 1
    grid = [[""] * n_cols for _ in range(n_rows)]
    for cell in cells:
        ci = None
        for i in range(n_cols):
            if abs(cell.x0 - cols[i]) < 2.0:
                ci = i
                break
        ri = None
        for j in range(n_rows):
            if abs(cell.y0 - rows[j]) < 2.0:
                ri = j
                break
        if ci is not None and ri is not None:
            grid[ri][ci] = cell.text.strip() if cell.text else ""
    return grid


# ---------------------------------------------------------------------------
# Edge detection + text shifting for spanning cells (Camelot parity)
# ---------------------------------------------------------------------------

def _set_edges_on_grid(
    cell_grid: list[list[Cell]],
    rows: list[float],
    cols: list[float],
    v_segments_pdf: list[tuple[float, float, float, float]],
    h_segments_pdf: list[tuple[float, float, float, float]],
    joint_tol: float = 2.0,
) -> None:
    """Mark cell edges based on detected line segments."""
    n_rows = len(rows) - 1
    n_cols = len(cols) - 1
    if n_rows < 1 or n_cols < 1:
        return

    for vx0, vy0, vx1, vy1 in v_segments_pdf:
        x = (vx0 + vx1) / 2.0
        y_top = min(vy0, vy1)
        y_bot = max(vy0, vy1)
        col_boundary_idx = None
        for ci in range(len(cols)):
            if abs(x - cols[ci]) <= joint_tol:
                col_boundary_idx = ci
                break
        if col_boundary_idx is None:
            continue
        start_row = None
        end_row = None
        for ri in range(n_rows):
            row_mid = (rows[ri] + rows[ri + 1]) / 2.0
            if y_top - joint_tol <= row_mid <= y_bot + joint_tol:
                if start_row is None:
                    start_row = ri
                end_row = ri
        if start_row is None:
            continue
        for ri in range(start_row, end_row + 1):
            if col_boundary_idx == 0:
                cell_grid[ri][0].left = True
            elif col_boundary_idx >= n_cols:
                cell_grid[ri][n_cols - 1].right = True
            else:
                cell_grid[ri][col_boundary_idx].left = True
                cell_grid[ri][col_boundary_idx - 1].right = True

    for hx0, hy0, hx1, hy1 in h_segments_pdf:
        y = (hy0 + hy1) / 2.0
        x_left = min(hx0, hx1)
        x_right = max(hx0, hx1)
        row_boundary_idx = None
        for ri in range(len(rows)):
            if abs(y - rows[ri]) <= joint_tol:
                row_boundary_idx = ri
                break
        if row_boundary_idx is None:
            continue
        start_col = None
        end_col = None
        for ci in range(n_cols):
            col_mid = (cols[ci] + cols[ci + 1]) / 2.0
            if x_left - joint_tol <= col_mid <= x_right + joint_tol:
                if start_col is None:
                    start_col = ci
                end_col = ci
        if start_col is None:
            continue
        for ci in range(start_col, end_col + 1):
            if row_boundary_idx == 0:
                cell_grid[0][ci].top = True
            elif row_boundary_idx >= n_rows:
                cell_grid[n_rows - 1][ci].bottom = True
            else:
                cell_grid[row_boundary_idx][ci].top = True
                cell_grid[row_boundary_idx - 1][ci].bottom = True

    for ri in range(n_rows):
        cell_grid[ri][0].left = True
        cell_grid[ri][n_cols - 1].right = True
    for ci in range(n_cols):
        cell_grid[0][ci].top = True
        cell_grid[n_rows - 1][ci].bottom = True


def _shift_text_in_spanning_cells(
    cell_grid: list[list[Cell]], n_rows: int, n_cols: int,
) -> None:
    """Move text from interior spanning cells to the anchor (top-left) cell.

    Sorts collected texts by (cell_y_center, cell_x_center) before joining,
    which matches Camelot's natural text ordering (pdfminer y-then-x order)
    rather than strict row-major grid iteration.
    """
    # Collect (text_y0, text_x0_proxy, text) tuples keyed by anchor cell.
    # Using _text_y0 (actual first text y-position) instead of cell center
    # ensures correct ordering when text y-positions don't align with grid rows.
    moved: dict[tuple[int, int], list[tuple[float, float, str]]] = {}
    for ri in range(n_rows):
        for ci in range(n_cols):
            cell = cell_grid[ri][ci]
            text = cell.text.strip() if cell.text else ""
            if not text:
                continue
            target_ci = ci
            while target_ci > 0 and not cell_grid[ri][target_ci].left:
                target_ci -= 1
            target_ri = ri
            while target_ri > 0 and not cell_grid[target_ri][target_ci].top:
                target_ri -= 1
            key = (target_ri, target_ci)
            if key not in moved:
                moved[key] = []
            # Use actual text y-position if available, fall back to cell center
            ty = cell._text_y0 if cell._text_y0 > 0 else (cell.y0 + cell.y1) / 2.0
            tx = cell.x0
            moved[key].append((ty, tx, text))
            if (target_ri, target_ci) != (ri, ci):
                cell.text = ""
    for (ri, ci), entries in moved.items():
        entries.sort()  # sort by (text_y0, cell_x0) — matches pdfminer order
        cell_grid[ri][ci].text = " \n".join(t for _, _, t in entries)


# ---------------------------------------------------------------------------
# Core pipeline: threshold + line detection + table finding for given params
# ---------------------------------------------------------------------------

def _run_pipeline(
    gray_arr: np.ndarray,
    line_scale: int,
    blocksize: int,
    constant: int,
    iterations: int,
    min_joints: int,
) -> tuple[
    dict[tuple[float, float, float, float], list[tuple[float, float]]],
    bytes, bytes, int, int,
    list[tuple[float, float, float, float]],
    list[tuple[float, float, float, float]],
]:
    """Run the threshold -> line detection -> contour pipeline with specific params."""
    thresh_bytes = _adaptive_threshold(
        _array_to_png_bytes(gray_arr), blocksize // 2, constant
    )
    thresh_png = _array_to_png_bytes(_png_bytes_to_array(thresh_bytes))

    iters = max(iterations, 1)
    h_mask_bytes = _erode_dilate_open(thresh_png, "horizontal", line_scale, iters)
    v_mask_bytes = _erode_dilate_open(thresh_png, "vertical", line_scale, iters)

    h_segments = _find_lines(thresh_png, "horizontal", line_scale, iters)
    v_segments = _find_lines(thresh_png, "vertical", line_scale, iters)

    table_data = _find_table_contours(h_mask_bytes, v_mask_bytes, min_joints=min_joints)

    return table_data, h_mask_bytes, v_mask_bytes, len(h_segments), len(v_segments), h_segments, v_segments


def _probe_single_config(
    gray_arr: np.ndarray, config: dict, min_joints: int, line_tol: float,
) -> LatticeProbeResult:
    """Run one parameter config and produce structured evidence."""
    name = config["name"]
    line_scale = config["line_scale"]
    blocksize = config["threshold_blocksize"]
    constant = config["threshold_constant"]
    iterations = config.get("iterations", 0)

    result = LatticeProbeResult(
        config_name=name, line_scale=line_scale,
        threshold_blocksize=blocksize, threshold_constant=constant,
        resolution=config.get("resolution", 300), iterations=iterations,
    )

    table_data, _, _, h_count, v_count, _, _ = _run_pipeline(
        gray_arr, line_scale, blocksize, constant, iterations, min_joints,
    )

    result.h_line_count = h_count
    result.v_line_count = v_count
    result.table_count = len(table_data)

    for bbox, joints in table_data.items():
        result.total_joints += len(joints)
        bx0, by0, bx1, by1 = bbox
        all_xs = sorted([j[0] for j in joints] + [bx0, bx1])
        all_ys = sorted([j[1] for j in joints] + [by0, by1])
        eff_tol_x = _adaptive_line_tol(all_xs, line_tol)
        eff_tol_y = _adaptive_line_tol(all_ys, line_tol)
        cols = _merge_close_lines(all_xs, eff_tol_x)
        rows = _merge_close_lines(all_ys, eff_tol_y)
        n_rows = max(len(rows) - 1, 0)
        n_cols = max(len(cols) - 1, 0)
        result.grid_dims.append((n_rows, n_cols))
        result.table_bboxes.append(bbox)
        area = n_rows * n_cols
        result.total_cells += area
        result.max_grid_area = max(result.max_grid_area, area)
        if n_rows < 2 or n_cols < 2:
            result.has_spurious = True

    return result


def _select_best_config(
    probes: list[LatticeProbeResult], pdf_path: str | None = None,
) -> LatticeProbeResult:
    """Select best config from probe results."""
    if not probes:
        raise ValueError("No probe results to select from")
    if len(probes) == 1:
        return probes[0]

    if pdf_path:
        try:
            from table_lab.config_selector import select_lattice_config
            evidence = [p.to_dict() for p in probes]
            best_name = select_lattice_config(evidence, pdf_path)
            if best_name:
                for p in probes:
                    if p.config_name == best_name:
                        logger.debug(f"table-lab selected config: {best_name}")
                        return p
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"table-lab config selection error: {e}")

    def score(p: LatticeProbeResult) -> tuple:
        # Prefer camelot_default when it finds valid tables —
        # ensures parity with Camelot's exact parameters.
        is_camelot = p.config_name == "camelot_default"
        return (
            not p.has_spurious,
            is_camelot,
            p.max_grid_area,
            -p.table_count,
            p.total_joints,
        )

    best = max(probes, key=score)
    logger.debug(
        f"Heuristic selected config: {best.config_name} "
        f"(joints={best.total_joints}, cells={best.total_cells}, "
        f"tables={best.table_count}, spurious={best.has_spurious})"
    )
    return best


def _dedup_overlapping_tables(tables: list) -> list:
    """Remove duplicate tables with heavily overlapping bounding boxes.

    When two tables share > 50% bbox overlap (IoU), keep the one with more
    cells. This handles cases where different line detection parameters
    find the same table region as separate contours.
    """
    if len(tables) <= 1:
        return tables

    keep = [True] * len(tables)
    for i in range(len(tables)):
        if not keep[i]:
            continue
        bx0_i, by0_i, bx1_i, by1_i = tables[i].bbox
        area_i = max((bx1_i - bx0_i) * (by1_i - by0_i), 1e-6)
        for j in range(i + 1, len(tables)):
            if not keep[j]:
                continue
            bx0_j, by0_j, bx1_j, by1_j = tables[j].bbox
            area_j = max((bx1_j - bx0_j) * (by1_j - by0_j), 1e-6)

            # Compute intersection
            ix0 = max(bx0_i, bx0_j)
            iy0 = max(by0_i, by0_j)
            ix1 = min(bx1_i, bx1_j)
            iy1 = min(by1_i, by1_j)
            inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)

            # IoU
            union = area_i + area_j - inter
            iou = inter / union if union > 0 else 0.0

            if iou > 0.5:
                cells_i = tables[i].rows * tables[i].cols
                cells_j = tables[j].rows * tables[j].cols
                if cells_j >= cells_i:
                    keep[i] = False
                else:
                    keep[j] = False

    return [t for t, k in zip(tables, keep) if k]


def _tables_from_pipeline(
    table_data: dict[tuple[float, float, float, float], list[tuple[float, float]]],
    text_elements: list[TextElement],
    pdf_w: float, pdf_h: float,
    img_w: int, img_h: int,
    page_num: int,
    line_tol: float,
    strip_text: str,
    h_segments_img: list[tuple[float, float, float, float]] | None = None,
    v_segments_img: list[tuple[float, float, float, float]] | None = None,
) -> list[Table]:
    """Build Table objects from pipeline output (table_data + text)."""
    h_segs_pdf: list[tuple[float, float, float, float]] = []
    v_segs_pdf: list[tuple[float, float, float, float]] = []
    if h_segments_img:
        for hx0, hy0, hx1, hy1 in h_segments_img:
            px0, py0 = _scale_image_to_pdf(hx0, hy0, pdf_w, pdf_h, img_w, img_h)
            px1, py1 = _scale_image_to_pdf(hx1, hy1, pdf_w, pdf_h, img_w, img_h)
            h_segs_pdf.append((px0, py0, px1, py1))
    if v_segments_img:
        for vx0, vy0, vx1, vy1 in v_segments_img:
            px0, py0 = _scale_image_to_pdf(vx0, vy0, pdf_w, pdf_h, img_w, img_h)
            px1, py1 = _scale_image_to_pdf(vx1, vy1, pdf_w, pdf_h, img_w, img_h)
            v_segs_pdf.append((px0, py0, px1, py1))

    tables = []
    for bbox_img, joints_img in table_data.items():
        joints_pdf = [
            _scale_image_to_pdf(jx, jy, pdf_w, pdf_h, img_w, img_h)
            for jx, jy in joints_img
        ]

        bx0, by0, bx1, by1 = bbox_img
        pdf_bx0, pdf_by0 = _scale_image_to_pdf(bx0, by0, pdf_w, pdf_h, img_w, img_h)
        pdf_bx1, pdf_by1 = _scale_image_to_pdf(bx1, by1, pdf_w, pdf_h, img_w, img_h)

        all_xs = sorted([j[0] for j in joints_pdf] + [pdf_bx0, pdf_bx1])
        all_ys = sorted([j[1] for j in joints_pdf] + [pdf_by0, pdf_by1])
        eff_tol_x = _adaptive_line_tol(all_xs, line_tol)
        eff_tol_y = _adaptive_line_tol(all_ys, line_tol)
        cols = _merge_close_lines(all_xs, eff_tol_x)
        rows = _merge_close_lines(all_ys, eff_tol_y)

        if len(cols) < 2 or len(rows) < 2:
            continue

        n_rows = len(rows) - 1
        n_cols = len(cols) - 1
        cells = _build_cells_from_grid(cols, rows)

        bbox_pdf = (pdf_bx0, pdf_by0, pdf_bx1, pdf_by1)
        table_text = [
            e for e in text_elements
            if (pdf_bx0 - 2 <= (e.x0 + e.x1) / 2 <= pdf_bx1 + 2
                and pdf_by0 - 2 <= (e.y0 + e.y1) / 2 <= pdf_by1 + 2)
        ]

        _assign_text_to_cells(cells, table_text, strip_text, col_boundaries=cols, row_boundaries=rows)

        if h_segs_pdf or v_segs_pdf:
            margin = max(eff_tol_x, eff_tol_y, 5.0)
            local_h = [
                s for s in h_segs_pdf
                if (s[1] >= pdf_by0 - margin and s[1] <= pdf_by1 + margin
                    and s[0] <= pdf_bx1 + margin and s[2] >= pdf_bx0 - margin)
            ]
            local_v = [
                s for s in v_segs_pdf
                if (s[0] >= pdf_bx0 - margin and s[0] <= pdf_bx1 + margin
                    and s[1] <= pdf_by1 + margin and s[3] >= pdf_by0 - margin)
            ]

            cell_grid = []
            for ri in range(n_rows):
                row = []
                for ci in range(n_cols):
                    row.append(cells[ri * n_cols + ci])
                cell_grid.append(row)

            edge_tol = max(eff_tol_x, eff_tol_y, 3.0)
            _set_edges_on_grid(cell_grid, rows, cols, local_v, local_h, joint_tol=edge_tol)
            _shift_text_in_spanning_cells(cell_grid, n_rows, n_cols)

        data = _build_data_grid(cells, cols, rows)

        table = Table(
            cells=cells,
            page_number=page_num + 1,
            page_index=page_num,
            bbox=bbox_pdf,
            strategy="lattice",
            _data=data,
            _rows=n_rows,
            _cols=n_cols,
        )

        try:
            from metrics import compute_accuracy, compute_whitespace
            table.accuracy = compute_accuracy(table)
            table.whitespace = compute_whitespace(table)
        except ImportError:
            pass

        tables.append(table)

    tables.sort(key=lambda t: (t.bbox[1], t.bbox[0]))

    # Dedup tables with heavily overlapping bounding boxes.
    # This handles cases where aggressive line detection finds the same
    # table region twice (e.g., sensitive config on column_span_1.pdf).
    if len(tables) > 1:
        tables = _dedup_overlapping_tables(tables)

    return tables


# ---------------------------------------------------------------------------
# LatticeParser
# ---------------------------------------------------------------------------

class LatticeParser:
    """Extract tables using line detection (lattice/bordered tables)."""

    def __init__(
        self,
        line_scale: int = 15,
        line_tol: float = 2.0,
        joint_tol: float = 2.0,
        threshold_blocksize: int = 15,
        threshold_constant: int = -2,
        iterations: int = 0,
        resolution: int = 300,
        process_background: bool = False,
        strip_text: str = "",
        min_table_joints: int = 4,
        probe: bool = True,
    ):
        self.line_scale = line_scale
        self.line_tol = line_tol
        self.joint_tol = joint_tol
        self.threshold_blocksize = threshold_blocksize
        self.threshold_constant = threshold_constant
        self.iterations = max(iterations, 0)
        self.resolution = resolution
        self.process_background = process_background
        self.strip_text = strip_text
        self.min_table_joints = min_table_joints
        self.probe = probe
        self._last_probe_results: list[LatticeProbeResult] = []

    def extract_tables(
        self, pdf_path: str, page_num: int, password: Optional[str] = None, **params,
    ) -> list[Table]:
        """Extract tables from a single PDF page using line detection."""
        line_tol = params.get("line_tol", self.line_tol)
        strip_text = params.get("strip_text", self.strip_text)
        min_joints = params.get("min_table_joints", self.min_table_joints)
        resolution = params.get("resolution", self.resolution)

        pdf_w, pdf_h = get_page_dimensions(pdf_path, page_num)
        text_elements = extract_text_elements(pdf_path, page_num, password, backend="pdfminer")

        pil_img = render_page_image(pdf_path, page_num, dpi=resolution, password=password)
        img_w, img_h = pil_img.size

        gray_arr = np.array(pil_img.convert("L"))
        if not self.process_background:
            gray_arr = 255 - gray_arr

        has_explicit_params = any(
            k in params for k in ("line_scale", "threshold_blocksize", "threshold_constant")
        )

        if self.probe and not has_explicit_params:
            return self._extract_with_probe(
                gray_arr, text_elements, pdf_path, page_num,
                pdf_w, pdf_h, img_w, img_h, line_tol, strip_text, min_joints,
            )

        line_scale = params.get("line_scale", self.line_scale)
        blocksize = params.get("threshold_blocksize", self.threshold_blocksize)
        constant = params.get("threshold_constant", self.threshold_constant)
        iterations = max(params.get("iterations", self.iterations), 0)

        table_data, _, _, _, _, h_segs, v_segs = _run_pipeline(
            gray_arr, line_scale, blocksize, constant, iterations, min_joints,
        )
        if not table_data:
            return []

        return _tables_from_pipeline(
            table_data, text_elements, pdf_w, pdf_h, img_w, img_h,
            page_num, line_tol, strip_text, h_segs, v_segs,
        )

    def _extract_with_probe(
        self, gray_arr: np.ndarray, text_elements: list[TextElement],
        pdf_path: str, page_num: int,
        pdf_w: float, pdf_h: float, img_w: int, img_h: int,
        line_tol: float, strip_text: str, min_joints: int,
    ) -> list[Table]:
        """Multi-config probe: try multiple configs, select best via agent."""
        probes = []
        for config in PROBE_CONFIGS:
            probe = _probe_single_config(gray_arr, config, min_joints, line_tol)
            probes.append(probe)

        self._last_probe_results = probes

        viable = [p for p in probes if p.table_count > 0]
        if not viable:
            logger.debug("No config found tables in probe")
            return []

        best = _select_best_config(viable, pdf_path)
        logger.debug(
            f"Selected config '{best.config_name}' for page {page_num}: "
            f"{best.table_count} tables, {best.total_joints} joints, "
            f"grids={best.grid_dims}"
        )

        table_data, _, _, _, _, h_segs, v_segs = _run_pipeline(
            gray_arr, best.line_scale, best.threshold_blocksize,
            best.threshold_constant, best.iterations, min_joints,
        )
        if not table_data:
            return []

        return _tables_from_pipeline(
            table_data, text_elements, pdf_w, pdf_h, img_w, img_h,
            page_num, line_tol, strip_text, h_segs, v_segs,
        )
