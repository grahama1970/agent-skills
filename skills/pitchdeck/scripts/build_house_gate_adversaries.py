"""#1380: matched adversarial style negatives for the house gate.

Each mutant preserves the nuisance variables the gate measures (words, colors,
object counts, rough areas) while breaking exactly one style dimension a real
looks-like-Graham classifier must catch. A mutant that PASSES the gate is a
documented false-pass — the hole, reproduced.

Inputs: a passing deck.pptx. Outputs: mutant .pptx files + cases.json.
Failure modes: an unreadable deck raises; every mutation is seeded (7) so
mutants are deterministic.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Pt

SEED = 7


def _content_shapes(slide):
    """Authored, movable content: skip inherited chrome, band boxes, footers."""
    out = []
    for shape in slide.shapes:
        name = shape.name or ""
        if name.startswith("chrome:"):
            continue
        try:
            if shape.top is None or shape.left is None:
                continue
            # keep the band title in place: it lives in the top strip
            if shape.top < 0.14 * 5143500:
                continue
        except (TypeError, AttributeError):
            continue
        out.append(shape)
    return out


def bbox_shuffle(deck_path: Path, out_path: Path) -> None:
    """Permute content positions. Pixel marginals barely move; layout dies."""
    rng = random.Random(SEED)
    pres = Presentation(str(deck_path))
    for slide in pres.slides:
        shapes = _content_shapes(slide)
        if len(shapes) < 2:
            continue
        spots = [(s.left, s.top) for s in shapes]
        rng.shuffle(spots)
        for shape, (left, top) in zip(shapes, spots):
            shape.left, shape.top = left, top
    pres.save(str(out_path))


def typography_swap(deck_path: Path, out_path: Path) -> None:
    """Same words and boxes; ransom-note type: mixed fonts/sizes, no hierarchy."""
    rng = random.Random(SEED)
    fonts = ["Comic Sans MS", "Courier New", "Impact", "Times New Roman"]
    pres = Presentation(str(deck_path))
    for slide in pres.slides:
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False) or not shape.has_text_frame:
                continue
            if (shape.name or "").startswith("chrome:"):
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    run.font.name = rng.choice(fonts)
                    if run.font.size is not None:
                        run.font.size = Pt(max(8, int(run.font.size.pt * rng.choice([0.55, 0.8, 1.5, 2.1]))))
                    run.font.underline = rng.random() < 0.3
                    run.font.bold = rng.random() < 0.5
    pres.save(str(out_path))


def two_tiny_visuals(deck_path: Path, out_path: Path) -> None:
    """Strip every real visual, satisfy density with two meaningless 20px groups."""
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from pptx.util import Emu

    pres = Presentation(str(deck_path))
    for slide in pres.slides:
        doomed = [s for s in slide.shapes
                  if s.shape_type in (MSO_SHAPE_TYPE.PICTURE, MSO_SHAPE_TYPE.GROUP)
                  and not (s.name or "").startswith("chrome:")]
        for shape in doomed:
            shape._element.getparent().remove(shape._element)
        for i in (0, 1):
            group = slide.shapes.add_group_shape()
            group.left, group.top = Emu(457200 + i * 300000), Emu(4000000)
            group.width, group.height = Emu(190500), Emu(190500)  # ~20px each
    pres.save(str(out_path))


def layout_mirror(deck_path: Path, out_path: Path) -> None:
    """Mirror every content shape horizontally. Ink, palette, words, and object
    counts are EXACTLY preserved (no overlap is introduced), but every
    composition rule — chevrons left, art placement, mark positions, reading
    order — is broken. A spatially blind gate cannot see this."""
    pres = Presentation(str(deck_path))
    width = pres.slide_width
    for slide in pres.slides:
        for shape in _content_shapes(slide):
            shape.left = width - shape.left - shape.width
    pres.save(str(out_path))


MUTANTS = {"bbox-shuffle": bbox_shuffle, "typography-swap": typography_swap,
           "two-tiny-visuals": two_tiny_visuals, "layout-mirror": layout_mirror}


def main() -> None:
    source = Path(sys.argv[sys.argv.index("--source-pptx") + 1])
    out_dir = Path(sys.argv[sys.argv.index("--output-dir") + 1])
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = []
    for name, fn in MUTANTS.items():
        target = out_dir / f"{name}.pptx"
        fn(source, target)
        cases.append({"mutant": name, "pptx": str(target),
                      "breaks": {"bbox-shuffle": "layout/composition",
                                 "typography-swap": "typography/hierarchy",
                                 "two-tiny-visuals": "visual substance",
                                 "layout-mirror": "composition/reading order"}[name],
                      "expected_from_real_classifier": "FAIL"})
    (out_dir / "cases.json").write_text(json.dumps({"source": str(source), "seed": SEED,
                                                     "cases": cases}, indent=1))
    print(json.dumps({"built": [c["mutant"] for c in cases], "out_dir": str(out_dir)}))


if __name__ == "__main__":
    main()
