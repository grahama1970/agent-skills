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
    # File is at pi-mono/.pi/skills/extractor/config.py
    potential_root = Path(__file__).resolve().parents[4]
    if (potential_root / "src/extractor").exists():
        return potential_root

    # Fallback to local workspace assumptions
    return Path("/home/graham/workspace/experiments/extractor")


EXTRACTOR_ROOT = _resolve_extractor_root()

if not EXTRACTOR_ROOT.exists():
    print(f"FATAL: Extractor root not found at {EXTRACTOR_ROOT}", file=sys.stderr)
    sys.exit(1)

# Add extractor src to path
sys.path.insert(0, str(EXTRACTOR_ROOT / "src"))

# Memory skill path
MEMORY_SKILL_PATH = Path(os.environ.get(
    "MEMORY_SKILL_PATH",
    EXTRACTOR_ROOT.parent / "pi-mono/.pi/skills/memory/run.sh"
))
if not MEMORY_SKILL_PATH.exists():
    MEMORY_SKILL_PATH = Path(__file__).resolve().parents[3] / "memory/run.sh"

# --------------------------------------------------------------------------
# Format Definitions
# --------------------------------------------------------------------------

# Formats that use the full PDF pipeline
PIPELINE_FORMATS = {".pdf"}

# Formats that use fast structured extraction
STRUCTURED_FORMATS = {".docx", ".html", ".htm", ".xml", ".pptx", ".xlsx", ".md", ".rst", ".epub"}

# Image formats (low parity without VLM, but still supported)
IMAGE_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}

# Confidence threshold for auto-extraction
CONFIDENCE_THRESHOLD = 8

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
