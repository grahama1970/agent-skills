"""Synthesize dream narratives from jumbled memory/code/event chunks via scillm."""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

SCILLM_URL = os.environ.get("SCILLM_URL", "http://127.0.0.1:4001")
SCILLM_KEY = os.environ.get("SCILLM_KEY", "sk-dev-proxy-123")


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
        response = httpx.post(
            f"{SCILLM_URL.rstrip('/')}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {SCILLM_KEY}",
                "X-Caller-Skill": "persona-dream-s01-idea",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-5.5",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,  # Higher temp for creative dream generation
            },
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"].strip()
        # Strip any markdown formatting
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("\n```", 1)[0]
        return content
    except Exception as exc:
        # Fail closed: return a raw jumble so the pipeline can continue
        lines = [f"A dream where {persona_id} experiences: {dominant_text[:400]}"]
        for text in supporting_texts:
            lines.append(f"Bleeding into the dream: {text[:200]}")
        if about:
            lines.append(f"The dream gravitates around {about}.")
        return " ".join(lines)
