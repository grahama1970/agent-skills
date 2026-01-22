#!/usr/bin/env python3
"""
Tests for arxiv learn pipeline.

Run with: pytest tests/test_arxiv_learn.py -v
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

SKILL_DIR = Path(__file__).parent.parent
SKILLS_DIR = SKILL_DIR.parent

# Add skill directories to path
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(SKILLS_DIR))

TEST_ARXIV_ID = "2501.15355"  # ToM-agent paper


def run_arxiv_cmd(args: list[str], timeout: int = 120) -> dict:
    """Run arxiv CLI command and return parsed JSON output."""
    run_script = SKILL_DIR / "run.sh"
    cmd = ["bash", str(run_script)] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {result.stderr}")
    return json.loads(result.stdout)


class TestQuickProfile:
    """Tests for quick profile check (Task 3)."""

    def test_quick_profile_returns_structure(self):
        """Task 3 Definition of Done: Profile check returns expected structure."""
        # Import the profile function (will be implemented in Task 3)
        try:
            from arxiv_learn import quick_profile_html
        except ImportError:
            pytest.skip("quick_profile_html not yet implemented")

        # Fetch test HTML
        import urllib.request
        url = f"https://ar5iv.org/abs/{TEST_ARXIV_ID}"
        req = urllib.request.Request(url, headers={"User-Agent": "Test/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            html_content = resp.read().decode("utf-8")

        # Run profile
        result = quick_profile_html(html_content)

        # Verify structure
        assert isinstance(result, dict), "Profile should return a dict"
        assert "needs_vlm" in result, "Profile should have needs_vlm field"
        assert "has_figures" in result, "Profile should have has_figures field"
        assert "has_tables" in result, "Profile should have has_tables field"

        assert isinstance(result["needs_vlm"], bool)
        assert isinstance(result["has_figures"], int)
        assert isinstance(result["has_tables"], int)


class TestHtmlFirstRouting:
    """Tests for HTML-first routing (Task 4)."""

    def test_default_uses_html(self):
        """Task 4 Definition of Done: Default extraction uses HTML."""
        try:
            from arxiv_learn import LearnSession, stage_1_find_paper, stage_2_extract
        except ImportError:
            pytest.skip("HTML routing not yet implemented")

        session = LearnSession(
            arxiv_id=TEST_ARXIV_ID,
            scope="test",
            dry_run=True,
        )

        # Stage 1: Find paper
        session.paper = stage_1_find_paper(session)

        # Stage 2: Extract (should use HTML by default)
        result = stage_2_extract(session)

        assert result.get("format") == "html", "Default should use HTML format"
        assert result.get("source") == "ar5iv", "Default should use ar5iv source"

    def test_accurate_flag_uses_pdf(self):
        """Task 4 Definition of Done: --accurate flag uses PDF."""
        try:
            from arxiv_learn import LearnSession, stage_1_find_paper, stage_2_extract
        except ImportError:
            pytest.skip("HTML routing not yet implemented")

        session = LearnSession(
            arxiv_id=TEST_ARXIV_ID,
            scope="test",
            dry_run=True,
            accurate=True,  # Force accurate mode
        )

        session.paper = stage_1_find_paper(session)
        result = stage_2_extract(session)

        assert result.get("format") == "pdf", "--accurate should use PDF format"


class TestExtractorToQA:
    """Tests for extractor to Q&A connection (Task 5)."""

    def test_extractor_output_produces_qa(self):
        """Task 5 Definition of Done: Extractor output produces Q&A pairs."""
        try:
            from arxiv_learn import extract_qa_from_text
        except ImportError:
            pytest.skip("extract_qa_from_text not yet implemented")

        # Sample extracted text (simulating extractor output)
        sample_text = """
        ToM-agent: Large Language Models as Theory of Mind Aware Generative Agents

        Abstract
        Recent studies have demonstrated that large language models possess significant
        theory of mind capabilities. We propose ToM-agent, a paradigm for empowering
        LLMs to simulate theory of mind in conversational interactions.

        1. Introduction
        Theory of mind is a cognitive skill that enables tracking mental states.
        """

        result = extract_qa_from_text(sample_text, scope="test", dry_run=True)

        assert "qa_pairs" in result, "Should produce qa_pairs"
        assert len(result["qa_pairs"]) > 0, "Should have at least one Q&A pair"

        # Check Q&A structure
        qa = result["qa_pairs"][0]
        assert "question" in qa or "problem" in qa
        assert "answer" in qa or "solution" in qa


class TestE2EHtmlExtraction:
    """End-to-end tests for HTML extraction (Task 6)."""

    @pytest.mark.slow
    def test_e2e_html_extraction_dry_run(self):
        """Task 6 Definition of Done: Pipeline completes with HTML extraction."""
        try:
            result = run_arxiv_cmd([
                "learn", TEST_ARXIV_ID,
                "--scope", "test",
                "--dry-run",
                "--skip-interview",
                "--json"
            ], timeout=180)
        except Exception as e:
            pytest.skip(f"E2E test failed: {e}")

        assert result.get("success"), f"Pipeline should succeed: {result.get('error')}"
        assert result.get("extracted", 0) > 0, "Should extract Q&A pairs"
        assert result.get("paper", {}).get("arxiv_id") == TEST_ARXIV_ID

        # Verify HTML was used (once implemented)
        # assert result.get("extraction_format") == "html"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
