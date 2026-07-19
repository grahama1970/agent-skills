"""Synthesize dream narratives from jumbled memory/code/event chunks.

Model inference is routed through the sanctioned Tau text-reasoning node
(``tau_text_reasoning_adapter``); this module never POSTs to scillm directly
(operator rule: only /tau may reach /scillm).
"""
from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

# Load the sanctioned persona-dream -> Tau text-reasoning adapter by file path so
# this works whether the module is imported as a package or run standalone.
_ADAPTER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "tau_text_reasoning_adapter.py"
_aspec = _ilu.spec_from_file_location("tau_text_reasoning_adapter", _ADAPTER_PATH)
assert _aspec and _aspec.loader
tau_adapter = _ilu.module_from_spec(_aspec)
_aspec.loader.exec_module(tau_adapter)

# Caller-defined JSON output contract (hash-recorded by the Tau node).
_DREAM_OUTPUT_CONTRACT = {"dream": "str"}


def _build_synthesis_prompt(
    persona_id: str,
    dominant_text: str,
    supporting_texts: list[str],
    about: str | None,
) -> str:
    """Build a prompt that asks the model to weave chunks into a dream narrative."""
    parts = [
        f"Write a single paragraph describing a vivid, surreal dream from {persona_id}'s perspective.",
        "",
        "Rules:",
        "- Weave ALL the following material into one dream scene. Do not summarize or list them — blend them.",
        "- The tone should be dreamlike: visual, sensory, slightly disorienting, mixing the significant with the mundane.",
        "- Keep it under 200 words. Do not use bullet points. Do not say 'this dream is about'. Just describe the dream.",
        '- Return ONLY a JSON object of the form {"dream": "<the dream paragraph>"} and nothing else.',
    ]

    if about:
        parts.append(f"- The dream should gravitate around the theme of: {about}")

    parts.append("")
    parts.append("--- DOMINANT THREAD (the core scene) ---")
    parts.append(dominant_text[:600])

    if supporting_texts:
        parts.append("")
        parts.append("--- TEXTURES BLEEDING INTO THE DREAM ---")
        for i, text in enumerate(supporting_texts, 1):
            parts.append(f"Element {i}: {text[:300]}")

    return "\n".join(parts)


def synthesize_dream(
    persona_id: str,
    dominant_text: str,
    supporting_texts: list[str],
    *,
    about: str | None = None,
    timeout: float = 60.0,
) -> str:
    """Call scillm to synthesize a dream narrative from jumbled source material.

    Returns the synthesized dream text, or falls back to a raw jumble on error.
    """
    prompt = _build_synthesis_prompt(persona_id, dominant_text, supporting_texts, about)

    try:
        # Route through Tau (only /tau may reach /scillm). The node DRAFTS the
        # dream text as a JSON object; code below extracts the paragraph.
        parsed, _receipt = tau_adapter.dispatch_text_reasoning(
            prompt,
            role="persona-dream-s01-dream-synthesis",
            output_contract=_DREAM_OUTPUT_CONTRACT,
            caller_skill="persona-dream-s01-idea",
            timeout_s=timeout,
        )
        content = (parsed or {}).get("dream", "").strip() if isinstance(parsed, dict) else ""
        if not content:
            raise ValueError("Tau text node returned no dream text")
        return content
    except Exception as exc:
        # Fail closed: return a raw jumble so the pipeline can continue
        lines = [f"A dream where {persona_id} experiences: {dominant_text[:400]}"]
        for text in supporting_texts:
            lines.append(f"Bleeding into the dream: {text[:200]}")
        if about:
            lines.append(f"The dream gravitates around {about}.")
        return " ".join(lines)
