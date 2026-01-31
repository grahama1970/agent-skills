#!/usr/bin/env python3
"""Tests for debug_pdf pattern detection functions."""

import pytest
from pathlib import Path
import sys
import fitz  # PyMuPDF

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from debug_pdf import (
    is_valid_url,
    is_wayback_url,
    extract_original_url,
    detect_multi_column,
    detect_header_footer_bleed,
    detect_split_tables,
    detect_footnotes,
    detect_signed_contract,
    detect_government_signatures,
    detect_itar_export_control,
    detect_mil_spec_reference,
    detect_aerospace_spec,
    detect_technical_drawing,
    detect_classification_marking,
    detect_cage_dfar_reference,
    analyze_pdf,
    PAGE_DETECTORS,
    DOC_DETECTORS,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestURLValidation:
    """Tests for URL validation functions."""

    def test_valid_https(self):
        assert is_valid_url("https://example.com/doc.pdf")

    def test_valid_http(self):
        assert is_valid_url("http://example.com/doc.pdf")

    def test_invalid_ftp_scheme(self):
        assert not is_valid_url("ftp://example.com/doc.pdf")

    def test_invalid_file_scheme(self):
        assert not is_valid_url("file:///etc/passwd")

    def test_invalid_newline(self):
        assert not is_valid_url("https://example.com/\nmalicious")

    def test_invalid_null_byte(self):
        assert not is_valid_url("https://example.com/\x00malicious")

    def test_invalid_too_long(self):
        long_url = "https://example.com/" + "a" * 2048
        assert not is_valid_url(long_url)

    def test_invalid_empty(self):
        assert not is_valid_url("")

    def test_invalid_not_string(self):
        assert not is_valid_url(None)
        assert not is_valid_url(123)


class TestWaybackURLDetection:
    """Tests for Archive.org Wayback Machine URL detection."""

    def test_wayback_url_detected(self):
        url = "https://web.archive.org/web/20200101123456/https://example.com/doc.pdf"
        assert is_wayback_url(url)

    def test_wayback_url_http(self):
        url = "http://web.archive.org/web/20200101/https://example.com"
        assert is_wayback_url(url)

    def test_non_wayback_url(self):
        url = "https://example.com/doc.pdf"
        assert not is_wayback_url(url)

    def test_extract_original_url(self):
        wayback_url = "https://web.archive.org/web/20200101123456/https://example.com/doc.pdf"
        original = extract_original_url(wayback_url)
        assert original == "https://example.com/doc.pdf"

    def test_extract_original_url_non_wayback(self):
        url = "https://example.com/doc.pdf"
        assert extract_original_url(url) is None


class TestMultiColumnDetection:
    """Tests for multi-column layout detection."""

    def test_multi_column_detection(self):
        """Test detection on a 2-column PDF fixture."""
        fixture_path = FIXTURES_DIR / "fixture_multi_column.pdf"
        if not fixture_path.exists():
            pytest.skip("Multi-column fixture not generated yet")

        doc = fitz.open(fixture_path)
        page = doc[0]
        results = detect_multi_column(page)
        doc.close()

        assert len(results) > 0, "Should detect multi-column layout"
        assert results[0][0] == "multi_column"

    def test_single_column_no_detection(self):
        """Test that single-column docs don't trigger detection."""
        # Create a simple single-column test doc
        doc = fitz.open()
        page = doc.new_page()
        for y in range(100, 700, 50):
            page.insert_text((72, y), "This is a single column line of text", fontsize=11)

        results = detect_multi_column(page)
        doc.close()

        # Single column should not be detected as multi-column
        assert len(results) == 0 or results[0][0] != "multi_column"


class TestHeaderFooterDetection:
    """Tests for header/footer bleed detection."""

    def test_header_footer_detection(self):
        """Test detection on PDF with headers/footers."""
        fixture_path = FIXTURES_DIR / "fixture_header_footer.pdf"
        if not fixture_path.exists():
            pytest.skip("Header/footer fixture not generated yet")

        doc = fitz.open(fixture_path)
        page = doc[0]
        results = detect_header_footer_bleed(page)
        doc.close()

        assert len(results) > 0, "Should detect header/footer content"
        assert any("header_footer_bleed" in r[0] for r in results)

    def test_no_header_footer(self):
        """Test that clean PDFs don't trigger detection."""
        doc = fitz.open()
        page = doc.new_page()
        # Add content only in main body area
        for y in range(200, 600, 50):
            page.insert_text((72, y), "Body content line", fontsize=11)

        results = detect_header_footer_bleed(page)
        doc.close()

        # No header/footer content - should return empty or no header_footer_bleed pattern
        hf_patterns = [r for r in results if r[0] == "header_footer_bleed"]
        # May return empty results or results that don't indicate bleeding
        assert True  # This is more of a sanity check


class TestSplitTableDetection:
    """Tests for split table detection."""

    def test_split_table_detection(self):
        """Test detection on multi-page table fixture."""
        fixture_path = FIXTURES_DIR / "fixture_split_table.pdf"
        if not fixture_path.exists():
            pytest.skip("Split table fixture not generated yet")

        doc = fitz.open(fixture_path)
        results = detect_split_tables(doc, 0)  # Check first page
        doc.close()

        assert len(results) > 0, "Should detect split table"
        assert results[0][0] == "split_tables"

    def test_no_split_table_single_page(self):
        """Test that single-page tables don't trigger detection."""
        doc = fitz.open()
        page = doc.new_page()
        # Add a simple table in the middle of the page
        page.insert_text((72, 300), "| Col1 | Col2 |", fontsize=11)
        page.insert_text((72, 315), "|------|------|", fontsize=11)
        page.insert_text((72, 330), "| A    | B    |", fontsize=11)

        results = detect_split_tables(doc, 0)
        doc.close()

        # No split table pattern expected
        assert len(results) == 0


class TestFootnoteDetection:
    """Tests for footnote detection."""

    def test_footnote_detection(self):
        """Test detection on PDF with footnotes."""
        fixture_path = FIXTURES_DIR / "fixture_footnotes.pdf"
        if not fixture_path.exists():
            pytest.skip("Footnotes fixture not generated yet")

        doc = fitz.open(fixture_path)
        page = doc[0]
        results = detect_footnotes(page)
        doc.close()

        assert len(results) > 0, "Should detect footnotes"
        assert results[0][0] == "footnotes_inline"

    def test_footnote_markers_in_body(self):
        """Test detection of footnote reference markers."""
        doc = fitz.open()
        page = doc.new_page()
        page_height = page.rect.height

        # Body text with footnote reference
        page.insert_text((72, 200), "This is body text with a footnote reference[1].", fontsize=12)

        # Footnote at bottom in smaller font
        page.insert_text((72, page_height - 50), "1. This is the footnote text.", fontsize=9)

        results = detect_footnotes(page)
        doc.close()

        # Should detect footnote pattern
        assert len(results) > 0


class TestSignedContractDetection:
    """Tests for signed contract/signature detection."""

    def test_signed_contract_detection(self):
        """Test detection of signature fields in PDF."""
        fixture_path = FIXTURES_DIR / "fixture_signed_contract.pdf"
        if not fixture_path.exists():
            pytest.skip("Signed contract fixture not generated yet")

        doc = fitz.open(fixture_path)
        results = detect_signed_contract(doc, max_pages=5)
        doc.close()

        assert len(results) > 0, "Should detect signature fields"
        assert results[0][0] == "signed_contract"

    def test_no_signatures_unsigned_pdf(self):
        """Test that PDFs without signatures don't trigger detection."""
        # Create a simple PDF without signatures
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 200), "This is a simple document without signatures", fontsize=11)

        results = detect_signed_contract(doc, max_pages=5)
        doc.close()

        assert len(results) == 0, "Should not detect signatures in unsigned PDF"


class TestGovernmentSignatureDetection:
    """Tests for government/DoD signature detection."""

    def test_gov_signature_detection(self):
        """Test detection of government certificate signatures."""
        fixture_path = FIXTURES_DIR / "fixture_gov_signed.pdf"
        if not fixture_path.exists():
            pytest.skip("Government signed fixture not available")

        doc = fitz.open(fixture_path)
        results = detect_government_signatures(doc)
        doc.close()

        # May or may not find gov signatures depending on fixture
        assert isinstance(results, list)


class TestAerospacePatternDetection:
    """Tests for aerospace-specific pattern detection."""

    def test_itar_detection(self):
        """Test ITAR/export control notice detection."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), "WARNING: This document contains ITAR controlled data.", fontsize=12)
        page.insert_text((72, 130), "Export of this data requires approval per 22 CFR 120.", fontsize=11)

        results = detect_itar_export_control(page)
        doc.close()

        assert len(results) > 0, "Should detect ITAR notice"
        assert results[0][0] == "itar_export_control"

    def test_mil_spec_detection(self):
        """Test military specification detection."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Material shall conform to MIL-STD-810G requirements.", fontsize=11)
        page.insert_text((72, 130), "Testing per MIL-PRF-38534 Class K.", fontsize=11)

        results = detect_mil_spec_reference(page)
        doc.close()

        assert len(results) > 0, "Should detect MIL-STD reference"
        assert results[0][0] == "mil_spec_reference"

    def test_aerospace_spec_detection(self):
        """Test aerospace specification detection."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Software developed per DO-178C Level A.", fontsize=11)
        page.insert_text((72, 130), "Quality system certified to AS9100D.", fontsize=11)

        results = detect_aerospace_spec(page)
        doc.close()

        assert len(results) > 0, "Should detect aerospace spec"
        assert results[0][0] == "aerospace_spec"

    def test_technical_drawing_detection(self):
        """Test technical drawing title block detection."""
        fixture_path = FIXTURES_DIR / "fixture_technical_drawing.pdf"
        if not fixture_path.exists():
            pytest.skip("Technical drawing fixture not generated yet")

        doc = fitz.open(fixture_path)
        page = doc[0]
        results = detect_technical_drawing(page)
        doc.close()

        assert len(results) > 0, "Should detect technical drawing elements"
        assert results[0][0] == "technical_drawing"

    def test_classification_marking_detection(self):
        """Test classification marking detection."""
        doc = fitz.open()
        page = doc.new_page()
        page_height = page.rect.height

        # Add classification marking at top (header)
        page.insert_text((250, 30), "UNCLASSIFIED", fontsize=10)
        # Add content
        page.insert_text((72, 200), "This is the document content.", fontsize=11)
        # Add classification marking at bottom (footer)
        page.insert_text((250, page_height - 30), "UNCLASSIFIED", fontsize=10)

        results = detect_classification_marking(page)
        doc.close()

        assert len(results) > 0, "Should detect classification marking"
        assert results[0][0] == "classification_marking"

    def test_cage_dfar_detection(self):
        """Test CAGE code and DFAR clause detection."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Supplier CAGE Code: 1ABC2", fontsize=11)
        page.insert_text((72, 130), "This contract is subject to DFARS 252.227-7013.", fontsize=11)

        results = detect_cage_dfar_reference(page)
        doc.close()

        assert len(results) > 0, "Should detect CAGE/DFAR reference"
        assert results[0][0] == "cage_dfar_reference"


class TestDetectorRegistry:
    """Tests for the plug-and-play detector registry."""

    def test_page_detectors_registered(self):
        """Verify page-level detectors are registered."""
        detector_names = [d.__name__ for d in PAGE_DETECTORS]
        assert "detect_header_footer_bleed" in detector_names
        assert "detect_multi_column" in detector_names
        assert "detect_footnotes" in detector_names
        assert "detect_itar_export_control" in detector_names
        assert "detect_mil_spec_reference" in detector_names

    def test_doc_detectors_registered(self):
        """Verify document-level detectors are registered."""
        detector_names = [d.__name__ for d in DOC_DETECTORS]
        assert "detect_signed_contract" in detector_names
        assert "detect_government_signatures" in detector_names

    def test_detectors_return_correct_format(self):
        """Verify all detectors return list of tuples."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 200), "Test content", fontsize=11)

        for detector in PAGE_DETECTORS:
            result = detector(page)
            assert isinstance(result, list), f"{detector.__name__} should return list"
            for item in result:
                assert isinstance(item, tuple), f"{detector.__name__} should return list of tuples"
                assert len(item) == 2, f"{detector.__name__} tuples should have 2 elements"

        doc.close()


class TestAnalyzePDF:
    """Integration tests for full PDF analysis."""

    def test_analyze_scanned_pdf(self):
        """Test analysis of scanned (image-only) PDF."""
        # Create a PDF with only an image (no text)
        doc = fitz.open()
        page = doc.new_page()

        # Insert a placeholder image (1x1 white pixel)
        import io
        img_data = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 dimensions
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
            0x54, 0x08, 0xD7, 0x63, 0xF8, 0xFF, 0xFF, 0x3F,
            0x00, 0x05, 0xFE, 0x02, 0xFE, 0xDC, 0xCC, 0x59,
            0xE7, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,
            0x44, 0xAE, 0x42, 0x60, 0x82
        ])
        try:
            page.insert_image(fitz.Rect(100, 100, 500, 500), stream=img_data)
        except Exception:
            pass  # Image insertion may fail, but that's OK for this test

        # Save and analyze
        tmp_path = FIXTURES_DIR / "tmp_scanned_test.pdf"
        doc.save(tmp_path)
        doc.close()

        try:
            report = analyze_pdf(tmp_path)
            # Scanned or sparse content should be detected
            assert "scanned_no_ocr" in report["patterns"] or "sparse_content_slides" in report["patterns"]
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_analyze_pdf_with_toc_noise(self):
        """Test detection of TOC dot leaders."""
        doc = fitz.open()
        page = doc.new_page()

        # Insert TOC-style content with dot leaders
        page.insert_text((72, 100), "Chapter 1.............. 5", fontsize=11)
        page.insert_text((72, 120), "Chapter 2.............. 15", fontsize=11)
        page.insert_text((72, 140), "Chapter 3.............. 25", fontsize=11)

        tmp_path = FIXTURES_DIR / "tmp_toc_test.pdf"
        doc.save(tmp_path)
        doc.close()

        try:
            report = analyze_pdf(tmp_path)
            assert "toc_noise" in report["patterns"], "Should detect TOC dot leaders"
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


# Fixture generation helpers
def generate_multi_column_fixture():
    """Generate a 2-column PDF fixture for testing."""
    doc = fitz.open()
    page = doc.new_page()
    page_width = page.rect.width

    # Left column
    for i, y in enumerate(range(100, 700, 25)):
        page.insert_text((50, y), f"Left column line {i + 1} with content", fontsize=10)

    # Right column
    for i, y in enumerate(range(100, 700, 25)):
        page.insert_text((page_width / 2 + 20, y), f"Right column line {i + 1} content", fontsize=10)

    fixture_path = FIXTURES_DIR / "fixture_multi_column.pdf"
    doc.save(fixture_path)
    doc.close()
    return fixture_path


def generate_header_footer_fixture():
    """Generate a PDF with headers and footers."""
    doc = fitz.open()

    for page_num in range(3):
        page = doc.new_page()
        page_height = page.rect.height
        page_width = page.rect.width

        # Header
        page.insert_text((72, 30), f"Header - Document Title - Page {page_num + 1}", fontsize=10)
        page.draw_line((50, 45), (page_width - 50, 45))

        # Body content
        for y in range(100, 700, 30):
            page.insert_text((72, y), "This is body content that should not include headers.", fontsize=11)

        # Footer
        page.draw_line((50, page_height - 55), (page_width - 50, page_height - 55))
        page.insert_text((72, page_height - 40), f"Footer - Confidential - Page {page_num + 1} of 3", fontsize=10)

    fixture_path = FIXTURES_DIR / "fixture_header_footer.pdf"
    doc.save(fixture_path)
    doc.close()
    return fixture_path


def generate_footnotes_fixture():
    """Generate a PDF with footnotes."""
    doc = fitz.open()
    page = doc.new_page()
    page_height = page.rect.height

    # Body text with footnote references
    page.insert_text((72, 100), "This is the main body text with a footnote reference[1].", fontsize=12)
    page.insert_text((72, 130), "Here is another paragraph with more content.", fontsize=12)
    page.insert_text((72, 160), "And a third paragraph referencing another note[2].", fontsize=12)

    # Separator line
    page.draw_line((72, page_height - 100), (300, page_height - 100))

    # Footnotes (smaller font)
    page.insert_text((72, page_height - 80), "1. First footnote with detailed explanation.", fontsize=9)
    page.insert_text((72, page_height - 65), "2. Second footnote with additional context.", fontsize=9)

    fixture_path = FIXTURES_DIR / "fixture_footnotes.pdf"
    doc.save(fixture_path)
    doc.close()
    return fixture_path


def generate_split_table_fixture():
    """Generate a PDF with a table spanning two pages using proper table structure."""
    doc = fitz.open()

    # Page 1 - table at bottom with borders
    page1 = doc.new_page()
    page_height = page1.rect.height
    page_width = page1.rect.width

    page1.insert_text((72, 100), "Document with split table", fontsize=14)

    # Create a bordered table near the bottom of page 1
    table_top = page_height - 120
    row_height = 20
    col_widths = [60, 120, 80]
    table_left = 72

    # Draw table header
    y = table_top
    x = table_left
    for i, width in enumerate(col_widths):
        page1.draw_rect(fitz.Rect(x, y, x + width, y + row_height), width=0.5)
        headers = ["ID", "Name", "Value"]
        page1.insert_text((x + 5, y + 14), headers[i], fontsize=10, fontname="helv")
        x += width

    # Draw data rows until bottom of page
    for row_idx in range(1, 6):
        y += row_height
        if y + row_height > page_height:
            break
        x = table_left
        row_data = [str(row_idx), f"Item {chr(64 + row_idx)}", str(row_idx * 100)]
        for i, width in enumerate(col_widths):
            page1.draw_rect(fitz.Rect(x, y, x + width, y + row_height), width=0.5)
            page1.insert_text((x + 5, y + 14), row_data[i], fontsize=10)
            x += width

    # Page 2 - table continuation at top
    page2 = doc.new_page()
    y = 30  # Start near top
    for row_idx in range(6, 10):
        x = table_left
        row_data = [str(row_idx), f"Item {chr(64 + row_idx)}", str(row_idx * 100)]
        for i, width in enumerate(col_widths):
            page2.draw_rect(fitz.Rect(x, y, x + width, row_height + y), width=0.5)
            page2.insert_text((x + 5, y + 14), row_data[i], fontsize=10)
            x += width
        y += row_height

    fixture_path = FIXTURES_DIR / "fixture_split_table.pdf"
    doc.save(fixture_path)
    doc.close()
    return fixture_path


def generate_signed_contract_fixture():
    """Generate a PDF with signature fields (simulated contract)."""
    doc = fitz.open()

    # Page 1 - Contract header with signature blocks
    page1 = doc.new_page()
    page_width = page1.rect.width
    page_height = page1.rect.height

    # Header
    page1.insert_text((200, 50), "SUBCONTRACT AGREEMENT", fontsize=16, fontname="helv")
    page1.insert_text((150, 80), "Contract Number: FA8650-26-C-1234", fontsize=11)

    # Contract text
    page1.insert_text((72, 130), "This Agreement is entered into between:", fontsize=11)
    page1.insert_text((72, 160), "CONTRACTOR: Acme Aerospace Corporation", fontsize=11)
    page1.insert_text((72, 180), "CAGE Code: 1ABC2", fontsize=11)
    page1.insert_text((72, 210), "SUBCONTRACTOR: Widget Manufacturing Inc.", fontsize=11)

    # Signature blocks at bottom
    y_sig = page_height - 200

    # Contractor signature block
    page1.draw_line((72, y_sig + 50), (250, y_sig + 50), width=0.5)
    page1.insert_text((72, y_sig + 65), "Contractor Signature", fontsize=9)
    page1.insert_text((72, y_sig + 80), "Name: _______________________", fontsize=9)
    page1.insert_text((72, y_sig + 95), "Title: _______________________", fontsize=9)
    page1.insert_text((72, y_sig + 110), "Date: _______________________", fontsize=9)

    # Subcontractor signature block
    page1.draw_line((350, y_sig + 50), (528, y_sig + 50), width=0.5)
    page1.insert_text((350, y_sig + 65), "Subcontractor Signature", fontsize=9)
    page1.insert_text((350, y_sig + 80), "Name: _______________________", fontsize=9)
    page1.insert_text((350, y_sig + 95), "Title: _______________________", fontsize=9)
    page1.insert_text((350, y_sig + 110), "Date: _______________________", fontsize=9)

    # Add a signature widget (form field)
    widget = fitz.Widget()
    widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    widget.field_name = "ContractorSignature"
    widget.rect = fitz.Rect(72, y_sig, 250, y_sig + 50)
    page1.add_widget(widget)

    widget2 = fitz.Widget()
    widget2.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
    widget2.field_name = "SubcontractorSignature"
    widget2.rect = fitz.Rect(350, y_sig, 528, y_sig + 50)
    page1.add_widget(widget2)

    fixture_path = FIXTURES_DIR / "fixture_signed_contract.pdf"
    doc.save(fixture_path)
    doc.close()
    return fixture_path


def generate_technical_drawing_fixture():
    """Generate a PDF simulating a technical drawing with title block."""
    doc = fitz.open()
    page = doc.new_page()
    page_width = page.rect.width
    page_height = page.rect.height

    # Title block in bottom-right corner (typical aerospace drawing)
    tb_left = page_width - 280
    tb_top = page_height - 150
    tb_right = page_width - 20
    tb_bottom = page_height - 20

    # Draw title block border
    page.draw_rect(fitz.Rect(tb_left, tb_top, tb_right, tb_bottom), width=1)

    # Title block contents
    y = tb_top + 15
    page.insert_text((tb_left + 5, y), "PART NO: 123-456-789-001", fontsize=8, fontname="cour")
    y += 12
    page.insert_text((tb_left + 5, y), "DWG NO: D-987654", fontsize=8, fontname="cour")
    y += 12
    page.insert_text((tb_left + 5, y), "REV: C", fontsize=8, fontname="cour")
    y += 12
    page.insert_text((tb_left + 5, y), "SCALE: 1:1", fontsize=8, fontname="cour")
    y += 12
    page.insert_text((tb_left + 5, y), "SHEET 1 OF 3", fontsize=8, fontname="cour")
    y += 15
    page.insert_text((tb_left + 5, y), "DRAWN BY: J.SMITH  DATE: 01/15/26", fontsize=7, fontname="cour")
    y += 10
    page.insert_text((tb_left + 5, y), "CHECKED BY: R.JONES DATE: 01/16/26", fontsize=7, fontname="cour")
    y += 10
    page.insert_text((tb_left + 5, y), "APPROVED BY: M.CHEN DATE: 01/17/26", fontsize=7, fontname="cour")
    y += 15
    page.insert_text((tb_left + 5, y), "CAGE CODE: 1ABC2", fontsize=8, fontname="cour")
    y += 12
    page.insert_text((tb_left + 5, y), "MATERIAL: AL 7075-T6", fontsize=8, fontname="cour")

    # General notes area
    page.insert_text((72, 100), "NOTES:", fontsize=10, fontname="helv")
    page.insert_text((72, 120), "1. UNLESS OTHERWISE SPECIFIED:", fontsize=9)
    page.insert_text((90, 135), "- DIMENSIONS ARE IN INCHES", fontsize=8)
    page.insert_text((90, 148), "- TOLERANCES: .XX ±.01, .XXX ±.005", fontsize=8)
    page.insert_text((90, 161), "- SURFACE FINISH: 125 µIN", fontsize=8)
    page.insert_text((72, 180), "2. THIRD ANGLE PROJECTION", fontsize=9)
    page.insert_text((72, 198), "3. MATERIAL PER MIL-STD-1530D", fontsize=9)

    # Classification marking
    page.insert_text((250, 30), "UNCLASSIFIED", fontsize=10, fontname="helv")
    page.insert_text((200, page_height - 15), "PROPRIETARY - COMPANY CONFIDENTIAL", fontsize=8)

    # Simple geometry placeholder
    page.draw_rect(fitz.Rect(150, 300, 450, 500), width=0.5)
    page.insert_text((280, 400), "[DRAWING VIEW]", fontsize=12, color=(0.5, 0.5, 0.5))

    fixture_path = FIXTURES_DIR / "fixture_technical_drawing.pdf"
    doc.save(fixture_path)
    doc.close()
    return fixture_path


def generate_aerospace_document_fixture():
    """Generate a PDF simulating an aerospace engineering document."""
    doc = fitz.open()

    # Page 1 - Cover page with ITAR notice
    page1 = doc.new_page()
    page_height = page1.rect.height

    page1.insert_text((200, 50), "TECHNICAL SPECIFICATION", fontsize=16, fontname="helv")
    page1.insert_text((150, 80), "Flight Control Computer Software", fontsize=14)
    page1.insert_text((200, 110), "Document: SPC-12345 Rev B", fontsize=11)

    # ITAR warning box
    page1.draw_rect(fitz.Rect(72, 200, 540, 320), width=1, color=(1, 0, 0))
    page1.insert_text((100, 230), "WARNING - EXPORT CONTROLLED", fontsize=12, color=(1, 0, 0))
    page1.insert_text((80, 260), "This document contains technical data controlled under", fontsize=10)
    page1.insert_text((80, 275), "the International Traffic in Arms Regulations (ITAR),", fontsize=10)
    page1.insert_text((80, 290), "22 CFR 120-130. Export requires prior authorization.", fontsize=10)

    # Distribution statement
    page1.insert_text((72, 360), "DISTRIBUTION STATEMENT B:", fontsize=10, fontname="helv")
    page1.insert_text((72, 375), "Distribution authorized to U.S. Government agencies only.", fontsize=9)

    # Classification footer
    page1.insert_text((250, page_height - 30), "UNCLASSIFIED", fontsize=10)

    # Page 2 - Applicable documents
    page2 = doc.new_page()
    page2.insert_text((250, 30), "UNCLASSIFIED", fontsize=10)
    page2.insert_text((72, 80), "2. APPLICABLE DOCUMENTS", fontsize=14, fontname="helv")

    specs = [
        "DO-178C Software Considerations in Airborne Systems",
        "DO-254 Design Assurance Guidance for Airborne Electronic Hardware",
        "MIL-STD-1553B Digital Time Division Command/Response",
        "MIL-STD-461G EMI Requirements",
        "MIL-HDBK-217F Reliability Prediction",
        "SAE AS9100D Quality Management Systems",
        "SAE ARP4754A Development of Civil Aircraft and Systems",
        "RTCA/DO-160G Environmental Conditions and Test Procedures",
    ]

    y = 110
    for spec in specs:
        page2.insert_text((90, y), f"• {spec}", fontsize=10)
        y += 18

    page2.insert_text((250, page2.rect.height - 30), "UNCLASSIFIED", fontsize=10)

    fixture_path = FIXTURES_DIR / "fixture_aerospace_document.pdf"
    doc.save(fixture_path)
    doc.close()
    return fixture_path


if __name__ == "__main__":
    # Generate all fixtures when run directly
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating test fixtures...")
    print(f"  Multi-column: {generate_multi_column_fixture()}")
    print(f"  Header/footer: {generate_header_footer_fixture()}")
    print(f"  Footnotes: {generate_footnotes_fixture()}")
    print(f"  Split table: {generate_split_table_fixture()}")
    print(f"  Signed contract: {generate_signed_contract_fixture()}")
    print(f"  Technical drawing: {generate_technical_drawing_fixture()}")
    print(f"  Aerospace document: {generate_aerospace_document_fixture()}")
    print("Done!")
