#!/usr/bin/env python3
"""
Configuration and constants for arxiv-learn skill.

This module centralizes all paths, constants, and configuration values
used across the arxiv skill modules.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# =============================================================================
# Path Configuration
# =============================================================================

# Resolve skill directories
SCRIPT_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPT_DIR.parent

# Add skills dir to path for imports
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

# Paper storage directories
PAPERS_DIR = SCRIPT_DIR / "papers"
CONTEXTS_DIR = SCRIPT_DIR / "contexts"

# State file for task monitor
STATE_DIR = Path.home() / ".pi" / "arxiv"

# =============================================================================
# API Configuration
# =============================================================================

# arXiv API rate limits
ARXIV_MAX_REQ_PER_MIN = int(os.environ.get("ARXIV_MAX_REQ_PER_MIN", "30") or "30")
ARXIV_REQUEST_TIMEOUT = 20  # seconds

# ar5iv HTML download
AR5IV_BASE_URL = "https://ar5iv.org/abs"
AR5IV_TIMEOUT = 30  # seconds

# =============================================================================
# Processing Configuration
# =============================================================================

# Extraction mode thresholds
# VLM is recommended only for papers with heavy visual content
VLM_FIGURE_THRESHOLD = 20  # figures > this triggers VLM
VLM_TABLE_THRESHOLD = 10   # tables > this triggers VLM

# Q&A extraction
MIN_TEXT_LENGTH = 100  # minimum chars for Q&A extraction
MIN_FALLBACK_TEXT_LENGTH = 1000  # minimum chars before trying legacy distill

# Grounding score thresholds for recommendations
GROUNDING_KEEP_THRESHOLD = 0.7  # >= this is "well grounded"
GROUNDING_REVIEW_THRESHOLD = 0.5  # >= this is "moderately grounded"

# =============================================================================
# Memory Configuration
# =============================================================================

# Rate limiting for memory operations
MEMORY_REQUESTS_PER_SECOND = 5

# Edge verification limits
DEFAULT_MAX_EDGES = 20
EDGE_VERIFIER_K = 25
EDGE_VERIFIER_TOP = 5
EDGE_VERIFIER_MAX_LLM = 5
EDGE_VERIFIER_TIMEOUT = 120  # seconds

# Memory root path resolution
def get_memory_root() -> str:
    """Get the memory root path from env or derive from project structure.

    Prefer the local skills/memory workspace; fallback to repo-root memory.
    """
    env_root = os.environ.get("MEMORY_ROOT")
    if env_root:
        return env_root

    # Prefer memory under skills (modularized layout)
    skills_mem = SKILLS_DIR / "memory"
    if skills_mem.exists():
        return str(skills_mem)

    # Fallback: repo-root memory
    default_mem = SKILLS_DIR.parent.parent.parent / "memory"
    return str(default_mem)

# =============================================================================
# Skill Integration
# =============================================================================

# Skill run timeouts
SKILL_RUN_TIMEOUT = 600  # 10 minutes
MEMORY_LEARN_TIMEOUT = 30  # seconds

# Common word filter for query building
SKIP_WORDS = frozenset({
    "of", "the", "a", "an", "in", "on", "for", "to", "and", "or", "with"
})

# Implementation detail patterns (for filtering Q&A pairs)
IMPLEMENTATION_DETAIL_PATTERNS = (
    "dataset size", "how many", "what number",
    "learning rate", "batch size", "epoch",
    "table", "figure", "listing",
)

# =============================================================================
# Pipeline Stages
# =============================================================================

PIPELINE_STAGES = 5  # Total stages in the learn pipeline

# Stage descriptions for logging
STAGE_NAMES = {
    1: "Finding paper",
    2: "Extracting content",
    3: "Interview review",
    4: "Storing to memory",
    5: "Verifying edges",
}
