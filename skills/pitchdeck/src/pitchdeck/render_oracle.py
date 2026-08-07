"""Rendered-output oracle (#1262): slides measured against the corpus envelope.

Theme-only mimicry is the named false-green: petrol band + Calibri can make a
generic deck look right. This oracle measures RENDERED PIXELS — whitespace
ratio, petrol-family presence, header-band height, ink coverage — and gates
each slide against a p10–p90 envelope measured from the committed exemplar
corpus (positives only; anti-exemplars excluded). Banner-free recipes
(cover/statement) are a NAMED exemption class, not a silent skip. Exit 1
with typed ORACLE_* findings when a slide leaves the envelope.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

PETROL = (0x06, 0x5E, 0x7C)


def _metrics(image_path: Path) -> dict:
    img = Image.open(image_path).convert("RGB")
    img = img.resize((320, 180))
    pixels = list(img.getdata())
    total = len(pixels)
    white = sum(1 for r, g, b in pixels if r > 235 and g > 235 and b > 235)
    petrol = sum(1 for r, g, b in pixels if abs(r - PETROL[0]) < 60 and abs(g - PETROL[1]) < 55 and abs(b - PETROL[2]) < 55 and b > r)
    ink = sum(1 for r, g, b in pixels if r < 100 and g < 100 and b < 100)
    # band height: fraction of top rows where petrol-family dominates
    width, height = img.size
    band_rows = 0
    misses = 0
    for y in range(height // 3):
        row = [img.getpixel((x, y)) for x in range(0, width, 4)]
        hits = sum(1 for r, g, b in row if abs(r - PETROL[0]) < 70 and abs(g - PETROL[1]) < 65 and abs(b - PETROL[2]) < 65 and b > r)
        if hits / len(row) > 0.30:
            band_rows = y + 1  # last qualifying row from the top
            misses = 0
        else:
            # white title glyphs can dominate a few rows INSIDE the band —
            # only three consecutive non-band rows end it (slide-4 debug,
            # 2026-08-07: rows 7–9 dipped to 24/80 and truncated the count).
            misses += 1
            if misses >= 3 or band_rows == 0:
                break
    return {
        "white_ratio": round(white / total, 3),
        "petrol_ratio": round(petrol / total, 4),
        "ink_ratio": round(ink / total, 4),
        "band_height_frac": round(band_rows / height, 3),
    }


def measure_corpus(exemplar_dir: Path, manifest: Path) -> dict:
    """p10–p90 envelope from POSITIVE exemplars only."""
    entries = json.loads(manifest.read_text(encoding="utf-8"))["exemplars"]
    positives = [e for e in entries if e["kind"] == "exemplar"]
    rows = [_metrics(exemplar_dir / Path(e["image"]).name) for e in positives]
    envelope = {}
    for key in rows[0]:
        values = sorted(r[key] for r in rows)
        lo = values[max(0, int(len(values) * 0.10))]
        hi = values[min(len(values) - 1, int(len(values) * 0.90))]
        envelope[key] = [lo, hi]
    return {"schema": "pitchdeck.render_envelope.v1", "samples": len(rows), "envelope": envelope}


def check_slides(slide_pngs: list[Path], envelope: dict, *, banner_free: set[int] = frozenset()) -> list[dict]:
    findings = []
    bounds = envelope["envelope"]
    for index, png in enumerate(slide_pngs, start=1):
        m = _metrics(png)
        exempt_band = index in banner_free
        for key, value in m.items():
            lo, hi = bounds[key]
            slack = (hi - lo) * 0.5 + 0.02  # envelope tolerance
            if key == "band_height_frac" and exempt_band:
                continue  # named exemption: hero recipes are banner-free
            if value < lo - slack or value > hi + slack:
                findings.append({
                    "code": f"ORACLE_{key.upper()}",
                    "slide": index,
                    "value": value,
                    "envelope": [round(lo - slack, 3), round(hi + slack, 3)],
                })
    return findings
