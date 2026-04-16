"""Blind adversarial tests for Task 11: Cross-page table merger."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))


@pytest.fixture(scope="module")
def merger():
    try:
        from merger import merge_split_tables
        return merge_split_tables
    except ImportError as e:
        pytest.fail(f"Cannot import merger: {e}")


@pytest.fixture(scope="module")
def make_table():
    """Factory for creating mock Table objects for merger tests."""
    try:
        from models import Table, Cell
    except ImportError:
        pytest.fail("Cannot import Table/Cell from models")

    import polars as pl

    def _make(page_number, bbox, col_count=3, title=None, row_data=None):
        cells = []
        df_data = {}
        for c in range(col_count):
            col_name = f"col_{c}"
            df_data[col_name] = [f"val_{c}_r{r}" for r in range(3)]

        df = pl.DataFrame(df_data)

        return Table(
            cells=cells,
            page_number=page_number,
            page_index=page_number - 1,
            bbox=bbox,
            strategy="lattice",
            accuracy=95.0,
            whitespace=5.0,
            fragmentation=0.0,
            title=title,
            ai_title=None,
            ai_description=None,
            df=df,
        )

    return _make


class TestSameColumnMerge:
    def test_consecutive_pages_same_columns_merge(self, merger, make_table):
        """Tables on consecutive pages with same column count should merge."""
        t1 = make_table(3, (72.0, 100.0, 540.0, 700.0), col_count=4)
        t2 = make_table(4, (72.0, 50.0, 540.0, 400.0), col_count=4)
        result = merger([t1, t2])
        # Should merge into 1 table (or fewer than 2)
        assert len(result) <= 1, (
            f"Two tables with same columns on consecutive pages should merge, "
            f"got {len(result)} tables"
        )

    def test_different_columns_no_merge(self, merger, make_table):
        """Tables with different column counts should NOT merge."""
        t1 = make_table(1, (72.0, 100.0, 540.0, 700.0), col_count=3)
        t2 = make_table(2, (72.0, 50.0, 540.0, 400.0), col_count=5)
        result = merger([t1, t2])
        assert len(result) == 2, (
            f"Tables with different column counts should NOT merge, "
            f"got {len(result)} tables"
        )

    def test_non_consecutive_pages_no_merge(self, merger, make_table):
        """Tables on non-consecutive pages should NOT merge."""
        t1 = make_table(1, (72.0, 100.0, 540.0, 700.0), col_count=3)
        t2 = make_table(5, (72.0, 50.0, 540.0, 400.0), col_count=3)
        result = merger([t1, t2])
        assert len(result) == 2, "Non-consecutive pages should not merge"


class TestContinuedTitle:
    def test_continued_triggers_merge(self, merger, make_table):
        """'continued' in title should trigger merge even with slight mismatch."""
        t1 = make_table(3, (72.0, 100.0, 540.0, 700.0), col_count=4, title="Table 5")
        t2 = make_table(4, (72.0, 50.0, 540.0, 400.0), col_count=4, title="Table 5 (continued)")
        result = merger([t1, t2])
        assert len(result) <= 1, "'continued' title should trigger merge"


class TestMergedTableStructure:
    def test_merged_has_components(self, merger, make_table):
        """Merged table must have components list tracking originals."""
        t1 = make_table(3, (72.0, 100.0, 540.0, 700.0), col_count=4)
        t2 = make_table(4, (72.0, 50.0, 540.0, 400.0), col_count=4)
        result = merger([t1, t2])
        if len(result) == 1:
            merged = result[0]
            assert hasattr(merged, "components"), "Merged table must have 'components' attribute"
            if merged.components is not None:
                assert len(merged.components) >= 2, \
                    f"Components should list both originals, got {len(merged.components)}"

    def test_single_table_passthrough(self, merger, make_table):
        """Single table should pass through unchanged."""
        t1 = make_table(1, (72.0, 100.0, 540.0, 700.0), col_count=3)
        result = merger([t1])
        assert len(result) == 1, "Single table should pass through"

    def test_empty_input(self, merger):
        """Empty input should return empty list."""
        result = merger([])
        assert result == [] or len(result) == 0
