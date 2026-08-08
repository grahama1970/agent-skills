"""Generate static Fraunces instances used by the resume PDF.

The resume PDF renders through PyMuPDF, which embeds static TrueType faces but
cannot read the variable WOFF2 the site ships. This script instances the site's
own ``site/public/fonts/fraunces-var.woff2`` at fixed axis values and writes
plain TTFs into ``docs/resume/fonts/``, so the PDF display face is derived from
the same file grahama.co serves rather than an unrelated lookalike.

Regenerate after changing the site font:

    uv run --with fonttools --with brotli python scripts/build_resume_fonts.py
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "site" / "public" / "fonts" / "fraunces-var.woff2"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "resume" / "fonts"


@dataclass(frozen=True, slots=True)
class Instance:
    """One static instance to cut from the variable source."""

    filename: str
    family: str
    subfamily: str
    axes: dict[str, float]


# opsz follows the intended rendered size: the name is display-sized, section
# headings are small. WONK=1 keeps the site's canted/quirky letterforms.
INSTANCES: tuple[Instance, ...] = (
    Instance(
        "Fraunces-Display.ttf",
        "Fraunces Display",
        "Regular",
        {"wght": 600.0, "opsz": 144.0, "SOFT": 0.0, "WONK": 1.0},
    ),
    Instance(
        "Fraunces-Heading.ttf",
        "Fraunces Heading",
        "Regular",
        {"wght": 600.0, "opsz": 24.0, "SOFT": 0.0, "WONK": 1.0},
    ),
)


def build_instance(source: Path, output_dir: Path, spec: Instance) -> Path:
    """Cut one static TTF and give it an unambiguous name record."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    font = TTFont(source)
    font.flavor = None  # emit TTF, not WOFF2
    instancer.instantiateVariableFont(font, spec.axes, inplace=True, updateFontNames=False)

    # The instancer keeps the variable font's name records, which would leave a
    # wght=600 cut advertising itself as "Black". Restate the names so the PDF
    # font list matches what was actually embedded.
    ps_name = f"{spec.family}-{spec.subfamily}".replace(" ", "")
    name_table = font["name"]
    for name_id, value in (
        (1, spec.family),
        (2, spec.subfamily),
        (3, f"{ps_name};resume"),
        (4, f"{spec.family} {spec.subfamily}"),
        (6, ps_name),
    ):
        name_table.setName(value, name_id, 3, 1, 0x409)
        name_table.setName(value, name_id, 1, 0, 0)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / spec.filename
    font.save(out_path)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if not args.source.is_file():
        print(f"error: font source does not exist: {args.source}", file=sys.stderr)
        return 1
    try:
        for spec in INSTANCES:
            path = build_instance(args.source, args.output_dir, spec)
            print(f"{path} ({path.stat().st_size} bytes)")
    except Exception as exc:  # fonttools raises a wide range of parse errors
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
