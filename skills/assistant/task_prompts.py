"""Task-specific system prompts for scillm (Tier 2) escalation.

Each key maps a task name to the system prompt loaded from /prompt-lab.
Prompts are validated via /prompt-lab eval with provenance recorded in /memory.

RULE: Never hand-craft system prompts inline. All prompts live in
prompt-lab/prompts/*.txt and must pass /prompt-lab eval before use.
"""

from __future__ import annotations

from typing import Dict

from prompt_loader import load_prompt

TASK_PROMPTS: Dict[str, str] = {
    "bridge-tagger": load_prompt("bridge-tagger"),
    "viz-type-selector": load_prompt("viz-type-selector"),
    "data-sufficiency-gate": load_prompt("data-sufficiency-gate"),
    "paper-section-reviewer": load_prompt("paper-section-reviewer"),
    "humanization-rewriter": load_prompt("humanization-rewriter"),
    "sparta-intent": load_prompt("sparta_intent_queryspec"),
}
