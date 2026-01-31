# Debug-PDF Pattern Detection Enhancement Tasks

## Overview
Implement missing pattern detection for debug-pdf skill based on /dogpile research.
Currently 9/17 patterns detected, target: 14/17 (network patterns remain undetectable locally).

## Prerequisites
- [x] GPT-5 security review applied
- [x] Sanity check passes (11/11)

## Questions/Blockers
None - all clarified via user input.

---

## Task 1: Add PyMuPDF Layout dependency and header/footer detection
- [ ] Complete
- Agent: claude
- Priority: 1
- Dependencies: none

### Description
Add PyMuPDF4LLM Layout extension for ML-based header/footer detection.

### Implementation
1. Update `pyproject.toml` to add `pymupdf4llm` dependency
2. Add import handling: `import pymupdf.layout` before `import pymupdf4llm`
3. Create `detect_header_footer_bleed()` function using Layout API
4. Add pattern detection in `analyze_pdf()` for `header_footer_bleed`

### Code Pattern
```python
def detect_header_footer_bleed(page) -> list[tuple[str, str]]:
    """Detect header/footer content bleeding into body text."""
    try:
        import pymupdf.layout
        import pymupdf4llm
        # Compare extraction with/without header/footer
        with_hf = pymupdf4llm.to_markdown(page.parent, pages=[page.number])
        without_hf = pymupdf4llm.to_markdown(page.parent, pages=[page.number], header=False, footer=False)
        if len(with_hf) > len(without_hf) * 1.1:  # >10% difference
            return [("header_footer_bleed", "Detected via PyMuPDF Layout")]
    except ImportError:
        pass
    return []
```

### Definition of Done
- `test_debug_pdf.py::test_header_footer_detection` passes
- Pattern `header_footer_bleed` detected on test fixture with headers/footers

---

## Task 2: Add multi-column layout detection using column_boxes
- [ ] Complete
- Agent: claude
- Priority: 1
- Dependencies: none

### Description
Implement multi-column detection using PyMuPDF's column_boxes utility pattern.

### Implementation
1. Create `detect_multi_column()` function
2. Use text block bounding boxes to identify column structures
3. Detect when page has 2+ distinct vertical text regions
4. Add to `analyze_pdf()` pattern detection

### Code Pattern
```python
def detect_multi_column(page) -> list[tuple[str, str]]:
    """Detect multi-column layouts using text block analysis."""
    blocks = page.get_text("dict")["blocks"]
    text_blocks = [b for b in blocks if b.get("type") == 0]

    if len(text_blocks) < 4:
        return []

    # Get x-coordinates of block centers
    x_centers = [(b["bbox"][0] + b["bbox"][2]) / 2 for b in text_blocks]

    # Check for bimodal distribution (2 columns)
    x_centers.sort()
    page_width = page.rect.width
    mid = page_width / 2

    left_count = sum(1 for x in x_centers if x < mid * 0.8)
    right_count = sum(1 for x in x_centers if x > mid * 1.2)

    if left_count >= 3 and right_count >= 3:
        return [("multi_column", f"Detected {left_count} left, {right_count} right blocks")]

    return []
```

### Definition of Done
- `test_debug_pdf.py::test_multi_column_detection` passes
- Pattern `multi_column` detected on 2-column PDF fixture

---

## Task 3: Add split table detection (flag only, no merging)
- [ ] Complete
- Agent: claude
- Priority: 2
- Dependencies: none

### Description
Detect tables that likely span multiple pages. Flag for extractor to handle merging.

### Implementation
1. Create `detect_split_tables()` function
2. Check if page ends with partial table (table at bottom edge)
3. Check if next page starts with table (table at top edge)
4. Flag pattern without attempting merge

### Code Pattern
```python
def detect_split_tables(doc, page_num: int) -> list[tuple[str, str]]:
    """Detect tables that may span across pages."""
    page = doc[page_num]
    tables = page.find_tables()

    if not tables:
        return []

    page_height = page.rect.height
    results = []

    for table in tables:
        bbox = table.bbox
        # Table extends to bottom 5% of page
        if bbox[3] > page_height * 0.95:
            # Check if next page starts with a table
            if page_num + 1 < len(doc):
                next_page = doc[page_num + 1]
                next_tables = next_page.find_tables()
                for nt in next_tables:
                    # Table starts in top 10% of next page
                    if nt.bbox[1] < page_height * 0.10:
                        results.append(("split_tables",
                            f"Table spans pages {page_num+1}-{page_num+2}"))
                        break

    return results
```

### Definition of Done
- `test_debug_pdf.py::test_split_table_detection` passes
- Pattern `split_tables` detected on multi-page table fixture

---

## Task 4: Add footnote detection heuristics
- [ ] Complete
- Agent: claude
- Priority: 2
- Dependencies: none

### Description
Detect inline footnotes using position and font-size heuristics.

### Implementation
1. Create `detect_footnotes()` function
2. Look for superscript numbers in body text
3. Look for small-font text in bottom 15% of page
4. Check for footnote markers (*, †, ‡, §)

### Code Pattern
```python
def detect_footnotes(page) -> list[tuple[str, str]]:
    """Detect footnote patterns in page content."""
    blocks = page.get_text("dict")["blocks"]
    page_height = page.rect.height

    # Find text in bottom 15%
    bottom_threshold = page_height * 0.85
    bottom_text_blocks = []
    body_font_sizes = []

    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                y = span.get("origin", [0, 0])[1]
                size = span.get("size", 12)

                if y > bottom_threshold:
                    bottom_text_blocks.append(span)
                else:
                    body_font_sizes.append(size)

    if not body_font_sizes or not bottom_text_blocks:
        return []

    avg_body_size = sum(body_font_sizes) / len(body_font_sizes)

    # Check if bottom text is smaller (footnote-like)
    for span in bottom_text_blocks:
        if span.get("size", 12) < avg_body_size * 0.85:
            text = span.get("text", "")[:50]
            return [("footnotes_inline", f"Small text at bottom: {text}")]

    return []
```

### Definition of Done
- `test_debug_pdf.py::test_footnote_detection` passes
- Pattern `footnotes_inline` detected on PDF with footnotes

---

## Task 5: Add Archive.org Wayback URL detection
- [ ] Complete
- Agent: claude
- Priority: 1
- Dependencies: none

### Description
Detect Archive.org Wayback Machine URLs and extract original URL.

### Implementation
1. Add `WAYBACK_PATTERN` regex constant
2. Create `is_wayback_url()` and `extract_original_url()` helpers
3. Add URL-based pattern detection in download/analyze flow
4. Flag `archive_org_wrap` when Wayback URL detected

### Code Pattern
```python
import re

WAYBACK_PATTERN = re.compile(
    r'https?://web\.archive\.org/web/(\d{1,14})/(.+)',
    re.IGNORECASE
)

def is_wayback_url(url: str) -> bool:
    """Check if URL is an Archive.org Wayback Machine URL."""
    return bool(WAYBACK_PATTERN.match(url))

def extract_original_url(wayback_url: str) -> str | None:
    """Extract original URL from Wayback Machine URL."""
    match = WAYBACK_PATTERN.match(wayback_url)
    return match.group(2) if match else None
```

### Definition of Done
- `test_debug_pdf.py::test_wayback_url_detection` passes
- Pattern `archive_org_wrap` detected when analyzing Wayback URLs

---

## Task 6: Create test fixtures and test suite
- [ ] Complete
- Agent: claude
- Priority: 1
- Dependencies: Task 1-5

### Description
Create PDF test fixtures and comprehensive test suite for all pattern detection.

### Implementation
1. Create `tests/` directory in debug-pdf skill
2. Create test fixtures using fixture-tricky or manual PyMuPDF generation:
   - `fixture_multi_column.pdf` - 2-column layout
   - `fixture_header_footer.pdf` - with headers/footers
   - `fixture_split_table.pdf` - table spanning 2 pages
   - `fixture_footnotes.pdf` - document with footnotes
3. Create `test_debug_pdf.py` with pytest tests
4. Test each detection function individually
5. Test `analyze_pdf()` integration

### Test Structure
```python
# tests/test_debug_pdf.py
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from debug_pdf import (
    is_valid_url, is_wayback_url, extract_original_url,
    detect_multi_column, detect_header_footer_bleed,
    detect_split_tables, detect_footnotes, analyze_pdf
)

FIXTURES = Path(__file__).parent / "fixtures"

class TestURLValidation:
    def test_valid_https(self):
        assert is_valid_url("https://example.com/doc.pdf")

    def test_invalid_scheme(self):
        assert not is_valid_url("ftp://example.com/doc.pdf")

    def test_wayback_detection(self):
        url = "https://web.archive.org/web/20200101/https://example.com"
        assert is_wayback_url(url)
        assert extract_original_url(url) == "https://example.com"

class TestPatternDetection:
    def test_multi_column_detection(self):
        # Test with fixture
        pass

    def test_header_footer_detection(self):
        pass

    def test_split_table_detection(self):
        pass

    def test_footnote_detection(self):
        pass
```

### Definition of Done
- All tests in `test_debug_pdf.py` pass
- `pytest tests/` exits with code 0
- Coverage for all new detection functions

---

## Task 7: Update SKILL.md and run sanity check
- [ ] Complete
- Agent: claude
- Priority: 3
- Dependencies: Task 1-6

### Description
Update documentation to reflect new capabilities and verify everything works.

### Implementation
1. Update SKILL.md with new detected patterns
2. Update pattern coverage (14/17 vs 9/17)
3. Add new dependency notes (pymupdf4llm)
4. Run sanity.sh and fix any issues
5. Run full test suite

### Definition of Done
- SKILL.md accurately reflects all detected patterns
- `./sanity.sh` passes (11/11 or better)
- `pytest tests/` passes
- No regressions in existing functionality

---

## Summary

| Task | Description | Priority | Est. Complexity |
|------|-------------|----------|-----------------|
| 1 | Header/footer detection via Layout | 1 | Medium |
| 2 | Multi-column detection | 1 | Medium |
| 3 | Split table detection (flag only) | 2 | Low |
| 4 | Footnote detection | 2 | Medium |
| 5 | Wayback URL detection | 1 | Low |
| 6 | Test fixtures and test suite | 1 | High |
| 7 | Documentation and sanity | 3 | Low |

**Total new patterns**: 5 (multi_column, header_footer_bleed, split_tables, footnotes_inline, archive_org_wrap)

**Pattern coverage after completion**: 14/17 (82%) - up from 9/17 (53%)

**Remaining undetectable patterns**: auth_required, access_restricted (network-level, can't detect locally)
