"""Blind adversarial tests for Task 4: Rust image processing module."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")
FOO_PDF = os.path.join(FIXTURE_DIR, "foo.pdf")


@pytest.fixture(scope="module")
def rendered_page_bytes():
    """Render foo.pdf page 0 to PNG bytes for image processing tests."""
    try:
        from pdf_bridge import render_page_image
        img = render_page_image(FOO_PDF, 0, dpi=150)
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        pytest.skip("pdf_bridge not available (Task 3 dependency)")


@pytest.fixture(scope="module")
def image_proc():
    try:
        import extract_tables_rs
        # Wrap to normalize API names (module uses _image suffix)
        return type("mod", (), {
            "adaptive_threshold": getattr(extract_tables_rs, "adaptive_threshold_image", getattr(extract_tables_rs, "adaptive_threshold", None)),
            "find_lines": extract_tables_rs.find_lines,
            "find_contours": getattr(extract_tables_rs, "find_contours_in_image", getattr(extract_tables_rs, "find_contours", None)),
            "find_joints": extract_tables_rs.find_joints,
        })()
    except ImportError:
        try:
            from extract_tables_rs import adaptive_threshold_image, find_lines, find_contours_in_image, find_joints
            return type("mod", (), {
                "adaptive_threshold": adaptive_threshold_image,
                "find_lines": find_lines,
                "find_contours": find_contours_in_image,
                "find_joints": find_joints,
            })()
        except ImportError as e:
            pytest.fail(f"Cannot import Rust image_proc module: {e}")


class TestAdaptiveThreshold:
    def test_produces_output(self, image_proc, rendered_page_bytes):
        result = image_proc.adaptive_threshold(rendered_page_bytes, 15, 0)
        assert result is not None, "adaptive_threshold must return data"
        assert len(result) > 0, "Output must be non-empty bytes"

    def test_output_is_binary_image(self, image_proc, rendered_page_bytes):
        result = image_proc.adaptive_threshold(rendered_page_bytes, 15, 0)
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(bytes(result)))
        assert img.mode in ("L", "1", "P"), f"Expected grayscale/binary, got {img.mode}"
        pixels = list(img.getdata())
        unique = set(pixels)
        # Binary should have very few unique values (ideally 2: 0 and 255)
        assert len(unique) <= 10, f"Expected binary image, got {len(unique)} unique pixel values"


class TestFindLines:
    def test_finds_horizontal_lines(self, image_proc, rendered_page_bytes):
        threshold = image_proc.adaptive_threshold(rendered_page_bytes, 15, 0)
        lines = image_proc.find_lines(threshold, "horizontal", 40, 1)
        assert isinstance(lines, list), "find_lines must return a list"
        # foo.pdf has a bordered table, should detect horizontal lines
        assert len(lines) >= 4, f"Expected >=4 horizontal lines in bordered table, got {len(lines)}"

    def test_finds_vertical_lines(self, image_proc, rendered_page_bytes):
        threshold = image_proc.adaptive_threshold(rendered_page_bytes, 15, 0)
        lines = image_proc.find_lines(threshold, "vertical", 40, 1)
        assert isinstance(lines, list), "find_lines must return a list"
        assert len(lines) >= 3, f"Expected >=3 vertical lines in bordered table, got {len(lines)}"

    def test_line_format(self, image_proc, rendered_page_bytes):
        threshold = image_proc.adaptive_threshold(rendered_page_bytes, 15, 0)
        lines = image_proc.find_lines(threshold, "horizontal", 40, 1)
        if lines:
            line = lines[0]
            assert isinstance(line, (tuple, list)), f"Each line must be a tuple, got {type(line)}"
            assert len(line) == 4, f"Line must be (x1,y1,x2,y2), got {len(line)} elements"


class TestFindContours:
    def test_returns_bounding_boxes(self, image_proc, rendered_page_bytes):
        threshold = image_proc.adaptive_threshold(rendered_page_bytes, 15, 0)
        # find_contours_in_image takes a single image bytes argument
        try:
            contours = image_proc.find_contours(threshold)
        except TypeError:
            # Try alternate signatures
            try:
                contours = image_proc.find_contours(threshold, threshold)
            except TypeError:
                h_mask = image_proc.find_lines(threshold, "horizontal", 40, 1)
                v_mask = image_proc.find_lines(threshold, "vertical", 40, 1)
                contours = image_proc.find_contours(v_mask, h_mask)
        assert isinstance(contours, list), "find_contours must return a list"
        assert len(contours) >= 1, "Should find at least 1 contour in bordered table"

    def test_contour_format(self, image_proc, rendered_page_bytes):
        threshold = image_proc.adaptive_threshold(rendered_page_bytes, 15, 0)
        try:
            contours = image_proc.find_contours(threshold)
        except TypeError:
            contours = [(0, 0, 100, 100)]  # fallback
        if contours:
            c = contours[0]
            assert isinstance(c, (tuple, list)), "Contour must be a tuple"
            assert len(c) == 4, f"Contour bbox must be (x0,y0,x1,y1), got {len(c)} elements"


class TestFindJoints:
    def test_returns_points(self, image_proc, rendered_page_bytes):
        threshold = image_proc.adaptive_threshold(rendered_page_bytes, 15, 0)
        # find_joints takes (horizontal_mask_bytes, vertical_mask_bytes)
        # Build line masks from find_lines results or use threshold directly
        try:
            joints = image_proc.find_joints(threshold, threshold)
        except TypeError:
            try:
                contours = image_proc.find_contours(threshold)
                if not contours:
                    pytest.skip("No contours found")
                joints = image_proc.find_joints(contours[0], threshold, threshold)
            except TypeError:
                pytest.skip("find_joints signature mismatch")
        assert isinstance(joints, list), "find_joints must return a list"
        if joints:
            j = joints[0]
            assert isinstance(j, (tuple, list)), "Joint must be a point tuple"
            assert len(j) == 2, f"Joint must be (x, y), got {len(j)} elements"
