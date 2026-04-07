#!/usr/bin/env python3
"""
Paper download functionality for arxiv-learn skill.

Handles downloading PDFs from arXiv and HTML from ar5iv.org.
"""
from __future__ import annotations

import tempfile
import shutil
import urllib.request
from pathlib import Path

from config import (
    SCRIPT_DIR,
    SKILLS_DIR,
    PAPERS_DIR,
    AR5IV_BASE_URL,
    AR5IV_TIMEOUT,
)
from utils import log, run_skill, Paper
from loguru import logger

# =============================================================================
# HTML Download (ar5iv)
# =============================================================================

def download_html(arxiv_id: str, output_dir: Path | None = None) -> str | None:
    """Download HTML from ar5iv.org.

    Args:
        arxiv_id: arXiv paper ID
        output_dir: Directory to save HTML (default: PAPERS_DIR)

    Returns:
        Path to downloaded HTML file, or None if failed
    """
    if output_dir is None:
        output_dir = PAPERS_DIR
        output_dir.mkdir(exist_ok=True)

    # Strip version suffix if present (e.g., 2501.15355v1 -> 2501.15355)
    base_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

    url = f"{AR5IV_BASE_URL}/{base_id}"
    output_path = output_dir / f"{base_id}.html"

    # Check cache first
    if output_path.exists() and output_path.stat().st_size > 100:
        log(f"HTML cache hit: {output_path.name}", style="dim")
        return str(output_path)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "arxiv-learn/1.0"})
        with urllib.request.urlopen(req, timeout=AR5IV_TIMEOUT) as resp:
            raw = resp.read()
            output_path.write_bytes(raw)
            return str(output_path)
    except Exception as e:
        log(f"HTML download failed: {e}", style="yellow")
        return None

# =============================================================================
# PDF Download (via arxiv skill)
# =============================================================================

def download_pdf(arxiv_id: str, output_dir: Path | None = None) -> str | None:
    """Download PDF from arXiv.

    Uses the arxiv skill for actual download with proper rate limiting.

    Args:
        arxiv_id: arXiv paper ID
        output_dir: Directory to save PDF (default: PAPERS_DIR)

    Returns:
        Path to downloaded PDF file, or None if failed
    """
    if output_dir is None:
        output_dir = PAPERS_DIR
        output_dir.mkdir(exist_ok=True)

    # Check cache first - PDF uses underscores instead of dots
    base_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
    cached_pdf = output_dir / f"{base_id.replace('.', '_')}.pdf"
    if cached_pdf.exists() and cached_pdf.stat().st_size > 100:
        log(f"PDF cache hit: {cached_pdf.name}", style="dim")
        return str(cached_pdf)

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            dl_result = run_skill("arxiv", [
                "download", "-i", arxiv_id, "-o", tmpdir
            ])
            if not isinstance(dl_result, dict):
                log("PDF download returned non-JSON output", style="red")
                return None
            pdf_path = dl_result.get("downloaded")
            if not pdf_path:
                return None

            # Move to persistent location (handle cross-device moves)
            final_path = output_dir / Path(pdf_path).name
            shutil.move(str(pdf_path), str(final_path))
            return str(final_path)
        except Exception as e:
            log(f"PDF download failed: {e}", style="red")
            return None

# =============================================================================
# Full Paper Download
# =============================================================================

def download_paper(
    arxiv_id: str,
    include_html: bool = True,
    force_pdf: bool = False,
) -> Paper | None:
    """Download paper with metadata, PDF, and optionally HTML.

    Args:
        arxiv_id: arXiv paper ID
        include_html: Whether to download HTML from ar5iv
        force_pdf: Always download PDF even if HTML is available

    Returns:
        Paper object with paths, or None if failed
    """
    log(f"Downloading {arxiv_id}...")

    # Strip version suffix
    base_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

    # ---- Cache check: if PDF and HTML already exist, skip metadata fetch ----
    cached_html = PAPERS_DIR / f"{base_id}.html"
    cached_pdf = PAPERS_DIR / f"{base_id.replace('.', '_')}.pdf"
    has_cached_html = cached_html.exists() and cached_html.stat().st_size > 100
    has_cached_pdf = cached_pdf.exists() and cached_pdf.stat().st_size > 100

    if has_cached_pdf:
        # Try to extract title from cached HTML <title> tag
        title = f"Paper {base_id}"
        if has_cached_html:
            try:
                html_head = cached_html.read_text(errors="replace")[:5000]
                import re
                m = re.search(r"<title[^>]*>([^<]+)</title>", html_head, re.IGNORECASE)
                if m:
                    title = m.group(1).strip()
                    # Clean up ar5iv title format
                    for prefix in ["[", "ar5iv"]:
                        if title.startswith(prefix):
                            title = title.split("]", 1)[-1].strip()
            except Exception as e:
                logger.debug("value lookup failed: {}", e)

        log(f"Using cached files for {base_id}", style="green")
        log(f"Title: {title[:60]}...", style="green")

        paper = Paper(
            arxiv_id=base_id,
            title=title,
            authors=[],
            pdf_path=str(cached_pdf),
            abstract="",
            html_url=f"https://ar5iv.org/abs/{base_id}",
        )

        if include_html and has_cached_html:
            paper.html_path = str(cached_html)
            log("HTML: Using cached ar5iv file", style="dim")

        return paper

    # ---- No cache - download from arXiv ----

    # Get paper metadata
    try:
        result = run_skill("arxiv", ["get", "-i", arxiv_id])
        if not isinstance(result, dict):
            log("Failed to get metadata: non-JSON output", style="red")
            return None
        items = result.get("items", [])
        if not items:
            log(f"Paper not found: {arxiv_id}", style="red")
            return None
        paper_info = items[0]
    except Exception as e:
        log(f"Failed to get metadata: {e}", style="red")
        return None

    # Download PDF
    pdf_path = download_pdf(arxiv_id)
    if not pdf_path:
        log(f"Failed to download PDF: {arxiv_id}", style="red")
        return None

    paper = Paper(
        arxiv_id=arxiv_id,
        title=paper_info.get("title", ""),
        authors=paper_info.get("authors", []),
        pdf_path=pdf_path,
        abstract=paper_info.get("abstract", ""),
        html_url=paper_info.get("html_url", ""),
    )

    log(f"Title: {paper.title[:60]}...", style="green")
    log(f"Authors: {', '.join(paper.authors[:3])}", style="dim")

    # Download HTML if requested
    if include_html and not force_pdf:
        html_path = download_html(arxiv_id)
        if html_path:
            paper.html_path = html_path
            log("HTML: Downloaded from ar5iv", style="dim")

    return paper

# =============================================================================
# Local File Loading
# =============================================================================

def load_local_paper(file_path: str) -> Paper:
    """Load a local PDF as a Paper object.

    Args:
        file_path: Path to local PDF file

    Returns:
        Paper object

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    log(f"Using local file: {path.name}", style="green")
    return Paper(
        arxiv_id="local",
        title=path.stem,
        authors=[],
        pdf_path=str(path),
    )

# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "download_html",
    "download_pdf",
    "download_paper",
    "load_local_paper",
]
