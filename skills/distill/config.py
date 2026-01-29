#!/usr/bin/env python3
"""Configuration constants, paths, and environment variables for distill skill.

This module centralizes all configuration to make the distill skill
more maintainable and testable.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict

# =============================================================================
# Paths
# =============================================================================

SCRIPT_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPT_DIR.parent

# Add skills directory to path for common imports
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

# =============================================================================
# Environment Loading
# =============================================================================

# Best-effort .env loading
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except Exception:
    pass

# =============================================================================
# LLM/API Configuration
# =============================================================================


def get_scillm_config() -> Dict[str, str]:
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


def get_chutes_config() -> Dict[str, str]:
    """Get Chutes API configuration for marker-pdf LLM enhancement."""
    return {
        "api_key": os.getenv("CHUTES_API_KEY", ""),
        "base_url": os.getenv("CHUTES_API_BASE", "https://llm.chutes.ai/v1"),
        "model": os.getenv("CHUTES_MODEL", "deepseek-ai/DeepSeek-V3"),
    }


# =============================================================================
# PDF Complexity Thresholds
# =============================================================================

COMPLEXITY_THRESHOLDS: Dict[str, int] = {
    "table_weight": 2,        # Weight for tables detected
    "image_weight": 1,        # Weight for images detected
    "multi_col_weight": 2,    # Weight for multi-column layout
    "large_doc_pages": 50,    # Pages threshold for "large doc" penalty
    "large_doc_weight": 1,    # Weight for large documents
    "medium_threshold": 2,    # Score >= this = medium complexity
    "complex_threshold": 4,   # Score >= this = complex (recommend accurate)
}

# =============================================================================
# Section Detection Patterns
# =============================================================================

# Markdown headers
RE_MD_HEADER = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

# Section numbering patterns (from extractor/pipeline/utils/sections/heuristics.py)
# Decimal: 1.2.3 Title, 1.2.3. Title
RE_DECIMAL = re.compile(
    r'^\s*(\d+(?:\.\d+)*(?:\.[a-z])?)\s*[.:)\-\u2013\u2014]?\s+(\S.*)$',
    re.MULTILINE | re.IGNORECASE
)

# Roman numerals: I. Title, II. Title (require trailing dot to avoid false positives)
RE_ROMAN = re.compile(
    r'^\s*([IVXLCDM]+(?:\.[IVXLCDM]+)*)\.\s+(\S.*)$',
    re.MULTILINE | re.IGNORECASE
)

# Alpha sections: A. Title, A.1 Title, B.2.3 Title
RE_ALPHA = re.compile(
    r'^\s*([A-Z](?:\.\d+)*)\.\s+([^=].*)$',
    re.MULTILINE
)

# Labeled sections: Appendix A, Chapter 1, Section 2.3
RE_LABELED = re.compile(
    r'^\s*(Appendix|Annex|Section|Chapter|Part)\s+([A-Za-z0-9IVXLCDM.]+)\s*[:.\-\u2013\u2014]?\s+(\S.*)$',
    re.MULTILINE | re.IGNORECASE
)

# Negative patterns - skip these as sections (from extractor heuristics)
RE_CAPTION = re.compile(
    r'^\s*(Table|Figure|Exhibit|Listing)\s+\d+(?:[-\u2013]\d+)?(?:[.:]|\s*\()',
    re.IGNORECASE
)

RE_REQUIREMENT = re.compile(r'^\s*REQ-[\w-]+[:\s]', re.IGNORECASE)

# Date patterns: "13 February 2015", "2024-01-15", "January 15, 2024"
RE_DATE = re.compile(
    r'^\s*(?:'
    r'\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}'
    r'|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}'
    r'|\d{4}[-/]\d{2}[-/]\d{2}'
    r')\s*$',
    re.IGNORECASE
)

# =============================================================================
# Common Abbreviations for Sentence Splitting
# =============================================================================

ABBREVIATIONS = {
    "fig", "sec", "no", "dr", "mr", "mrs", "ms", "prof",
    "u.s", "u.k", "dept", "inc", "ltd", "vs", "etc", "e.g", "i.e", "cf", "al"
}

# =============================================================================
# Default QRA Extraction Settings
# =============================================================================

DEFAULT_MAX_SECTION_CHARS = 5000
DEFAULT_CONCURRENCY = 6
DEFAULT_GROUNDING_THRESHOLD = 0.6
DEFAULT_TIMEOUT = 60
DEFAULT_BATCH_TIMEOUT = 900  # 15 minutes wall time

# =============================================================================
# Treesitter Language Mapping
# =============================================================================

TREESITTER_LANG_MAP: Dict[str, str] = {
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
