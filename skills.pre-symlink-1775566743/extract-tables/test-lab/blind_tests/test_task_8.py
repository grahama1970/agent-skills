"""Blind adversarial tests for Task 8: Stream parser."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")
COLUMN_SPAN_PDF = os.path.join(FIXTURE_DIR, "column_span_2.pdf")


@pytest.fixture(scope="module")
def stream_parser():
    try:
        from extract_tables.parsers.stream import StreamParser
        return StreamParser()
    except ImportError:
        try:
            from parsers.stream import StreamParser
            return StreamParser()
        except ImportError as e:
            pytest.fail(f"Cannot import StreamParser: {e}")


class TestStreamExtraction:
    def test_extracts_tables_from_borderless(self, stream_parser):
        tables = stream_parser.extract_tables(COLUMN_SPAN_PDF, 0)
        assert isinstance(tables, list), "extract_tables must return a list"
        assert len(tables) >= 1, f"column_span_2.pdf should have >=1 table, got {len(tables)}"

    def test_bboxes_top_left_origin(self, stream_parser):
        """CRITICAL: All bboxes must be top-left origin."""
        tables = stream_parser.extract_tables(COLUMN_SPAN_PDF, 0)
        for table in tables:
            bbox = table.bbox
            assert isinstance(bbox, (tuple, list)), f"bbox must be tuple, got {type(bbox)}"
            assert len(bbox) == 4, f"bbox must be (x0, y0, x1, y1)"
            x0, y0, x1, y1 = bbox
            assert y0 < y1, (
                f"Bottom-left coordinate leak! y0={y0} >= y1={y1}. "
                f"Stream parser bboxes must be top-left origin."
            )
            assert x0 < x1, f"x0={x0} should be < x1={x1}"

    def test_has_dataframe(self, stream_parser):
        tables = stream_parser.extract_tables(COLUMN_SPAN_PDF, 0)
        if tables:
            table = tables[0]
            assert hasattr(table, "df"), "Table must have df attribute"
            df = table.df
            assert df is not None, "DataFrame should not be None"
            if hasattr(df, "shape"):
                assert df.shape[0] > 0, "DataFrame should have rows"

    def test_table_strategy_is_stream(self, stream_parser):
        tables = stream_parser.extract_tables(COLUMN_SPAN_PDF, 0)
        if tables:
            table = tables[0]
            if hasattr(table, "strategy"):
                assert "stream" in table.strategy.lower(), \
                    f"Stream parser should set strategy to 'stream', got '{table.strategy}'"

    def test_handles_empty_page_gracefully(self, stream_parser):
        """Should return empty list for page with no tables, not crash."""
        # Try a page that likely doesn't exist or has no tables
        try:
            tables = stream_parser.extract_tables(COLUMN_SPAN_PDF, 99)
            assert isinstance(tables, list)
        except (IndexError, ValueError):
            pass  # Acceptable to raise for invalid page
