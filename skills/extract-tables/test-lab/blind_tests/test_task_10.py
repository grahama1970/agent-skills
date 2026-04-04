"""Blind adversarial tests for Task 10: Hybrid parser."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")
FOO_PDF = os.path.join(FIXTURE_DIR, "foo.pdf")
HEALTH_PDF = os.path.join(FIXTURE_DIR, "health.pdf")
MULTIPLE_PDF = os.path.join(FIXTURE_DIR, "multiple_tables.pdf")


@pytest.fixture(scope="module")
def hybrid_parser():
    try:
        from extract_tables.parsers.hybrid import HybridParser
        return HybridParser()
    except ImportError:
        try:
            from parsers.hybrid import HybridParser
            return HybridParser()
        except ImportError as e:
            pytest.fail(f"Cannot import HybridParser: {e}")


class TestHybridExtraction:
    def test_finds_tables_bordered(self, hybrid_parser):
        tables = hybrid_parser.extract_tables(FOO_PDF, 0)
        assert isinstance(tables, list), "extract_tables must return a list"
        assert len(tables) >= 1, "Should find at least 1 table in bordered PDF"

    def test_finds_tables_complex_layout(self, hybrid_parser):
        """Hybrid should handle complex layouts that pure lattice might miss."""
        if not os.path.exists(HEALTH_PDF):
            pytest.skip("health.pdf not available")
        tables = hybrid_parser.extract_tables(HEALTH_PDF, 0)
        assert isinstance(tables, list)

    def test_no_duplicate_tables(self, hybrid_parser):
        """Hybrid merges lattice+network results; should deduplicate overlaps."""
        tables = hybrid_parser.extract_tables(FOO_PDF, 0)
        if len(tables) >= 2:
            # Check no two tables have >80% overlap
            for i, t1 in enumerate(tables):
                for j, t2 in enumerate(tables):
                    if i >= j:
                        continue
                    x0_1, y0_1, x1_1, y1_1 = t1.bbox
                    x0_2, y0_2, x1_2, y1_2 = t2.bbox
                    # Compute IoU
                    ix0 = max(x0_1, x0_2)
                    iy0 = max(y0_1, y0_2)
                    ix1 = min(x1_1, x1_2)
                    iy1 = min(y1_1, y1_2)
                    if ix0 < ix1 and iy0 < iy1:
                        inter = (ix1 - ix0) * (iy1 - iy0)
                        area1 = (x1_1 - x0_1) * (y1_1 - y0_1)
                        area2 = (x1_2 - x0_2) * (y1_2 - y0_2)
                        union = area1 + area2 - inter
                        iou = inter / union if union > 0 else 0
                        assert iou < 0.8, (
                            f"Tables {i} and {j} have IoU={iou:.2f} - possible duplicate"
                        )

    def test_bboxes_top_left(self, hybrid_parser):
        tables = hybrid_parser.extract_tables(FOO_PDF, 0)
        for table in tables:
            x0, y0, x1, y1 = table.bbox
            assert y0 < y1, f"Top-left violation: y0={y0} >= y1={y1}"
