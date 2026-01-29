#!/usr/bin/env python3
"""Multi-provider AI code review skill.

Submits structured code review requests to multiple AI providers:
- GitHub Copilot (copilot CLI)
- Anthropic Claude (claude CLI)
- OpenAI Codex (codex CLI)
- Google Gemini (gemini CLI)

Commands:
    check       - Verify provider CLI and authentication
    login       - OAuth device code login for GitHub Copilot
    review      - Submit single code review request
    review-full - Run iterative 3-step review pipeline
    build       - Generate review request markdown from options
    bundle      - Package request for GitHub Copilot web
    find        - Search for review request files
    template    - Print example template
    models      - List available models for a provider

Usage:
    python code_review.py check
    python code_review.py check --provider anthropic
    python code_review.py review --file request.md
    python code_review.py review --file request.md --provider anthropic --model opus
    python code_review.py review --file request.md --provider openai --reasoning high
    python code_review.py review --file request.md --workspace ./src
    python code_review.py review-full --file request.md --save-intermediate
"""
from __future__ import annotations

import sys
from pathlib import Path

# Handle both direct execution and module import scenarios
# When run directly (python code_review.py), we need to add parent to sys.path
# When run as module (python -m code_review.code_review), relative imports work
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# Use absolute imports that work in both scenarios
try:
    # Try relative imports first (module mode)
    from .config import HELP_TEXT
    from .commands import (
        build,
        bundle,
        check,
        find,
        login,
        loop,
        models,
        review,
        review_full,
        template,
    )
except ImportError:
    # Fall back to absolute imports (direct execution mode)
    from config import HELP_TEXT
    from commands import (
        build,
        bundle,
        check,
        find,
        login,
        loop,
        models,
        review,
        review_full,
        template,
    )

import typer

# Create Typer app
app = typer.Typer(
    add_completion=False,
    help=HELP_TEXT,
    rich_markup_mode="markdown",
)

# Register commands
app.command()(check)
app.command()(review)
app.command(name="review-full")(review_full)
app.command()(build)
app.command()(models)
app.command()(template)
app.command()(bundle)
app.command()(find)
app.command()(login)
app.command()(loop)


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
