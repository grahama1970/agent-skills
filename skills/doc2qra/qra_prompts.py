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


def build_qra_system_prompt(context: str = None, version: str = "v2") -> str:
    """Build QRA system prompt with optional domain context.

    Args:
        context: Optional domain context/persona for focused extraction
        version: Prompt version ("v1" for legacy, "v2" for grounded extraction)

    Returns:
        System prompt string
    """
    base_prompt = _load_prompt(f"doc2qra_system_{version}")

    if context:
        context_section = _load_prompt("doc2qra_context_prefix_v1").format(context=context) + "\n\n"
        return context_section + base_prompt

    return base_prompt


def build_qra_user_prompt(text: str, source_url: str = "", doc_type: str = "", version: str = "v2") -> str:
    """Build QRA user prompt with document content.

    Args:
        text: Document content to extract from
        source_url: Source URL of the document
        doc_type: Type of document (PDF, web page, etc.)
        version: Prompt version ("v1" for legacy, "v2" for grounded extraction)

    Returns:
        User prompt string
    """
    template = _load_prompt(f"doc2qra_user_{version}")
    return template.format(text=text, source_url=source_url or "unknown", doc_type=doc_type or "document")


# Default prompts (v2 - grounded extraction with evidence quotes)
QRA_SYSTEM_PROMPT = build_qra_system_prompt(version="v2")

# Legacy user prompt for backwards compatibility
QRA_PROMPT = _load_prompt("doc2qra_user_v1")
