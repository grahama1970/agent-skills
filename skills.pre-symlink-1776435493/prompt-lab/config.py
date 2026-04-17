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
SCILLM_API_BASE = os.environ.get("SCILLM_API_BASE", "http://localhost:4001/v1").strip('"\'')
SCILLM_PROXY_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123").strip('"\'')
CHUTES_MODEL_ID = os.environ.get("CHUTES_MODEL_ID", "").strip('"\'')
CHUTES_TEXT_MODEL = os.environ.get("CHUTES_TEXT_MODEL", "").strip('"\'')
# Backwards compat aliases
CHUTES_API_BASE = SCILLM_API_BASE
CHUTES_API_KEY = SCILLM_PROXY_KEY

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
SKILL_DIR = Path(__file__).parent
PROMPTS_DIR = SKILL_DIR / "prompts"
GROUND_TRUTH_DIR = SKILL_DIR / "ground_truth"
RESULTS_DIR = SKILL_DIR / "results"
MODELS_FILE = SKILL_DIR / "models.json"

# SPARTA data paths (for ground truth building)
_PROJECT_ROOT = SKILL_DIR.parent.parent.parent
SPARTA_DATA = _PROJECT_ROOT / "sparta" / "data" / "raw"
SPARTA_TAXONOMY = _PROJECT_ROOT / "sparta" / "src" / "sparta" / "taxonomy"

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
        "api_base": "$SCILLM_API_BASE",
        "api_key": "$SCILLM_PROXY_KEY"
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

    if not SCILLM_API_BASE:
        warnings.append("SCILLM_API_BASE not set. LLM calls will fail.")
    if not SCILLM_PROXY_KEY:
        warnings.append("SCILLM_PROXY_KEY not set. LLM calls will fail.")
    if not CHUTES_MODEL_ID and not CHUTES_TEXT_MODEL:
        warnings.append("No model ID set (CHUTES_MODEL_ID or CHUTES_TEXT_MODEL).")

    return warnings


def ensure_dirs() -> None:
    """Ensure required directories exist."""
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
