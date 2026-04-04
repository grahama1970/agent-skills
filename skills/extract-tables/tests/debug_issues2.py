#!/usr/bin/env python3
"""Debug foo.pdf and health.pdf extraction paths."""
import os, sys
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "src"))
from python.pdf_bridge import _extract_with_pdf_oxide
from python.extract_tables import read_pdf

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")

# 1. foo.pdf: extract and show all header cells
print("=== foo.pdf: extraction result ===")
pdf_path = os.path.join(FIXTURE_DIR, "foo.pdf")
tables = list(read_pdf(pdf_path, pages="1", flavor="lattice"))
if tables:
    t = tables[0]
    print(f"  Shape: {len(t._data)}x{len(t._data[0]) if t._data else 0}")
    for ci in range(min(5, len(t._data[0]) if t._data else 0)):
        print(f"  [0,{ci}]: {repr(t._data[0][ci])}")
    # Show all elements in table header y-range
    oxide = _extract_with_pdf_oxide(pdf_path, 0)
    print("\n  All elements y0 < 200:")
    for e in sorted(oxide, key=lambda e: (e.y0, e.x0)):
        if e.y0 < 200 and e.y0 > 80:
            print(f"    x0={e.x0:.1f} x1={e.x1:.1f} y0={e.y0:.1f} y1={e.y1:.1f} fs={e.font_size:.1f} text={repr(e.text)}")

# 2. health.pdf: check what parser is used and show cell details
print("\n=== health.pdf: extraction result ===")
pdf_path = os.path.join(FIXTURE_DIR, "health.pdf")
tables = list(read_pdf(pdf_path, pages="1", flavor="stream"))
if tables:
    t = tables[0]
    print(f"  Shape: {len(t._data)}x{len(t._data[0]) if t._data else 0}")
    # Show row 0 cells
    for ci in range(len(t._data[0]) if t._data else 0):
        val = t._data[0][ci]
        if val:
            print(f"  [0,{ci}]: {repr(val)}")

# 3. foo.pdf: check if elements get trailing space before \n
# Simulate what happens during text assignment
print("\n=== foo.pdf: simulate text assignment for header cells ===")
oxide = _extract_with_pdf_oxide(os.path.join(FIXTURE_DIR, "foo.pdf"), 0)
# Find header elements - between table top and first data row
header_elems = sorted([e for e in oxide if 88 < e.y0 < 130], key=lambda e: (e.y0, e.x0))
print(f"  Header elements ({len(header_elems)}):")
for e in header_elems:
    print(f"    x0={e.x0:.1f} x1={e.x1:.1f} y0={e.y0:.1f} y1={e.y1:.1f} fs={e.font_size:.1f} text={repr(e.text)}")
