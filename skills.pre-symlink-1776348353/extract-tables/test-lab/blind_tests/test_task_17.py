"""Blind adversarial tests for Task 17: Extractor pipeline compatibility shim."""
import sys
import os
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")
FOO_PDF = os.path.join(FIXTURE_DIR, "foo.pdf")


@pytest.fixture(scope="module")
def compat():
    try:
        from compat import to_extractor_format, from_extractor_strategy
        return {
            "to_extractor_format": to_extractor_format,
            "from_extractor_strategy": from_extractor_strategy,
        }
    except ImportError as e:
        pytest.fail(f"Cannot import compat module: {e}")


@pytest.fixture(scope="module")
def sample_result():
    """Create a sample ExtractionResult for testing."""
    try:
        from extract_tables import read_pdf
        return read_pdf(FOO_PDF, pages="all")
    except ImportError:
        pytest.skip("read_pdf not available (Task 13 dependency)")


class TestToExtractorFormat:
    def test_returns_list_of_dicts(self, compat, sample_result):
        output = compat["to_extractor_format"](sample_result)
        assert isinstance(output, list), f"Must return list, got {type(output)}"
        assert len(output) >= 1, "foo.pdf should produce at least 1 table entry"
        assert isinstance(output[0], dict), f"Each entry must be dict, got {type(output[0])}"

    def test_has_required_keys(self, compat, sample_result):
        output = compat["to_extractor_format"](sample_result)
        required_keys = {"page_number", "bbox", "pandas_df"}
        for entry in output:
            for key in required_keys:
                assert key in entry, (
                    f"Missing required key '{key}' in extractor format. "
                    f"Got keys: {list(entry.keys())}"
                )

    def test_bbox_top_left_origin(self, compat, sample_result):
        """Bboxes in extractor format must be top-left origin."""
        output = compat["to_extractor_format"](sample_result)
        for entry in output:
            bbox = entry["bbox"]
            assert isinstance(bbox, (tuple, list)), f"bbox must be tuple/list, got {type(bbox)}"
            assert len(bbox) == 4, f"bbox must have 4 elements, got {len(bbox)}"
            x0, y0, x1, y1 = bbox
            assert y0 < y1, f"Top-left violation in extractor format: y0={y0} >= y1={y1}"

    def test_pandas_df_is_records(self, compat, sample_result):
        """pandas_df should be serializable (list of dicts or pandas DataFrame)."""
        output = compat["to_extractor_format"](sample_result)
        for entry in output:
            pdf_data = entry["pandas_df"]
            # Should be either a list of dicts (records) or a pandas DataFrame
            assert pdf_data is not None, "pandas_df should not be None"


class TestFromExtractorStrategy:
    def test_lattice_default(self, compat):
        params = compat["from_extractor_strategy"]("lattice_default")
        assert isinstance(params, dict), f"Must return dict, got {type(params)}"
        assert len(params) > 0, "Should return non-empty params dict"

    def test_lattice_strong(self, compat):
        params = compat["from_extractor_strategy"]("lattice_strong")
        assert isinstance(params, dict), f"Must return dict, got {type(params)}"

    def test_unknown_strategy_handled(self, compat):
        """Unknown strategy should return defaults or raise ValueError, not crash."""
        try:
            params = compat["from_extractor_strategy"]("nonexistent_strategy_xyz")
            assert isinstance(params, dict), "Should return default params for unknown strategy"
        except (ValueError, KeyError):
            pass  # Acceptable to raise for unknown strategy

    def test_stream_strategy(self, compat):
        params = compat["from_extractor_strategy"]("stream")
        assert isinstance(params, dict)
