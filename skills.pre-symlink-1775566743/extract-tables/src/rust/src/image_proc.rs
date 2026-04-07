//! Image processing hotspots for table extraction.
//!
//! Provides Rust implementations of the image processing pipeline from
//! camelot/image_processing.py, using imageproc (pure Rust, no C++ dependency).
//!
//! Architecture: core logic uses Result<T, String> for testability without Python.
//! PyO3 wrappers (at the bottom) convert to PyResult for the Python interface.

use image::{GrayImage, ImageFormat, Luma};
use imageproc::contours::{find_contours, BorderType, Contour};
use imageproc::morphology::{grayscale_dilate, grayscale_erode, Mask};
use std::io::Cursor;

// ---------------------------------------------------------------------------
// Core logic (no PyO3 dependency, testable standalone)
// ---------------------------------------------------------------------------

/// Decode PNG bytes to a GrayImage.
fn decode_gray(img_bytes: &[u8]) -> Result<GrayImage, String> {
    image::load_from_memory(img_bytes)
        .map(|img| img.to_luma8())
        .map_err(|e| format!("Failed to decode image: {}", e))
}

/// Encode a GrayImage to PNG bytes.
fn encode_png(img: &GrayImage) -> Result<Vec<u8>, String> {
    let mut buf = Vec::new();
    img.write_to(&mut Cursor::new(&mut buf), ImageFormat::Png)
        .map_err(|e| format!("Failed to encode PNG: {}", e))?;
    Ok(buf)
}

/// Build a rectangular Mask for morphological operations.
///
/// For horizontal line detection: wide kernel (width x 1)
/// For vertical line detection: tall kernel (1 x height)
///
/// The Mask::from_image API requires images with side lengths <= 511.
/// We clamp dimensions accordingly.
fn make_rect_mask(width: u32, height: u32) -> Mask {
    let w = width.clamp(1, 511);
    let h = height.clamp(1, 511);
    let kernel = GrayImage::from_fn(w, h, |_, _| Luma([255u8]));
    let cx = (w / 2) as u8;
    let cy = (h / 2) as u8;
    Mask::from_image(&kernel, cx, cy)
}

/// Morphological opening with a rectangular kernel.
///
/// Erode then dilate with the same kernel, repeated `iterations` times.
/// This isolates structures matching the kernel shape (horizontal or vertical lines).
fn morphological_open(img: &GrayImage, mask: &Mask, iterations: u32) -> GrayImage {
    let mut result = img.clone();
    for _ in 0..iterations {
        result = grayscale_erode(&result, mask);
        result = grayscale_dilate(&result, mask);
    }
    result
}

/// Compute bounding box of a contour: (x_min, y_min, x_max, y_max).
fn contour_bbox<T: num::NumCast + Copy>(contour: &Contour<T>) -> Option<(f64, f64, f64, f64)> {
    if contour.points.is_empty() {
        return None;
    }
    let mut x_min = f64::MAX;
    let mut y_min = f64::MAX;
    let mut x_max = f64::MIN;
    let mut y_max = f64::MIN;
    for p in &contour.points {
        let x: f64 = num::cast(p.x)?;
        let y: f64 = num::cast(p.y)?;
        if x < x_min {
            x_min = x;
        }
        if x > x_max {
            x_max = x;
        }
        if y < y_min {
            y_min = y;
        }
        if y > y_max {
            y_max = y;
        }
    }
    Some((x_min, y_min, x_max, y_max))
}

/// Compute kernel dimensions for a given direction and image size.
fn kernel_dims(
    direction: &str,
    img_w: u32,
    img_h: u32,
    line_scale: u32,
) -> Result<(u32, u32), String> {
    match direction {
        "horizontal" => {
            let kernel_w = (img_w / line_scale.max(1)).max(1);
            Ok((kernel_w, 1u32))
        }
        "vertical" => {
            let kernel_h = (img_h / line_scale.max(1)).max(1);
            Ok((1u32, kernel_h))
        }
        _ => Err("direction must be 'horizontal' or 'vertical'".to_string()),
    }
}

/// Core: apply adaptive threshold to a grayscale image (PNG bytes in, PNG bytes out).
fn core_adaptive_threshold(
    img_bytes: &[u8],
    block_radius: u32,
    delta: i32,
) -> Result<Vec<u8>, String> {
    let img = decode_gray(img_bytes)?;
    let result = imageproc::contrast::adaptive_threshold(&img, block_radius, delta);
    encode_png(&result)
}

/// Core: find horizontal or vertical lines in a binary image.
///
/// Returns list of (x1, y1, x2, y2) line segments derived from contour bounding boxes.
fn core_find_lines(
    img_bytes: &[u8],
    direction: &str,
    line_scale: u32,
    iterations: u32,
) -> Result<Vec<(f64, f64, f64, f64)>, String> {
    let img = decode_gray(img_bytes)?;
    let (w, h) = img.dimensions();
    let (kw, kh) = kernel_dims(direction, w, h, line_scale)?;

    let mask = make_rect_mask(kw, kh);
    let opened = morphological_open(&img, &mask, iterations.max(1));

    let contours: Vec<Contour<i32>> = find_contours(&opened);

    let mut lines = Vec::new();
    for contour in &contours {
        if contour.border_type != BorderType::Outer {
            continue;
        }
        if let Some((x_min, y_min, x_max, y_max)) = contour_bbox(contour) {
            let seg = match direction {
                "horizontal" => {
                    let y_mid = (y_min + y_max) / 2.0;
                    (x_min, y_mid, x_max, y_mid)
                }
                "vertical" => {
                    let x_mid = (x_min + x_max) / 2.0;
                    (x_mid, y_min, x_mid, y_max)
                }
                _ => unreachable!(),
            };
            // Filter out tiny segments (noise)
            let length = ((seg.2 - seg.0).powi(2) + (seg.3 - seg.1).powi(2)).sqrt();
            if length > 2.0 {
                lines.push(seg);
            }
        }
    }

    Ok(lines)
}

/// Core: find contours in a binary image, return bounding boxes as (x, y, w, h).
fn core_find_contours(img_bytes: &[u8]) -> Result<Vec<(f64, f64, f64, f64)>, String> {
    let img = decode_gray(img_bytes)?;
    let contours: Vec<Contour<i32>> = find_contours(&img);

    let mut bboxes = Vec::new();
    for contour in &contours {
        if contour.border_type != BorderType::Outer {
            continue;
        }
        if let Some((x_min, y_min, x_max, y_max)) = contour_bbox(contour) {
            let w = x_max - x_min;
            let h = y_max - y_min;
            if w > 0.0 && h > 0.0 {
                bboxes.push((x_min, y_min, w, h));
            }
        }
    }

    Ok(bboxes)
}

/// Core: find joints (intersections) between horizontal and vertical line masks.
fn core_find_joints(
    horizontal_mask_bytes: &[u8],
    vertical_mask_bytes: &[u8],
) -> Result<Vec<(f64, f64)>, String> {
    let h_mask = decode_gray(horizontal_mask_bytes)?;
    let v_mask = decode_gray(vertical_mask_bytes)?;

    let (w, h) = h_mask.dimensions();
    if v_mask.dimensions() != (w, h) {
        return Err("Horizontal and vertical masks must have the same dimensions".to_string());
    }

    // Bitwise AND: pixel is white only where both masks are white
    let mut joint_mask = GrayImage::new(w, h);
    for y in 0..h {
        for x in 0..w {
            let hp = h_mask.get_pixel(x, y)[0];
            let vp = v_mask.get_pixel(x, y)[0];
            if hp > 0 && vp > 0 {
                joint_mask.put_pixel(x, y, Luma([255u8]));
            }
        }
    }

    let contours: Vec<Contour<i32>> = find_contours(&joint_mask);

    let mut joints = Vec::new();
    for contour in &contours {
        if contour.border_type != BorderType::Outer {
            continue;
        }
        if let Some((x_min, y_min, x_max, y_max)) = contour_bbox(contour) {
            let cx = (x_min + x_max) / 2.0;
            let cy = (y_min + y_max) / 2.0;
            joints.push((cx, cy));
        }
    }

    Ok(joints)
}

/// Core: morphological opening, returns PNG bytes.
fn core_morphological_open(
    img_bytes: &[u8],
    direction: &str,
    line_scale: u32,
    iterations: u32,
) -> Result<Vec<u8>, String> {
    let img = decode_gray(img_bytes)?;
    let (w, h) = img.dimensions();
    let (kw, kh) = kernel_dims(direction, w, h, line_scale)?;

    let mask = make_rect_mask(kw, kh);
    let result = morphological_open(&img, &mask, iterations.max(1));
    encode_png(&result)
}

// ---------------------------------------------------------------------------
// PyO3 wrappers (thin layer converting Result<T,String> -> PyResult<T>)
// ---------------------------------------------------------------------------

use pyo3::prelude::*;
use pyo3::types::PyBytes;

fn to_pyerr(e: String) -> PyErr {
    pyo3::exceptions::PyValueError::new_err(e)
}

/// Apply adaptive threshold to a grayscale image.
///
/// Input: PNG bytes. Output: binary PNG bytes.
/// block_radius: half-size of the threshold block (must be > 0).
/// delta: offset from local mean (Camelot default: 15).
#[pyfunction]
pub fn adaptive_threshold_image(
    py: Python<'_>,
    img_bytes: &[u8],
    block_radius: u32,
    delta: i32,
) -> PyResult<PyObject> {
    let buf = core_adaptive_threshold(img_bytes, block_radius, delta).map_err(to_pyerr)?;
    Ok(PyBytes::new(py, &buf).into())
}

/// Find horizontal or vertical lines using morphological operations + contour detection.
///
/// direction: "horizontal" or "vertical"
/// line_scale: kernel = image_dimension / line_scale
/// iterations: number of morphological open passes
///
/// Returns list of (x1, y1, x2, y2) line segments.
#[pyfunction]
pub fn find_lines(
    img_bytes: &[u8],
    direction: &str,
    line_scale: u32,
    iterations: u32,
) -> PyResult<Vec<(f64, f64, f64, f64)>> {
    core_find_lines(img_bytes, direction, line_scale, iterations).map_err(to_pyerr)
}

/// Find contours in a binary image and return their bounding boxes.
///
/// Returns: list of (x, y, w, h) bounding boxes for outer contours.
#[pyfunction]
pub fn find_contours_in_image(img_bytes: &[u8]) -> PyResult<Vec<(f64, f64, f64, f64)>> {
    core_find_contours(img_bytes).map_err(to_pyerr)
}

/// Find joints (intersections) between horizontal and vertical line masks.
///
/// Returns: list of (x, y) coordinates of intersections.
#[pyfunction]
pub fn find_joints(
    horizontal_mask_bytes: &[u8],
    vertical_mask_bytes: &[u8],
) -> PyResult<Vec<(f64, f64)>> {
    core_find_joints(horizontal_mask_bytes, vertical_mask_bytes).map_err(to_pyerr)
}

/// Apply morphological opening and return result as PNG bytes.
///
/// direction: "horizontal" or "vertical"
/// line_scale: kernel = image_dimension / line_scale
/// iterations: number of open passes
#[pyfunction]
pub fn morphological_open_image(
    py: Python<'_>,
    img_bytes: &[u8],
    direction: &str,
    line_scale: u32,
    iterations: u32,
) -> PyResult<PyObject> {
    let buf =
        core_morphological_open(img_bytes, direction, line_scale, iterations).map_err(to_pyerr)?;
    Ok(PyBytes::new(py, &buf).into())
}

// ---------------------------------------------------------------------------
// Tests (use core_* functions directly, no PyO3 linkage needed)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use image::{GrayImage, Luma};

    fn make_test_image(width: u32, height: u32, fill: u8) -> GrayImage {
        GrayImage::from_fn(width, height, |_, _| Luma([fill]))
    }

    fn to_png(img: &GrayImage) -> Vec<u8> {
        encode_png(img).unwrap()
    }

    #[test]
    fn test_adaptive_threshold_basic() {
        let img = GrayImage::from_fn(100, 100, |x, y| {
            if x > 30 && x < 70 && y > 30 && y < 70 {
                Luma([0u8])
            } else {
                Luma([255u8])
            }
        });
        let result = imageproc::contrast::adaptive_threshold(&img, 10, 0);
        assert_eq!(result.dimensions(), (100, 100));
        // Corner pixel (far from border) should be white
        assert_eq!(result.get_pixel(5, 5)[0], 255);
        // Interior of the dark rectangle: centre pixel is 0, local mean in
        // the interior is also ~0, so 0 >= 0 - 0 is true -> white (255).
        // The dark-to-light transitions at the border are where black pixels appear.
        // Test a pixel right at the border of the dark region (block_radius=10):
        // pixel at (31, 50) is dark(0), but its neighborhood straddles the border
        // so the local mean is high -> 0 < mean -> black (0).
        assert_eq!(result.get_pixel(31, 50)[0], 0);
    }

    #[test]
    fn test_adaptive_threshold_png_roundtrip() {
        let img = GrayImage::from_fn(80, 80, |x, y| {
            if x > 20 && x < 60 && y > 20 && y < 60 {
                Luma([0u8])
            } else {
                Luma([200u8])
            }
        });
        let png = to_png(&img);
        let result = core_adaptive_threshold(&png, 5, 0).unwrap();
        let decoded = decode_gray(&result).unwrap();
        assert_eq!(decoded.dimensions(), (80, 80));
    }

    #[test]
    fn test_make_rect_mask_horizontal() {
        let mask = make_rect_mask(50, 1);
        let img = make_test_image(100, 100, 128);
        let _eroded = grayscale_erode(&img, &mask);
    }

    #[test]
    fn test_make_rect_mask_vertical() {
        let mask = make_rect_mask(1, 50);
        let img = make_test_image(100, 100, 128);
        let _eroded = grayscale_erode(&img, &mask);
    }

    #[test]
    fn test_make_rect_mask_clamps_at_511() {
        let mask = make_rect_mask(1000, 1);
        let img = make_test_image(100, 100, 128);
        let _eroded = grayscale_erode(&img, &mask);
    }

    #[test]
    fn test_morphological_open_preserves_dimensions() {
        let img = make_test_image(200, 200, 255);
        let mask = make_rect_mask(20, 1);
        let result = morphological_open(&img, &mask, 1);
        assert_eq!(result.dimensions(), (200, 200));
    }

    #[test]
    fn test_find_lines_horizontal() {
        let mut img = GrayImage::new(200, 100);
        for x in 10..190 {
            for y in 48..52 {
                img.put_pixel(x, y, Luma([255u8]));
            }
        }
        let png = to_png(&img);

        let lines = core_find_lines(&png, "horizontal", 15, 1).unwrap();
        assert!(
            !lines.is_empty(),
            "Should find at least one horizontal line"
        );

        for (x1, y1, x2, y2) in &lines {
            assert!(
                (y1 - y2).abs() < 5.0,
                "Horizontal line should have similar y coords"
            );
            assert!(x2 - x1 > 10.0, "Line should have meaningful length");
        }
    }

    #[test]
    fn test_find_lines_vertical() {
        let mut img = GrayImage::new(100, 200);
        for y in 10..190 {
            for x in 48..52 {
                img.put_pixel(x, y, Luma([255u8]));
            }
        }
        let png = to_png(&img);

        let lines = core_find_lines(&png, "vertical", 15, 1).unwrap();
        assert!(!lines.is_empty(), "Should find at least one vertical line");

        for (x1, y1, x2, y2) in &lines {
            assert!(
                (x1 - x2).abs() < 5.0,
                "Vertical line should have similar x coords"
            );
            assert!(y2 - y1 > 10.0, "Line should have meaningful length");
        }
    }

    #[test]
    fn test_find_lines_invalid_direction() {
        let img = make_test_image(100, 100, 0);
        let png = to_png(&img);
        let result = core_find_lines(&png, "diagonal", 15, 1);
        assert!(result.is_err());
    }

    #[test]
    fn test_find_contours_basic() {
        let mut img = GrayImage::new(100, 100);
        for y in 20..80 {
            for x in 20..80 {
                img.put_pixel(x, y, Luma([255u8]));
            }
        }
        let png = to_png(&img);

        let bboxes = core_find_contours(&png).unwrap();
        assert!(!bboxes.is_empty(), "Should find at least one contour");

        let (bx, by, bw, bh) = bboxes[0];
        assert!(bx >= 19.0 && bx <= 21.0, "x should be ~20, got {}", bx);
        assert!(by >= 19.0 && by <= 21.0, "y should be ~20, got {}", by);
        assert!(bw >= 58.0 && bw <= 61.0, "w should be ~60, got {}", bw);
        assert!(bh >= 58.0 && bh <= 61.0, "h should be ~60, got {}", bh);
    }

    #[test]
    fn test_find_joints_basic() {
        let mut h_mask = GrayImage::new(100, 100);
        for x in 0..100 {
            for y in 48..52 {
                h_mask.put_pixel(x, y, Luma([255u8]));
            }
        }

        let mut v_mask = GrayImage::new(100, 100);
        for y in 0..100 {
            for x in 48..52 {
                v_mask.put_pixel(x, y, Luma([255u8]));
            }
        }

        let h_png = to_png(&h_mask);
        let v_png = to_png(&v_mask);

        let joints = core_find_joints(&h_png, &v_png).unwrap();
        assert!(!joints.is_empty(), "Should find at least one joint");

        let (jx, jy) = joints[0];
        assert!(
            (jx - 49.5).abs() < 3.0 && (jy - 49.5).abs() < 3.0,
            "Joint should be near (50,50), got ({}, {})",
            jx,
            jy
        );
    }

    #[test]
    fn test_find_joints_dimension_mismatch() {
        let h = GrayImage::new(100, 100);
        let v = GrayImage::new(200, 200);
        let h_png = to_png(&h);
        let v_png = to_png(&v);
        let result = core_find_joints(&h_png, &v_png);
        assert!(result.is_err());
    }

    #[test]
    fn test_contour_bbox_empty() {
        let contour: Contour<i32> = Contour::new(vec![], BorderType::Outer, None);
        assert!(contour_bbox(&contour).is_none());
    }

    #[test]
    fn test_encode_decode_roundtrip() {
        let img = make_test_image(50, 50, 128);
        let png = to_png(&img);
        let decoded = decode_gray(&png).unwrap();
        assert_eq!(decoded.dimensions(), (50, 50));
        assert_eq!(decoded.get_pixel(25, 25)[0], 128);
    }

    #[test]
    fn test_morphological_open_image_core() {
        let mut img = GrayImage::new(200, 100);
        for x in 10..190 {
            for y in 48..52 {
                img.put_pixel(x, y, Luma([255u8]));
            }
        }
        let png = to_png(&img);
        let result = core_morphological_open(&png, "horizontal", 15, 1).unwrap();
        let decoded = decode_gray(&result).unwrap();
        assert_eq!(decoded.dimensions(), (200, 100));
    }
}
