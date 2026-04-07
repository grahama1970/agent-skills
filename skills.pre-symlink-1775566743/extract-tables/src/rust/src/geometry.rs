//! Geometry utilities for table extraction.
//!
//! Ports the coordinate math from camelot/utils.py:
//! - merge_close_lines
//! - scale_coordinates
//! - segments_in_bbox

use pyo3::prelude::*;

/// A line segment as (x1, y1, x2, y2).
type Segment = (f64, f64, f64, f64);

/// Merge lines that are within `tolerance` of each other.
///
/// Equivalent to camelot.utils.merge_close_lines().
#[pyfunction]
pub fn merge_close_lines(lines: Vec<f64>, line_tol: f64) -> Vec<f64> {
    if lines.is_empty() {
        return vec![];
    }

    let mut merged = vec![lines[0]];
    for &line in &lines[1..] {
        // SAFETY: merged always has at least one element (initialized above)
        let last = *merged.last().expect("invariant: merged is never empty");
        if (line - last).abs() > line_tol {
            merged.push(line);
        }
    }
    merged
}

/// Scale coordinates between PDF and image coordinate spaces.
#[pyfunction]
pub fn scale_coordinates(
    coords: Vec<Segment>,
    x_scale: f64,
    y_scale: f64,
    height: f64,
) -> Vec<Segment> {
    coords
        .into_iter()
        .map(|(x1, y1, x2, y2)| {
            (
                x1 * x_scale,
                (height - y1) * y_scale,
                x2 * x_scale,
                (height - y2) * y_scale,
            )
        })
        .collect()
}

/// Filter line segments that fall within a bounding box.
#[pyfunction]
pub fn segments_in_bbox(
    bbox: Segment,
    vertical: Vec<Segment>,
    horizontal: Vec<Segment>,
) -> (Vec<Segment>, Vec<Segment>) {
    let (x1, y1, x2, y2) = bbox;
    let lb = x1.min(x2);
    let rb = x1.max(x2);
    let tb = y1.max(y2);
    let bb = y1.min(y2);

    let v_filtered: Vec<_> = vertical
        .into_iter()
        .filter(|(sx1, sy1, sx2, sy2)| {
            let sx_min = sx1.min(*sx2);
            let sy_min = sy1.min(*sy2);
            let sy_max = sy1.max(*sy2);
            sx_min >= lb && sx_min <= rb && sy_min >= bb && sy_max <= tb
        })
        .collect();

    let h_filtered: Vec<_> = horizontal
        .into_iter()
        .filter(|(sx1, sy1, sx2, sy2)| {
            let sy_min = sy1.min(*sy2);
            let sx_min = sx1.min(*sx2);
            let sx_max = sx1.max(*sx2);
            sy_min >= bb && sy_min <= tb && sx_min >= lb && sx_max <= rb
        })
        .collect();

    (v_filtered, h_filtered)
}

/// Filter text elements whose center falls within a bounding box.
///
/// bbox: (x0, y0, x1, y1) in top-left origin.
/// text_elements: list of (text, x0, y0, x1, y1) tuples.
///
/// Uses a 2-pixel tolerance matching camelot's original Python.
#[pyfunction]
pub fn text_in_bbox(
    bbox: (f64, f64, f64, f64),
    text_elements: Vec<(String, f64, f64, f64, f64)>,
) -> Vec<(String, f64, f64, f64, f64)> {
    let (bx0, by0, bx1, by1) = bbox;
    let lb_x = bx0.min(bx1);
    let rb_x = bx0.max(bx1);
    let lb_y = by0.min(by1);
    let rb_y = by0.max(by1);
    text_elements
        .into_iter()
        .filter(|(_, x0, y0, x1, y1)| {
            let cx = (x0 + x1) / 2.0;
            let cy = (y0 + y1) / 2.0;
            cx >= lb_x - 2.0 && cx <= rb_x + 2.0 && cy >= lb_y - 2.0 && cy <= rb_y + 2.0
        })
        .collect()
}

/// Flag super/subscripts in text by enclosing smaller-font characters with <s></s>.
///
/// textline: list of (char_text, size) tuples (height for horizontal, width for vertical).
/// direction: "horizontal" or "vertical" (used for documentation; sizes should already be correct).
/// strip_text: characters to strip from result.
///
/// Returns the processed string with flagged super/subscripts.
#[pyfunction]
#[pyo3(signature = (textline, direction, strip_text = ""))]
pub fn flag_font_size(
    textline: Vec<(String, f64)>,
    direction: &str,
    strip_text: &str,
) -> PyResult<String> {
    if direction != "horizontal" && direction != "vertical" {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "Invalid direction provided. Use 'horizontal' or 'vertical'.",
        ));
    }

    if textline.is_empty() {
        return Ok(String::new());
    }

    // Round sizes to 6 decimal places
    let rounded: Vec<(String, f64)> = textline
        .into_iter()
        .map(|(text, size)| {
            let factor = 1_000_000.0;
            (text, (size * factor).round() / factor)
        })
        .collect();

    // Group by size, preserving insertion order via Vec
    let mut size_groups: Vec<(f64, Vec<String>)> = Vec::new();
    for (text, size) in &rounded {
        if let Some(entry) = size_groups
            .iter_mut()
            .find(|(s, _)| (*s - size).abs() < 1e-9)
        {
            entry.1.push(text.clone());
        } else {
            size_groups.push((*size, vec![text.clone()]));
        }
    }

    let fstring = if size_groups.len() > 1 {
        let min_size = size_groups
            .iter()
            .map(|(s, _)| *s)
            .fold(f64::INFINITY, f64::min);

        let mut parts: Vec<String> = Vec::new();
        for (size, chars) in &size_groups {
            let combined: String = chars.concat();
            let trimmed = combined.trim().to_string();
            if !trimmed.is_empty() {
                if (*size - min_size).abs() < 1e-9 {
                    parts.push(format!("<s>{}</s>", trimmed));
                } else {
                    parts.push(trimmed);
                }
            }
        }
        parts.concat()
    } else {
        rounded.iter().map(|(t, _)| t.as_str()).collect::<String>()
    };

    // Strip characters
    if strip_text.is_empty() {
        Ok(fstring)
    } else {
        Ok(fstring
            .chars()
            .filter(|c| !strip_text.contains(*c))
            .collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_merge_close_lines() {
        let lines = vec![10.0, 10.5, 11.0, 20.0, 20.3, 30.0];
        let merged = merge_close_lines(lines, 1.5);
        assert_eq!(merged, vec![10.0, 20.0, 30.0]);
    }

    #[test]
    fn test_merge_empty() {
        let merged = merge_close_lines(vec![], 1.0);
        assert!(merged.is_empty());
    }

    #[test]
    fn test_text_in_bbox_filters() {
        let elements = vec![
            ("inside".to_string(), 150.0, 150.0, 200.0, 170.0),
            ("outside".to_string(), 500.0, 500.0, 550.0, 520.0),
            ("also_inside".to_string(), 200.0, 200.0, 300.0, 220.0),
        ];
        let result = text_in_bbox((100.0, 100.0, 400.0, 400.0), elements);
        assert_eq!(result.len(), 2);
        assert_eq!(result[0].0, "inside");
        assert_eq!(result[1].0, "also_inside");
    }

    #[test]
    fn test_text_in_bbox_empty() {
        let result = text_in_bbox((0.0, 0.0, 100.0, 100.0), vec![]);
        assert!(result.is_empty());
    }

    #[test]
    fn test_text_in_bbox_tolerance() {
        // Element center at (51, 51) should be inside bbox (0,0,50,50) with 2px tolerance
        let elements = vec![("edge".to_string(), 50.0, 50.0, 54.0, 54.0)];
        let result = text_in_bbox((0.0, 0.0, 50.0, 50.0), elements);
        assert_eq!(result.len(), 1);
    }

    #[test]
    fn test_flag_font_size_subscript() {
        let textline = vec![
            ("H".to_string(), 12.0),
            ("2".to_string(), 8.0),
            ("O".to_string(), 12.0),
        ];
        let result = flag_font_size(textline, "horizontal", "").unwrap();
        assert!(result.contains("<s>"));
        assert!(result.contains("2"));
    }

    #[test]
    fn test_flag_font_size_empty() {
        let result = flag_font_size(vec![], "horizontal", "").unwrap();
        assert!(result.is_empty());
    }

    #[test]
    fn test_flag_font_size_uniform() {
        let textline = vec![("A".to_string(), 12.0), ("B".to_string(), 12.0)];
        let result = flag_font_size(textline, "horizontal", "").unwrap();
        assert_eq!(result, "AB");
        assert!(!result.contains("<s>"));
    }

    #[test]
    fn test_flag_font_size_invalid_direction() {
        let result = flag_font_size(vec![], "diagonal", "");
        assert!(result.is_err());
    }
}
