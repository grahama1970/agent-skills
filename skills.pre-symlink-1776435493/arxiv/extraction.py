#!/usr/bin/env python3
"""Content extraction for arxiv-learn skill."""
from __future__ import annotations

import re
from pathlib import Path
from html.parser import HTMLParser

from config import VLM_FIGURE_THRESHOLD, VLM_TABLE_THRESHOLD
from utils import log, run_skill, LearnSession


def quick_profile_html(html_content: str) -> dict:
    """Profile HTML to determine if VLM is needed based on figure/table counts."""
    # Count figure tags (including nested img in figures)
    figure_pattern = re.compile(r'<figure[^>]*>', re.IGNORECASE)
    figures = len(figure_pattern.findall(html_content))

    # Count table tags (data tables, not layout tables)
    table_pattern = re.compile(r'<table[^>]*class="[^"]*ltx_tabular[^"]*"[^>]*>', re.IGNORECASE)
    tables = len(table_pattern.findall(html_content))

    # Fallback: count all table tags if no ltx_tabular found
    if tables == 0:
        all_tables_pattern = re.compile(r'<table[^>]*>', re.IGNORECASE)
        tables = len(all_tables_pattern.findall(html_content))

    # Heuristic: ar5iv HTML includes figure captions and table data,
    # so VLM is only needed for papers with heavy visual content
    # that can't be understood from captions alone.
    needs_vlm = figures > VLM_FIGURE_THRESHOLD or tables > VLM_TABLE_THRESHOLD

    recommendation = "accurate" if needs_vlm else "fast"

    return {
        "needs_vlm": needs_vlm, "has_figures": figures,
        "has_tables": tables, "recommendation": recommendation,
    }


class _Ar5ivTextExtractor(HTMLParser):
    """Stdlib HTML parser for ar5iv papers. No external dependencies."""

    # Tags whose content we skip entirely
    SKIP_TAGS = {"script", "style", "nav", "footer", "header", "noscript", "svg", "math"}
    # Block-level tags that get newlines
    BLOCK_TAGS = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6",
                  "li", "tr", "blockquote", "pre", "figcaption", "dt", "dd"}
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0
        self._tag_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        tag = tag.lower()
        self._tag_stack.append(tag)
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if self._skip_depth == 0:
            if tag in self.HEADING_TAGS:
                self._parts.append("\n## ")
            elif tag in self.BLOCK_TAGS:
                self._parts.append("\n")
            if tag == "li":
                self._parts.append("  - ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if self._skip_depth == 0 and tag in self.BLOCK_TAGS:
            self._parts.append("\n")
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        # Collapse runs of 3+ newlines to 2
        import re as _re
        return _re.sub(r"\n{3,}", "\n\n", raw).strip()


def _extract_text_from_ar5iv_html(html_path: str) -> str:
    """Extract text from ar5iv HTML using stdlib html.parser.

    This is a zero-dependency fallback for when the extractor skill
    (which needs Ollama/Schematron3B) is unavailable.
    """
    with open(html_path, encoding="utf-8", errors="replace") as f:
        html_content = f.read()

    parser = _Ar5ivTextExtractor()
    parser.feed(html_content)
    return parser.get_text()


def extract_from_html(html_path: str, dry_run: bool = False) -> dict:
    """Extract content from HTML file."""
    log("Using HTML extraction (fast mode)", style="green")

    if dry_run:
        log("DRY RUN - would extract from HTML", style="yellow")
        return {
            "format": "html",
            "source": "ar5iv",
            "success": True,
            "dry_run": True,
            "full_text": "",
            "char_count": 0,
            "sections": [],
        }

    # Run extractor in HTML mode
    extractor_args = [
        html_path,
        "--fast",
        "--json",
    ]

    try:
        result = run_skill("extractor", extractor_args)

        # Extract text from blocks
        full_text = ""
        if isinstance(result, dict):
            doc = result.get("document", {})
            blocks = doc.get("blocks", [])
            text_parts = []

            for block in blocks:
                content = block.get("content", "")
                block_type = block.get("type", "")

                # Handle different block types
                if isinstance(content, dict):
                    # Figure blocks: extract caption
                    if block_type == "figure":
                        caption = content.get("caption", "")
                        title = content.get("title", "")
                        if caption:
                            text_parts.append(f"[Figure: {caption}]")
                        elif title:
                            text_parts.append(f"[Figure: {title}]")
                    continue
                elif isinstance(content, str) and content.strip():
                    if block_type == "heading":
                        text_parts.append(f"\n## {content}\n")
                    elif block_type == "listitem":
                        text_parts.append(f"  - {content}")
                    else:
                        text_parts.append(content)

            full_text = "\n".join(text_parts)

        return {
            "format": "html",
            "source": "ar5iv",
            "success": True,
            "full_text": full_text,
            "char_count": len(full_text),
            "sections": [],
        }
    except Exception as e:
        log(f"HTML extraction failed: {e}", style="yellow")
        # Fallback: pure stdlib HTML text extraction (no Ollama needed)
        log("Trying stdlib HTML text extraction (no Ollama required)...", style="cyan")
        try:
            fallback_text = _extract_text_from_ar5iv_html(html_path)
            if fallback_text and len(fallback_text) > 500:
                log(f"Stdlib extraction got {len(fallback_text)} chars", style="green")
                return {
                    "format": "html",
                    "source": "ar5iv-stdlib",
                    "success": True,
                    "full_text": fallback_text,
                    "char_count": len(fallback_text),
                    "sections": [],
                }
            else:
                log(f"Stdlib extraction too short ({len(fallback_text)} chars)", style="yellow")
        except Exception as e2:
            log(f"Stdlib HTML fallback also failed: {e2}", style="yellow")
        raise


def extract_from_pdf(pdf_path: str, dry_run: bool = False) -> dict:
    """Extract content from PDF file."""
    log("Using PDF extraction (accurate mode)", style="cyan")

    if dry_run:
        log("DRY RUN - would extract from PDF", style="yellow")
        return {
            "format": "pdf",
            "source": "arxiv",
            "success": True,
            "dry_run": True,
            "full_text": "",
            "char_count": 0,
            "sections": [],
        }

    extractor_args = [
        pdf_path,
        "--accurate",
        "--json",
    ]

    try:
        result = run_skill("extractor", extractor_args)
        if not isinstance(result, dict):
            raise RuntimeError("Extractor returned non-JSON output")

        return {
            "format": "pdf",
            "source": "arxiv",
            "success": True,
            "full_text": result.get("full_text", ""),
            "char_count": len(result.get("full_text", "")),
            "sections": result.get("sections", []),
        }
    except Exception as e:
        raise RuntimeError(f"Extraction failed: {e}")


def extract_content(session: LearnSession) -> dict:
    """Extract content using HTML-first routing with PDF fallback."""
    log("Extracting content...", style="bold", stage=2)

    if not session.paper:
        raise ValueError("No paper loaded")

    # Determine extraction mode
    use_pdf = session.accurate

    # Check if profile suggests VLM is needed
    if session.profile and session.profile.get("needs_vlm"):
        log("Profile suggests VLM needed (many figures/tables)", style="yellow")
        use_pdf = True

    # Use HTML if available and not forced to PDF
    if not use_pdf and session.paper.html_path:
        try:
            return extract_from_html(session.paper.html_path, session.dry_run)
        except Exception as e:
            log(f"HTML extraction failed, falling back to PDF: {e}", style="yellow")
            use_pdf = True

    return extract_from_pdf(session.paper.pdf_path, session.dry_run)


# ---------------------------------------------------------------------------
# Backward-compatible re-exports from qa_extraction (split for line limit)
# ---------------------------------------------------------------------------
from qa_extraction import (  # noqa: F401
    find_context_file,
    extract_qa_from_text,
    is_implementation_detail,
    add_recommendations,
    distill_paper,
)


__all__ = [
    "quick_profile_html",
    "find_context_file",
    "extract_from_html",
    "_extract_text_from_ar5iv_html",
    "extract_from_pdf",
    "extract_content",
    "extract_qa_from_text",
    "is_implementation_detail",
    "add_recommendations",
    "distill_paper",
]
