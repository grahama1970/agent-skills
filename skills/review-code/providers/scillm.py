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
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Send a review request through scillm and return structured response.

    Returns:
        {"content": str, "model": str, "usage": dict, "ok": bool, "error": str | None}

    Note: Does NOT set max_tokens per best-practices-scillm Rule 4.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        payload: dict = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},  # Enable JSON mode for structured output
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
                    "X-Caller-Skill": "review-code",  # Required per best-practices-scillm
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

    # RATIONALE (not sent to LLM — for maintainers)
    # Purpose: Generate structured code review findings from source files
    # Consumer: review-code skill → parsed into ReviewFinding objects → displayed or stored
    # Why this matters: Unstructured reviews are unparseable. Severity without vocabulary causes inconsistency.
    # Input: dict of {filepath: content}, optional context and focus strings
    # Output: JSON array of findings with severity, file, line, title, evidence, issue, fix
    # Last reviewed: 2026-04-15

    Args:
        files: {relative_path: file_content} — all files to review
        context: Architectural context, what problem this solves, what it replaces
        focus: Specific areas to focus on (security, correctness, etc.)
    """
    parts = []

    parts.append("## Task\n")
    parts.append("Review the code below and produce a structured list of findings.")
    parts.append("For each finding, identify the file, line number, and provide a concrete fix.\n")

    if context:
        parts.append(f"## Context\n\n{context}\n")

    if focus:
        parts.append(f"## Focus Areas\n\n{focus}\n")

    parts.append("## Review Criteria\n")
    parts.append("Check for these issues in priority order:")
    parts.append("1. **Security**: injection (SQL, command, XSS), path traversal, SSRF, auth bypass, secrets in code")
    parts.append("2. **Correctness**: logic errors, race conditions, null/undefined access, off-by-one, edge cases")
    parts.append("3. **Error handling**: uncaught exceptions, silent failures, missing validation")
    parts.append("4. **Resource leaks**: unclosed files, database connections, spawned processes")
    parts.append("5. **Documentation drift**: code behavior differs from comments/docs/SKILL.md claims")
    parts.append("6. **Maintainability**: dead code, unclear naming, missing type hints on public APIs\n")

    parts.append("## Rejection Criteria (do NOT report these)\n")
    parts.append("- Style preferences (quote style, trailing commas) unless they cause bugs")
    parts.append("- Missing tests (unless the code is untestable)")
    parts.append("- Hypothetical issues that require conditions not present in the code")
    parts.append("- Duplicate findings for the same root cause\n")

    parts.append("## Severity Vocabulary (use exactly these strings)\n")
    parts.append("- `critical`: exploitable without authentication, leads to RCE or data loss")
    parts.append("- `high`: exploitable with low-privilege access, significant security/data impact")
    parts.append("- `medium`: requires specific conditions to exploit, moderate impact")
    parts.append("- `low`: minor issue, defense-in-depth concern, no direct exploit path")
    parts.append("- `info`: observation or suggestion, no security impact\n")

    parts.append("## Files to Review\n")
    for filepath, content in files.items():
        parts.append(f"### `{filepath}`\n\n```\n{content}\n```\n")

    parts.append("## Output Format\n")
    parts.append("Output ONLY a JSON array of findings. No commentary before or after the JSON.")
    parts.append("Start with `[` and end with `]`. Each finding must have ALL fields:\n")
    parts.append("```json")
    parts.append('[')
    parts.append('  {')
    parts.append('    "severity": "high",')
    parts.append('    "file": "src/auth.py",')
    parts.append('    "line": 42,')
    parts.append('    "title": "SQL injection in user lookup",')
    parts.append('    "evidence": "cursor.execute(f\\"SELECT * FROM users WHERE id={user_id}\\")",')
    parts.append('    "issue": "User input concatenated directly into SQL query allows injection",')
    parts.append('    "fix": "Use parameterized query: cursor.execute(\\"SELECT * FROM users WHERE id=?\\", (user_id,))"')
    parts.append('  }')
    parts.append(']')
    parts.append("```\n")

    parts.append("If the code has no findings, return: `[]`")

    return "\n".join(parts)
