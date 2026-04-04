"""Blind adversarial tests for Task 13: Full pipeline read_pdf()."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")
FOO_PDF = os.path.join(FIXTURE_DIR, "foo.pdf")
MULTIPLE_PDF = os.path.join(FIXTURE_DIR, "multiple_tables.pdf")


@pytest.fixture(scope="module")
def read_pdf():
    try:
        from extract_tables import read_pdf
        return read_pdf
    except ImportError:
        try:
            sys.path.insert(0, SKILL_DIR)
            from src.python.extract_tables import read_pdf
            return read_pdf
        except ImportError as e:
            pytest.fail(f"Cannot import read_pdf: {e}")


class TestReadPdfBasic:
    def test_returns_extraction_result(self, read_pdf):
        result = read_pdf(FOO_PDF, pages="all")
        assert result is not None, "read_pdf must return a result"
        # Check it's an ExtractionResult or similar
        assert hasattr(result, "tables") or hasattr(result, "__iter__"), \
            "Result must have 'tables' attribute or be iterable"

    def test_tables_have_required_fields(self, read_pdf):
        result = read_pdf(FOO_PDF, pages="all")
        tables = result.tables if hasattr(result, "tables") else list(result)
        assert len(tables) >= 1, "foo.pdf should produce at least 1 table"

        table = tables[0]
        assert hasattr(table, "page_number"), "Table must have page_number"
        assert hasattr(table, "bbox"), "Table must have bbox"
        assert hasattr(table, "df"), "Table must have df (DataFrame)"

    def test_bbox_top_left_origin(self, read_pdf):
        """CRITICAL: All bboxes must be top-left origin."""
        result = read_pdf(FOO_PDF, pages="all")
        tables = result.tables if hasattr(result, "tables") else list(result)
        for table in tables:
            x0, y0, x1, y1 = table.bbox
            assert y0 < y1, f"Top-left violation: y0={y0} >= y1={y1}"
            assert x0 < x1, f"x0={x0} >= x1={x1}"

    def test_df_is_polars(self, read_pdf):
        import polars as pl
        result = read_pdf(FOO_PDF, pages="all")
        tables = result.tables if hasattr(result, "tables") else list(result)
        if tables:
            df = tables[0].df
            assert isinstance(df, pl.DataFrame), \
                f"df should be polars DataFrame, got {type(df)}"


class TestReadingOrder:
    def test_tables_sorted_by_page_y_x(self, read_pdf):
        """Tables must be sorted by (page_number, y0, x0) - reading order."""
        if not os.path.exists(MULTIPLE_PDF):
            pytest.skip("multiple_tables.pdf not available")
        result = read_pdf(MULTIPLE_PDF, pages="all")
        tables = result.tables if hasattr(result, "tables") else list(result)
        if len(tables) < 2:
            pytest.skip("Need multiple tables for ordering test")

        for i in range(len(tables) - 1):
            t1, t2 = tables[i], tables[i + 1]
            p1 = t1.page_number
            p2 = t2.page_number
            if p1 == p2:
                y0_1 = t1.bbox[1]
                y0_2 = t2.bbox[1]
                if abs(y0_1 - y0_2) > 5:  # not same row
                    assert y0_1 <= y0_2, (
                        f"Tables not in reading order: table {i} y0={y0_1} > table {i+1} y0={y0_2}"
                    )
            else:
                assert p1 <= p2, (
                    f"Tables not sorted by page: {p1} > {p2}"
                )


class TestResultIterable:
    def test_indexable(self, read_pdf):
        result = read_pdf(FOO_PDF, pages="all")
        # Should support result[0]
        try:
            first = result[0]
            assert first is not None
        except (TypeError, IndexError):
            pytest.fail("ExtractionResult must be indexable: result[0]")

    def test_iterable(self, read_pdf):
        result = read_pdf(FOO_PDF, pages="all")
        count = 0
        for table in result:
            count += 1
        assert count >= 1, "Should iterate over at least 1 table"

    def test_has_pages_processed(self, read_pdf):
        result = read_pdf(FOO_PDF, pages="all")
        if hasattr(result, "pages_processed"):
            assert result.pages_processed >= 1
