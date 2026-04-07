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
from loguru import logger

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

# Best-effort .env loading — check multiple locations since subprocesses
# may have temp dirs as cwd and miss the project .env
_ENV_SEARCH_PATHS = [
    Path.home() / "workspace" / "experiments" / "embry-os" / ".env",
    Path.home() / "workspace" / "experiments" / "pi-mono" / ".env",
    SKILLS_DIR.parent / ".env",  # project root relative to skills
]
try:
    from dotenv import load_dotenv, find_dotenv
    # First try cwd (normal case)
    load_dotenv(find_dotenv(usecwd=True), override=False)
    # Then load from known project paths to catch DEEPSEEK_API_KEY etc.
    for env_path in _ENV_SEARCH_PATHS:
        if env_path.exists():
            load_dotenv(env_path, override=False)
except Exception as e:
    logger.debug("loading failed: {}", e)

# =============================================================================
# LLM/API Configuration
# =============================================================================


def get_llm_provider_chain() -> list[Dict[str, str]]:
    """Get ordered list of LLM providers for 429 fallback.

    Priority: SciLLM Proxy → DeepSeek (reliable) → OpenRouter (fallback).
    Each provider dict has: model, api_base, api_key, name.
    """
    providers = []
    proxy_key = os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    if proxy_key:
        model = (
            os.getenv("CHUTES_TEXT_MODEL")
            or os.getenv("SCILLM_DEFAULT_MODEL")
            or os.getenv("CHUTES_MODEL_ID", "deepseek-ai/DeepSeek-V3")
        )
        providers.append({
            "model": model,
            "api_base": os.getenv("SCILLM_API_BASE", "http://localhost:4001/v1"),
            "api_key": proxy_key,
            "name": "scillm_proxy",
        })

    if deepseek_key:
        providers.append({
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "api_base": "https://api.deepseek.com/v1",
            "api_key": deepseek_key,
            "name": "deepseek",
        })

    if openrouter_key:
        providers.append({
            "model": os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324"),
            "api_base": "https://openrouter.ai/api/v1",
            "api_key": openrouter_key,
            "name": "openrouter",
        })

    return providers


def get_scillm_config() -> Dict[str, str]:
    """Get the first available LLM provider config.

    Uses get_llm_provider_chain() priority: SciLLM Proxy → DeepSeek → OpenRouter.
    SCILLM_USE_OPENROUTER=1 overrides to OpenRouter first.
    """
    use_openrouter = os.getenv("SCILLM_USE_OPENROUTER", "").strip() in ("1", "true", "yes")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    if use_openrouter and openrouter_key:
        return {
            "model": os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324"),
            "api_base": "https://openrouter.ai/api/v1",
            "api_key": openrouter_key,
        }

    chain = get_llm_provider_chain()
    if chain:
        return {k: v for k, v in chain[0].items() if k != "name"}

    return {"model": "", "api_base": "", "api_key": ""}


def preflight_budget_check(estimated_calls: int = 50) -> Dict[str, str]:
    """Check if Chutes has enough budget for this batch.

    Part of Shadow-LEGO's teacher tier management: ensures the teacher
    stays on a consistent provider throughout a batch for reliable
    shadow comparison data.
    """
    config = get_scillm_config()
    if "chutes" not in config.get("api_base", ""):
        return config  # already on fallback

    try:
        _ops_chutes = os.path.join(str(SKILLS_DIR), "ops-chutes")
        if _ops_chutes not in sys.path:
            sys.path.insert(0, _ops_chutes)
        from util import ChutesClient
        client = ChutesClient()
        quota = client.get_quota()
        remaining = quota["quota"] - quota["used"]
        if remaining < estimated_calls:
            logger.warning(f"Chutes budget low ({remaining:.0f} remaining, need ~{estimated_calls})")
            deepseek_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API")
            if deepseek_key:
                return {"model": "deepseek-chat",
                        "api_base": "https://api.deepseek.com/v1",
                        "api_key": deepseek_key}
            openrouter_key = os.getenv("OPENROUTER_API_KEY")
            if openrouter_key:
                return {"model": os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324"),
                        "api_base": "https://openrouter.ai/api/v1",
                        "api_key": openrouter_key}
            logger.warning("No fallback keys; proceeding with Chutes")
    except Exception as e:
        logger.debug("Budget pre-flight failed: {}", e)
    return config


def get_chutes_config() -> Dict[str, str]:
    """Get LLM API configuration for marker-pdf LLM enhancement."""
    return {
        "api_key": os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123"),
        "base_url": os.getenv("SCILLM_API_BASE", "http://localhost:4001/v1"),
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
