"""Blind adversarial tests for Task 18: Full integration test + shadow logging."""
import sys
import os
import json
import subprocess
import pytest

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(SKILL_DIR, "src", "python"))

FIXTURE_DIR = os.path.join(SKILL_DIR, "tests", "fixtures")
FOO_PDF = os.path.join(FIXTURE_DIR, "foo.pdf")


class TestSanityScript:
    def test_sanity_sh_exists(self):
        sanity_path = os.path.join(SKILL_DIR, "sanity.sh")
        assert os.path.exists(sanity_path), f"sanity.sh not found at {sanity_path}"

    def test_sanity_sh_passes(self):
        sanity_path = os.path.join(SKILL_DIR, "sanity.sh")
        if not os.path.exists(sanity_path):
            pytest.skip("sanity.sh not found")
        result = subprocess.run(
            ["bash", sanity_path],
            cwd=SKILL_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        assert result.returncode == 0, (
            f"sanity.sh failed with exit code {result.returncode}\n"
            f"stdout: {result.stdout[-500:]}\n"
            f"stderr: {result.stderr[-500:]}"
        )


class TestShadowLogging:
    def test_shadow_jsonl_exists_after_extraction(self):
        """After running read_pdf, shadow.jsonl should have entries."""
        try:
            from extract_tables import read_pdf
            read_pdf(FOO_PDF, pages="all")
        except ImportError:
            pytest.skip("read_pdf not available")

        shadow_path = os.path.join(SKILL_DIR, "shadow.jsonl")
        if not os.path.exists(shadow_path):
            # Also check common alternative locations
            for alt in ["logs/shadow.jsonl", "data/shadow.jsonl"]:
                alt_path = os.path.join(SKILL_DIR, alt)
                if os.path.exists(alt_path):
                    shadow_path = alt_path
                    break

        assert os.path.exists(shadow_path), (
            f"shadow.jsonl not found after extraction. "
            f"Checked: {shadow_path}"
        )

    def test_shadow_entries_valid_json(self):
        shadow_path = os.path.join(SKILL_DIR, "shadow.jsonl")
        if not os.path.exists(shadow_path):
            for alt in ["logs/shadow.jsonl", "data/shadow.jsonl"]:
                alt_path = os.path.join(SKILL_DIR, alt)
                if os.path.exists(alt_path):
                    shadow_path = alt_path
                    break

        if not os.path.exists(shadow_path):
            pytest.skip("shadow.jsonl not found")

        with open(shadow_path) as f:
            lines = f.readlines()

        assert len(lines) > 0, "shadow.jsonl should have at least one entry"

        for i, line in enumerate(lines[-5:]):  # Check last 5 entries
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                assert isinstance(entry, dict), f"Line {i}: entry must be dict"
            except json.JSONDecodeError as e:
                pytest.fail(f"Line {i}: invalid JSON in shadow.jsonl: {e}")


class TestRunShCommands:
    def test_run_sh_exists(self):
        run_path = os.path.join(SKILL_DIR, "run.sh")
        assert os.path.exists(run_path), f"run.sh not found at {run_path}"

    def test_run_sh_extract(self):
        """run.sh extract should work on test PDF."""
        run_path = os.path.join(SKILL_DIR, "run.sh")
        if not os.path.exists(run_path):
            pytest.skip("run.sh not found")
        result = subprocess.run(
            ["bash", run_path, "extract", FOO_PDF, "--strategy", "auto"],
            cwd=SKILL_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        # Should succeed or at least not crash with unhandled exception
        assert result.returncode == 0, (
            f"run.sh extract failed: {result.stderr[-300:]}"
        )


class TestEndToEndDiversePDFs:
    @pytest.mark.parametrize("pdf_name", [
        "foo.pdf",
        "column_span_2.pdf",
        "health.pdf",
        "multiple_tables.pdf",
        "row_span_1.pdf",
    ])
    def test_diverse_pdf_extraction(self, pdf_name):
        """Each fixture PDF should extract without crashing."""
        pdf_path = os.path.join(FIXTURE_DIR, pdf_name)
        if not os.path.exists(pdf_path):
            pytest.skip(f"{pdf_name} not available")

        try:
            from extract_tables import read_pdf
        except ImportError:
            pytest.skip("read_pdf not available")

        result = read_pdf(pdf_path, pages="all")
        tables = result.tables if hasattr(result, "tables") else list(result)
        # Should not crash; tables may be empty for some PDFs
        assert isinstance(tables, list), f"{pdf_name}: result must be a list of tables"

        # All bboxes must be top-left
        for table in tables:
            x0, y0, x1, y1 = table.bbox
            assert y0 < y1, f"{pdf_name}: y0={y0} >= y1={y1}"
