"""Deck-level structural positive bar, leave-one-deck-out calibrated (#1382).

The per-slide gates are anomaly floors; this measures POSITIVE resemblance in
a text-invariant, spatially-aware feature space computable identically for
real corpus pages (their committed layout_signature records) and a generated
deck (the same extractor on the delivered pptx). Calibration is
leave-one-entire-deck-out: each real deck is scored against only the OTHER
decks' pages, and the bar is set so the worst held-out real deck still passes
— never tuned on the candidate deck.

Inputs: records dir + a delivered pptx. Outputs: per-slide nearest-real-page
structural distances, deck aggregates, and a typed verdict. Failure modes:
missing records raise; a deck whose pages cannot be featurized fails.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from .build_manifest import bytes_digest

GRID = 3  # 3x3 spatial occupancy — the channel the mirror mutant cannot fool


def _features(blocks: list[dict]) -> list[float]:
    """Slide feature vector: spatial occupancy per kind-agnostic cell, plus
    kind areas, counts, words. All normalized to [0,1]-ish ranges."""
    grid = [0.0] * (GRID * GRID)
    areas = {"text": 0.0, "picture": 0.0, "shape": 0.0}
    counts = {"text": 0, "picture": 0, "shape": 0}
    words = 0
    for b in blocks:
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        areas[b["kind"]] += w * h
        counts[b["kind"]] += 1
        words += b.get("words", 0)
        # distribute the block's area over the grid cells it covers
        for gy in range(GRID):
            for gx in range(GRID):
                cx0, cy0 = gx / GRID, gy / GRID
                overlap_w = max(0.0, min(x + w, cx0 + 1 / GRID) - max(x, cx0))
                overlap_h = max(0.0, min(y + h, cy0 + 1 / GRID) - max(y, cy0))
                grid[gy * GRID + gx] += overlap_w * overlap_h * GRID * GRID
    return ([min(g, 2.0) for g in grid]
            + [min(areas[k], 1.5) for k in ("text", "picture", "shape")]
            + [min(counts[k] / 10.0, 2.0) for k in ("text", "picture", "shape")]
            + [min(words / 120.0, 2.0)])


def _distance(a: list[float], b: list[float]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _load_corpus(records_dir: Path) -> list[tuple[str, list[float]]]:
    out = []
    for path in sorted(records_dir.glob("*.json")):
        rec = json.loads(path.read_text())
        out.append((rec["deck"], _features(rec["blocks"])))
    if not out:
        raise ValueError(f"no layout records under {records_dir}")
    return out


class DeckGateCalibration(BaseModel):
    schema_: str = Field(default="pitchdeck.deck_gate_calibration.v1", alias="schema")
    fold_medians: dict[str, float]
    fold_p90s: dict[str, float]
    median_bar: float
    p90_bar: float
    provenance: str

    def content_digest(self) -> str:
        return bytes_digest(self.model_dump_json(by_alias=True))


def calibrate(records_dir: Path) -> DeckGateCalibration:
    """Leave-one-deck-out: score each real deck against the other decks only."""
    import statistics

    corpus = _load_corpus(records_dir)
    decks = sorted({deck for deck, _ in corpus})
    fold_medians: dict[str, float] = {}
    fold_p90s: dict[str, float] = {}
    for held in decks:
        others = [f for deck, f in corpus if deck != held]
        mine = [f for deck, f in corpus if deck == held]
        dists = sorted(min(_distance(f, o) for o in others) for f in mine)
        fold_medians[held] = round(statistics.median(dists), 4)
        fold_p90s[held] = round(dists[int(0.9 * (len(dists) - 1))], 4)
    return DeckGateCalibration(
        fold_medians=fold_medians,
        fold_p90s=fold_p90s,
        median_bar=round(max(fold_medians.values()), 4),
        p90_bar=round(max(fold_p90s.values()), 4),
        provenance=("leave-one-entire-deck-out over the layout_signature records; the bar is the "
                     "WORST held-out real deck (every real deck passes by construction, none of the "
                     "candidate deck's data is in the calibration)"),
    )


def score_deck(pptx_path: Path, records_dir: Path) -> dict:
    """Median / p90 nearest-real-page structural distance for a delivered deck."""
    import statistics
    import tempfile

    from .layout_retrieval import extract_signatures

    with tempfile.TemporaryDirectory(prefix="pd-deckgate-") as tmp:
        link = Path(tmp) / pptx_path.name
        link.write_bytes(pptx_path.read_bytes())
        signatures = extract_signatures(Path(tmp))
    corpus = _load_corpus(records_dir)
    per_slide = []
    for sig in signatures:
        feats = _features([b.model_dump() for b in sig.blocks])
        best = min(_distance(feats, f) for _, f in corpus)
        per_slide.append(round(best, 4))
    ordered = sorted(per_slide)
    return {
        "per_slide": per_slide,
        "median": round(statistics.median(per_slide), 4) if per_slide else 9.9,
        "p90": ordered[int(0.9 * (len(ordered) - 1))] if ordered else 9.9,
        "slides": len(per_slide),
    }
