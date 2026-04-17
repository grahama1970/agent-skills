"""Blind adversarial tests for Task 6: Table title extraction."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))


@pytest.fixture(scope="module")
def title_extractor():
    try:
        from title_extractor import extract_title_from_context, infer_title_vlm
        return {
            "extract_title_from_context": extract_title_from_context,
            "infer_title_vlm": infer_title_vlm,
        }
    except ImportError as e:
        pytest.fail(f"Cannot import title_extractor: {e}")


class TestExtractTitleFromContext:
    def test_finds_table_n_pattern(self, title_extractor):
        """Should find 'Table N:' pattern in text above the table."""
        # Simulate text elements above a table at y=200
        class FakeText:
            def __init__(self, text, x0, y0, x1, y1, font_size=12.0, is_bold=False):
                self.text = text
                self.x0 = x0
                self.y0 = y0
                self.x1 = x1
                self.y1 = y1
                self.font_size = font_size
                self.font_name = "Arial"
                self.is_bold = is_bold

        elements = [
            FakeText("Table 1: Revenue Summary", 72.0, 160.0, 300.0, 175.0, font_size=14.0, is_bold=True),
            FakeText("Some cell content", 72.0, 210.0, 200.0, 225.0),
            FakeText("More data", 200.0, 210.0, 350.0, 225.0),
        ]
        table_bbox = (72.0, 200.0, 540.0, 500.0)
        page_dims = (612.0, 792.0)

        title = title_extractor["extract_title_from_context"](elements, table_bbox, page_dims)
        assert title is not None, "Should find 'Table 1: Revenue Summary'"
        assert "Revenue" in title or "Table 1" in title, f"Title should contain key text, got: {title}"

    def test_returns_none_when_no_title(self, title_extractor):
        """Should return None when no title text above table."""
        class FakeText:
            def __init__(self, text, x0, y0, x1, y1, font_size=12.0, is_bold=False):
                self.text = text
                self.x0 = x0
                self.y0 = y0
                self.x1 = x1
                self.y1 = y1
                self.font_size = font_size
                self.font_name = "Arial"
                self.is_bold = is_bold

        elements = [
            FakeText("random paragraph text here", 72.0, 50.0, 300.0, 65.0),
            FakeText("cell data A", 72.0, 210.0, 200.0, 225.0),
        ]
        table_bbox = (72.0, 200.0, 540.0, 500.0)
        page_dims = (612.0, 792.0)

        title = title_extractor["extract_title_from_context"](elements, table_bbox, page_dims)
        # Should be None since no title pattern found
        assert title is None, f"Expected None when no title pattern, got: {title}"

    def test_table_dot_pattern(self, title_extractor):
        """Should also match 'Table N.' pattern."""
        class FakeText:
            def __init__(self, text, x0, y0, x1, y1, font_size=12.0, is_bold=False):
                self.text = text
                self.x0 = x0
                self.y0 = y0
                self.x1 = x1
                self.y1 = y1
                self.font_size = font_size
                self.font_name = "Arial"
                self.is_bold = is_bold

        elements = [
            FakeText("Table 3. Quarterly Expenses", 72.0, 155.0, 350.0, 170.0, font_size=13.0, is_bold=True),
        ]
        table_bbox = (72.0, 200.0, 540.0, 500.0)
        page_dims = (612.0, 792.0)

        title = title_extractor["extract_title_from_context"](elements, table_bbox, page_dims)
        assert title is not None, "Should find 'Table 3.' pattern"


class TestInferTitleVLM:
    def test_returns_dict_with_ai_title(self, title_extractor):
        """VLM inference must return dict with ai_title key."""
        # This should gracefully degrade if VLM unavailable
        result = title_extractor["infer_title_vlm"]("/nonexistent/path.png", "some context")
        assert isinstance(result, dict), f"infer_title_vlm must return dict, got {type(result)}"
        assert "ai_title" in result, f"Result dict must have 'ai_title' key, got keys: {list(result.keys())}"

    def test_graceful_degradation(self, title_extractor):
        """Must not raise even with invalid inputs."""
        result = title_extractor["infer_title_vlm"]("", "")
        assert isinstance(result, dict), "Must return dict even on failure"
        assert "ai_title" in result, "Must have ai_title key even on failure"
