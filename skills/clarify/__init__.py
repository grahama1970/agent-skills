"""
Clarify: Interactive form system for gathering structured user input.

Quick Start:
    >>> from clarify import ask, choose, ask_questions
    >>> name = ask("What is the project name?")
    >>> db = choose("Which database?", [
    ...     {"id": "pg", "label": "PostgreSQL"},
    ...     {"id": "mysql", "label": "MySQL"},
    ... ])
"""

from .api import ask, ask_questions, choose
from .runner import (
    ClarifyError,
    ClarifySession,
    ClarifyTimeout,
    normalize_questions,
    run_clarification_flow,
)
from .types import ClarifyOption, ClarifyQuestion

__all__ = [
    # High-level API
    "ask",
    "ask_questions",
    "choose",
    # Types
    "ClarifyOption",
    "ClarifyQuestion",
    # Low-level API
    "ClarifyError",
    "ClarifyTimeout",
    "ClarifySession",
    "normalize_questions",
    "run_clarification_flow",
]
