"""Shared LLM routing helpers for skills that call /scillm.

These helpers keep "backend" aliases used by orchestration/code tasks separate
from concrete /scillm model names.
"""
from __future__ import annotations

from urllib.parse import urlparse


DEFAULT_SCILLM_CHAT_URL = "http://localhost:4001/v1/chat/completions"

CANONICAL_BACKENDS = {"codex", "claude", "text", "gemini", "deepseek", "test"}

_BACKEND_ALIASES: dict[str, str] = {
    "codex": "codex",
    "gpt": "codex",
    "gpt-5": "codex",
    "gpt-5.5": "codex",
    "gpt-5.3-codex": "codex",
    "gpt-5.2-codex": "codex",
    "codex-cli": "codex",
    "openai": "codex",
    "chatgpt": "codex",
    "claude": "claude",
    "text-claude": "claude",
    "text-claude-opus": "claude",
    "text-claude-haiku": "claude",
    "claude-sonnet-4-6": "claude",
    "claude-opus-4-6": "claude",
    "claude-haiku-4-5": "claude",
    "sonnet": "claude",
    "opus": "claude",
    "haiku": "claude",
    "gemini": "gemini",
    "text-gemini": "gemini",
    "text-gemini-oauth": "gemini",
    "text-gemini-3": "gemini",
    "gemini-cli": "gemini",
    "google": "gemini",
    "deepseek": "deepseek",
    "deepseek-v3": "deepseek",
    "deepseek-ai/deepseek-v3": "deepseek",
    "deepseek-ai/deepseek-v3-0324-tee": "deepseek",
    "deepseek-ai/deepseek-v4": "deepseek",
    "text": "text",
    "default": "text",
    "llm": "text",
    "local-text": "text",
    "test": "test",
}

_BACKEND_TO_SCILLM_MODEL: dict[str, str] = {
    "codex": "gpt-5.5",
    "claude": "claude-sonnet-4-6",
    "gemini": "text-gemini-oauth",
    "deepseek": "text",
    "text": "text",
    "test": "local-text",
}


def normalize_backend_alias(value: str, *, allow_empty: bool = False) -> str:
    """Normalize a CLI/model alias to a code-runner backend name."""
    raw = (value or "").strip()
    if not raw:
        if allow_empty:
            return ""
        raise ValueError(
            f"Missing backend. Valid backends: {', '.join(sorted(CANONICAL_BACKENDS))}"
        )
    lower = raw.lower()
    if lower in _BACKEND_ALIASES:
        return _BACKEND_ALIASES[lower]
    if lower.startswith(("gpt-", "codex-")):
        return "codex"
    if lower.startswith("claude-"):
        return "claude"
    if lower.startswith("gemini-"):
        return "gemini"
    if lower.startswith("opencode-go/deepseek") or lower.startswith("deepseek-ai/"):
        return "deepseek"
    raise ValueError(
        f"Unknown backend/model alias '{value}'. "
        f"Valid backends: {', '.join(sorted(CANONICAL_BACKENDS))}; "
        "accepted model aliases include gpt-5.5, gpt-5.3-codex, "
        "claude-sonnet-4-6, and text-gemini-oauth."
    )


def backend_to_scillm_model(value: str) -> str:
    """Resolve a backend/model alias to a concrete /scillm model name."""
    backend = normalize_backend_alias(value)
    return _BACKEND_TO_SCILLM_MODEL[backend]


def normalize_scillm_model_alias(value: str, *, default: str = "text") -> str:
    """Normalize friendly aliases for one-shot /scillm tasks.

    Unknown model names are returned unchanged because /scillm can auto-route
    direct provider model ids.
    """
    raw = (value or "").strip()
    if not raw:
        raw = default
    lower = raw.lower()
    if lower in _BACKEND_ALIASES:
        return backend_to_scillm_model(raw)
    return raw


def normalize_scillm_chat_url(value: str | None) -> str:
    """Return an OpenAI-compatible /scillm chat completions URL.

    Accepts root/base values such as http://localhost:4001 or
    http://localhost:4001/v1 and normalizes them to
    http://localhost:4001/v1/chat/completions.
    """
    raw = (value or DEFAULT_SCILLM_CHAT_URL).strip()
    if not raw:
        return DEFAULT_SCILLM_CHAT_URL
    stripped = raw.rstrip("/")
    if stripped.endswith("/v1/chat/completions"):
        return stripped
    if stripped.endswith("/v1"):
        return f"{stripped}/chat/completions"

    parsed = urlparse(stripped)
    if parsed.scheme and parsed.netloc and parsed.path in ("", "/"):
        return f"{stripped}/v1/chat/completions"
    return stripped
