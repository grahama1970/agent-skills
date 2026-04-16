#!/usr/bin/env python3
"""Debug spacing differences between pdf_oxide and pdfminer."""
import os, sys
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "src"))

from python.pdf_bridge import extract_text_elements, _extract_with_pdfminer, _extract_with_pdf_oxide

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")

def compare_elements(pdf_name, search_text, page=0):
    pdf_path = os.path.join(FIXTURE_DIR, pdf_name)
    if not os.path.exists(pdf_path):
        # Try camelot test files
        pdf_path = os.path.expanduser(f"~/workspace/experiments/camelot/tests/files/{pdf_name}")

    print(f"\n=== {pdf_name}: searching for '{search_text}' ===")

    oxide_elems = _extract_with_pdf_oxide(pdf_path, page)
    miner_elems = _extract_with_pdfminer(pdf_path, page)

    print(f"\npdf_oxide ({len(oxide_elems)} elements):")
    for e in sorted(oxide_elems, key=lambda e: (e.y0, e.x0)):
        if search_text.lower() in e.text.lower():
            print(f"  y0={e.y0:.1f} y1={e.y1:.1f} x0={e.x0:.1f} x1={e.x1:.1f} fs={e.font_size:.1f} text={repr(e.text)}")

    print(f"\npdfminer ({len(miner_elems)} elements):")
    for e in sorted(miner_elems, key=lambda e: (e.y0, e.x0)):
        if search_text.lower() in e.text.lower():
            print(f"  y0={e.y0:.1f} y1={e.y1:.1f} x0={e.x0:.1f} x1={e.x1:.1f} fs={e.font_size:.1f} text={repr(e.text)}")

# foo.pdf header elements
print("\n" + "="*60)
print("FOO.PDF - Header row elements (first 50pt)")
print("="*60)
pdf_path = os.path.join(FIXTURE_DIR, "foo.pdf")
oxide_elems = _extract_with_pdf_oxide(pdf_path, 0)
miner_elems = _extract_with_pdfminer(pdf_path, 0)

print("\npdf_oxide header elements:")
for e in sorted(oxide_elems, key=lambda e: (e.y0, e.x0)):
    if e.y0 < 60:
        print(f"  y0={e.y0:.1f} y1={e.y1:.1f} x0={e.x0:.1f} x1={e.x1:.1f} fs={e.font_size:.1f} text={repr(e.text)}")

print("\npdfminer header elements:")
for e in sorted(miner_elems, key=lambda e: (e.y0, e.x0)):
    if e.y0 < 60:
        print(f"  y0={e.y0:.1f} y1={e.y1:.1f} x0={e.x0:.1f} x1={e.x1:.1f} fs={e.font_size:.1f} text={repr(e.text)}")

# Double-space issue
compare_elements("twotables_1.pdf", "xix")
compare_elements("twotables_1.pdf", "Cases  of")  # pdfminer double space
compare_elements("row_span_1.pdf", "Source")

# health.pdf Others issue
compare_elements("health.pdf", "Others")
