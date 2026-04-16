"""Review prompts for code-review skill.

Contains all prompt templates for:
- 3-step review pipeline (review-full)
- Coder-Reviewer loop (loop)

All prompts loaded from /prompt-lab/prompts/*.txt files.
"""
from __future__ import annotations

from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()


# =============================================================================
# 3-Step Review Pipeline Prompts (review-full command)
# =============================================================================

STEP1_PROMPT = _load_prompt("review_code_step1_v1")

STEP2_PROMPT = _load_prompt("review_code_step2_v1")

STEP3_PROMPT = _load_prompt("review_code_step3_v1")


# =============================================================================
# Coder-Reviewer Loop Prompts (loop command)
# =============================================================================

LOOP_CODER_INIT_PROMPT = _load_prompt("review_code_loop_coder_init_v1")

LOOP_REVIEWER_PROMPT = _load_prompt("review_code_loop_reviewer_v1")

LOOP_CODER_FIX_PROMPT = _load_prompt("review_code_loop_coder_fix_v1")
