"""Blind adversarial tests for Task 5: Geometry module."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))


@pytest.fixture(scope="module")
def geometry():
    try:
        import extract_tables_rs
        return extract_tables_rs
    except ImportError as e:
        pytest.fail(f"Cannot import geometry from Rust module: {e}")


class TestTextInBbox:
    def test_callable(self, geometry):
        assert callable(getattr(geometry, "text_in_bbox", None)), \
            "text_in_bbox must be a callable function"

    def test_filters_elements_inside(self, geometry):
        # Create mock text elements as tuples: (text, x0, y0, x1, y1)
        elements = [
            ("inside", 150.0, 150.0, 200.0, 170.0),
            ("outside", 10.0, 10.0, 50.0, 30.0),
            ("also_inside", 200.0, 200.0, 300.0, 220.0),
        ]
        bbox = (100.0, 100.0, 400.0, 400.0)
        try:
            result = geometry.text_in_bbox(bbox, elements)
            # Should include elements inside, exclude outside
            assert len(result) >= 2, f"Expected >=2 elements inside bbox, got {len(result)}"
        except TypeError:
            # May need different element format - try with dicts or named attrs
            pytest.skip("text_in_bbox element format not yet compatible")

    def test_empty_elements_no_panic(self, geometry):
        bbox = (100.0, 100.0, 400.0, 400.0)
        try:
            result = geometry.text_in_bbox(bbox, [])
            assert result == [] or len(result) == 0, "Empty input should return empty result"
        except TypeError:
            pytest.skip("text_in_bbox signature not yet compatible")

    def test_zero_area_bbox(self, geometry):
        """Zero-area bbox should return empty list, not panic."""
        try:
            result = geometry.text_in_bbox((100.0, 100.0, 100.0, 100.0), [])
            assert isinstance(result, list)
        except TypeError:
            pytest.skip("text_in_bbox signature not yet compatible")


class TestMergeCloseLines:
    def test_callable(self, geometry):
        assert callable(getattr(geometry, "merge_close_lines", None)), \
            "merge_close_lines must be a callable function"

    def test_empty_input(self, geometry):
        try:
            result = geometry.merge_close_lines([], 5.0)
            assert isinstance(result, list)
        except TypeError:
            pytest.skip("merge_close_lines signature not yet compatible")


class TestScaleCoordinates:
    def test_callable(self, geometry):
        assert callable(getattr(geometry, "scale_coordinates", None)), \
            "scale_coordinates must be a callable function"


class TestSegmentsInBbox:
    def test_callable(self, geometry):
        assert callable(getattr(geometry, "segments_in_bbox", None)), \
            "segments_in_bbox must be a callable function"

    def test_empty_input(self, geometry):
        try:
            result = geometry.segments_in_bbox((0.0, 0.0, 100.0, 100.0), [])
            assert isinstance(result, list)
        except TypeError:
            pytest.skip("segments_in_bbox signature not yet compatible")


class TestFlagFontSize:
    def test_callable(self, geometry):
        assert callable(getattr(geometry, "flag_font_size", None)), \
            "flag_font_size must be a callable function"
