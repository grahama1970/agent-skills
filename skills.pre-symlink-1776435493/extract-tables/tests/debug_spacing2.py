#!/usr/bin/env python3
"""Debug spacing: show all elements in specific cells."""
import os, sys
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "src"))

from python.pdf_bridge import _extract_with_pdf_oxide, _extract_with_pdfminer, extract_text_elements

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")

# 1. twotables_1.pdf - all elements in y range 75-100 (row with "xix. Acute")
print("=== twotables_1.pdf: row with xix.Acute (y0=75-100) ===")
pdf_path = os.path.join(FIXTURE_DIR, "twotables_1.pdf")
oxide = _extract_with_pdf_oxide(pdf_path, 0)
print("\npdf_oxide:")
for e in sorted(oxide, key=lambda e: (e.y0, e.x0)):
    if 75 < e.y0 < 100 and e.x0 > 200:
        print(f"  x0={e.x0:.1f} x1={e.x1:.1f} y0={e.y0:.1f} text={repr(e.text)}")
miner = _extract_with_pdfminer(pdf_path, 0)
print("\npdfminer:")
for e in sorted(miner, key=lambda e: (e.y0, e.x0)):
    if 75 < e.y0 < 100 and e.x0 > 200:
        print(f"  x0={e.x0:.1f} x1={e.x1:.1f} y0={e.y0:.1f} text={repr(e.text)}")

# 2. twotables_1.pdf - CONTENT diff cell: row 1 col 9 (large text block)
# Find elements in the rightmost column area (x > 500) around y=55-70
print("\n\n=== twotables_1.pdf: row1,col9 text block (x>490, y=50-80) ===")
print("\npdf_oxide:")
for e in sorted(oxide, key=lambda e: (e.y0, e.x0)):
    if 50 < e.y0 < 160 and e.x0 > 490:
        print(f"  x0={e.x0:.1f} x1={e.x1:.1f} y0={e.y0:.1f} text={repr(e.text)}")

print("\npdfminer:")
for e in sorted(miner, key=lambda e: (e.y0, e.x0)):
    if 50 < e.y0 < 160 and e.x0 > 490:
        print(f"  x0={e.x0:.1f} x1={e.x1:.1f} y0={e.y0:.1f} text={repr(e.text)}")

# 3. Check which backend "auto" mode uses for each problematic file
print("\n\n=== Backend selection ===")
for pdf_name in ["twotables_1.pdf", "row_span_1.pdf", "row_span_2.pdf", "foo.pdf", "health.pdf"]:
    pdf_path = os.path.join(FIXTURE_DIR, pdf_name)
    if not os.path.exists(pdf_path):
        continue
    oxide = _extract_with_pdf_oxide(pdf_path, 0)
    from python.pdf_bridge import _is_suspicious_positioning, _has_merged_spans, get_page_dimensions
    w, h = get_page_dimensions(pdf_path, 0)
    susp = _is_suspicious_positioning(oxide, w)
    merged = _has_merged_spans(oxide)
    auto = extract_text_elements(pdf_path, 0)
    print(f"  {pdf_name}: suspicious={susp}, merged={merged}, auto_count={len(auto)}, oxide_count={len(oxide)}")
    if len(auto) != len(oxide):
        print(f"    -> USING PDFMINER FALLBACK")

# 4. row_span_1.pdf "Source" line - all elements in that y-range
print("\n\n=== row_span_1.pdf: Source line elements ===")
pdf_path = os.path.join(FIXTURE_DIR, "row_span_1.pdf")
oxide = _extract_with_pdf_oxide(pdf_path, 0)
auto = extract_text_elements(pdf_path, 0)
# Find the "Source" element in auto
for e in auto:
    if "Source" in e.text:
        print(f"  auto: x0={e.x0:.1f} x1={e.x1:.1f} y0={e.y0:.1f} text={repr(e.text)}")
for e in oxide:
    if "Source" in e.text:
        print(f"  oxide: x0={e.x0:.1f} x1={e.x1:.1f} y0={e.y0:.1f} text={repr(e.text)}")

# 5. foo.pdf - all header elements (y0 < 100)
print("\n\n=== foo.pdf: all elements y0 < 100 ===")
pdf_path = os.path.join(FIXTURE_DIR, "foo.pdf")
auto = extract_text_elements(pdf_path, 0)
for e in sorted(auto, key=lambda e: (e.y0, e.x0)):
    if e.y0 < 100:
        print(f"  y0={e.y0:.1f} y1={e.y1:.1f} x0={e.x0:.1f} x1={e.x1:.1f} text={repr(e.text)}")

# 6. health.pdf "Others" area
print("\n\n=== health.pdf: Others area ===")
pdf_path = os.path.join(FIXTURE_DIR, "health.pdf")
auto = extract_text_elements(pdf_path, 0)
for e in sorted(auto, key=lambda e: (e.y0, e.x0)):
    if "Others" in e.text or ("(" in e.text and e.x0 > 450 and e.y0 < 90):
        print(f"  y0={e.y0:.1f} y1={e.y1:.1f} x0={e.x0:.1f} x1={e.x1:.1f} text={repr(e.text)}")
