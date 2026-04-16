"""QRA prompt templates for doc2qra skill.

Centralises the system and user prompts used by LLM-based QRA
extraction so they can be shared across qra_llm, qra_batch,
and qra_cascade without circular imports.
"""

from __future__ import annotations

from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()


def build_qra_system_prompt(context: str = None) -> str:
    """Build QRA system prompt with optional domain context.

    Args:
        context: Optional domain context/persona for focused extraction

    Returns:
        System prompt string
    """
    base_prompt = _load_prompt("doc2qra_system_v1")

    if context:
        context_section = _load_prompt("doc2qra_context_prefix_v1").format(context=context) + "\n\n"
        return context_section + base_prompt

    return base_prompt


# Default prompt (no context)
QRA_SYSTEM_PROMPT = build_qra_system_prompt()

QRA_PROMPT = _load_prompt("doc2qra_user_v1")
