#!/usr/bin/env python3
"""Verify grahama.co's display type direction avoids known template residue."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "globals.css"
LAYOUT = ROOT / "app" / "layout.tsx"
FONTS = ROOT / "public" / "fonts"

css = CSS.read_text(encoding="utf-8")
layout = LAYOUT.read_text(encoding="utf-8")

failures: list[str] = []

if "'Fraunces'" in css or "fraunces-" in css.lower() or "Fraunces" in layout:
    failures.append("Fraunces remains referenced in CSS/layout")

if "font-family: 'Literata'" not in css:
    failures.append("Literata @font-face is missing")

if "--serif: 'Literata'" not in css:
    failures.append("--serif does not point at Literata")

if "SOFT" in css or "WONK" in css:
    failures.append("Fraunces-specific variation axes remain in CSS")

for filename in ("literata-latin-var.woff2", "literata-latin-italic-var.woff2"):
    if not (FONTS / filename).is_file():
        failures.append(f"missing local display font asset: {filename}")

for filename in ("fraunces-var.woff2", "fraunces-italic-var.woff2"):
    if (FONTS / filename).exists():
        failures.append(f"unused overused display font asset remains: {filename}")

if "href=\"/fonts/literata-latin-var.woff2\"" not in layout:
    failures.append("layout preload does not target the Literata roman asset")

if failures:
    print(f"FAIL: {len(failures)} type-direction invariant(s) failed")
    for failure in failures:
        print(f"  {failure}")
    sys.exit(1)

print("OK: display type uses local Literata assets and no Fraunces-specific residue")
