"""
Prompt Lab Skill - Configuration
Constants, vocabulary, paths, and environment configuration.
"""
import os
import sys
from pathlib import Path
from typing import Set

# -----------------------------------------------------------------------------
# Environment Variables
# -----------------------------------------------------------------------------
CHUTES_API_BASE = os.environ.get("CHUTES_API_BASE", "").strip('"\'')
CHUTES_API_KEY = os.environ.get("CHUTES_API_KEY", "").strip('"\'')
CHUTES_MODEL_ID = os.environ.get("CHUTES_MODEL_ID", "").strip('"\'')
CHUTES_TEXT_MODEL = os.environ.get("CHUTES_TEXT_MODEL", "").strip('"\'')

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
SKILL_DIR = Path(__file__).parent
PROMPTS_DIR = SKILL_DIR / "prompts"
GROUND_TRUTH_DIR = SKILL_DIR / "ground_truth"
RESULTS_DIR = SKILL_DIR / "results"
MODELS_FILE = SKILL_DIR / "models.json"

# SPARTA data paths (for ground truth building)
SPARTA_DATA = Path("/home/graham/workspace/experiments/sparta/data/raw")
SPARTA_TAXONOMY = Path("/home/graham/workspace/experiments/sparta/src/sparta/taxonomy")

# -----------------------------------------------------------------------------
# Vocabulary Definitions (Presented to LLM in prompt)
# -----------------------------------------------------------------------------
TIER0_CONCEPTUAL: Set[str] = {
    "Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"
}

TIER1_TACTICAL: Set[str] = {
    "Model", "Harden", "Detect", "Isolate", "Restore", "Evade", "Exploit", "Persist"
}

VOCABULARY_PROMPT_SECTION = """
Valid conceptual tags (Tier 0 - abstract concepts):
- Precision: Exactness, targeting, reconnaissance, enumeration
- Resilience: Recovery, hardening, defense, protection, restoration
- Fragility: Weakness, vulnerability, exploit, misconfiguration
- Corruption: Persistence, backdoor, unauthorized modification, malware
- Loyalty: Authentication, authorization, trust, access control
- Stealth: Evasion, obfuscation, anti-forensics, defense evasion

Valid tactical tags (Tier 1 - D3FEND actions):
- Model: Enumerate, map, discover, fingerprint
- Harden: Patch, configure, restrict, secure
- Detect: Monitor, alert, log, analyze
- Isolate: Segment, quarantine, contain
- Restore: Backup, recover, rollback
- Evade: Bypass, obfuscate, hide
- Exploit: Attack, weaponize, abuse vulnerability
- Persist: Maintain access, implant, backdoor
"""

# Correction prompt sent when LLM outputs invalid tags
CORRECTION_PROMPT = """Your response contained invalid tags that are not in the allowed vocabulary.

Invalid tags you used: {rejected_tags}

Valid conceptual tags (Tier 0): {valid_conceptual}
Valid tactical tags (Tier 1): {valid_tactical}

Please correct your response. Return ONLY valid JSON with tags from the allowed vocabulary above.
Do NOT invent new categories. Only use the exact tag names listed."""

# -----------------------------------------------------------------------------
# Quality Thresholds
# -----------------------------------------------------------------------------
F1_THRESHOLD = 0.8
CORRECTION_SUCCESS_THRESHOLD = 0.9
QRA_SCORE_THRESHOLD = 0.6

# -----------------------------------------------------------------------------
# Default Model Configuration
# -----------------------------------------------------------------------------
DEFAULT_MODELS_CONFIG = {
    "deepseek": {
        "provider": "chutes",
        "model": "deepseek-ai/DeepSeek-V3-0324-TEE",
        "api_base": "$CHUTES_API_BASE",
        "api_key": "$CHUTES_API_KEY"
    },
    "deepseek-direct": {
        "provider": "openai_like",
        "model": "deepseek-chat",
        "api_base": "https://api.deepseek.com",
        "api_key": "$DEEPSEEK_API_KEY"
    }
}


def get_env_value(key: str) -> str:
    """Get environment variable value, stripping quotes."""
    return os.environ.get(key, "").strip('"\'')


def validate_env() -> list[str]:
    """
    Validate environment configuration.

    Returns:
        List of warning messages (empty if all ok)
    """
    warnings = []

    if not CHUTES_API_BASE:
        warnings.append("CHUTES_API_BASE not set. LLM calls will fail.")
    if not CHUTES_API_KEY:
        warnings.append("CHUTES_API_KEY not set. LLM calls will fail.")
    if not CHUTES_MODEL_ID and not CHUTES_TEXT_MODEL:
        warnings.append("No model ID set (CHUTES_MODEL_ID or CHUTES_TEXT_MODEL).")

    return warnings


def ensure_dirs() -> None:
    """Ensure required directories exist."""
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
