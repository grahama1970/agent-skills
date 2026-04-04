"""Load validated prompts from /prompt-lab file registry.

RULE: Never hand-craft system prompts. All prompts must:
1. Exist as .txt files in prompt-lab/prompts/
2. Have ground truth in prompt-lab/ground_truth/
3. Pass /prompt-lab eval
4. Have provenance recorded in /memory

Usage:
    from prompt_loader import load_prompt

    system = load_prompt("bridge-tagger")  # loads prompt-lab/prompts/bridge-tagger.txt
"""
from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompt-lab" / "prompts"


def load_prompt(name: str) -> str:
    """Load a validated prompt by name (without .txt extension).

    Args:
        name: Prompt filename stem (e.g. "bridge-tagger" loads bridge-tagger.txt)

    Returns:
        Prompt text content (stripped).

    Raises:
        FileNotFoundError: If prompt file doesn't exist — run /prompt-lab first.
    """
    path = PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt '{name}' not found at {path}. "
            f"Create it via /prompt-lab and run eval before using."
        )
    return path.read_text().strip()
