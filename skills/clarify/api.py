"""High-level API for asking clarifying questions."""

from __future__ import annotations

import json
import os
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, List, Optional, Sequence

from .runner import normalize_questions, run_clarification_flow
from .types import ClarifyOption, ClarifyQuestion


def ask_questions(
    questions: Sequence[Any],
    *,
    timeout_sec: int = 300,
    context: str = "clarify",
    open_browser: bool = True,
) -> List[dict[str, Any]]:
    """
    Launch clarifying UI and collect user responses.

    Args:
        questions: List of question dicts or ClarifyQuestion objects.
        timeout_sec: How long to wait for responses (default: 5 minutes).
        context: Context string shown in UI header.
        open_browser: Whether to auto-open browser (default: True).

    Returns:
        List of response dicts with user answers.

    Raises:
        ClarifyTimeout: If user doesn't respond within timeout.
        ClarifyError: If UI exits without responses.

    Example:
        >>> responses = ask_questions([
        ...     {"prompt": "What is the project name?"},
        ...     {
        ...         "prompt": "Select a framework:",
        ...         "kind": "single-choice",
        ...         "options": [
        ...             {"id": "react", "label": "React"},
        ...             {"id": "vue", "label": "Vue"},
        ...         ]
        ...     }
        ... ])
    """
    timeout_sec = int(os.environ.get("CLARIFY_TIMEOUT", timeout_sec))

    with tempfile.TemporaryDirectory(prefix="clarify_") as tmp:
        out_dir = Path(tmp)
        response_path = run_clarification_flow(
            out_dir=out_dir,
            step_name=context,
            attempt=1,
            raw_questions=questions,
            timeout_sec=timeout_sec,
        )

        if response_path and response_path.exists():
            data = json.loads(response_path.read_text())
            return data.get("responses", [])

    return []


def ask(prompt: str, **kwargs) -> str:
    """
    Ask a single text question and return the answer.

    Args:
        prompt: The question to ask.
        **kwargs: Additional ClarifyQuestion fields.

    Returns:
        User's text response.

    Example:
        >>> name = ask("What should we call this project?")
    """
    responses = ask_questions([{"prompt": prompt, **kwargs}])
    if responses:
        return responses[0].get("value", "")
    return ""


def choose(
    prompt: str,
    options: List[dict[str, str]],
    *,
    allow_multiple: bool = False,
    **kwargs,
) -> List[str]:
    """
    Ask user to choose from options.

    Args:
        prompt: The question to ask.
        options: List of {"id": ..., "label": ..., "description": ...} dicts.
        allow_multiple: Allow selecting multiple options.
        **kwargs: Additional ClarifyQuestion fields.

    Returns:
        List of selected option IDs.

    Example:
        >>> selected = choose(
        ...     "Which database?",
        ...     [
        ...         {"id": "pg", "label": "PostgreSQL"},
        ...         {"id": "mysql", "label": "MySQL"},
        ...     ]
        ... )
    """
    kind = "multi-choice" if allow_multiple else "single-choice"
    responses = ask_questions([
        {"prompt": prompt, "kind": kind, "options": options, **kwargs}
    ])
    if responses:
        return responses[0].get("selectedOptions", [])
    return []
