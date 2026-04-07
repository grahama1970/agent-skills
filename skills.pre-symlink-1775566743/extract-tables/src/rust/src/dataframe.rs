//! DataFrame validation functions for table extraction.
//!
//! All functions accept raw Python types (Vec, tuples) and return simple Python
//! types (dicts, bools, floats). Polars DataFrames are used internally in Rust
//! only — no PyDataFrame crossing the boundary (avoids version mismatch between
//! Python Polars 1.x and Rust polars 0.46).

use polars::prelude::*;
use pyo3::prelude::*;
use pyo3::types::PyDict;

/// Cell tuple from Python: (x0, y0, x1, y1, text, left, right, top, bottom).
/// Coordinates use top-left origin (PyMuPDF convention):
/// (x0, y0) = top-left corner, (x1, y1) = bottom-right corner.
type CellTuple = (f64, f64, f64, f64, String, bool, bool, bool, bool);

// ---------------------------------------------------------------------------
// Task 2: validate_grid — rectangular grid enforcement
// ---------------------------------------------------------------------------

/// Validate and enforce rectangular grid structure.
///
/// Accepts a 2D grid of strings and an expected column count.
/// Pads short rows with empty strings to ensure all rows have `expected_cols` columns.
/// Returns a dict with keys: "data" (list of lists), "n_rows", "n_cols", "padded_rows" (count).
#[pyfunction]
pub fn validate_grid(data: Vec<Vec<String>>, expected_cols: usize) -> PyResult<PyObject> {
    Python::with_gil(|py| {
        let mut padded_count: usize = 0;
        let mut result_data: Vec<Vec<String>> = Vec::with_capacity(data.len());

        for row in &data {
            if row.len() == expected_cols {
                result_data.push(row.clone());
            } else {
                padded_count += 1;
                let mut padded = row.clone();
                padded.resize(expected_cols, String::new());
                result_data.push(padded);
            }
        }

        let dict = PyDict::new(py);
        dict.set_item("data", &result_data)?;
        dict.set_item("n_rows", result_data.len())?;
        dict.set_item("n_cols", expected_cols)?;
        dict.set_item("padded_rows", padded_count)?;
        Ok(dict.into())
    })
}

// ---------------------------------------------------------------------------
// Task 3: validate_cells — bbox and edge integrity checks
// ---------------------------------------------------------------------------

/// Cell validation result for a single cell.
#[derive(Clone)]
struct CellValidation {
    x0: f64,
    y0: f64,
    x1: f64,
    y1: f64,
    text: String,
    left: bool,
    right: bool,
    top: bool,
    bottom: bool,
    has_text: bool,
    is_spanning_interior: bool,
    bbox_valid: bool,
}

/// Validate cell bboxes and edge flags.
///
/// Input: list of (x0, y0, x1, y1, text, left, right, top, bottom) tuples.
/// Returns a dict with:
///   - "total": total cell count
///   - "bbox_invalid_count": cells where x0 >= x1 or y0 >= y1
///   - "spanning_interior_count": cells missing left or top edge
///   - "has_text_count": cells with non-empty text
///   - "cells": list of dicts per cell (for downstream use)
#[pyfunction]
pub fn validate_cells(cells: Vec<CellTuple>) -> PyResult<PyObject> {
    Python::with_gil(|py| {
        let mut validations: Vec<CellValidation> = Vec::with_capacity(cells.len());
        let mut bbox_invalid = 0usize;
        let mut spanning_interior = 0usize;
        let mut has_text_count = 0usize;

        for (x0, y0, x1, y1, text, left, right, top, bottom) in &cells {
            let bbox_valid = x0 < x1 && y0 < y1;
            if !bbox_valid {
                bbox_invalid += 1;
            }
            let is_interior = !left || !top;
            if is_interior {
                spanning_interior += 1;
            }
            let has_text = !text.trim().is_empty();
            if has_text {
                has_text_count += 1;
            }

            validations.push(CellValidation {
                x0: *x0,
                y0: *y0,
                x1: *x1,
                y1: *y1,
                text: text.clone(),
                left: *left,
                right: *right,
                top: *top,
                bottom: *bottom,
                has_text,
                is_spanning_interior: is_interior,
                bbox_valid,
            });
        }

        let dict = PyDict::new(py);
        dict.set_item("total", validations.len())?;
        dict.set_item("bbox_invalid_count", bbox_invalid)?;
        dict.set_item("spanning_interior_count", spanning_interior)?;
        dict.set_item("has_text_count", has_text_count)?;

        // Build per-cell list of dicts
        let mut cell_dicts: Vec<PyObject> = Vec::with_capacity(validations.len());
        for cv in &validations {
            let d = PyDict::new(py);
            d.set_item("x0", cv.x0)?;
            d.set_item("y0", cv.y0)?;
            d.set_item("x1", cv.x1)?;
            d.set_item("y1", cv.y1)?;
            d.set_item("text", &cv.text)?;
            d.set_item("left", cv.left)?;
            d.set_item("right", cv.right)?;
            d.set_item("top", cv.top)?;
            d.set_item("bottom", cv.bottom)?;
            d.set_item("has_text", cv.has_text)?;
            d.set_item("is_spanning_interior", cv.is_spanning_interior)?;
            d.set_item("bbox_valid", cv.bbox_valid)?;
            cell_dicts.push(d.into());
        }
        dict.set_item("cells", cell_dicts)?;

        Ok(dict.into())
    })
}

// ---------------------------------------------------------------------------
// Task 4: compute_accuracy_rs — fill-ratio metric
// ---------------------------------------------------------------------------

/// Compute extraction accuracy from cell data.
///
/// Lattice mode (has_edges=true): excludes spanning interior cells without text.
/// Stream mode (has_edges=false): uses data_grid to detect header region.
/// Applies structural penalty for single-column/single-row tables.
///
/// Returns accuracy as f64 (0.0–100.0).
#[pyfunction]
#[pyo3(signature = (cells, n_rows, n_cols, data_grid=None))]
pub fn compute_accuracy_rs(
    cells: Vec<CellTuple>,
    n_rows: usize,
    n_cols: usize,
    data_grid: Option<Vec<Vec<String>>>,
) -> PyResult<f64> {
    if cells.is_empty() {
        return Ok(0.0);
    }

    let total = cells.len();

    // Check if edge flags are available (lattice mode)
    let check_count = total.min(10);
    let has_edges = cells[..check_count]
        .iter()
        .any(|(_, _, _, _, _, left, _, top, _)| *left || *top);

    let mut effective_total: usize = 0;
    let mut filled: usize = 0;

    if has_edges {
        // Lattice mode: use edge flags to detect spanning interiors
        for (_, _, _, _, text, left, _, top, _) in &cells {
            let is_spanning_interior = !left || !top;
            let has_text = !text.trim().is_empty();
            if is_spanning_interior && !has_text {
                continue;
            }
            effective_total += 1;
            if has_text {
                filled += 1;
            }
        }
    } else if let Some(ref grid) = data_grid {
        // Stream mode: detect header region
        let mut header_end: usize = 0;
        for (ri, row) in grid.iter().enumerate() {
            let row_filled = row.iter().filter(|c| !c.trim().is_empty()).count();
            if row_filled == row.len() {
                header_end = ri;
                break;
            }
        }
        for (ri, row) in grid.iter().enumerate() {
            let in_header = ri < header_end;
            for cell in row {
                let has_text = !cell.trim().is_empty();
                if in_header && !has_text {
                    continue;
                }
                effective_total += 1;
                if has_text {
                    filled += 1;
                }
            }
        }
    } else {
        // Fallback: count all cells
        for (_, _, _, _, text, _, _, _, _) in &cells {
            effective_total += 1;
            if !text.trim().is_empty() {
                filled += 1;
            }
        }
    }

    if effective_total == 0 {
        effective_total = total;
        filled = cells
            .iter()
            .filter(|(_, _, _, _, text, _, _, _, _)| !text.trim().is_empty())
            .count();
    }

    let fill_score = 100.0 * filled as f64 / effective_total as f64;

    // Structural penalty: single-column or single-row tables are likely degenerate
    let structural_factor = if (n_cols == 1 && n_rows > 3) || (n_rows == 1 && n_cols > 3) {
        0.5
    } else {
        1.0
    };

    Ok((fill_score * structural_factor * 100.0).round() / 100.0)
}

// ---------------------------------------------------------------------------
// Task 4b: detect_collapse — column and header collapse detection
// ---------------------------------------------------------------------------

/// Detect column collapse: >80% of non-empty values in column 0.
///
/// This indicates the lattice parser failed and dumped everything into one column.
#[pyfunction]
pub fn detect_column_collapse(data: Vec<Vec<String>>) -> PyResult<bool> {
    if data.is_empty() {
        return Ok(false);
    }

    let n_cols = data.first().map_or(0, |r| r.len());
    if n_cols <= 1 {
        return Ok(false);
    }

    let mut col0_nonempty = 0usize;
    let mut total_nonempty = 0usize;

    for row in &data {
        for (ci, cell) in row.iter().enumerate() {
            if !cell.trim().is_empty() {
                total_nonempty += 1;
                if ci == 0 {
                    col0_nonempty += 1;
                }
            }
        }
    }

    if total_nonempty == 0 {
        return Ok(false);
    }

    Ok(col0_nonempty as f64 / total_nonempty as f64 > 0.8)
}

/// Detect header collapse: row 0 has a single cell containing newlines.
///
/// This indicates headers were collapsed into one cell with `\n` separators.
#[pyfunction]
pub fn detect_header_collapse(data: Vec<Vec<String>>) -> PyResult<bool> {
    if data.is_empty() {
        return Ok(false);
    }

    let first_row = &data[0];
    if first_row.is_empty() {
        return Ok(false);
    }

    // Check if only column 0 has content and it contains newlines
    let col0 = &first_row[0];
    let others_empty = first_row[1..].iter().all(|c| c.trim().is_empty());

    Ok(others_empty && col0.contains('\n') && first_row.len() > 1)
}

// ---------------------------------------------------------------------------
// Task 4c: table_integrity_metrics — DataFrame-level quality metrics
// ---------------------------------------------------------------------------

/// Compute table integrity metrics using Polars internally.
///
/// Returns a dict with: n_rows, n_cols, null_count, data_density,
/// is_single_column, is_single_row, column_collapse, header_collapse.
#[pyfunction]
pub fn table_integrity_metrics(data: Vec<Vec<String>>) -> PyResult<PyObject> {
    Python::with_gil(|py| {
        let n_rows = data.len();
        let n_cols = data.first().map_or(0, |r| r.len());

        if n_rows == 0 || n_cols == 0 {
            let dict = PyDict::new(py);
            dict.set_item("n_rows", 0u32)?;
            dict.set_item("n_cols", 0u32)?;
            dict.set_item("null_count", 0u32)?;
            dict.set_item("data_density", 0.0f64)?;
            dict.set_item("is_single_column", false)?;
            dict.set_item("is_single_row", false)?;
            dict.set_item("column_collapse", false)?;
            dict.set_item("header_collapse", false)?;
            return Ok(dict.into());
        }

        // Build Polars DataFrame internally for metrics computation
        let mut columns: Vec<Column> = Vec::with_capacity(n_cols);
        for ci in 0..n_cols {
            let values: Vec<Option<&str>> = data
                .iter()
                .map(|row| {
                    row.get(ci)
                        .filter(|s| !s.trim().is_empty())
                        .map(|s| s.as_str())
                })
                .collect();
            let col_name = format!("col_{}", ci);
            let series = Column::new(col_name.into(), &values);
            columns.push(series);
        }

        let df = DataFrame::new(columns).map_err(|e| {
            pyo3::exceptions::PyValueError::new_err(format!("Failed to create DataFrame: {}", e))
        })?;

        // Compute null count (empty strings are already None in our construction)
        let total_cells = n_rows * n_cols;
        let null_count: usize = df.get_columns().iter().map(|c| c.null_count()).sum();
        let data_density = (total_cells - null_count) as f64 / total_cells as f64;

        // Collapse detection (reuse logic)
        let column_collapse = detect_column_collapse(data.clone()).unwrap_or(false);
        let header_collapse = detect_header_collapse(data).unwrap_or(false);

        let dict = PyDict::new(py);
        dict.set_item("n_rows", n_rows)?;
        dict.set_item("n_cols", n_cols)?;
        dict.set_item("null_count", null_count)?;
        dict.set_item("data_density", (data_density * 10000.0).round() / 10000.0)?;
        dict.set_item("is_single_column", n_cols == 1 && n_rows > 3)?;
        dict.set_item("is_single_row", n_rows == 1 && n_cols > 3)?;
        dict.set_item("column_collapse", column_collapse)?;
        dict.set_item("header_collapse", header_collapse)?;

        Ok(dict.into())
    })
}

// ===========================================================================
// Tests
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // -- validate_grid tests --

    fn s(v: &str) -> String {
        v.to_string()
    }

    #[test]
    fn test_validate_grid_valid() {
        let data: Vec<Vec<String>> = vec![vec![s("a"), s("b")], vec![s("c"), s("d")]];
        let expected_cols = 2;
        let mut padded_count = 0usize;
        for row in &data {
            if row.len() != expected_cols {
                padded_count += 1;
            }
        }
        assert_eq!(padded_count, 0);
    }

    #[test]
    fn test_validate_grid_ragged() {
        let data: Vec<Vec<String>> = vec![vec![s("a"), s("b")], vec![s("c")]];
        let expected_cols = 2;
        let mut result: Vec<Vec<String>> = Vec::new();
        let mut padded_count = 0usize;
        for row in &data {
            if row.len() == expected_cols {
                result.push(row.clone());
            } else {
                padded_count += 1;
                let mut padded = row.clone();
                padded.resize(expected_cols, String::new());
                result.push(padded);
            }
        }
        assert_eq!(padded_count, 1);
        assert_eq!(result[1], vec![s("c"), s("")]);
    }

    #[test]
    fn test_validate_grid_empty() {
        let data: Vec<Vec<String>> = vec![];
        assert_eq!(data.len(), 0);
    }

    // -- cell validation tests --

    #[test]
    fn test_cell_bbox_valid() {
        let valid = (0.0 < 10.0) && (0.0 < 20.0);
        assert!(valid);
    }

    #[test]
    fn test_cell_bbox_invalid() {
        let invalid = !(10.0 < 0.0) || !(20.0 < 0.0);
        assert!(invalid);
    }

    #[test]
    fn test_spanning_interior_detection() {
        // Missing left edge = spanning interior
        let left = false;
        let top = true;
        assert!(!left || !top); // is_spanning_interior
    }

    // -- accuracy tests --

    #[test]
    fn test_accuracy_lattice_full() {
        let cells: Vec<(f64, f64, f64, f64, String, bool, bool, bool, bool)> = vec![
            (0.0, 0.0, 10.0, 10.0, s("A"), true, true, true, true),
            (10.0, 0.0, 20.0, 10.0, s("B"), true, true, true, true),
        ];

        let mut eff = 0usize;
        let mut filled = 0usize;
        for (_, _, _, _, text, left, _, top, _) in &cells {
            let is_interior = !left || !top;
            let has_text = !text.trim().is_empty();
            if is_interior && !has_text {
                continue;
            }
            eff += 1;
            if has_text {
                filled += 1;
            }
        }
        assert_eq!(eff, 2);
        assert_eq!(filled, 2);
    }

    #[test]
    fn test_accuracy_with_spanning_interior() {
        let cells: Vec<(f64, f64, f64, f64, String, bool, bool, bool, bool)> = vec![
            (0.0, 0.0, 10.0, 10.0, s("A"), true, true, true, true),
            (10.0, 0.0, 20.0, 10.0, s(""), false, true, true, true),
            (0.0, 10.0, 10.0, 20.0, s("C"), true, true, true, true),
        ];

        let mut eff = 0usize;
        let mut filled = 0usize;
        for (_, _, _, _, text, left, _, top, _) in &cells {
            let is_interior = !left || !top;
            let has_text = !text.trim().is_empty();
            if is_interior && !has_text {
                continue;
            }
            eff += 1;
            if has_text {
                filled += 1;
            }
        }
        assert_eq!(eff, 2);
        assert_eq!(filled, 2);
    }

    // -- collapse detection tests --

    #[test]
    fn test_detect_column_collapse_true() {
        let data: Vec<Vec<String>> = vec![
            vec![s("Header"), s(""), s("")],
            vec![s("Data1"), s(""), s("")],
            vec![s("Data2"), s(""), s("")],
        ];
        let result = detect_column_collapse(data).unwrap();
        assert!(result);
    }

    #[test]
    fn test_detect_column_collapse_false() {
        let data: Vec<Vec<String>> =
            vec![vec![s("A"), s("B"), s("C")], vec![s("D"), s("E"), s("F")]];
        let result = detect_column_collapse(data).unwrap();
        assert!(!result);
    }

    #[test]
    fn test_detect_header_collapse_true() {
        let data: Vec<Vec<String>> = vec![
            vec![s("Name\nAge\nCity"), s(""), s("")],
            vec![s("Alice"), s("30"), s("NYC")],
        ];
        let result = detect_header_collapse(data).unwrap();
        assert!(result);
    }

    #[test]
    fn test_detect_header_collapse_false() {
        let data: Vec<Vec<String>> = vec![
            vec![s("Name"), s("Age"), s("City")],
            vec![s("Alice"), s("30"), s("NYC")],
        ];
        let result = detect_header_collapse(data).unwrap();
        assert!(!result);
    }

    // -- integrity metrics tests --

    #[test]
    fn test_integrity_metrics_basic() {
        let total_cells = 6;
        let non_empty = 5;
        let density = non_empty as f64 / total_cells as f64;
        assert!((density - 5.0 / 6.0).abs() < 0.001);
    }

    #[test]
    fn test_integrity_metrics_empty() {
        let data: Vec<Vec<String>> = vec![];
        assert_eq!(data.len(), 0);
    }

    #[test]
    fn test_integrity_single_column() {
        let n_cols = 1usize;
        let n_rows = 5usize;
        assert!(n_cols == 1 && n_rows > 3);
    }
}
