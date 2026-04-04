"""
Layout and structure pattern detectors for PDF analysis.

Detectors: header/footer bleed, multi-column, split tables, footnotes,
signed contracts, government signatures.
"""
import re

import fitz

from dp_registry import register_page_detector, register_doc_detector
from loguru import logger


@register_page_detector
def detect_header_footer_bleed(page) -> list[tuple[str, str]]:
    """Detect header/footer content bleeding into body text using PyMuPDF4LLM Layout."""
    try:
        # Try using pymupdf4llm for ML-based layout detection
        import pymupdf4llm

        doc = page.parent
        page_num = page.number

        # Extract with headers/footers
        with_hf = pymupdf4llm.to_markdown(doc, pages=[page_num])

        # Extract without headers/footers (if supported)
        try:
            without_hf = pymupdf4llm.to_markdown(
                doc, pages=[page_num],
                margins=(72, 72, 72, 72)  # Use margins to exclude header/footer areas
            )

            # If significant difference, headers/footers are bleeding
            if len(with_hf) > len(without_hf) * 1.15:  # >15% difference
                diff_chars = len(with_hf) - len(without_hf)
                return [("header_footer_bleed", f"Detected via Layout API: {diff_chars} chars in header/footer regions")]
        except (TypeError, AttributeError):
            pass  # Fallback if margins param not supported

    except ImportError:
        pass

    # Fallback: Heuristic-based detection
    page_height = page.rect.height
    blocks = page.get_text("dict").get("blocks", [])

    header_threshold = page_height * 0.08  # Top 8%
    footer_threshold = page_height * 0.92  # Bottom 8%

    header_text = []
    footer_text = []

    for block in blocks:
        if block.get("type") != 0:  # Not text
            continue
        bbox = block.get("bbox", [0, 0, 0, 0])

        # Check header region
        if bbox[1] < header_threshold:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if text and len(text) > 10:  # Substantial text
                        header_text.append(text)

        # Check footer region
        if bbox[3] > footer_threshold:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if text and len(text) > 10:
                        footer_text.append(text)

    results = []
    if header_text:
        results.append(("header_footer_bleed", f"Header content: {header_text[0][:50]}"))
    if footer_text:
        results.append(("header_footer_bleed", f"Footer content: {footer_text[0][:50]}"))

    return results


@register_page_detector
def detect_multi_column(page) -> list[tuple[str, str]]:
    """Detect multi-column layouts using text block analysis."""
    blocks = page.get_text("dict").get("blocks", [])
    text_blocks = [b for b in blocks if b.get("type") == 0]

    if len(text_blocks) < 4:
        return []

    # Get x-coordinates of block centers
    page_width = page.rect.width
    mid = page_width / 2

    # Analyze block positions
    left_blocks = []
    right_blocks = []

    for b in text_blocks:
        bbox = b.get("bbox", [0, 0, 0, 0])
        block_center_x = (bbox[0] + bbox[2]) / 2
        block_width = bbox[2] - bbox[0]

        # Skip blocks that span most of the page (likely headers/titles)
        if block_width > page_width * 0.7:
            continue

        if block_center_x < mid * 0.85:
            left_blocks.append(b)
        elif block_center_x > mid * 1.15:
            right_blocks.append(b)

    # Need multiple blocks on each side for column detection
    if len(left_blocks) >= 3 and len(right_blocks) >= 3:
        # Verify vertical overlap (columns should have content at similar y-positions)
        left_y_ranges = [(b["bbox"][1], b["bbox"][3]) for b in left_blocks]
        right_y_ranges = [(b["bbox"][1], b["bbox"][3]) for b in right_blocks]

        overlap_count = 0
        for ly1, ly2 in left_y_ranges:
            for ry1, ry2 in right_y_ranges:
                if ly1 < ry2 and ly2 > ry1:  # Ranges overlap
                    overlap_count += 1

        if overlap_count >= 2:
            return [("multi_column", f"Detected 2 columns: {len(left_blocks)} left, {len(right_blocks)} right blocks")]

    return []


def detect_split_tables(doc, page_num: int) -> list[tuple[str, str]]:
    """Detect tables that may span across pages (flag only, no merging)."""
    page = doc[page_num]

    try:
        tables = page.find_tables()
    except Exception:
        return []

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
                try:
                    next_tables = next_page.find_tables()
                    for nt in next_tables:
                        # Table starts in top 10% of next page
                        if nt.bbox[1] < page_height * 0.10:
                            results.append((
                                "split_tables",
                                f"Table likely spans pages {page_num + 1}-{page_num + 2}"
                            ))
                            break
                except Exception as e:
                    logger.debug("value lookup failed: {}", e)

    return results


@register_page_detector
def detect_footnotes(page) -> list[tuple[str, str]]:
    """Detect footnote patterns in page content."""
    blocks = page.get_text("dict").get("blocks", [])
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
                origin = span.get("origin", [0, 0])
                y = origin[1] if len(origin) > 1 else 0
                size = span.get("size", 12)
                text = span.get("text", "")

                if y > bottom_threshold:
                    bottom_text_blocks.append({
                        "text": text,
                        "size": size,
                        "y": y
                    })
                else:
                    body_font_sizes.append(size)

    if not body_font_sizes or not bottom_text_blocks:
        return []

    avg_body_size = sum(body_font_sizes) / len(body_font_sizes)

    # Check for footnote indicators
    results = []

    for span_data in bottom_text_blocks:
        text = span_data["text"]
        size = span_data["size"]

        # Check if bottom text is smaller (footnote-like)
        if size < avg_body_size * 0.85:
            # Check for footnote markers
            if re.match(r'^[\d\*†‡§¶\[\(]', text.strip()):
                results.append(("footnotes_inline", f"Footnote marker: {text[:60]}"))
                break
            elif len(text.strip()) > 20:  # Substantial small text at bottom
                results.append(("footnotes_inline", f"Small text at bottom: {text[:60]}"))
                break

    # Also check for superscript numbers in body
    body_text = ""
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                body_text += span.get("text", "")

    # Look for footnote reference patterns in body
    if re.search(r'\[\d+\]|\(\d+\)|[\*†‡§]\s', body_text):
        if not results:  # Only add if not already detected
            results.append(("footnotes_inline", "Footnote references detected in body"))

    return results


@register_doc_detector
def detect_signed_contract(doc, max_pages: int = 5) -> list[tuple[str, str]]:
    """Detect signature fields in first N pages (typical for contracts/aerospace docs)."""
    results = []
    sig_flags = doc.get_sigflags()

    if sig_flags == -1:
        return []  # Error or no signature support
    elif sig_flags == 0:
        return []  # No signature fields
    elif sig_flags >= 1:
        # Has signature fields - find them
        signature_pages = []
        for page_num in range(min(max_pages, len(doc))):
            page = doc[page_num]
            try:
                sig_widgets = list(page.widgets(types=[fitz.PDF_WIDGET_TYPE_SIGNATURE]))
                if sig_widgets:
                    for widget in sig_widgets:
                        is_signed = getattr(widget, 'is_signed', None)
                        field_name = getattr(widget, 'field_name', 'unknown')
                        signature_pages.append({
                            "page": page_num + 1,
                            "field": field_name,
                            "signed": is_signed
                        })
            except Exception as e:
                logger.debug("value lookup failed: {}", e)

        if signature_pages:
            signed_count = sum(1 for s in signature_pages if s.get("signed"))
            total = len(signature_pages)
            pages_with_sigs = list(set(s["page"] for s in signature_pages))
            results.append((
                "signed_contract",
                f"{signed_count}/{total} signatures on pages {pages_with_sigs}"
            ))

    return results


@register_doc_detector
def detect_government_signatures(doc) -> list[tuple[str, str]]:
    """Detect government/DoD certificate signatures in PDF."""
    results = []
    gov_issuers = [
        "Department of Defense",
        "DoD Root CA",
        "Federal PKI",
        "FPKI",
        "DOD ID CA",
        "DOD EMAIL CA",
        "Common Access Card",
        "PIV",
        "US Government"
    ]

    for page in doc:
        try:
            for widget in page.widgets(types=[fitz.PDF_WIDGET_TYPE_SIGNATURE]):
                xref = widget.xref
                # Try to extract signature details via low-level API
                try:
                    v_key = doc.xref_get_key(xref, "V")
                    if v_key[0] == "xref":
                        v_xref = int(v_key[1].split()[0])
                        keys = doc.xref_get_keys(v_xref)

                        # Check for Name/Reason fields that might indicate gov certs
                        for key in ["Name", "Reason", "ContactInfo", "Location"]:
                            if key in keys:
                                val = doc.xref_get_key(v_xref, key)
                                if val[0] == "string":
                                    text = val[1]
                                    for issuer in gov_issuers:
                                        if issuer.lower() in text.lower():
                                            results.append((
                                                "government_signed",
                                                f"Detected {issuer} signature: {text[:60]}"
                                            ))
                                            return results  # One is enough
                except Exception as e:
                    logger.debug("value lookup failed: {}", e)
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    return results



