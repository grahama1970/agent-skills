"""Pixel-level spacing audit from a rendered screenshot.

Inputs: a PNG of the rendered card and the artwork's canvas height (to scale
tolerance). Detects horizontal row bands by scanline luminance (panel strokes
are brighter than the ground), then asserts uniform inter-band gaps.
Failure mode: returns (ok, findings); raises only on unreadable images.
"""
from __future__ import annotations

from PIL import Image


def _luma_profile(im: Image.Image, x0: float, x1: float) -> list[float]:
    """Fraction of sampled pixels per scanline that are brighter than the
    ground: wide panel strokes score high, 2px connectors stay near zero."""
    g = im.convert("L")
    w, h = g.size
    a, b = int(w * x0), int(w * x1)
    px = g.load()
    samples = list(range(a, b, 3))
    all_vals = sorted(px[x, y] for y in range(0, h, 7) for x in samples)
    base = all_vals[len(all_vals) // 2]
    rows = []
    for y in range(h):
        vals = [px[x, y] for x in samples]
        rows.append(sum(1 for v in vals if v > base + 15) / len(vals))
    return rows


def detect_bands(im: Image.Image, x0: float = 0.55, x1: float = 0.97,
                 min_h: int = 8) -> list[tuple[int, int]]:
    prof = _luma_profile(im, x0, x1)
    thresh = 0.10
    bands: list[tuple[int, int]] = []
    start = None
    for y, v in enumerate(prof):
        if v >= thresh and start is None:
            start = y
        elif v < thresh and start is not None:
            if y - start >= min_h:
                bands.append((start, y))
            start = None
    if start is not None and len(prof) - start >= min_h:
        bands.append((start, len(prof)))
    merged: list[list[int]] = []
    for s, e in bands:
        if merged and s - merged[-1][1] <= min_h:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def audit_pixels(png_path: str, canvas_h: float = 1200.0, tol_svg: float = 4.0,
                 x0: float = 0.55, x1: float = 0.97) -> tuple[bool, list[str]]:
    im = Image.open(png_path)
    bands = detect_bands(im, x0, x1)
    out = [f"image={im.size[0]}x{im.size[1]} bands={len(bands)}"]
    if len(bands) < 3:
        return False, out + ["PIXELS_FAIL fewer than 3 row bands detected"]
    scale = im.size[1] / canvas_h
    tol = max(2.0, tol_svg * scale)
    centers = [(s + e) / 2 for s, e in bands]
    steps = [round(centers[i + 1] - centers[i], 1) for i in range(len(centers) - 1)]
    for i, (s, e) in enumerate(bands):
        out.append(f"band{i}: y={s}-{e} h={e - s} center={centers[i]:.1f}")
    out.append(f"band center steps(px): {steps} tol={tol:.1f}")
    if max(steps) - min(steps) > tol:
        out.append(f"PIXELS_FAIL uneven painted rhythm (spread {max(steps) - min(steps):.1f} > {tol:.1f})")
        return False, out
    return True, out
