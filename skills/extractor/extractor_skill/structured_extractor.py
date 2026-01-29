#!/usr/bin/env python3
"""
Structured document extraction (DOCX, HTML, XML, PPTX, XLSX, etc.).

This module handles fast extraction for structured formats using
the extractor provider registry.
"""
from pathlib import Path
from typing import Any, Dict

from extractor_skill.utils import format_error_guidance


def extract_structured(filepath: Path) -> Dict[str, Any]:
    """
    Fast extraction for structured formats (DOCX, HTML, XML, etc.).

    Uses the extractor provider registry to find the appropriate
    provider for the file format.

    Args:
        filepath: Path to the document

    Returns:
        Dict with extraction result:
        - success: True/False
        - mode: "structured"
        - format: File extension
        - document: Extracted document (on success)
        - error: Error message (on failure)
        - guidance: Troubleshooting guidance (on failure)
    """
    try:
        from extractor.core.providers.registry import provider_from_filepath

        provider_cls = provider_from_filepath(str(filepath))
        # All providers now support the standard pattern
        provider = provider_cls()
        doc = provider.extract_document(str(filepath))

        return {
            "success": True,
            "mode": "structured",
            "format": filepath.suffix.lower(),
            "document": doc.model_dump(),
        }
    except Exception as e:
        error_msg = str(e)
        return {
            "success": False,
            "error": error_msg,
            "format": filepath.suffix.lower(),
            "guidance": format_error_guidance(error_msg, filepath),
        }
