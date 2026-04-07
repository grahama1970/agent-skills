#!/usr/bin/env python3
"""Debug specific gap widths."""
import os, sys
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "src"))
from python.pdf_bridge import _extract_with_pdf_oxide

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")

# twotables_1.pdf: find "xx." and "Acute" near it
pdf_path = os.path.join(FIXTURE_DIR, "twotables_1.pdf")
oxide = _extract_with_pdf_oxide(pdf_path, 0)

print("=== twotables_1.pdf: all elements 140 < y0 < 200, x0 > 200, x0 < 300 ===")
for e in sorted(oxide, key=lambda e: (e.y0, e.x0)):
    if 140 < e.y0 < 200 and 200 < e.x0 < 300:
        print(f"  x0={e.x0:.1f} x1={e.x1:.1f} y0={e.y0:.1f} fs={e.font_size:.1f} text={repr(e.text)}")

# row_span_2.pdf: find "i." and "Food" near it
print("\n=== row_span_2.pdf: check 'i.' + 'Food' spans ===")
pdf_path = os.path.join(FIXTURE_DIR, "row_span_2.pdf")
oxide = _extract_with_pdf_oxide(pdf_path, 0)
for e in sorted(oxide, key=lambda e: (e.y0, e.x0)):
    if 200 < e.x0 < 310 and ('Food' in e.text or e.text.strip().startswith('i.') or e.text.strip().startswith('v.')):
        print(f"  x0={e.x0:.1f} x1={e.x1:.1f} y0={e.y0:.1f} fs={e.font_size:.1f} text={repr(e.text)}")

# What gap threshold to use? Print all span-to-span gaps for justified first lines
print("\n=== twotables_1.pdf: word-span gaps in first line (y0~53) ===")
pdf_path = os.path.join(FIXTURE_DIR, "twotables_1.pdf")
oxide = _extract_with_pdf_oxide(pdf_path, 0)
line_elems = sorted(
    [e for e in oxide if abs(e.y0 - 53.1) < 1.0 and e.x0 > 540],
    key=lambda e: e.x0
)
for i in range(len(line_elems) - 1):
    gap = line_elems[i+1].x0 - line_elems[i].x1
    sw = line_elems[i].font_size * 0.25
    ratio = gap / sw if sw > 0 else 0
    print(f"  {repr(line_elems[i].text)} -> {repr(line_elems[i+1].text)}: gap={gap:.1f} sw={sw:.2f} ratio={ratio:.2f}")

# Now check "reported" and "from" which should also have wide gap
print("\n=== Non-word-split lines: check if 'vomiting' and 'reported' have \n in camelot ===")
# Actually check: is 'reported' a separate span at same y?
for e in sorted(oxide, key=lambda e: (e.y0, e.x0)):
    if abs(e.y0 - 53.1) < 1.0 and e.x0 > 700:
        print(f"  x0={e.x0:.1f} x1={e.x1:.1f} y0={e.y0:.1f} text={repr(e.text)}")

# Check if "Source:   Data Warehouse" is being split
print("\n=== row_span_1.pdf: Source element and col boundaries ===")
pdf_path = os.path.join(FIXTURE_DIR, "row_span_1.pdf")
from python.extract_tables import read_pdf
result = list(read_pdf(pdf_path, pages="1", flavor="lattice"))
if result:
    t = result[0]
    print(f"  Table shape: {len(t._data)}x{len(t._data[0]) if t._data else 0}")
    # Find Source cell
    for ri, row in enumerate(t._data):
        for ci, cell in enumerate(row):
            if 'Source' in cell:
                print(f"  Cell [{ri},{ci}]: {repr(cell)}")
