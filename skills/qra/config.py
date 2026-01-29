"""QRA Configuration - Constants, paths, and environment settings.

This module centralizes all configuration for the QRA skill.

Import direction: other modules (utils, extractor, validator, storage, __main__)
may import from config. This module must not import from any qra.* sibling
to avoid circular imports.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Dict

# =============================================================================
# Paths
# =============================================================================

SCRIPT_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPT_DIR.parent

# Debug output directory
DEBUG_DIR = Path("/tmp/qra_debug")

# =============================================================================
# Environment Configuration
# =============================================================================


def get_scillm_config() -> Dict[str, str]:
    """Get scillm/Chutes API configuration from environment.

    Environment variables:
        CHUTES_TEXT_MODEL: Preferred text model
        SCILLM_DEFAULT_MODEL: Fallback model setting
        CHUTES_MODEL_ID: Default model ID
        CHUTES_API_BASE: API endpoint
        CHUTES_API_KEY: API authentication key

    Returns:
        Dict with 'model', 'api_base', 'api_key' keys
    """
    model = (
        os.getenv("CHUTES_TEXT_MODEL")
        or os.getenv("SCILLM_DEFAULT_MODEL")
        or os.getenv("CHUTES_MODEL_ID", "deepseek-ai/DeepSeek-V3")
    )
    return {
        "model": model,
        "api_base": os.getenv("CHUTES_API_BASE", "https://llm.chutes.ai/v1"),
        "api_key": os.getenv("CHUTES_API_KEY", ""),
    }


# =============================================================================
# QRA Extraction Settings
# =============================================================================


def getenv_bool(name: str, default: bool = False) -> bool:
    """Parse boolean-like environment variables.

    True if value in {1,true,yes,on}; False if in {0,false,no,off} (case-insensitive).
    Legacy fallback: if set to an unrecognized non-empty value, warn and treat
    as True to preserve prior behavior.

    Args:
        name: Environment variable name
        default: Default value if not set

    Returns:
        Parsed boolean value
    """
    v = os.getenv(name)
    if v is None:
        return default
    val = v.strip().lower()
    if val in {"1", "true", "yes", "on"}:
        return True
    if val in {"0", "false", "no", "off", ""}:
        return False
    # Legacy fallback: non-empty unrecognized value treated as True
    warnings.warn(
        f"Unrecognized boolean for {name}: '{v}', treating as True (legacy)",
        stacklevel=2,
    )
    return True


# Default extraction parameters
DEFAULT_CONCURRENCY = int(os.getenv("QRA_CONCURRENCY", "6"))
DEFAULT_GROUNDING_THRESHOLD = float(os.getenv("QRA_GROUNDING_THRESH", "0.6"))
SKIP_GROUNDING = getenv_bool("QRA_NO_GROUNDING", False)

# Section splitting
DEFAULT_MAX_SECTION_CHARS = 5000
MAX_CONTENT_PER_REQUEST = 3000  # Truncate section content for LLM

# Batch processing
DEFAULT_TIMEOUT = 60
DEFAULT_WALL_TIME = 900
MAX_TOKENS = 4096
TEMPERATURE = 0.1

# Rate limiting
MEMORY_REQUESTS_PER_SECOND = 5

# =============================================================================
# Common Abbreviations (for sentence splitting)
# =============================================================================

ABBREVIATIONS = {
    "fig", "sec", "no", "dr", "mr", "mrs", "ms", "prof",
    "u.s", "u.k", "dept", "inc", "ltd", "vs", "etc", "e.g", "i.e", "cf", "al"
}

# =============================================================================
# QRA Prompts
# =============================================================================

QRA_JSON_FORMAT = """{{"items": [
  {{"question": "string", "reasoning": "string", "answer": "string"}},
  ...
]}}"""

QRA_BASE_RULES = """CRITICAL RULES:
- GROUNDING: Every answer MUST be directly supported by text in the source. Do NOT hallucinate.
- question: A clear, specific question that the text answers
- reasoning: Brief explanation of where/how the answer is found in the text
- answer: The factual answer, using words from the source text when possible
- Include as many items as the text supports (could be 1 to 50+)
- If text is too short, garbled, or lacks factual content, return {{"items": []}}

SKIP these sections (no value):
- Abstract summaries, acknowledgments, author bios
- References, bibliography, appendix boilerplate
- Figure/table captions without substantive content
- "Future work" without concrete approaches
"""

QRA_USER_PROMPT = """Extract all grounded knowledge items from this text. Every answer must be supported by the source text.

Text:
{text}

JSON:"""
