"""
Extraction quality pattern detectors.

Detectors: symbol fonts, math symbol loss, section under-segmentation,
low block density, TOC leaders in headers, partial sentence headers.
"""
import re

import fitz

from dp_registry import register_page_detector, register_doc_detector


def detect_symbol_fonts(page) -> list[tuple[str, str]]:
    """Detect Microsoft Symbol/Wingdings PUA characters (U+F000-U+F8FF)."""
    text = page.get_text()
    pua_chars = [c for c in text if '\ue000' <= c <= '\uf8ff']
    if len(pua_chars) >= 3:
        unique = set(pua_chars)
        sample = ', '.join(f'U+{ord(c):04X}' for c in list(unique)[:5])
        return [("symbol_fonts", f"{len(pua_chars)} PUA chars ({sample})")]
    return []


@register_page_detector
def detect_math_symbols_lost(page) -> list[tuple[str, str]]:
    """Detect mathematical symbols becoming '?' during extraction."""
    text = page.get_text()
    if not text:
        return []
    # High density of '?' near mathematical context (integrals, superscripts)
    question_marks = text.count('?')
    total_chars = len(text)
    if total_chars < 50:
        return []
    qm_ratio = question_marks / total_chars
    # Check for math context clues
    math_context = bool(re.search(
        r'(?:equation|integral|sum|lim|dx|dy|d[a-z]|x[²³⁴]|'
        r'\\(?:int|sum|lim|frac|sqrt)|'
        r'(?:^|\s)[?]{2,}(?:\s|$))',
        text, re.IGNORECASE
    ))
    if qm_ratio > 0.05 and math_context:
        return [("math_symbols_lost",
                 f"{question_marks} '?' chars ({qm_ratio:.1%} of text), math context detected")]
    if qm_ratio > 0.10:
        return [("math_symbols_lost",
                 f"{question_marks} '?' chars ({qm_ratio:.1%} of text), likely symbol loss")]
    return []


@register_doc_detector
def detect_section_under_segmentation(doc) -> list[tuple[str, str]]:
    """Detect when a document has suspiciously few sections for its page count."""
    page_count = len(doc)
    if page_count < 20:
        return []  # Only flag for substantial documents

    # Estimate section count from header-like blocks
    section_count = 0
    for i in range(min(page_count, 50)):  # Sample first 50 pages
        page = doc[i]
        blocks = page.get_text("dict", sort=True).get("blocks", [])
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    size = span.get("size", 0)
                    if size > 13 and text and len(text) < 100:
                        if re.match(r'^\d+(\.\d+)*\s+\S', text):
                            section_count += 1

    sections_per_page = section_count / min(page_count, 50) if page_count > 0 else 0
    if sections_per_page < 0.05:
        return [("section_under_segmentation",
                 f"{section_count} headers in {min(page_count, 50)} sampled pages "
                 f"({sections_per_page:.3f}/page, threshold: 0.05)")]
    return []


@register_doc_detector
def detect_low_block_density(doc) -> list[tuple[str, str]]:
    """Detect documents with suspiciously few text blocks per page."""
    page_count = len(doc)
    if page_count < 5:
        return []

    total_blocks = 0
    sample = min(page_count, 20)
    for i in range(sample):
        page = doc[i]
        blocks = page.get_text("dict", sort=True).get("blocks", [])
        text_blocks = [b for b in blocks if b.get("type") == 0]
        total_blocks += len(text_blocks)

    blocks_per_page = total_blocks / sample if sample > 0 else 0
    if blocks_per_page < 0.5:
        return [("low_block_density",
                 f"{total_blocks} blocks in {sample} pages ({blocks_per_page:.2f}/page)")]
    return []


@register_page_detector
def detect_toc_leaders_in_headers(page) -> list[tuple[str, str]]:
    """Detect dotted leaders captured in section titles (TOC bleed)."""
    blocks = page.get_text("dict", sort=True).get("blocks", [])
    toc_headers = []
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                size = span.get("size", 0)
                # Large bold text with dotted leaders = TOC bleed into headers
                if size > 12 and re.search(r'\.{5,}', text) and len(text) > 20:
                    toc_headers.append(text[:60])
    if toc_headers:
        return [("toc_leaders_in_headers",
                 f"{len(toc_headers)} headers with dots: {toc_headers[0][:50]}")]
    return []


@register_page_detector
def detect_partial_sentence_headers(page) -> list[tuple[str, str]]:
    """Detect sentence fragments misclassified as section headers."""
    blocks = page.get_text("dict", sort=True).get("blocks", [])
    fragments = []
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                size = span.get("size", 0)
                # Large/bold text that looks like a sentence fragment
                if size > 12 and text:
                    lower = text.lower()
                    is_fragment = (
                        (text[0].islower() and len(text) > 20)
                        or text.rstrip().endswith(',')
                        or any(lower.startswith(w) for w in
                               ['and ', 'or ', 'but ', 'which ', 'that ', 'including '])
                        or ' such as ' in lower
                    )
                    if is_fragment and len(text) > 30:
                        fragments.append(text[:60])
    if fragments:
        return [("partial_sentence_headers",
                 f"{len(fragments)} fragments: {fragments[0][:50]}")]
    return []



