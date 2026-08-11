"""Text-invariant visual-style metrics for the house gate.

The multimodal embedding used by house-similarity is a retrieval model
(jina-embeddings-v5-omni-small-retrieval) and is dominated by the TEXT it reads
in a render (measured 2026-08-11: two real pages sharing only their words score
0.952; a generated page against its visual archetype twin with different words
scores 0.25), so it detects content duplication, not style. These metrics
measure what that channel cannot, without hand-invented rules: the corpus's own
pixels define the house palette (a mean color histogram over all 233 real
pages), and a slide is scored by similarity to that empirical distribution.

Inputs: a rendered slide PNG (plus, for calibration, the corpus pages).
Outputs: ink_fraction (share of non-background pixels — a plain measurement)
and palette_similarity (Bhattacharyya coefficient between the slide's color
histogram and the corpus mean histogram). Failure modes: an unreadable image
raises — a page that cannot be measured is never certified; a missing corpus
histogram raises rather than silently passing.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from pydantic import BaseModel

CALIBRATION_PATH = Path(
    "/mnt/storage12tb/skills/pitchdeck/outputs/house-slides/self-similarity-calibration.json"
)
_BINS = 6  # 6x6x6 RGB histogram — coarse enough to be style, not content


class StyleMetrics(BaseModel):
    ink_fraction: float
    palette_similarity: float


def _histogram(image_path: Path) -> tuple[list[float], float]:
    """Normalized color histogram over INK pixels, plus the ink fraction.

    Background (near-white) pixels are excluded so a sparse and a dense page
    with the same palette histogram compare as the same style."""
    from PIL import Image

    img = Image.open(image_path).convert("RGB").resize((320, 180))
    pixels = list(img.getdata())
    hist = [0.0] * (_BINS**3)
    ink = 0
    for r, g, b in pixels:
        if min(r, g, b) > 235 and max(r, g, b) - min(r, g, b) < 12:
            continue
        ink += 1
        idx = (r * _BINS // 256) * _BINS * _BINS + (g * _BINS // 256) * _BINS + (b * _BINS // 256)
        hist[idx] += 1.0
    total = sum(hist) or 1.0
    return [h / total for h in hist], ink / len(pixels)


def corpus_mean_histogram(pages_dir: Path) -> list[float]:
    """The empirical house palette: mean ink-pixel histogram over all real pages."""
    pages = sorted(pages_dir.glob("*.png"))
    if not pages:
        raise ValueError(f"no corpus pages found under {pages_dir}")
    acc = [0.0] * (_BINS**3)
    for page in pages:
        hist, _ = _histogram(page)
        acc = [a + h for a, h in zip(acc, hist)]
    return [a / len(pages) for a in acc]


def _load_corpus_histogram() -> list[float]:
    data = json.loads(CALIBRATION_PATH.read_text())
    hist = data.get("corpus_palette_histogram")
    if not hist:
        raise ValueError(
            f"corpus_palette_histogram missing from {CALIBRATION_PATH}; "
            "run corpus_mean_histogram over the house pages and store it"
        )
    return hist


def measure(image_path: Path, corpus_hist: list[float] | None = None) -> StyleMetrics:
    hist, ink = _histogram(Path(image_path))
    reference = corpus_hist if corpus_hist is not None else _load_corpus_histogram()
    # Bhattacharyya coefficient: 1.0 = identical distributions
    similarity = sum(math.sqrt(h * r) for h, r in zip(hist, reference))
    return StyleMetrics(ink_fraction=round(ink, 4), palette_similarity=round(similarity, 4))
