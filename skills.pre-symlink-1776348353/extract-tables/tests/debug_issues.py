#!/usr/bin/env python3
"""Debug specific parity issues."""
import os, sys
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "src"))
from python.pdf_bridge import _extract_with_pdf_oxide

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")

# 1. health.pdf: "Others" and "(1)" - what's the gap?
print("=== health.pdf: Others and (1) spans ===")
pdf_path = os.path.join(FIXTURE_DIR, "health.pdf")
oxide = _extract_with_pdf_oxide(pdf_path, 0)
for e in sorted(oxide, key=lambda e: (e.y0, e.x0)):
    if "Others" in e.text or (e.text.strip().startswith("(") and e.y0 < 90):
        print(f"  x0={e.x0:.2f} x1={e.x1:.2f} y0={e.y0:.2f} fs={e.font_size:.2f} text={repr(e.text)}")

# 2. foo.pdf: header row elements - check y values for line break detection
print("\n=== foo.pdf: header elements (first 80pt y) ===")
pdf_path = os.path.join(FIXTURE_DIR, "foo.pdf")
oxide = _extract_with_pdf_oxide(pdf_path, 0)
for e in sorted(oxide, key=lambda e: (e.y0, e.x0)):
    if e.y0 < 80:
        sw = e.font_size * 0.25
        print(f"  x0={e.x0:.2f} x1={e.x1:.2f} y0={e.y0:.2f} y1={e.y1:.2f} fs={e.font_size:.2f} text={repr(e.text)}")

# 3. twotables_1.pdf: "xx." and "Acute" spans
print("\n=== twotables_1.pdf: 'xx.' area spans ===")
pdf_path = os.path.join(FIXTURE_DIR, "twotables_1.pdf")
oxide = _extract_with_pdf_oxide(pdf_path, 0)
for e in sorted(oxide, key=lambda e: (e.y0, e.x0)):
    if 75 < e.y0 < 100 and 200 < e.x0 < 400:
        print(f"  x0={e.x0:.2f} x1={e.x1:.2f} y0={e.y0:.2f} fs={e.font_size:.2f} text={repr(e.text)}")

# 4. row_span_2.pdf: line breaks in justified text - check y values
print("\n=== row_span_2.pdf: cell [1,9] area spans (first block) ===")
pdf_path = os.path.join(FIXTURE_DIR, "row_span_2.pdf")
oxide = _extract_with_pdf_oxide(pdf_path, 0)
# Find spans in rightmost column, first few rows
rightmost = sorted([e for e in oxide if e.x0 > 450 and 30 < e.y0 < 120], key=lambda e: (e.y0, e.x0))
for e in rightmost[:30]:
    print(f"  x0={e.x0:.2f} x1={e.x1:.2f} y0={e.y0:.2f} y1={e.y1:.2f} fs={e.font_size:.2f} text={repr(e.text)}")

# 5. foo.pdf: "Percent Fuel Savings" header area
print("\n=== foo.pdf: 'Percent Fuel' / 'Fuel Savings' area ===")
pdf_path = os.path.join(FIXTURE_DIR, "foo.pdf")
oxide = _extract_with_pdf_oxide(pdf_path, 0)
for e in sorted(oxide, key=lambda e: (e.y0, e.x0)):
    if e.y0 < 80 and e.x0 > 200:
        print(f"  x0={e.x0:.2f} x1={e.x1:.2f} y0={e.y0:.2f} y1={e.y1:.2f} fs={e.font_size:.2f} text={repr(e.text)}")
