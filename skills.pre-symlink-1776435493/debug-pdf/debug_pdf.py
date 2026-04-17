#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pymupdf>=1.23.0",
#     "pymupdf4llm>=0.0.17",
#     "httpx>=0.25.0",
#     "typer>=0.9.0",
#     "loguru>=0.7.0",
# ]
# ///
"""
Debug PDF Skill - Failure-to-fixture automation for PDF extractors.

Assembles all CLI command groups and re-exports public symbols
for backward compatibility with tests and task files.
"""
import sys
from pathlib import Path

# Ensure this directory is importable when running as a script
ROOT = Path(__file__).parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dp_app import app

# Import all modules to register detectors and CLI commands
import dp_config  # noqa: F401
import dp_registry  # noqa: F401
import dp_detectors_layout  # noqa: F401
import dp_detectors_domain  # noqa: F401
import dp_detectors_quality  # noqa: F401
import dp_core  # noqa: F401
import dp_cli  # noqa: F401

# Re-export public symbols for backward compatibility (used by tests/test_debug_pdf.py)
from dp_registry import (
    PAGE_DETECTORS,
    DOC_DETECTORS,
    PATTERNS,
    is_wayback_url,
    extract_original_url,
    is_valid_url,
    register_page_detector,
    register_doc_detector,
)
from dp_detectors_layout import (
    detect_header_footer_bleed,
    detect_multi_column,
    detect_split_tables,
    detect_footnotes,
    detect_signed_contract,
    detect_government_signatures,
)
from dp_detectors_domain import (
    detect_itar_export_control,
    detect_mil_spec_reference,
    detect_aerospace_spec,
    detect_technical_drawing,
    detect_classification_marking,
    detect_cage_dfar_reference,
)
from dp_core import analyze_pdf


if __name__ == "__main__":
    app()
