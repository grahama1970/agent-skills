"""Pixel-level spacing audit from a rendered screenshot.

Inputs: a PNG of the rendered card, the artwork's canvas height (to scale
tolerance), and optionally the card's grid manifest. Detects horizontal ink
bands by scanline luminance and asserts they land on the manifest's row spans
(bijection band<->row). Without a manifest the audit is descriptive only.
Failure mode: returns (ok, findings); raises only on unreadable images.
"""
from __future__ import annotations

import json

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
                 x0: float = 0.55, x1: float = 0.97,
                 manifest_path: str | None = None) -> tuple[bool, list[str]]:
    im = Image.open(png_path)
    bands = detect_bands(im, x0, x1)
    out = [f"image={im.size[0]}x{im.size[1]} bands={len(bands)}"]
    if len(bands) < 3:
        return False, out + ["PIXELS_FAIL fewer than 3 row bands detected"]
    scale = im.size[1] / canvas_h
    tol = max(2.0, tol_svg * scale)
    centers = [(s + e) / 2 for s, e in bands]
    gaps = [bands[i + 1][0] - bands[i][1] for i in range(len(bands) - 1)]
    for i, (s, e) in enumerate(bands):
        out.append(f"band{i}: y={s}-{e} h={e - s} center={centers[i]:.1f}")
    out.append(f"band gaps(px): {gaps} tol={tol:.1f}")
    if manifest_path is None:
        return True, out + ["PIXELS_OK (descriptive only — no manifest provided)"]
    # Grid law at pixel level: ink bands are label lines INSIDE panels, so the
    # invariant is bijection with the manifest rows (one band per row span),
    # not band-gap uniformity — rows differ in height by design.
    man = json.load(open(manifest_path))
    rows = sorted(man["rows"], key=lambda r: r["y"])
    if len(rows) != len(bands):
        return False, out + [f"PIXELS_FAIL {len(bands)} painted bands vs {len(rows)} manifest rows"]
    ok = True
    for i, (r, c) in enumerate(zip(rows, centers)):
        top, bottom = float(r["y"]), float(r["y"]) + float(r["h"])
        inside = (top - tol) <= c <= (bottom + tol)
        out.append(f"row{i} [{r['name']}]: manifest {top:.0f}-{bottom:.0f} band-center {c:.1f} {'OK' if inside else 'OUTSIDE'}")
        if not inside:
            ok = False
    if not ok:
        out.append("PIXELS_FAIL painted bands off the manifest grid")
        return False, out
    return True, out
