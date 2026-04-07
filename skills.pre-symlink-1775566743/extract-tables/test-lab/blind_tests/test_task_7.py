"""Blind adversarial tests for Task 7: Lattice parser."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")
FOO_PDF = os.path.join(FIXTURE_DIR, "foo.pdf")


@pytest.fixture(scope="module")
def lattice_parser():
    try:
        from extract_tables.parsers.lattice import LatticeParser
        return LatticeParser()
    except ImportError:
        try:
            from parsers.lattice import LatticeParser
            return LatticeParser()
        except ImportError as e:
            pytest.fail(f"Cannot import LatticeParser: {e}")


class TestLatticeExtraction:
    def test_extracts_tables_from_foo(self, lattice_parser):
        tables = lattice_parser.extract_tables(FOO_PDF, 0)
        assert isinstance(tables, list), "extract_tables must return a list"
        assert len(tables) >= 1, f"foo.pdf should have >=1 table, got {len(tables)}"

    def test_cell_content_nonempty(self, lattice_parser):
        tables = lattice_parser.extract_tables(FOO_PDF, 0)
        assert len(tables) > 0, "Need at least one table"
        table = tables[0]

        # Check that cells have content
        if hasattr(table, "cells"):
            cells_with_text = [c for c in table.cells if c.text and c.text.strip()]
            assert len(cells_with_text) > 0, "Table should have cells with text content"
        elif hasattr(table, "df"):
            df = table.df
            # Check polars DataFrame has data
            if hasattr(df, "shape"):
                assert df.shape[0] > 0, "DataFrame should have rows"
                assert df.shape[1] > 0, "DataFrame should have columns"

    def test_bboxes_top_left_origin(self, lattice_parser):
        """CRITICAL: All bboxes must be top-left origin."""
        tables = lattice_parser.extract_tables(FOO_PDF, 0)
        for table in tables:
            bbox = table.bbox
            assert isinstance(bbox, (tuple, list)), f"bbox must be tuple, got {type(bbox)}"
            assert len(bbox) == 4, f"bbox must be (x0, y0, x1, y1), got {len(bbox)} elements"
            x0, y0, x1, y1 = bbox
            assert y0 < y1, (
                f"Bottom-left coordinate leak! y0={y0} >= y1={y1}. "
                f"Bboxes must be top-left origin (y0 < y1)."
            )
            assert x0 < x1, f"x0={x0} should be < x1={x1}"

    def test_table_has_page_info(self, lattice_parser):
        tables = lattice_parser.extract_tables(FOO_PDF, 0)
        if tables:
            table = tables[0]
            assert hasattr(table, "page_number") or hasattr(table, "page_index"), \
                "Table must have page_number or page_index"

    def test_table_has_strategy(self, lattice_parser):
        tables = lattice_parser.extract_tables(FOO_PDF, 0)
        if tables:
            table = tables[0]
            if hasattr(table, "strategy"):
                assert "lattice" in table.strategy.lower(), \
                    f"Lattice parser should set strategy to 'lattice', got '{table.strategy}'"

    def test_row_span_pdf(self, lattice_parser):
        """Test with row_span_1.pdf if available."""
        row_span_pdf = os.path.join(FIXTURE_DIR, "row_span_1.pdf")
        if not os.path.exists(row_span_pdf):
            pytest.skip("row_span_1.pdf fixture not available")
        tables = lattice_parser.extract_tables(row_span_pdf, 0)
        assert isinstance(tables, list), "Must return list even for complex PDFs"
