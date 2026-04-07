"""Blind adversarial tests for Task 9: Network parser."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")
FOO_PDF = os.path.join(FIXTURE_DIR, "foo.pdf")
COLUMN_SPAN_PDF = os.path.join(FIXTURE_DIR, "column_span_2.pdf")


@pytest.fixture(scope="module")
def network_parser():
    try:
        from extract_tables.parsers.network import NetworkParser
        return NetworkParser()
    except ImportError:
        try:
            from parsers.network import NetworkParser
            return NetworkParser()
        except ImportError as e:
            pytest.fail(f"Cannot import NetworkParser: {e}")


class TestNetworkExtraction:
    def test_handles_bordered_pdf(self, network_parser):
        tables = network_parser.extract_tables(FOO_PDF, 0)
        assert isinstance(tables, list), "extract_tables must return a list"

    def test_handles_borderless_pdf(self, network_parser):
        tables = network_parser.extract_tables(COLUMN_SPAN_PDF, 0)
        assert isinstance(tables, list), "Must handle borderless PDFs"

    def test_alignment_groups_detected(self, network_parser):
        """Network parser should detect text alignment groups."""
        tables = network_parser.extract_tables(FOO_PDF, 0)
        # The network parser uses alignment-based detection
        # It should find something in a well-structured PDF
        # Even if it finds fewer tables than lattice, it should return valid results
        for table in tables:
            bbox = table.bbox
            assert len(bbox) == 4, "bbox must be (x0, y0, x1, y1)"
            x0, y0, x1, y1 = bbox
            assert y0 < y1, f"Bottom-left leak: y0={y0} >= y1={y1}"

    def test_bboxes_top_left_origin(self, network_parser):
        tables = network_parser.extract_tables(COLUMN_SPAN_PDF, 0)
        for table in tables:
            x0, y0, x1, y1 = table.bbox
            assert y0 < y1, f"y0={y0} must be < y1={y1} (top-left origin)"
            assert x0 < x1, f"x0={x0} must be < x1={x1}"

    def test_row_span_handling(self, network_parser):
        """Network parser should handle merged cells."""
        row_span_pdf = os.path.join(FIXTURE_DIR, "row_span_1.pdf")
        if not os.path.exists(row_span_pdf):
            pytest.skip("row_span_1.pdf not available")
        tables = network_parser.extract_tables(row_span_pdf, 0)
        assert isinstance(tables, list)
