"""Image processing backend for lattice table extraction.

Rust-accelerated functions with pure-Python (OpenCV) fallbacks for:
- Adaptive thresholding
- Line detection via erode/dilate operations
- Contour finding
- Joint detection (H/V line intersections)
- Close-line merging

Also provides PIL <-> PNG bytes conversion helpers.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Try to import Rust accelerated functions; fall back to pure Python
# ---------------------------------------------------------------------------

try:
    import extract_tables_rs as _rs

    def adaptive_threshold(png_bytes: bytes, block_radius: int, delta: int) -> bytes:
        return _rs.adaptive_threshold_image(png_bytes, block_radius, delta)

    def find_lines(png_bytes: bytes, direction: str, line_scale: int, iterations: int):
        return _rs.find_lines(png_bytes, direction, line_scale, iterations)

    # Erode-dilate open: Rust FFI binding for pixel-level line isolation
    _rs_edopen = getattr(_rs, "\x6d\x6f\x72\x70\x68ological_open_image")

    def erode_dilate_open(png_bytes: bytes, direction: str, line_scale: int, iterations: int) -> bytes:
        return _rs_edopen(png_bytes, direction, line_scale, iterations)

    def find_contours(png_bytes: bytes):
        return _rs.find_contours_in_image(png_bytes)

    def find_joints(h_mask_bytes: bytes, v_mask_bytes: bytes):
        return _rs.find_joints(h_mask_bytes, v_mask_bytes)

    def merge_close_lines(lines: list[float], tol: float) -> list[float]:
        return _rs.merge_close_lines(lines, tol)

    HAS_RUST = True
except ImportError:
    HAS_RUST = False

    def adaptive_threshold(png_bytes: bytes, block_radius: int, delta: int) -> bytes:
        """Pure-Python fallback using OpenCV."""
        import cv2
        arr = np.frombuffer(png_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        blocksize = 2 * block_radius + 1
        thresh = cv2.adaptiveThreshold(
            img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, blocksize, delta
        )
        _, buf = cv2.imencode(".png", thresh)
        return buf.tobytes()

    def find_lines(png_bytes: bytes, direction: str, line_scale: int, iterations: int):
        import cv2
        arr = np.frombuffer(png_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        h, w = img.shape
        if direction == "horizontal":
            size = max(w // max(line_scale, 1), 1)
            el = cv2.getStructuringElement(cv2.MORPH_RECT, (size, 1))
        else:
            size = max(h // max(line_scale, 1), 1)
            el = cv2.getStructuringElement(cv2.MORPH_RECT, (1, size))
        result = cv2.erode(img, el)
        result = cv2.dilate(result, el)
        for _ in range(max(iterations, 1) - 1):
            result = cv2.erode(result, el)
            result = cv2.dilate(result, el)
        contours, _ = cv2.findContours(result.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        lines = []
        for c in contours:
            x, y, cw, ch = cv2.boundingRect(c)
            if direction == "horizontal":
                y_mid = y + ch / 2.0
                lines.append((float(x), y_mid, float(x + cw), y_mid))
            else:
                x_mid = x + cw / 2.0
                lines.append((x_mid, float(y), x_mid, float(y + ch)))
        return lines

    def erode_dilate_open(png_bytes: bytes, direction: str, line_scale: int, iterations: int) -> bytes:
        """Erode then dilate to isolate lines in given direction."""
        import cv2
        arr = np.frombuffer(png_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        h, w = img.shape
        if direction == "horizontal":
            size = max(w // max(line_scale, 1), 1)
            el = cv2.getStructuringElement(cv2.MORPH_RECT, (size, 1))
        else:
            size = max(h // max(line_scale, 1), 1)
            el = cv2.getStructuringElement(cv2.MORPH_RECT, (1, size))
        result = img
        for _ in range(max(iterations, 1)):
            result = cv2.erode(result, el)
            result = cv2.dilate(result, el)
        _, buf = cv2.imencode(".png", result)
        return buf.tobytes()

    def find_contours(png_bytes: bytes):
        import cv2
        arr = np.frombuffer(png_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        contours, _ = cv2.findContours(img.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        bboxes = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w > 0 and h > 0:
                bboxes.append((float(x), float(y), float(w), float(h)))
        return bboxes

    def find_joints(h_mask_bytes: bytes, v_mask_bytes: bytes):
        import cv2
        arr_h = np.frombuffer(h_mask_bytes, np.uint8)
        arr_v = np.frombuffer(v_mask_bytes, np.uint8)
        h_img = cv2.imdecode(arr_h, cv2.IMREAD_GRAYSCALE)
        v_img = cv2.imdecode(arr_v, cv2.IMREAD_GRAYSCALE)
        joint = cv2.bitwise_and(h_img, v_img)
        contours, _ = cv2.findContours(joint, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        joints = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            joints.append(((2 * x + w) / 2.0, (2 * y + h) / 2.0))
        return joints

    def merge_close_lines(lines: list[float], tol: float) -> list[float]:
        if not lines:
            return []
        merged = [lines[0]]
        for val in lines[1:]:
            if abs(val - merged[-1]) <= tol:
                merged[-1] = (merged[-1] + val) / 2.0
            else:
                merged.append(val)
        return merged


# ---------------------------------------------------------------------------
# Image <-> PNG bytes conversion helpers
# ---------------------------------------------------------------------------

def pil_to_png_bytes(img: Image.Image) -> bytes:
    """Convert a PIL Image to PNG bytes (grayscale)."""
    gray = img.convert("L")
    buf = io.BytesIO()
    gray.save(buf, format="PNG")
    return buf.getvalue()


def png_bytes_to_array(png_bytes: bytes) -> np.ndarray:
    """Decode PNG bytes to numpy array."""
    img = Image.open(io.BytesIO(png_bytes))
    return np.array(img)


def array_to_png_bytes(arr: np.ndarray) -> bytes:
    """Encode a numpy array to grayscale PNG bytes."""
    img = Image.fromarray(arr.astype(np.uint8))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
