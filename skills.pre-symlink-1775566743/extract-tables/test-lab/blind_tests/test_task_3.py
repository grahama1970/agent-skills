"""Blind adversarial tests for Task 3: pdf_bridge text extraction bridge."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")
FOO_PDF = os.path.join(FIXTURE_DIR, "foo.pdf")


@pytest.fixture(scope="module")
def pdf_bridge():
    try:
        from pdf_bridge import extract_text_elements, render_page_image, get_page_dimensions, get_page_count
        return {
            "extract_text_elements": extract_text_elements,
            "render_page_image": render_page_image,
            "get_page_dimensions": get_page_dimensions,
            "get_page_count": get_page_count,
        }
    except ImportError as e:
        pytest.fail(f"Cannot import pdf_bridge: {e}")


class TestExtractTextElements:
    def test_returns_list(self, pdf_bridge):
        elements = pdf_bridge["extract_text_elements"](FOO_PDF, 0)
        assert isinstance(elements, list), "extract_text_elements must return a list"
        assert len(elements) > 0, "foo.pdf page 0 should have text elements"

    def test_elements_have_coordinates(self, pdf_bridge):
        elements = pdf_bridge["extract_text_elements"](FOO_PDF, 0)
        for elem in elements[:5]:
            assert hasattr(elem, "x0") or (isinstance(elem, (tuple, list)) and len(elem) >= 5), \
                f"TextElement must have coordinate attributes or be a tuple with >=5 elements"

    def test_coordinates_are_top_left_origin(self, pdf_bridge):
        """CRITICAL: y0 must be less than y1 (top-left origin, y increases downward)."""
        elements = pdf_bridge["extract_text_elements"](FOO_PDF, 0)
        for elem in elements:
            if hasattr(elem, "y0"):
                y0, y1 = elem.y0, elem.y1
            elif hasattr(elem, "bbox"):
                _, y0, _, y1 = elem.bbox if len(elem.bbox) == 4 else (0, 0, 0, 0)
            else:
                continue
            assert y0 <= y1, (
                f"Bottom-left coordinate leak detected! y0={y0} > y1={y1}. "
                f"All coordinates must be top-left origin (y0 < y1)."
            )

    def test_no_negative_coordinates(self, pdf_bridge):
        elements = pdf_bridge["extract_text_elements"](FOO_PDF, 0)
        for elem in elements:
            if hasattr(elem, "x0"):
                assert elem.x0 >= 0, f"Negative x0: {elem.x0}"
                assert elem.y0 >= 0, f"Negative y0: {elem.y0}"

    def test_coordinates_within_page_bounds(self, pdf_bridge):
        width, height = pdf_bridge["get_page_dimensions"](FOO_PDF, 0)
        elements = pdf_bridge["extract_text_elements"](FOO_PDF, 0)
        for elem in elements:
            if hasattr(elem, "x1"):
                assert elem.x1 <= width + 5, f"x1={elem.x1} exceeds page width={width}"
                assert elem.y1 <= height + 5, f"y1={elem.y1} exceeds page height={height}"

    def test_text_content_nonempty(self, pdf_bridge):
        elements = pdf_bridge["extract_text_elements"](FOO_PDF, 0)
        texts = [e.text if hasattr(e, "text") else str(e) for e in elements]
        nonempty = [t for t in texts if t.strip()]
        assert len(nonempty) > 0, "Should have non-empty text elements"


class TestRenderPageImage:
    def test_returns_pil_image(self, pdf_bridge):
        from PIL import Image
        img = pdf_bridge["render_page_image"](FOO_PDF, 0)
        assert isinstance(img, Image.Image), "render_page_image must return PIL.Image"

    def test_image_dimensions_positive(self, pdf_bridge):
        img = pdf_bridge["render_page_image"](FOO_PDF, 0)
        assert img.width > 0, "Image width must be > 0"
        assert img.height > 0, "Image height must be > 0"

    def test_dpi_affects_size(self, pdf_bridge):
        img_low = pdf_bridge["render_page_image"](FOO_PDF, 0, dpi=72)
        img_high = pdf_bridge["render_page_image"](FOO_PDF, 0, dpi=150)
        assert img_high.width > img_low.width, "Higher DPI should produce larger image"


class TestGetPageDimensions:
    def test_returns_tuple(self, pdf_bridge):
        dims = pdf_bridge["get_page_dimensions"](FOO_PDF, 0)
        assert isinstance(dims, (tuple, list)), "get_page_dimensions must return tuple"
        assert len(dims) == 2, "Must return (width, height)"

    def test_dimensions_positive(self, pdf_bridge):
        w, h = pdf_bridge["get_page_dimensions"](FOO_PDF, 0)
        assert w > 0 and h > 0, f"Dimensions must be positive: ({w}, {h})"

    def test_letter_size_approximate(self, pdf_bridge):
        w, h = pdf_bridge["get_page_dimensions"](FOO_PDF, 0)
        # US Letter is 612x792 points
        assert 500 < w < 700, f"Width {w} doesn't look like letter size"
        assert 700 < h < 900, f"Height {h} doesn't look like letter size"


class TestGetPageCount:
    def test_returns_int(self, pdf_bridge):
        count = pdf_bridge["get_page_count"](FOO_PDF)
        assert isinstance(count, int), "get_page_count must return int"

    def test_positive_count(self, pdf_bridge):
        count = pdf_bridge["get_page_count"](FOO_PDF)
        assert count >= 1, "foo.pdf must have at least 1 page"
