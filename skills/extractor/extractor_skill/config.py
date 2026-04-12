#!/usr/bin/env python3
"""
Configuration and constants for extractor skill.

This module centralizes all paths, format definitions, and configuration
constants used across the extractor modules.
"""
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------
# Path Configuration
# --------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPT_DIR.parent

# Add skills directory to path for common imports
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))


def _resolve_extractor_root() -> Path:
    """Resolve the extractor project root directory."""
    if os.environ.get("EXTRACTOR_ROOT"):
        return Path(os.environ["EXTRACTOR_ROOT"])

    # Attempt to find it relative to this file
    # File is at pi-mono/.pi/skills/extractor/extractor_skill/config.py
    potential_root = Path(__file__).resolve().parents[4]
    if (potential_root / "src/extractor").exists():
        return potential_root

    # Check sibling directory (pi-mono/../extractor)
    sibling = potential_root.parent / "extractor"
    if (sibling / "src/extractor").exists():
        return sibling

    # Fallback
    return potential_root / "extractor"


EXTRACTOR_ROOT = _resolve_extractor_root()

# Legacy extractor path - non-fatal since pdf_oxide is primary now
if EXTRACTOR_ROOT.exists():
    sys.path.insert(0, str(EXTRACTOR_ROOT / "src"))
else:
    # pdf_oxide is the primary path now, legacy extractor optional
    print(
        f"INFO: Legacy extractor not found at {EXTRACTOR_ROOT}. "
        "Using pdf_oxide for PDF extraction.",
        file=sys.stderr,
    )

# --------------------------------------------------------------------------
# Format Definitions
# --------------------------------------------------------------------------

# Formats that use the full PDF pipeline
PIPELINE_FORMATS = {".pdf"}

# Formats that use fast structured extraction
STRUCTURED_FORMATS = {".docx", ".html", ".htm", ".xml", ".pptx", ".xlsx", ".md", ".rst", ".epub"}

# Image formats (low parity without VLM, but still supported)
IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}

# --------------------------------------------------------------------------
# Quality Gate Thresholds (env var configurable)
# --------------------------------------------------------------------------

# Confidence threshold for auto-extraction
CONFIDENCE_THRESHOLD = int(os.getenv("EXTRACTOR_GATE_CONFIDENCE_MIN", "8"))

# Batch operation thresholds
SUCCESS_RATE_THRESHOLD = float(os.getenv("EXTRACTOR_GATE_SUCCESS_RATE_MIN", "0.8"))
ERROR_RATE_MAX = float(os.getenv("EXTRACTOR_GATE_ERROR_RATE_MAX", "0.1"))
CONSECUTIVE_ERRORS_MAX = int(os.getenv("EXTRACTOR_GATE_CONSECUTIVE_ERRORS_MAX", "5"))

# Retry configuration
RETRY_MAX = int(os.getenv("EXTRACTOR_RETRY_MAX", "3"))
RETRY_BASE_DELAY = float(os.getenv("EXTRACTOR_RETRY_BASE_DELAY", "0.5"))

# --------------------------------------------------------------------------
# Table Classifier Integration (95%+ accuracy ensemble)
# --------------------------------------------------------------------------

TABLE_CLASSIFIER_MODEL_PATH = Path(os.environ.get(
    "TABLE_CLASSIFIER_MODEL_PATH",
    EXTRACTOR_ROOT.parent / "pi-mono/.pi/skills/create-table-classifier/models/table-classifier-ensemble-final"
))
USE_TABLE_CLASSIFIER = os.getenv("USE_STRATEGY_PREDICTOR", "true").lower() in ("1", "true", "yes")
TABLE_CLASSIFIER_CONFIDENCE = float(os.getenv("STRATEGY_PREDICTOR_CONFIDENCE_THRESHOLD", "0.75"))

# --------------------------------------------------------------------------
# Extraction Options
# --------------------------------------------------------------------------


@dataclass
class ExtractionOptions:
    """Consolidated options for the extraction pipeline."""
    mode: str = "auto"
    preset: Optional[str] = None
    output_dir: Optional[Path] = None
    return_markdown: bool = False
    interactive: bool = True
    auto_ocr: Optional[bool] = None
    skip_scanned: bool = False
    ocr_lang: str = "eng"
    ocr_deskew: bool = False
    ocr_force: bool = False
    ocr_timeout: int = 600
    continue_on_error: bool = False
    sections_only: bool = False
    sync_to_memory: bool = True
    # PDF decryption options
    auto_decrypt: bool = True  # Attempt to decrypt encrypted PDFs automatically
    decrypt_password: Optional[str] = None  # Password for encrypted PDFs
