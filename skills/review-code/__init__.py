"""Code Review skill package.

Multi-provider AI code review skill that submits structured code review requests
to GitHub Copilot, Anthropic Claude, OpenAI Codex, or Google Gemini.
"""
from .config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS

__all__ = ["DEFAULT_MODEL", "DEFAULT_PROVIDER", "PROVIDERS"]
