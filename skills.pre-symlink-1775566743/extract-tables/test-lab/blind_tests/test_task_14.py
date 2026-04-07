"""Blind adversarial tests for Task 14: Camelot test suite compatibility."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")

# Test PDFs that Camelot handles well
COMPAT_PDFS = {
    "foo.pdf": {"min_tables": 1, "strategy": "lattice"},
    "column_span_2.pdf": {"min_tables": 1, "strategy": "stream"},
}


@pytest.fixture(scope="module")
def read_pdf():
    try:
        from extract_tables import read_pdf
        return read_pdf
    except ImportError as e:
        pytest.fail(f"Cannot import read_pdf: {e}")


@pytest.fixture(scope="module")
def camelot_read():
    """Try to import Camelot for comparison."""
    try:
        import camelot
        return camelot.read_pdf
    except ImportError:
        return None


class TestTableCountCompatibility:
    def test_foo_pdf_table_count(self, read_pdf):
        """foo.pdf should produce at least 1 table (Camelot produces 1)."""
        pdf_path = os.path.join(FIXTURE_DIR, "foo.pdf")
        result = read_pdf(pdf_path, pages="all")
        tables = result.tables if hasattr(result, "tables") else list(result)
        assert len(tables) >= 1, f"foo.pdf: expected >=1 table, got {len(tables)}"

    def test_column_span_table_count(self, read_pdf):
        """column_span_2.pdf should produce at least 1 table."""
        pdf_path = os.path.join(FIXTURE_DIR, "column_span_2.pdf")
        if not os.path.exists(pdf_path):
            pytest.skip("column_span_2.pdf not available")
        result = read_pdf(pdf_path, pages="all")
        tables = result.tables if hasattr(result, "tables") else list(result)
        assert len(tables) >= 1, f"column_span_2.pdf: expected >=1 table, got {len(tables)}"

    @pytest.mark.skipif(
        not os.path.exists(os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "tests", "fixtures", "multiple_tables.pdf"
        )),
        reason="multiple_tables.pdf not available"
    )
    def test_multiple_tables_count(self, read_pdf):
        pdf_path = os.path.join(FIXTURE_DIR, "multiple_tables.pdf")
        result = read_pdf(pdf_path, pages="all")
        tables = result.tables if hasattr(result, "tables") else list(result)
        assert len(tables) >= 2, f"multiple_tables.pdf: expected >=2 tables, got {len(tables)}"


class TestCoordinateConsistency:
    def test_all_bboxes_top_left(self, read_pdf):
        """CRITICAL: Zero coordinate assertion failures allowed."""
        for pdf_name in COMPAT_PDFS:
            pdf_path = os.path.join(FIXTURE_DIR, pdf_name)
            if not os.path.exists(pdf_path):
                continue
            result = read_pdf(pdf_path, pages="all")
            tables = result.tables if hasattr(result, "tables") else list(result)
            for table in tables:
                x0, y0, x1, y1 = table.bbox
                assert y0 < y1, (
                    f"{pdf_name}: y0={y0} >= y1={y1} - not top-left origin"
                )
                assert x0 < x1, f"{pdf_name}: x0={x0} >= x1={x1}"


class TestCamelotComparison:
    def test_table_count_within_tolerance(self, read_pdf, camelot_read):
        """If Camelot available, verify >=95% table count match."""
        if camelot_read is None:
            pytest.skip("Camelot not installed for comparison")

        match = 0
        total = 0
        for pdf_name in COMPAT_PDFS:
            pdf_path = os.path.join(FIXTURE_DIR, pdf_name)
            if not os.path.exists(pdf_path):
                continue
            total += 1

            strategy = COMPAT_PDFS[pdf_name]["strategy"]
            camelot_tables = camelot_read(pdf_path, flavor=strategy, pages="all")
            native_result = read_pdf(pdf_path, pages="all")
            native_tables = native_result.tables if hasattr(native_result, "tables") else list(native_result)

            if len(native_tables) == len(camelot_tables):
                match += 1

        if total > 0:
            ratio = match / total
            assert ratio >= 0.95, f"Table count match: {ratio:.0%} < 95%"
