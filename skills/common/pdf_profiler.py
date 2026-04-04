"""Shared PDF profiler — thin wrapper around pdf_oxide.survey.

All detection logic lives in ``pdf_oxide.survey.survey_document()``.
This module provides the ``profile_pdf(path)`` convenience function
that opens a PdfDocument and calls ``survey_document(doc, enrich_profile=True)``.

Usage:
    from common.pdf_profiler import profile_pdf
    result = profile_pdf("/path/to/doc.pdf")
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def profile_pdf(pdf_path: str | Path) -> dict[str, Any]:
    """Profile a PDF document with page-level detail.

    Opens the PDF via ``pdf_oxide.PdfDocument``, runs
    ``survey_document()`` with profile enrichment, and returns
    the combined result dict.

    Returns:
        Dict with survey fields (table_pages, figure_pages, columns,
        equation_pages, section_count, has_toc, etc.) plus Rust-level
        profile fields (domain, complexity_score, is_scanned, preset,
        layout, primary_font, title).
    """
    from pdf_oxide import PdfDocument
    from pdf_oxide.survey import survey_document

    doc = PdfDocument(str(pdf_path))
    return survey_document(doc, enrich_profile=True)
