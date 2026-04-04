"""scillm provider for review-code — routes through local proxy to any backend.

Supports all scillm models including gpt-5.3-codex (Codex Cloud via OAuth).
No CLI subprocess, no temp workspace — direct httpx POST.

Usage:
    review-full --provider scillm --model gpt-5.3-codex
    review-full --provider scillm --model text-gemini
    review-full --provider scillm --model text  # default DeepSeek-V3
"""
from __future__ import annotations

from typing import Any, Optional

import httpx
from loguru import logger

SCILLM_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_KEY = "sk-dev-proxy-123"
DEFAULT_MODEL = "gpt-5.3-codex"


async def send_review(
    prompt: str,
    model: str = DEFAULT_MODEL,
    system_prompt: str = "",
    max_tokens: int = 4000,
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Send a review request through scillm and return structured response.

    Returns:
        {"content": str, "model": str, "usage": dict, "ok": bool, "error": str | None}
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        payload: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        # Codex Cloud rejects temperature param
        if not model.startswith("gpt-"):
            payload["temperature"] = 0.2

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                SCILLM_URL,
                headers={
                    "Authorization": f"Bearer {SCILLM_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return {
                "content": content,
                "model": data.get("model", model),
                "usage": data.get("usage", {}),
                "ok": True,
                "error": None,
            }
    except httpx.HTTPStatusError as e:
        error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        logger.error(f"scillm review failed: {error}")
        return {"content": "", "model": model, "usage": {}, "ok": False, "error": error}
    except Exception as e:
        logger.error(f"scillm review failed: {e}")
        return {"content": "", "model": model, "usage": {}, "ok": False, "error": str(e)}


def build_review_prompt(
    files: dict[str, str],
    context: str = "",
    focus: str = "",
) -> str:
    """Build a complete review prompt with all files bundled.

    Args:
        files: {relative_path: file_content} — all files to review
        context: Architectural context, what problem this solves, what it replaces
        focus: Specific areas to focus on (security, correctness, etc.)
    """
    parts = []

    parts.append("Review the following code. Be critical. Do not be agreeable for politeness.\n")

    if context:
        parts.append(f"## Context\n\n{context}\n")

    if focus:
        parts.append(f"## Focus Areas\n\n{focus}\n")

    parts.append("## Review Criteria\n")
    parts.append("1. Security issues (injection, traversal, SSRF, auth)")
    parts.append("2. Correctness bugs (logic errors, race conditions, edge cases)")
    parts.append("3. Error handling gaps")
    parts.append("4. Resource leaks (memory, file handles, processes)")
    parts.append("5. Whether documentation matches implementation")
    parts.append("6. Concrete improvement suggestions\n")

    parts.append("## Files\n")
    for filepath, content in files.items():
        parts.append(f"### `{filepath}`\n\n```\n{content}\n```\n")

    return "\n".join(parts)
