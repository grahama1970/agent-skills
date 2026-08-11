"""Text-invariant visual-style metrics for the house gate.

The multimodal embedding used by house-similarity is dominated by the TEXT it
reads in a render (measured 2026-08-11: two real pages sharing only their words
score 0.952; a generated page against its visual archetype twin with different
words scores 0.25), so it detects content duplication, not style. These metrics
measure what the embedder cannot: how much of the canvas carries ink and how
much of that ink sits in the house palette — both invariant to the words.

Inputs: a rendered slide PNG. Outputs: ink_fraction (share of non-background
pixels) and house_hue_fraction (share of ink pixels whose hue falls in the
petrol/teal band or is a warm gold accent). Failure modes: an unreadable image
raises — a page that cannot be measured is never certified.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class StyleMetrics(BaseModel):
    ink_fraction: float
    house_hue_fraction: float


def measure(image_path: Path) -> StyleMetrics:
    from PIL import Image

    img = Image.open(image_path).convert("RGB").resize((320, 180))
    pixels = list(img.getdata())
    ink = 0
    house = 0
    for r, g, b in pixels:
        mx, mn = max(r, g, b), min(r, g, b)
        # background = near-white / very light gray
        if mn > 235 and mx - mn < 12:
            continue
        ink += 1
        # petrol/teal band: blue-green dominance (house #076889/#1D7694/#26558E)
        if b >= r and g >= r * 0.8 and mx > 40:
            house += 1
        # warm gold accent (#D6A300)
        elif r > 150 and g > 100 and b < 110:
            house += 1
    total = len(pixels)
    return StyleMetrics(
        ink_fraction=round(ink / total, 4),
        house_hue_fraction=round(house / max(ink, 1), 4),
    )
