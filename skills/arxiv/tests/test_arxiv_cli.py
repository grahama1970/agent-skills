#!/usr/bin/env python3
"""
Tests for arxiv CLI commands.

Run with: pytest tests/test_arxiv_cli.py -v
"""
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).parent.parent
RUN_SCRIPT = SKILL_DIR / "run.sh"

TEST_ARXIV_ID = "2501.15355"  # ToM-agent paper


def run_arxiv_cmd(args: list[str], timeout: int = 60) -> dict:
    """Run arxiv CLI command and return parsed JSON output."""
    cmd = ["bash", str(RUN_SCRIPT)] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {result.stderr}")
    return json.loads(result.stdout)


class TestDownload:
    """Tests for arxiv download command."""

    def test_download_pdf_format(self):
        """Test downloading PDF (default format)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_arxiv_cmd([
                "download", "-i", TEST_ARXIV_ID, "-o", tmpdir
            ])

            assert result.get("errors") == [], f"Errors: {result.get('errors')}"
            assert result.get("downloaded") is not None

            downloaded_path = Path(result["downloaded"])
            assert downloaded_path.exists()
            assert downloaded_path.suffix == ".pdf"
            assert downloaded_path.stat().st_size > 100_000  # >100KB

    def test_download_html_format(self):
        """Test downloading HTML from ar5iv (Task 2 Definition of Done)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_arxiv_cmd([
                "download", "-i", TEST_ARXIV_ID, "-o", tmpdir, "--format", "html"
            ])

            assert result.get("errors") == [], f"Errors: {result.get('errors')}"
            assert result.get("downloaded") is not None
            assert result.get("meta", {}).get("format") == "html"

            downloaded_path = Path(result["downloaded"])
            assert downloaded_path.exists(), f"File not found: {downloaded_path}"
            assert downloaded_path.suffix == ".html"
            assert downloaded_path.stat().st_size > 50_000  # >50KB for real paper

            # Verify content is valid HTML
            content = downloaded_path.read_text()
            assert "<!DOCTYPE html>" in content or "<!doctype html>" in content.lower()
            assert "abstract" in content.lower()


class TestSearch:
    """Tests for arxiv search command."""

    def test_search_basic(self):
        """Test basic search functionality."""
        result = run_arxiv_cmd([
            "search", "-q", "theory of mind LLM", "-n", "3"
        ])

        assert result.get("errors") == []
        assert result.get("meta", {}).get("count") > 0
        assert len(result.get("items", [])) > 0

        # Check item structure
        item = result["items"][0]
        assert "id" in item
        assert "title" in item
        assert "abstract" in item
        assert "html_url" in item  # ar5iv URL should be present


class TestGet:
    """Tests for arxiv get command."""

    def test_get_by_id(self):
        """Test getting paper metadata by ID."""
        result = run_arxiv_cmd([
            "get", "-i", TEST_ARXIV_ID
        ])

        assert result.get("errors") == []
        assert len(result.get("items", [])) == 1

        item = result["items"][0]
        assert item["id"] == TEST_ARXIV_ID
        assert "ToM-agent" in item["title"] or "Theory of Mind" in item["title"]
        assert item.get("html_url")  # ar5iv URL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
