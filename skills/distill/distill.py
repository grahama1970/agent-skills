#!/usr/bin/env python3
"""Distill large text/URLs into Q&A pairs for memory.

Standalone skill - no sparta dependency. Uses sentence-aware windowing
inspired by sparta's approach but simplified for general use.

Usage:
    python distill.py --url https://arxiv.org/... --scope research
    python distill.py --text "large text..." --scope myproject
    python distill.py --file /path/to/doc.md --scope myproject
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

# Best-effort .env loading
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except Exception:
    pass

# =============================================================================
# Rich/tqdm Progress Indicators (optional, graceful fallback)
# =============================================================================

_HAS_RICH = False
_HAS_TQDM = False
_console = None
_Progress = None

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
    from rich.panel import Panel
    from rich.table import Table
    _HAS_RICH = True
    _console = Console(stderr=True)
except ImportError:
    pass

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except ImportError:
    pass


def _log(msg: str, style: str = None):
    """Log message with optional rich styling."""
    if _HAS_RICH and _console:
        _console.print(f"[dim][distill][/dim] {msg}", style=style)
    else:
        print(f"[distill] {msg}", file=sys.stderr)


def _status_panel(title: str, content: Dict[str, Any]):
    """Display a rich status panel if available."""
    if _HAS_RICH and _console:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")
        for k, v in content.items():
            table.add_row(str(k), str(v))
        _console.print(Panel(table, title=f"[bold]{title}[/bold]", border_style="blue"))
    else:
        print(f"[distill] {title}:", file=sys.stderr)
        for k, v in content.items():
            print(f"  {k}: {v}", file=sys.stderr)


def _create_progress():
    """Create a progress context manager."""
    if _HAS_RICH:
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=_console,
        )
    return None


def _iter_with_progress(iterable, desc: str = "Processing", total: int = None):
    """Iterate with progress bar (tqdm or rich fallback)."""
    if total is None:
        try:
            total = len(iterable)
        except TypeError:
            pass

    if _HAS_TQDM and not _HAS_RICH:
        # Use tqdm if rich not available
        return tqdm(iterable, desc=f"[distill] {desc}", total=total, file=sys.stderr)
    elif _HAS_RICH and _console:
        # Rich progress bar
        progress = _create_progress()
        if progress:
            task_id = progress.add_task(desc, total=total or 0)

            def gen():
                with progress:
                    for item in iterable:
                        yield item
                        progress.advance(task_id)
            return gen()
    # Fallback: plain iteration with periodic updates
    def gen():
        for i, item in enumerate(iterable):
            if total and i % max(1, total // 10) == 0:
                print(f"[distill] {desc}: {i}/{total}", file=sys.stderr)
            yield item
    return gen()


# =============================================================================
# Section Detection (structure-aware splitting)
# Patterns adapted from extractor project's heuristics.py
# =============================================================================

# Markdown headers
_RE_MD_HEADER = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

# Section numbering patterns (from extractor/pipeline/utils/sections/heuristics.py)
# Decimal: 1.2.3 Title, 1.2.3. Title
_RE_DECIMAL = re.compile(
    r'^\s*(\d+(?:\.\d+)*(?:\.[a-z])?)\s*[.:)\-–—]?\s+(\S.*)$',
    re.MULTILINE | re.IGNORECASE
)
# Roman numerals: I. Title, II. Title (require trailing dot to avoid false positives)
_RE_ROMAN = re.compile(
    r'^\s*([IVXLCDM]+(?:\.[IVXLCDM]+)*)\.\s+(\S.*)$',
    re.MULTILINE | re.IGNORECASE
)
# Alpha sections: A. Title, A.1 Title, B.2.3 Title
_RE_ALPHA = re.compile(
    r'^\s*([A-Z](?:\.\d+)*)\.\s+([^=].*)$',
    re.MULTILINE
)
# Labeled sections: Appendix A, Chapter 1, Section 2.3
_RE_LABELED = re.compile(
    r'^\s*(Appendix|Annex|Section|Chapter|Part)\s+([A-Za-z0-9IVXLCDM.]+)\s*[:.\-–—]?\s+(\S.*)$',
    re.MULTILINE | re.IGNORECASE
)

# Negative patterns - skip these as sections (from extractor heuristics)
_RE_CAPTION = re.compile(
    r'^\s*(Table|Figure|Exhibit|Listing)\s+\d+(?:[-–]\d+)?(?:[.:]|\s*\()',
    re.IGNORECASE
)
_RE_REQUIREMENT = re.compile(r'^\s*REQ-[\w-]+[:\s]', re.IGNORECASE)
# Date patterns: "13 February 2015", "2024-01-15", "January 15, 2024"
_RE_DATE = re.compile(
    r'^\s*(?:'
    r'\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}'
    r'|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}'
    r'|\d{4}[-/]\d{2}[-/]\d{2}'
    r')\s*$',
    re.IGNORECASE
)


def _is_likely_section_header(line: str) -> Tuple[bool, str]:
    """Check if line looks like a section header using extractor patterns.

    Returns (is_header, title) tuple.
    """
    line = line.strip()
    if not line or len(line) < 3:
        return False, ""

    # Negative patterns - reject these
    if _RE_CAPTION.match(line):
        return False, ""
    if _RE_REQUIREMENT.match(line):
        return False, ""
    if _RE_DATE.match(line):
        return False, ""
    # Short label ending with colon (e.g., "Note:", "Warning:")
    if len(line) <= 40 and line.endswith(":"):
        return False, ""
    # Sentences (end with . or ; unless clearly numbered)
    if (line.endswith(".") or line.endswith(";")) and not re.match(r'^\d+\.', line):
        # Allow numbered sections ending with period
        if not _RE_DECIMAL.match(line):
            return False, ""

    # Positive patterns
    m = _RE_DECIMAL.match(line)
    if m:
        return True, m.group(2).strip()

    m = _RE_ROMAN.match(line)
    if m:
        return True, m.group(2).strip()

    m = _RE_ALPHA.match(line)
    if m:
        return True, m.group(2).strip()

    m = _RE_LABELED.match(line)
    if m:
        return True, m.group(3).strip()

    return False, ""


def _remove_code_blocks(text: str) -> Tuple[str, List[Tuple[int, int]]]:
    """Remove code blocks and return positions for adjustment."""
    # Match fenced code blocks (``` or ~~~)
    code_block_re = re.compile(r'```[\s\S]*?```|~~~[\s\S]*?~~~', re.MULTILINE)
    ranges = [(m.start(), m.end()) for m in code_block_re.finditer(text)]
    cleaned = code_block_re.sub('', text)
    return cleaned, ranges


def extract_code_blocks(text: str) -> List[Dict[str, Any]]:
    """Extract fenced code blocks with language annotation.

    Returns list of {"language": str, "code": str, "start": int, "end": int}
    """
    # Match ```language\ncode\n``` or ~~~language\ncode\n~~~
    pattern = re.compile(
        r'(?:```|~~~)(\w*)\n([\s\S]*?)(?:```|~~~)',
        re.MULTILINE
    )

    blocks = []
    for match in pattern.finditer(text):
        language = match.group(1).strip().lower() or "text"
        code = match.group(2).strip()
        if code:  # Only include non-empty blocks
            blocks.append({
                "language": language,
                "code": code,
                "start": match.start(),
                "end": match.end(),
            })

    return blocks


def parse_code_with_treesitter(code: str, language: str) -> List[Dict[str, Any]]:
    """Parse code using treesitter skill to extract symbols.

    Returns list of symbols with kind, name, signature, docstring.
    """
    # Map common language names to treesitter language IDs
    lang_map = {
        "python": "python", "py": "python",
        "javascript": "javascript", "js": "javascript",
        "typescript": "typescript", "ts": "typescript",
        "rust": "rust", "rs": "rust",
        "go": "go", "golang": "go",
        "java": "java",
        "c": "c", "cpp": "cpp", "c++": "cpp",
        "ruby": "ruby", "rb": "ruby",
        "bash": "bash", "sh": "bash", "shell": "bash",
    }

    ts_lang = lang_map.get(language, language)

    try:
        result = subprocess.run(
            [
                "uvx", "--from", "git+https://github.com/grahama1970/treesitter-tools.git",
                "treesitter-tools", "symbols", "/dev/stdin",
                "--language", ts_lang, "--content"
            ],
            input=code,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        _log(f"treesitter parsing failed: {e}", style="yellow")

    return []


def split_by_sections(text: str) -> List[Tuple[str, str]]:
    """Split text by structural sections (headers, numbered sections).

    Uses patterns from extractor project for robust section detection.
    Returns list of (section_title, section_content) tuples.
    Falls back to single section if no structure detected.
    """
    sections: List[Tuple[str, str]] = []

    # Remove code blocks before detecting headers (to avoid # comments)
    cleaned_text, _ = _remove_code_blocks(text)

    # Try markdown headers first (only in non-code text)
    md_matches = list(_RE_MD_HEADER.finditer(cleaned_text))
    if len(md_matches) >= 2:  # Need at least 2 headers to split
        # Find header positions in original text
        for i, match in enumerate(md_matches):
            title = match.group(2).strip()
            # Find this header in original text
            header_text = match.group(0)
            orig_pos = text.find(header_text)
            if orig_pos == -1:
                continue
            start = orig_pos + len(header_text)
            # Find next header in original
            if i + 1 < len(md_matches):
                next_header = md_matches[i + 1].group(0)
                end = text.find(next_header, start)
                if end == -1:
                    end = len(text)
            else:
                end = len(text)
            content = text[start:end].strip()
            if content and len(content) > 20:  # Skip trivially small sections
                sections.append((title, content))
        if sections:
            return sections

    # Try numbered/labeled sections using extractor patterns
    # Scan line by line for section headers
    lines = cleaned_text.split('\n')
    header_positions: List[Tuple[int, str, str]] = []  # (line_idx, full_line, title)

    for idx, line in enumerate(lines):
        is_header, title = _is_likely_section_header(line)
        if is_header and title:
            header_positions.append((idx, line.strip(), title))

    if len(header_positions) >= 2:
        # Build sections from header positions
        text_lines = text.split('\n')
        for i, (line_idx, full_line, title) in enumerate(header_positions):
            # Content starts after header line
            start_line = line_idx + 1
            # Content ends at next header (or end of text)
            if i + 1 < len(header_positions):
                end_line = header_positions[i + 1][0]
            else:
                end_line = len(text_lines)

            content_lines = text_lines[start_line:end_line]
            content = '\n'.join(content_lines).strip()

            if content and len(content) > 20:
                sections.append((full_line, content))

        if sections:
            return sections

    # No structure found - return as single section
    return [("", text)]


# =============================================================================
# Sentence Splitting (simple, no heavy deps)
# =============================================================================

_ABBREVS = {
    "fig", "sec", "no", "dr", "mr", "mrs", "ms", "prof",
    "u.s", "u.k", "dept", "inc", "ltd", "vs", "etc", "e.g", "i.e", "cf", "al"
}


def split_sentences(text: str) -> List[str]:
    """Split text into sentences. Simple regex-based, handles common abbreviations."""
    if not text or not text.strip():
        return []

    # Try NLTK if available
    try:
        from nltk.tokenize import PunktSentenceTokenizer
        tok = PunktSentenceTokenizer()
        tok._params.abbrev_types.update({a.replace(".", "") for a in _ABBREVS})
        sents = [t.strip() for t in tok.tokenize(text) if t.strip()]
        if sents:
            return sents
    except Exception:
        pass

    # Fallback: regex split on sentence boundaries
    # Split on .!? followed by space and capital letter
    sents = re.split(r'(?<=[.!?])\s+(?=[A-Z(])', text)
    sents = [s.strip() for s in sents if s.strip()]

    # Merge sentences ending with known abbreviations
    merged: List[str] = []
    abbr_pat = r"\b(" + "|".join(re.escape(a + ".") for a in _ABBREVS) + r")$"
    abbr_re = re.compile(abbr_pat, re.I)
    for sent in sents:
        if merged and abbr_re.search(merged[-1]):
            merged[-1] = f"{merged[-1]} {sent}"
        else:
            merged.append(sent)

    return merged if merged else [text]


# =============================================================================
# Windowing (sentence-aware with overlap)
# =============================================================================

def build_sections(
    text: str,
    max_section_chars: int = 5000,
) -> List[Tuple[str, str]]:
    """Build sections from text, respecting document structure.

    Returns list of (section_title, section_content) tuples.

    Strategy:
    1. Split by section delimiters (markdown headers, numbered sections)
    2. Each section is ONE unit for Q&A extraction
    3. Only chunk very large sections (>max_section_chars) as fallback
    """
    sections = split_by_sections(text)
    result: List[Tuple[str, str]] = []

    for title, content in sections:
        content = content.strip()
        if not content:
            continue

        # Section is reasonable size - keep as single unit
        if len(content) <= max_section_chars:
            result.append((title, content))
            continue

        # Section too large - split at sentence boundaries, preserving coherence
        # Find natural break points (paragraph breaks, sentence ends)
        sents = split_sentences(content)
        if not sents:
            result.append((title, content[:max_section_chars]))
            continue

        # Group sentences into chunks, breaking at natural points
        chunk_sents: List[str] = []
        chunk_chars = 0
        part_num = 1

        for sent in sents:
            # Would adding this sentence exceed limit?
            if chunk_chars + len(sent) > max_section_chars and chunk_sents:
                # Save current chunk
                chunk_title = f"{title} (part {part_num})" if title else f"Part {part_num}"
                result.append((chunk_title, " ".join(chunk_sents)))
                part_num += 1
                chunk_sents = []
                chunk_chars = 0

            chunk_sents.append(sent)
            chunk_chars += len(sent) + 1

        # Don't forget last chunk
        if chunk_sents:
            chunk_title = f"{title} (part {part_num})" if title and part_num > 1 else title
            result.append((chunk_title, " ".join(chunk_sents)))

    return result


# =============================================================================
# Content Fetching
# =============================================================================

def fetch_url(url: str) -> str:
    """Fetch URL content and convert to text."""
    import urllib.request
    from urllib.error import URLError, HTTPError

    try:
        # Add headers to avoid 403
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; distill-skill/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except (URLError, HTTPError) as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}")

    # Try to extract text from HTML
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        # Remove script/style elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
    except ImportError:
        # Fallback: crude HTML stripping
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()

    return text


def read_file(path: str, mode: str = "fast", show_preflight: bool = False) -> str:
    """Read file content. Handles text files and PDFs.

    Args:
        path: File path to read
        mode: Extraction mode for PDFs - "fast" (pymupdf4llm), "accurate" (marker-pdf), "auto"
        show_preflight: If True, print PDF preflight assessment
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
            _log("Using accurate mode (marker-pdf + Chutes)", style="bold blue")
            return extract_pdf_accurate(p)
        else:
            _log("Using fast mode (pymupdf4llm)", style="bold green")
            return extract_pdf_text(p)

    return p.read_text(encoding="utf-8", errors="ignore")


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract PDF to markdown using pymupdf4llm.

    Returns clean markdown with:
    - Tables converted to markdown tables
    - Headers detected by font size
    - Multi-column layout handled
    - Structure preserved for section detection

    Falls back to uvx if not installed, then to basic PyMuPDF.
    """
    # Try direct import first (fastest if available)
    try:
        import pymupdf4llm
        return pymupdf4llm.to_markdown(str(pdf_path))
    except ImportError:
        pass

    # Try uvx auto-install
    try:
        _log("pymupdf4llm not installed, trying uvx...")
        result = subprocess.run(
            ["uvx", "--from", "pymupdf4llm", "python", "-c",
             f"import pymupdf4llm; print(pymupdf4llm.to_markdown('{pdf_path}'))"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Final fallback to basic PyMuPDF
    _log("Falling back to basic PyMuPDF extraction")
    return _extract_pdf_text_basic(pdf_path)


def _extract_pdf_text_basic(pdf_path: Path) -> str:
    """Fallback: Extract text from PDF using basic PyMuPDF.

    Used when pymupdf4llm is not available.
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


# Configurable complexity thresholds for preflight assessment
COMPLEXITY_THRESHOLDS = {
    "table_weight": 2,        # Weight for tables detected
    "image_weight": 1,        # Weight for images detected
    "multi_col_weight": 2,    # Weight for multi-column layout
    "large_doc_pages": 50,    # Pages threshold for "large doc" penalty
    "large_doc_weight": 1,    # Weight for large documents
    "medium_threshold": 2,    # Score >= this = medium complexity
    "complex_threshold": 4,   # Score >= this = complex (recommend accurate)
}


def pdf_preflight(pdf_path: Path, thresholds: Dict[str, int] = None) -> Dict[str, Any]:
    """Analyze PDF structure before extraction.

    Returns assessment of document complexity to choose extraction strategy.
    Uses pymupdf4llm's page_chunks for metadata without full LLM processing.

    Args:
        pdf_path: Path to PDF file
        thresholds: Optional custom thresholds (uses COMPLEXITY_THRESHOLDS if None)
    """
    th = {**COMPLEXITY_THRESHOLDS, **(thresholds or {})}

    # Try to import pymupdf4llm
    pymupdf4llm = None
    try:
        import pymupdf4llm as _pymupdf4llm
        pymupdf4llm = _pymupdf4llm
    except ImportError:
        # Will use fallback assessment based on basic analysis
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

    # Full assessment with pymupdf4llm
    assessment = {
        "page_count": 0,
        "has_tables": False,
        "has_images": False,
        "has_multi_column": False,
        "section_style": "none",  # decimal, roman, chapter, markdown, none
        "estimated_complexity": "simple",  # simple, medium, complex
        "recommended_mode": "fast",
    }

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
                short_lines = sum(1 for l in lines if 10 < len(l.strip()) < 40)
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


def _run_with_streaming(cmd: List[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """Run subprocess with real-time output streaming to stderr.

    Allows agent/human to monitor long-running processes (2-10 min).
    """
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout_lines = []
    stderr_lines = []

    try:
        # Use select for non-blocking read on both streams
        import time
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
    Falls back gracefully: LLM mode → no-LLM mode → pymupdf4llm.

    Args:
        pdf_path: Path to PDF file
        stream: If True, stream progress logs in real-time (for long processes)
    """
    import tempfile

    # Get Chutes configuration
    chutes_api_key = os.getenv("CHUTES_API_KEY", "")
    chutes_base_url = os.getenv("CHUTES_API_BASE", "https://llm.chutes.ai/v1")
    chutes_model = os.getenv("CHUTES_MODEL", "deepseek-ai/DeepSeek-V3")

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
            "--openai_base_url", chutes_base_url,
            "--openai_api_key", chutes_api_key,
            "--openai_model", chutes_model,
        ]

        # Choose run function based on streaming preference
        run_fn = _run_with_streaming if stream else lambda cmd, timeout: subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )

        # Try with LLM first if API key available
        use_llm = bool(chutes_api_key)

        try:
            if use_llm:
                _log("marker-pdf with Chutes LLM (may take 2-10 min)...", style="yellow")
                cmd_with_llm = cmd_base + llm_flags
                result = run_fn(cmd_with_llm, timeout=600)  # 10 min timeout for LLM mode

                # Fallback: If LLM mode failed, retry without LLM
                if result.returncode != 0:
                    _log("LLM mode failed, retrying without LLM...", style="yellow")
                    result = run_fn(cmd_base, timeout=300)
            else:
                _log("marker-pdf (no LLM - CHUTES_API_KEY not set)...", style="yellow")
                result = run_fn(cmd_base, timeout=300)

            if result.returncode != 0:
                _log(f"marker-pdf failed: {result.stderr[:200]}", style="red")
                return extract_pdf_text(pdf_path)

            # Find output markdown file
            md_files = list(output_dir.glob("**/*.md"))
            if md_files:
                _log("marker-pdf extraction complete", style="green")
                return md_files[0].read_text(encoding="utf-8")
            else:
                _log("marker-pdf produced no output, falling back", style="yellow")
                return extract_pdf_text(pdf_path)

        except subprocess.TimeoutExpired:
            _log("marker-pdf timeout, falling back to fast mode", style="yellow")
            return extract_pdf_text(pdf_path)
        except FileNotFoundError:
            _log("uvx not found, falling back to fast mode", style="yellow")
            return extract_pdf_text(pdf_path)
        except Exception as e:
            _log(f"marker-pdf error: {e}, falling back", style="red")
            return extract_pdf_text(pdf_path)


# =============================================================================
# QRA Extraction (Question, Reasoning, Answer)
# =============================================================================

def build_qra_system_prompt(context: str = None) -> str:
    """Build QRA system prompt with optional domain context.

    Args:
        context: Optional domain context/persona for focused extraction
    """
    base_prompt = """You are a knowledge extraction assistant. You MUST respond with valid JSON only.
Do not include any text before or after the JSON. Do not use markdown code blocks.
Return ONLY a JSON object matching this exact schema:

{{"items": [
  {{"question": "string", "reasoning": "string", "answer": "string"}},
  ...
]}}

CRITICAL RULES:
- Extract ALL meaningful facts, concepts, and relationships from the text
- GROUNDING: Every answer MUST be directly supported by text in the source. Do NOT hallucinate.
- question: A clear, specific question that the text answers
- reasoning: Brief explanation of where/how the answer is found in the text
- answer: The factual answer, using words from the source text when possible
- Include as many items as the text supports (could be 1 to 50+)
- If text is too short, garbled, or lacks factual content, return {{"items": []}}
- Prefer extracting: definitions, methods, results, comparisons, key findings
"""

    if context:
        context_section = f"""You are a {context}.

Extract knowledge items that are relevant to your expertise and domain.
Skip content that is outside your area of focus.
Prioritize information that would be valuable to someone with your background.

"""
        return context_section + base_prompt

    return base_prompt


# Default prompt (no context)
QRA_SYSTEM_PROMPT = build_qra_system_prompt()

QRA_PROMPT = """Extract all grounded knowledge items from this text. Every answer must be supported by the source text.

Text:
{text}

JSON:"""


def extract_qra_llm(section_content: str, source: str = "", section_title: str = "") -> List[Dict[str, str]]:
    """Extract QRA (Question, Reasoning, Answer) triplets using LLM."""
    try:
        from scillm import completion
        from scillm.extras.json_utils import clean_json_string
    except ImportError:
        return extract_qa_heuristic(section_content, source, section_title)

    prompt = QRA_PROMPT.format(text=section_content[:3000])  # Limit input size

    try:
        resp = completion(
            model=os.getenv("SCILLM_DEFAULT_MODEL", "deepseek/deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            api_base=os.getenv("CHUTES_API_BASE"),
            api_key=os.getenv("CHUTES_API_KEY"),
            timeout=30,
        )
        content = resp.choices[0].message.content or ""
        content = clean_json_string(content)
        data = json.loads(content)
        items = data.get("items", [])
        result = []
        for item in items:
            if item.get("question") and item.get("answer"):
                problem = item["question"]
                if section_title:
                    problem = f"[{section_title}] {problem}"
                # Combine reasoning + answer for solution
                reasoning = item.get("reasoning", "")
                answer = item["answer"]
                if reasoning:
                    solution = f"**Reasoning:** {reasoning}\n\n**Answer:** {answer}"
                else:
                    solution = answer
                result.append({
                    "problem": problem,
                    "solution": solution,
                    "reasoning": reasoning,
                    "answer": answer,
                })
        return result
    except Exception as e:
        _log(f"LLM extraction failed: {e}", style="red")
        return extract_qa_heuristic(section_content, source, section_title)


# Legacy alias
extract_qa_llm = extract_qra_llm


def _get_scillm_config() -> Dict[str, str]:
    """Get scillm configuration from environment.

    Follows SCILLM_PAVED_PATH_CONTRACT.md conventions.
    Uses CHUTES_TEXT_MODEL for text-only extraction (no vision needed).
    """
    # For text-only QRA extraction, prefer CHUTES_TEXT_MODEL
    model = (
        os.getenv("CHUTES_TEXT_MODEL")
        or os.getenv("SCILLM_DEFAULT_MODEL")
        or os.getenv("CHUTES_MODEL_ID", "deepseek/deepseek-chat")
    )
    return {
        "model": model,
        "api_base": os.getenv("CHUTES_API_BASE", "https://llm.chutes.ai/v1"),
        "api_key": os.getenv("CHUTES_API_KEY", ""),
    }


async def extract_qra_batch(
    sections: List[Tuple[str, str]],
    source: str = "",
    concurrency: int = 6,
    timeout: int = 60,
    context: str = None,
) -> List[Dict[str, Any]]:
    """Extract QRA from all sections using parallel LLM calls.

    Uses scillm batch_acompletions_iter for streaming progress.
    Per SCILLM_PAVED_PATH_CONTRACT.md - logs each section as it completes.

    Reference: .agents/skills/scillm/batch.py for batch patterns.

    Args:
        sections: List of (section_title, section_content) tuples
        source: Source identifier for the content
        concurrency: Max parallel requests (default 6)
        timeout: Per-request timeout in seconds
        context: Optional domain context/persona for focused extraction

    Returns:
        List of QRA dicts with section metadata
    """
    # Get config following scillm skill conventions
    config = _get_scillm_config()

    if not config["api_key"]:
        _log("CHUTES_API_KEY not set, falling back to heuristic extraction", style="yellow")
        return _fallback_heuristic_extraction(sections, source)

    # Try to import scillm batch functions - check multiple locations
    batch_acompletions_iter = None
    clean_json_string = None

    try:
        # Try local scillm fork first (preferred)
        from scillm.batch import parallel_acompletions_iter as batch_acompletions_iter
        from scillm.extras.json_utils import clean_json_string
    except ImportError:
        try:
            # Try main scillm module
            from scillm import batch_acompletions_iter
            from scillm.extras.json_utils import clean_json_string
        except ImportError:
            pass

    if batch_acompletions_iter is None:
        _log("scillm not available, falling back to heuristic extraction", style="yellow")
        return _fallback_heuristic_extraction(sections, source)

    if clean_json_string is None:
        # Fallback JSON cleaner if scillm.extras not available
        def clean_json_string(s: str) -> str:
            """Basic JSON string cleanup."""
            s = s.strip()
            if s.startswith("```json"):
                s = s[7:]
            if s.startswith("```"):
                s = s[3:]
            if s.endswith("```"):
                s = s[:-3]
            return s.strip()

    # Build batch requests - per SCILLM contract, model goes INSIDE each request dict
    # Keep metadata separate to avoid polluting request dicts
    requests = []
    metadata = []  # Parallel array for section metadata
    try:
        # Use system prompt for strict JSON schema enforcement
        # Include domain context if provided
        system_prompt = build_qra_system_prompt(context) if context else QRA_SYSTEM_PROMPT
        system_msg = {"role": "system", "content": system_prompt}
        if context:
            _log(f"Using domain context: {context[:50]}...", style="cyan")

        for idx, (section_title, section_content) in enumerate(sections):
            user_prompt = QRA_PROMPT.format(text=section_content[:3000])
            requests.append({
                "model": config["model"],
                "messages": [system_msg, {"role": "user", "content": user_prompt}],
                "response_format": {"type": "json_object"},
                "max_tokens": 4096,  # Allow comprehensive extraction
                "temperature": 0.1,  # Low temp for consistent, grounded JSON
            })
            metadata.append({"idx": idx, "title": section_title})
    except Exception as e:
        _log(f"Error building requests: {e}", style="red")
        return _fallback_heuristic_extraction(sections, source)

    _log(f"Batch: {len(requests)} sections, concurrency={concurrency}, model={config['model'][:40]}")

    all_qa: List[Dict[str, Any]] = []
    done = ok = err = 0

    try:
        async for ev in batch_acompletions_iter(
            requests,
            api_base=config["api_base"],
            api_key=config["api_key"],
            custom_llm_provider="openai_like",
            concurrency=concurrency,
            timeout=timeout,
            wall_time_s=900,
            tenacious=True,
        ):
            done += 1
            req_idx = ev.get("index", done - 1)
            meta = metadata[req_idx] if req_idx < len(metadata) else {"idx": req_idx, "title": f"Section {req_idx}"}
            section_idx = meta["idx"]
            section_title = meta["title"]

            if ev.get("ok") and ev.get("content"):
                ok += 1
                try:
                    qa_items = _parse_qra_response(
                        ev["content"], section_idx, section_title, source, clean_json_string
                    )
                    if qa_items:
                        all_qa.extend(qa_items)
                        _log(f"[{done}/{len(requests)}] '{section_title[:30]}...' → {len(qa_items)} QRAs", style="green")
                    else:
                        # Parse returned empty, use heuristic fallback
                        qa_pairs = _section_heuristic_fallback(sections, section_idx, source)
                        all_qa.extend(qa_pairs)
                        _log(f"[{done}/{len(requests)}] '{section_title[:30]}...' → empty parse, heuristic fallback", style="yellow")
                except Exception as parse_err:
                    err += 1
                    _log(f"[{done}/{len(requests)}] '{section_title[:30]}...' → {parse_err}", style="red")
                    qa_pairs = _section_heuristic_fallback(sections, section_idx, source)
                    all_qa.extend(qa_pairs)
            else:
                err += 1
                status = ev.get("status", "unknown")
                error = str(ev.get("error", ""))[:50]
                _log(f"[{done}/{len(requests)}] '{section_title[:30]}...' → {status} {error}", style="red")
                # Fallback to heuristic for failed sections
                qa_pairs = _section_heuristic_fallback(sections, section_idx, source)
                all_qa.extend(qa_pairs)

        _log(f"Batch complete: {ok} ok, {err} errors, {len(all_qa)} total QRAs", style="bold")

    except Exception as e:
        _log(f"Batch extraction failed: {e}, falling back to heuristic", style="red")
        return _fallback_heuristic_extraction(sections, source)

    return all_qa


# =============================================================================
# Grounding Validation - Check answers exist in source text
# =============================================================================

def _check_grounding(
    qra_items: List[Dict[str, Any]],
    sections: List[Tuple[str, str]],
    threshold: float = 0.5,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Validate QRA answers are grounded in source text.

    Uses rapidfuzz for fuzzy matching to catch paraphrased answers.
    Filters out hallucinated QRAs where the answer doesn't appear in the source.

    Args:
        qra_items: List of QRA dicts with section_idx
        sections: Original sections list for lookup
        threshold: Minimum similarity score (0-1) to consider grounded

    Returns:
        Tuple of (grounded_items, kept_count, filtered_count)
    """
    # Try to import rapidfuzz, fall back to simple word overlap
    try:
        from rapidfuzz import fuzz
        use_rapidfuzz = True
    except ImportError:
        use_rapidfuzz = False
        _log("rapidfuzz not available, using word overlap for grounding", style="dim")

    grounded = []
    filtered = 0

    for item in qra_items:
        section_idx = item.get("section_idx", 0)
        if section_idx >= len(sections):
            grounded.append(item)  # Keep if can't validate
            continue

        source_text = sections[section_idx][1].lower()
        answer = item.get("answer", "").lower()

        if not answer:
            filtered += 1
            continue

        # Calculate grounding score
        if use_rapidfuzz:
            # Use token_set_ratio for best partial matching
            score = fuzz.token_set_ratio(answer, source_text) / 100.0
        else:
            # Simple word overlap fallback
            answer_words = set(answer.split())
            source_words = set(source_text.split())
            if answer_words:
                overlap = len(answer_words & source_words) / len(answer_words)
                score = overlap
            else:
                score = 0.0

        if score >= threshold:
            item["grounding_score"] = round(score, 2)
            grounded.append(item)
        else:
            filtered += 1

    return grounded, len(grounded), filtered


def _validate_and_filter_qras(
    all_qa: List[Dict[str, Any]],
    sections: List[Tuple[str, str]],
    validate_grounding: bool = True,
    grounding_threshold: float = 0.5,
) -> List[Dict[str, Any]]:
    """Post-process QRAs with optional grounding validation.

    Args:
        all_qa: All extracted QRA items
        sections: Source sections for grounding check
        validate_grounding: Whether to filter out ungrounded QRAs
        grounding_threshold: Minimum similarity score (0.0-1.0)

    Returns:
        Validated QRA list
    """
    if not validate_grounding or not all_qa:
        return all_qa

    grounded, kept, filtered = _check_grounding(all_qa, sections, grounding_threshold)

    if filtered > 0:
        _log(f"Grounding check: {kept} kept, {filtered} filtered (threshold={grounding_threshold})", style="yellow")
    else:
        _log(f"Grounding check: all {kept} QRAs validated", style="green")

    return grounded


def _parse_qra_response(
    content,  # Can be str or dict
    section_idx: int,
    section_title: str,
    source: str,
    clean_json_fn,
) -> List[Dict[str, Any]]:
    """Parse LLM JSON response into QRA dicts."""
    try:
        # Handle content that's already a dict (from some LLM responses)
        if isinstance(content, dict):
            data = content
        else:
            cleaned = clean_json_fn(content) if clean_json_fn else content
            data = json.loads(cleaned)

        # Handle different response formats
        items = data.get("items", []) if isinstance(data, dict) else []
        if not items and isinstance(data, list):
            items = data  # Response is already a list
        if not items and isinstance(data, dict) and "question" in data:
            items = [data]  # Single item response

        result = []
        for item in items:
            if item.get("question") and item.get("answer"):
                problem = item["question"]
                if section_title:
                    problem = f"[{section_title}] {problem}"

                reasoning = item.get("reasoning", "")
                answer = item["answer"]
                solution = f"**Reasoning:** {reasoning}\n\n**Answer:** {answer}" if reasoning else answer

                result.append({
                    "problem": problem,
                    "solution": solution,
                    "reasoning": reasoning,
                    "answer": answer,
                    "section_idx": section_idx,
                    "section_title": section_title,
                    "source": source,
                    "type": "text",
                })
        return result
    except json.JSONDecodeError as e:
        _log(f"JSON parse error: {e} - content: {content[:100]}...", style="yellow")
        return []
    except Exception as e:
        _log(f"Parse error: {e}", style="yellow")
        return []


def _section_heuristic_fallback(
    sections: List[Tuple[str, str]],
    section_idx: int,
    source: str,
) -> List[Dict[str, Any]]:
    """Heuristic fallback for a single failed section."""
    title, content = sections[section_idx]
    qa_pairs = extract_qa_heuristic(content, source=source, section_title=title)
    for qa in qa_pairs:
        qa["section_idx"] = section_idx
        qa["section_title"] = title
        qa["source"] = source
        qa["type"] = "text"
    return qa_pairs


def _fallback_heuristic_extraction(
    sections: List[Tuple[str, str]],
    source: str,
) -> List[Dict[str, Any]]:
    """Full heuristic fallback when batch fails."""
    all_qa = []
    for idx, (title, content) in enumerate(sections):
        qa_pairs = extract_qa_heuristic(content, source=source, section_title=title)
        for qa in qa_pairs:
            qa["section_idx"] = idx
            qa["section_title"] = title
            qa["source"] = source
            qa["type"] = "text"
        all_qa.extend(qa_pairs)
    return all_qa


def extract_qa_heuristic(section_content: str, source: str = "", section_title: str = "") -> List[Dict[str, str]]:
    """Heuristic Q&A extraction from a section.

    Uses section title as question context, content as answer.
    """
    content = section_content.strip()
    if not content:
        return []

    # Build problem from section title or first sentence
    if section_title:
        # Section title tells us what this is about
        problem = f"What is {section_title}?" if not section_title.endswith("?") else section_title
    else:
        # Use first sentence as context
        sents = split_sentences(content)
        problem = sents[0][:200] if sents else "Unknown topic"

    # Add source prefix
    if source:
        problem = f"[{source}] {problem}"

    # Solution is the section content (truncated if needed)
    solution = content[:1000] if len(content) > 1000 else content

    return [{"problem": problem, "solution": solution}]


# =============================================================================
# Memory Integration
# =============================================================================

def store_qa(problem: str, solution: str, scope: str, tags: List[str] = None) -> bool:
    """Store Q&A pair via memory-agent learn."""
    cmd = [
        "memory-agent", "learn",
        "--problem", problem,
        "--solution", solution,
        "--scope", scope,
    ]
    if tags:
        for tag in tags:
            cmd.extend(["--tag", tag])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception as e:
        _log(f"Failed to store: {e}", style="red")
        return False


# =============================================================================
# Main Distill Logic
# =============================================================================

def distill(
    *,
    url: str = None,
    text: str = None,
    file_path: str = None,
    scope: str = "research",
    max_section_chars: int = 5000,
    dry_run: bool = False,
    no_llm: bool = False,
    extract_code: bool = True,
    use_treesitter: bool = False,
    mode: str = "fast",
    show_preflight: bool = False,
    batch: bool = True,
    concurrency: int = 6,
    validate_grounding: bool = True,
    grounding_threshold: float = 0.6,  # 60% similarity - catches most hallucinations
    context: str = None,
    context_file: str = None,
    sections_only: bool = False,
) -> Dict[str, Any]:
    """Distill content into Q&A pairs and store in memory.

    Args:
        extract_code: If True, extract code blocks separately with language metadata
        use_treesitter: If True, parse code with treesitter for symbol extraction
        mode: PDF extraction mode - "fast" (pymupdf4llm), "accurate" (marker-pdf), "auto"
        show_preflight: If True, show PDF preflight assessment
        batch: If True (default), use parallel batch LLM calls via scillm
        concurrency: Max parallel LLM requests for batch mode (default 6)
        validate_grounding: If True (default), filter out QRAs not grounded in source
        grounding_threshold: Minimum similarity score (0.0-1.0) for grounding (default 0.5)
        context: Domain context/persona for focused extraction (e.g., "cybersecurity expert")
        context_file: File path to read context from
        sections_only: If True, only extract sections without QRA generation

    Returns summary of what was distilled and stored (or sections if sections_only).
    """
    import asyncio

    # Load context from file if specified
    if context_file:
        context = Path(context_file).read_text(encoding="utf-8").strip()

    # Get content
    if url:
        content = fetch_url(url)
        source = urlparse(url).netloc + urlparse(url).path[:30]
    elif file_path:
        content = read_file(file_path, mode=mode, show_preflight=show_preflight)
        source = Path(file_path).name
    elif text:
        content = text
        source = "text"
    else:
        raise ValueError("Must provide --url, --file, or --text")

    if not content.strip():
        return {"stored": 0, "source": source, "error": "Empty content"}

    # Show initial status
    status_info = {
        "Source": source,
        "Content size": f"{len(content):,} chars",
        "Mode": mode,
        "Scope": scope,
    }
    if context:
        status_info["Context"] = (context[:40] + "...") if len(context) > 40 else context
    _status_panel("Distill Starting", status_info)

    # Extract code blocks first (before section splitting)
    code_qa: List[Dict[str, Any]] = []
    if extract_code:
        code_blocks = extract_code_blocks(content)
        _log(f"Found {len(code_blocks)} code blocks")

        for idx, block in enumerate(_iter_with_progress(code_blocks, desc="Parsing code blocks")):
            language = block["language"]
            code = block["code"]

            # Optionally parse with treesitter for richer extraction
            symbols = []
            if use_treesitter and language not in ("text", "output", ""):
                symbols = parse_code_with_treesitter(code, language)

            if symbols:
                # Create Q&A for each symbol
                for sym in symbols:
                    if sym.get("kind") in ("function", "class", "method"):
                        problem = f"[{source}][{language}] What does {sym['kind']} `{sym['name']}` do?"
                        solution = f"```{language}\n{sym.get('content', sym.get('signature', code[:500]))}\n```"
                        if sym.get("docstring"):
                            solution = f"{sym['docstring']}\n\n{solution}"
                        code_qa.append({
                            "problem": problem,
                            "solution": solution,
                            "type": "code",
                            "language": language,
                            "symbol": sym["name"],
                            "kind": sym["kind"],
                            "source": source,
                        })
            else:
                # Store code block as-is
                problem = f"[{source}][{language}] Code example"
                if len(code) < 100:
                    problem = f"[{source}][{language}] {code.split(chr(10))[0][:60]}"
                solution = f"```{language}\n{code}\n```"
                code_qa.append({
                    "problem": problem,
                    "solution": solution,
                    "type": "code",
                    "language": language,
                    "source": source,
                })

        _log(f"{len(code_qa)} code Q&A pairs created")

    # Build sections (respects document structure)
    sections = build_sections(content, max_section_chars=max_section_chars)
    _log(f"Split into {len(sections)} sections")

    # If sections_only, return early with just the sections
    if sections_only:
        _status_panel("Sections Extracted", {
            "Source": source,
            "Sections": len(sections),
            "Code blocks": len(code_qa) if extract_code else 0,
        })
        sections_data = [
            {"title": title, "content": content, "index": idx}
            for idx, (title, content) in enumerate(sections)
        ]
        return {
            "sections": sections_data,
            "section_count": len(sections),
            "code_blocks": len(code_qa) if extract_code else 0,
            "source": source,
        }

    # Extract Q&A from each section
    all_qa: List[Dict[str, str]] = []

    if no_llm or os.getenv("DISTILL_NO_LLM"):
        # Heuristic mode - sequential
        _log("Extracting QRA using heuristic method")
        for idx, (section_title, section_content) in enumerate(_iter_with_progress(sections, desc="Extracting QRA")):
            qa_pairs = extract_qa_heuristic(section_content, source=source, section_title=section_title)
            for qa in qa_pairs:
                qa["section_idx"] = idx
                qa["section_title"] = section_title
                qa["source"] = source
                qa["type"] = "text"
                all_qa.append(qa)
    elif batch:
        # Batch mode - parallel LLM calls via scillm
        _log(f"Extracting QRA using batch LLM (concurrency={concurrency})", style="bold blue")
        try:
            # Use asyncio.run() for clean event loop management
            all_qa = asyncio.run(
                extract_qra_batch(sections, source=source, concurrency=concurrency, timeout=60, context=context)
            )
        except Exception as e:
            import traceback
            _log(f"Batch extraction error: {e}", style="red")
            _log(f"Traceback: {traceback.format_exc()[:500]}", style="dim")
            _log("Falling back to heuristic extraction", style="yellow")
            all_qa = _fallback_heuristic_extraction(sections, source)
    else:
        # Sequential LLM mode
        _log("Extracting QRA using sequential LLM")
        for idx, (section_title, section_content) in enumerate(_iter_with_progress(sections, desc="Extracting QRA")):
            qa_pairs = extract_qra_llm(section_content, source=source, section_title=section_title)
            for qa in qa_pairs:
                qa["section_idx"] = idx
                qa["section_title"] = section_title
                qa["source"] = source
                qa["type"] = "text"
                all_qa.append(qa)

    # Combine text and code Q&A
    all_qa.extend(code_qa)
    _log(f"{len(all_qa)} total Q&A pairs extracted", style="bold")

    # Grounding validation - filter out hallucinated QRAs
    if validate_grounding and all_qa:
        all_qa = _validate_and_filter_qras(
            all_qa, sections,
            validate_grounding=True,
            grounding_threshold=grounding_threshold
        )

    # Store or dry-run
    stored = 0
    if dry_run:
        _log(f"DRY RUN - would store {len(all_qa)} pairs", style="yellow")
    else:
        _log(f"Storing {len(all_qa)} pairs to scope '{scope}'")
        for qa in _iter_with_progress(all_qa, desc="Storing to memory"):
            tags = ["distilled", source.split("/")[0] if "/" in source else source]
            if qa.get("type") == "code":
                tags.append("code")
                if qa.get("language"):
                    tags.append(qa["language"])
            if store_qa(qa["problem"], qa["solution"], scope, tags=tags):
                stored += 1

    # Final summary
    _status_panel("Distill Complete", {
        "Extracted": f"{len(all_qa)} Q&A pairs",
        "Stored": f"{stored}" if not dry_run else "(dry run)",
        "Sections": len(sections),
        "Code blocks": len(code_qa) if extract_code else 0,
        "Scope": scope,
    })

    return {
        "stored": stored,
        "extracted": len(all_qa),
        "sections": len(sections),
        "code_blocks": len(code_qa) if extract_code else 0,
        "text_qa": len(all_qa) - len(code_qa) if extract_code else len(all_qa),
        "source": source,
        "scope": scope,
        "qa_pairs": all_qa if dry_run else all_qa[:5],  # Sample in non-dry-run
    }


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Distill PDF/URL/text into Q&A pairs for memory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --file paper.pdf --scope research
  %(prog)s --file paper.pdf --context "ML researcher" --dry-run
  %(prog)s --url https://example.com/doc --scope web

Environment variables for tuning (optional):
  DISTILL_CONCURRENCY      Parallel LLM requests (default: 6)
  DISTILL_GROUNDING_THRESH Grounding similarity threshold (default: 0.6)
  DISTILL_NO_GROUNDING     Set to 1 to skip grounding validation
  DISTILL_PDF_MODE         PDF mode: fast, accurate, auto (default: fast)
"""
    )

    # === Essential flags (agent-facing) ===
    parser.add_argument("--file", dest="file_path", help="PDF, markdown, or text file to distill")
    parser.add_argument("--url", help="URL to fetch and distill")
    parser.add_argument("--text", help="Raw text to distill")
    parser.add_argument("--scope", default="research", help="Memory scope (default: research)")
    parser.add_argument("--context", help="Domain focus, e.g. 'ML researcher' or 'security expert'")
    parser.add_argument("--dry-run", action="store_true", help="Preview Q&A without storing to memory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--sections-only", action="store_true",
                        help="Only extract sections (no Q&A generation)")

    # === Hidden expert flags (use env vars instead) ===
    parser.add_argument("--context-file", dest="context_file", help=argparse.SUPPRESS)
    parser.add_argument("--mode", choices=["fast", "accurate", "auto"],
                        default=os.getenv("DISTILL_PDF_MODE", "fast"), help=argparse.SUPPRESS)
    parser.add_argument("--preflight", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--max-section-chars", type=int, default=5000, help=argparse.SUPPRESS)
    parser.add_argument("--no-llm", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-code", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--treesitter", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--batch", dest="batch", action="store_true", default=True, help=argparse.SUPPRESS)
    parser.add_argument("--no-batch", dest="batch", action="store_false", help=argparse.SUPPRESS)
    parser.add_argument("--concurrency", type=int,
                        default=int(os.getenv("DISTILL_CONCURRENCY", "6")), help=argparse.SUPPRESS)
    parser.add_argument("--validate-grounding", dest="validate_grounding", action="store_true",
                        default=not os.getenv("DISTILL_NO_GROUNDING"), help=argparse.SUPPRESS)
    parser.add_argument("--no-validate-grounding", dest="validate_grounding",
                        action="store_false", help=argparse.SUPPRESS)
    parser.add_argument("--grounding-threshold", type=float,
                        default=float(os.getenv("DISTILL_GROUNDING_THRESH", "0.6")), help=argparse.SUPPRESS)

    args = parser.parse_args()

    if not any([args.url, args.text, args.file_path]):
        parser.error("Must provide --url, --file, or --text")

    try:
        result = distill(
            url=args.url,
            text=args.text,
            file_path=args.file_path,
            scope=args.scope,
            max_section_chars=args.max_section_chars,
            dry_run=args.dry_run,
            no_llm=args.no_llm,
            extract_code=not args.no_code,
            use_treesitter=args.treesitter,
            mode=args.mode,
            show_preflight=args.preflight,
            batch=args.batch,
            concurrency=args.concurrency,
            validate_grounding=args.validate_grounding,
            grounding_threshold=args.grounding_threshold,
            context=args.context,
            context_file=args.context_file,
            sections_only=args.sections_only,
        )

        if args.json:
            print(json.dumps(result, indent=2))
        elif args.sections_only:
            # Sections-only output
            print(f"Extracted: {result['section_count']} sections from {result['source']}")
            if result.get("sections"):
                print("\nSections:")
                for sec in result["sections"][:5]:
                    title = sec.get("title", "(untitled)")[:50]
                    content_preview = sec.get("content", "")[:60].replace("\n", " ")
                    print(f"  [{sec['index']}] {title}")
                    print(f"      {content_preview}...")
                if len(result["sections"]) > 5:
                    print(f"  ... and {len(result['sections']) - 5} more")
        else:
            print(f"Distilled: {result['extracted']} Q&A pairs from {result['sections']} sections")
            print(f"Stored: {result['stored']} pairs in scope '{result['scope']}'")
            print(f"Source: {result['source']}")
            if result.get("qa_pairs"):
                print("\nSample Q&A:")
                for qa in result["qa_pairs"][:2]:
                    print(f"  Q: {qa['problem'][:80]}...")
                    print(f"  A: {qa['solution'][:80]}...")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
