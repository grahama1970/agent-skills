"""Configuration constants for code-review skill.

Contains:
- Provider configurations (CLI names, models, costs)
- Default values
- Path resolution
- Template strings
"""
from __future__ import annotations

import os
from pathlib import Path


# Resolve skill directories
SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parent

# Provider configurations
# Each provider has: cli (command), models (dict), default_model, and optional env vars
# COST WARNING: Only 'github' provider is free. Others make paid API calls.
PROVIDERS = {
    "github": {
        "cli": "copilot",
        "models": {
            # As of 2025-01: copilot CLI supports these models
            "gpt-5": "gpt-5",
            "claude-sonnet-4": "claude-sonnet-4",
            "claude-sonnet-4.5": "claude-sonnet-4.5",
            "claude-haiku-4.5": "claude-haiku-4.5",
        },
        "default_model": "gpt-5",
        "env": {"COPILOT_ALLOW_ALL": "1"},
        "cost": "free",  # Free with GitHub Copilot subscription
        "supports_continue": True,
    },
    "anthropic": {
        "cli": "claude",
        "models": {
            # Claude CLI accepts short aliases: opus, sonnet, haiku
            "opus": "opus",
            "sonnet": "sonnet",
            "haiku": "haiku",
            # Or full model IDs
            "opus-4.5": "claude-opus-4-5-20251101",
            "sonnet-4.5": "claude-sonnet-4-5-20250514",
            "sonnet-4": "claude-sonnet-4-20250514",
            "haiku-4.5": "claude-haiku-4-5-20250514",
        },
        "default_model": "sonnet",
        "env": {},
        "cost": "paid",  # Direct API calls cost money
        "supports_continue": True,
    },
    "openai": {
        "cli": "codex",  # OpenAI Codex CLI
        "models": {
            "gpt-5": "gpt-5",
            "gpt-5.2": "gpt-5.2",
            "gpt-5.2-codex": "gpt-5.2-codex",
            "o3": "o3",
            "o3-mini": "o3-mini",
        },
        "default_model": "gpt-5.2-codex",
        "default_reasoning": "high",  # Always use high reasoning for best results
        "env": {},
        "supports_reasoning": True,
        "supports_continue": False,
        "cost": "paid",  # Direct API calls cost money
    },
    "google": {
        # Gemini CLI: https://geminicli.com/docs/cli/headless/
        # Uses -p for prompt, -m for model, --include-directories for dirs
        # Supports stdin piping: echo "prompt" | gemini
        "cli": "gemini",
        "models": {
            "gemini-3-pro": "gemini-3-pro-preview",
            "gemini-3-flash": "gemini-3-flash-preview",
            "gemini-2.5-pro": "gemini-2.5-pro",
            "gemini-2.5-flash": "gemini-2.5-flash",
            "auto": "auto",  # Auto model selection (default)
        },
        "default_model": "gemini-2.5-flash",
        "env": {},
        # Session continuation: Not supported via CLI flags (uses /chat save/resume)
        "supports_continue": False,
        "cost": "paid",  # Direct API calls cost money
    },
}

DEFAULT_PROVIDER = "github"
DEFAULT_MODEL = PROVIDERS[DEFAULT_PROVIDER]["default_model"]

# Template matching COPILOT_REVIEW_REQUEST_EXAMPLE.md structure
REQUEST_TEMPLATE = '''# {title}

## Repository and branch

- **Repo:** `{repo}`
- **Branch:** `{branch}`
- **Paths of interest:**
{paths_formatted}

## Summary

{summary}

## Objectives

{objectives}

## Constraints for the patch

- **Output format:** Unified diff only, inline inside a single fenced code block.
- Include a one-line commit subject on the first line of the patch.
- Hunk headers must be numeric only (`@@ -old,+new @@`); no symbolic headers.
- Patch must apply cleanly on branch `{branch}`.
- No destructive defaults; retain existing behavior unless explicitly required by this change.
- No extra commentary, hosted links, or PR creation in the output.

## Acceptance criteria

{acceptance_criteria}

## Test plan

**Before change** (optional): {test_before}

**After change:**

{test_after}

## Implementation notes

{implementation_notes}

## Known touch points

{touch_points}

## Clarifying questions

*Answer inline here or authorize assumptions:*

{clarifying_questions}

## Deliverable

- Reply with a single fenced code block containing a unified diff that meets the constraints above (no prose before/after the fence)
- In the chat, provide answers to each clarifying question explicitly so reviewers do not need to guess
- Do not mark the request complete if either piece is missing; the review will be considered incomplete without both the diff block and the clarifying-answers section
'''

# Rich help formatting
HELP_TEXT = """
Multi-Provider AI Code Review Skill

Submit structured code review requests to multiple AI providers and get unified diffs.

WARNING: Only use 'github' provider to avoid API charges!
   Other providers make direct API calls that cost money.

PROVIDERS:
  github    - GitHub Copilot (FREE with subscription, includes Claude models)
  anthropic - Anthropic Claude (PAID - direct API calls cost money)
  openai    - OpenAI Codex (PAID - direct API calls cost money)
  google    - Google Gemini (PAID - direct API calls cost money)

QUICK START:
  code_review.py check                                    # Verify provider
  code_review.py review --file request.md                 # Submit review (default: GitHub)
  code_review.py review --file request.md -P github -m claude-sonnet-4.5  # FREE Claude
  code_review.py review --file request.md -P anthropic    # COSTS MONEY - AVOID
  code_review.py review --file request.md -P openai       # COSTS MONEY - AVOID
  code_review.py review --file request.md --workspace ./src  # Include uncommitted files

WORKFLOW:
  1. Create request:  code_review.py build -t "Fix bug" -r owner/repo -b main
  2. Edit request:    $EDITOR request.md
  3. Submit review:   code_review.py review --file request.md
  4. Apply patch:     git apply < patch.diff

WORKSPACE FEATURE:
  Use --workspace to copy uncommitted local files to a temp directory
  that providers can access. Useful when files aren't pushed yet.
"""


def get_timeout(default: int = 30) -> int:
    """Get timeout from CODE_REVIEW_TIMEOUT env var with fallback default."""
    try:
        return int(os.environ.get("CODE_REVIEW_TIMEOUT", default))
    except (TypeError, ValueError):
        return default
