#!/usr/bin/env python3
"""Verify the constellation legend has one marker source.

The legend labels already include explicit glyphs (▲, ◆, ●). CSS must not add a
second marker with .cl::before.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "components" / "capability-constellation.tsx"
CSS = ROOT / "app" / "globals.css"


def main() -> int:
    component = COMPONENT.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    errors: list[str] = []

    for label in ("▲ technical", "◆ hybrid", "● creative"):
        if label not in component:
            errors.append(f"missing explicit legend glyph label: {label}")

    if re.search(r"\.cl(?:--[a-z-]+)?::before", css):
        errors.append("legend uses .cl::before generated markers; explicit glyph labels would render double markers")

    if errors:
        print("CONSTELLATION_LEGEND_FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("CONSTELLATION_LEGEND_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
