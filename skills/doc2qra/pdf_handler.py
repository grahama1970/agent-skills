#!/usr/bin/env python3
"""PDF processing functions for distill skill.

Provides multiple extraction strategies:
- Fast mode: pymupdf4llm (default)
- Accurate mode: marker-pdf with LLM enhancement via Chutes
- Auto mode: Preflight assessment to choose optimal strategy
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import COMPLEXITY_THRESHOLDS, get_chutes_config
from .utils import log


def pdf_preflight(pdf_path: Path, thresholds: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Analyze PDF structure before extraction.

    Returns assessment of document complexity to choose extraction strategy.
    Uses pymupdf4llm's page_chunks for metadata without full LLM processing.

    Args:
        pdf_path: Path to PDF file
        thresholds: Optional custom thresholds (uses COMPLEXITY_THRESHOLDS if None)

    Returns:
        Dict with page_count, has_tables, has_images, has_multi_column,
        section_style, estimated_complexity, recommended_mode
    """
    import re

    th = {**COMPLEXITY_THRESHOLDS, **(thresholds or {})}

    # Try to import pymupdf4llm
    pymupdf4llm = None
    try:
        import pymupdf4llm as _pymupdf4llm
        pymupdf4llm = _pymupdf4llm
    except ImportError:
        pass

    assessment = {
        "page_count": 0,
        "has_tables": False,
        "has_images": False,
        "has_multi_column": False,
        "section_style": "none",
        "estimated_complexity": "simple",
        "recommended_mode": "fast",
    }

    # If pymupdf4llm not available, return basic assessment
    if pymupdf4llm is None:
        try:
            import fitz
            with fitz.open(str(pdf_path)) as doc:
                assessment["page_count"] = len(doc)
                if len(doc) > th["large_doc_pages"]:
                    assessment["estimated_complexity"] = "medium"
        except Exception:
            pass
        return assessment

    try:
        # Get page-level metadata
        pages = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)

        if isinstance(pages, list):
            assessment["page_count"] = len(pages)

            table_count = 0
            image_count = 0
            has_multi_col = False

            for page in pages:
                if isinstance(page, dict):
                    md = page.get("text", "") or page.get("md", "")
                else:
                    md = str(page)

                # Check for tables (markdown table syntax)
                if "|" in md and "---" in md:
                    table_count += 1

                # Check for images
                if "![" in md or "<img" in md.lower():
                    image_count += 1

                # Check for multi-column indicators (heuristic: very short lines)
                lines = md.split("\n")
                short_lines = sum(1 for line in lines if 10 < len(line.strip()) < 40)
                if short_lines > len(lines) * 0.4:
                    has_multi_col = True

            assessment["has_tables"] = table_count > 0
            assessment["has_images"] = image_count > 0
            assessment["has_multi_column"] = has_multi_col

            # Detect section style from first few pages
            sample_text = ""
            for page in pages[:5]:
                if isinstance(page, dict):
                    sample_text += page.get("text", "") or page.get("md", "")
                else:
                    sample_text += str(page)

            if re.search(r'^\d+\.\d+', sample_text, re.MULTILINE):
                assessment["section_style"] = "decimal"
            elif re.search(r'^[IVXLCDM]+\.', sample_text, re.MULTILINE):
                assessment["section_style"] = "roman"
            elif re.search(r'^Chapter\s+\d+', sample_text, re.MULTILINE | re.IGNORECASE):
                assessment["section_style"] = "chapter"
            elif re.search(r'^#{1,6}\s+', sample_text, re.MULTILINE):
                assessment["section_style"] = "markdown"

        # Determine complexity using configurable thresholds
        complexity_score = 0
        if assessment["has_tables"]:
            complexity_score += th["table_weight"]
        if assessment["has_images"]:
            complexity_score += th["image_weight"]
        if assessment["has_multi_column"]:
            complexity_score += th["multi_col_weight"]
        if assessment["page_count"] > th["large_doc_pages"]:
            complexity_score += th["large_doc_weight"]

        assessment["complexity_score"] = complexity_score

        if complexity_score >= th["complex_threshold"]:
            assessment["estimated_complexity"] = "complex"
            assessment["recommended_mode"] = "accurate"
        elif complexity_score >= th["medium_threshold"]:
            assessment["estimated_complexity"] = "medium"
            assessment["recommended_mode"] = "fast"  # fast is usually good enough
        else:
            assessment["estimated_complexity"] = "simple"
            assessment["recommended_mode"] = "fast"

    except Exception as e:
        assessment["error"] = str(e)

    return assessment


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract PDF to markdown using pymupdf4llm.

    Returns clean markdown with:
    - Tables converted to markdown tables
    - Headers detected by font size
    - Multi-column layout handled
    - Structure preserved for section detection

    Falls back to uvx if not installed, then to basic PyMuPDF.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted markdown text
    """
    # Try direct import first (fastest if available)
    try:
        import pymupdf4llm
        return pymupdf4llm.to_markdown(str(pdf_path))
    except ImportError:
        pass

    # Try uvx auto-install
    try:
        log("pymupdf4llm not installed, trying uvx...")
        result = subprocess.run(
            ["uvx", "--from", "pymupdf4llm", "python", "-c",
             f"import pymupdf4llm; print(pymupdf4llm.to_markdown({repr(str(pdf_path))}))"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Final fallback to basic PyMuPDF
    log("Falling back to basic PyMuPDF extraction")
    return _extract_pdf_text_basic(pdf_path)


def _extract_pdf_text_basic(pdf_path: Path) -> str:
    """Fallback: Extract text from PDF using basic PyMuPDF.

    Used when pymupdf4llm is not available.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted plain text
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError(
            "PyMuPDF required for PDF extraction. Install with: pip install pymupdf"
        )

    text_parts = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            page_text = page.get_text("text") or ""
            if page_text.strip():
                text_parts.append(page_text)

    return "\n\n".join(text_parts)


def _run_with_streaming(cmd: List[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """Run subprocess with real-time output streaming to stderr.

    Allows agent/human to monitor long-running processes (2-10 min).

    Args:
        cmd: Command and arguments to run
        timeout: Maximum execution time in seconds

    Returns:
        CompletedProcess with stdout and stderr captured
    """
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout_lines: List[str] = []
    stderr_lines: List[str] = []

    try:
        start_time = time.time()

        while process.poll() is None:
            if time.time() - start_time > timeout:
                process.kill()
                raise subprocess.TimeoutExpired(cmd, timeout)

            # Read available output
            if process.stderr:
                line = process.stderr.readline()
                if line:
                    stderr_lines.append(line)
                    # Stream to terminal in real-time
                    print(f"  [marker] {line.rstrip()}", file=sys.stderr)

            if process.stdout:
                line = process.stdout.readline()
                if line:
                    stdout_lines.append(line)

        # Get remaining output
        remaining_stdout, remaining_stderr = process.communicate(timeout=5)
        if remaining_stdout:
            stdout_lines.append(remaining_stdout)
        if remaining_stderr:
            for line in remaining_stderr.split('\n'):
                if line.strip():
                    print(f"  [marker] {line}", file=sys.stderr)
            stderr_lines.append(remaining_stderr)

    except subprocess.TimeoutExpired:
        process.kill()
        raise

    return subprocess.CompletedProcess(
        cmd,
        process.returncode,
        ''.join(stdout_lines),
        ''.join(stderr_lines),
    )


def extract_pdf_accurate(pdf_path: Path, stream: bool = True) -> str:
    """Extract PDF using marker-pdf with LLM enhancement via Chutes.

    Uses uvx for auto-installation - no pre-install required.
    Falls back gracefully: LLM mode -> no-LLM mode -> pymupdf4llm.

    Args:
        pdf_path: Path to PDF file
        stream: If True, stream progress logs in real-time (for long processes)

    Returns:
        Extracted markdown text
    """
    import tempfile

    # Get Chutes configuration
    chutes = get_chutes_config()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # Base command using uvx for auto-install
        cmd_base = [
            "uvx", "--from", "marker-pdf", "marker_single",
            str(pdf_path),
            str(output_dir),
            "--output_format", "markdown",
        ]

        # LLM enhancement flags (separate list for clean fallback)
        llm_flags = [
            "--use_llm",
            "--llm_service", "marker.services.openai.OpenAIService",
            "--openai_base_url", chutes["base_url"],
            "--openai_api_key", chutes["api_key"],
            "--openai_model", chutes["model"],
        ]

        # Choose run function based on streaming preference
        def run_simple(cmd: List[str], timeout: int) -> subprocess.CompletedProcess:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        run_fn = _run_with_streaming if stream else run_simple

        # Try with LLM first if API key available
        use_llm = bool(chutes["api_key"])

        try:
            if use_llm:
                log("marker-pdf with Chutes LLM (may take 2-10 min)...", style="yellow")
                cmd_with_llm = cmd_base + llm_flags
                result = run_fn(cmd_with_llm, timeout=600)  # 10 min timeout for LLM mode

                # Fallback: If LLM mode failed, retry without LLM
                if result.returncode != 0:
                    log("LLM mode failed, retrying without LLM...", style="yellow")
                    result = run_fn(cmd_base, timeout=300)
            else:
                log("marker-pdf (no LLM - CHUTES_API_KEY not set)...", style="yellow")
                result = run_fn(cmd_base, timeout=300)

            if result.returncode != 0:
                log(f"marker-pdf failed: {result.stderr[:200]}", style="red")
                return extract_pdf_text(pdf_path)

            # Find output markdown file
            md_files = list(output_dir.glob("**/*.md"))
            if md_files:
                log("marker-pdf extraction complete", style="green")
                return md_files[0].read_text(encoding="utf-8")
            else:
                log("marker-pdf produced no output, falling back", style="yellow")
                return extract_pdf_text(pdf_path)

        except subprocess.TimeoutExpired:
            log("marker-pdf timeout, falling back to fast mode", style="yellow")
            return extract_pdf_text(pdf_path)
        except FileNotFoundError:
            log("uvx not found, falling back to fast mode", style="yellow")
            return extract_pdf_text(pdf_path)
        except Exception as e:
            log(f"marker-pdf error: {e}, falling back", style="red")
            return extract_pdf_text(pdf_path)


def read_file(path: str, mode: str = "fast", show_preflight: bool = False) -> str:
    """Read file content. Handles text files and PDFs.

    Args:
        path: File path to read
        mode: Extraction mode for PDFs - "fast" (pymupdf4llm), "accurate" (marker-pdf), "auto"
        show_preflight: If True, print PDF preflight assessment

    Returns:
        File content as string
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # PDF extraction with mode selection
    if p.suffix.lower() == '.pdf':
        # Run preflight assessment
        if mode == "auto" or show_preflight:
            assessment = pdf_preflight(p)
            if show_preflight:
                print(f"[preflight] {json.dumps(assessment, indent=2)}", file=sys.stderr)
            if mode == "auto":
                mode = assessment.get("recommended_mode", "fast")

        if mode == "accurate":
            log("Using accurate mode (marker-pdf + Chutes)", style="bold blue")
            return extract_pdf_accurate(p)
        else:
            log("Using fast mode (pymupdf4llm)", style="bold green")
            return extract_pdf_text(p)

    return p.read_text(encoding="utf-8", errors="ignore")
