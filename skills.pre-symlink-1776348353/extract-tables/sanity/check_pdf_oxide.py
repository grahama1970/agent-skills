#!/usr/bin/env python3
"""Sanity: pdf_oxide text extraction + rendering."""
import sys
import os
# Prevent this script's directory from shadowing the real pdf_oxide module
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir in sys.path:
    sys.path.remove(script_dir)
try:
    import pdf_oxide
except ImportError:
    print("FAIL: pdf_oxide not installed")
    sys.exit(1)

doc = pdf_oxide.PdfDocument("/home/graham/workspace/experiments/camelot/tests/files/foo.pdf")

# page_count is a METHOD
pc = doc.page_count()
assert pc > 0, f"page_count() returned {pc}"

# extract_spans
spans = doc.extract_spans(0)
assert len(spans) > 0, "No spans extracted"
assert len(spans[0].bbox) == 4, f"bbox has {len(spans[0].bbox)} elements, expected 4"

# Verify bottom-left origin: top-of-page text should have high y value
# On a standard letter page (792pt), top text y should be ~700+
top_span = max(spans, key=lambda s: s.bbox[1])
assert top_span.bbox[1] > 600, f"Top span y={top_span.bbox[1]}, expected >600 for bottom-left origin"

# render_page
img_bytes = doc.render_page(0, dpi=150)
assert len(img_bytes) > 100, f"render_page returned only {len(img_bytes)} bytes"

print(f"PASS: pdf_oxide -- {pc} pages, {len(spans)} spans, {len(img_bytes)} bytes rendered")
sys.exit(0)
