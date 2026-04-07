"""Quick review command — bundle files + context, send to scillm, get review back.

This is the "project agent sends all code with complete context in one call" path.
No request.md file, no CLI subprocess, no temp workspace. Just:

    review-code quick-review --files a.ts b.py --context "..." --model gpt-5.3-codex

Or programmatically:

    from commands.quick_review import quick_review_files
    result = await quick_review_files(
        files={"executor.ts": code, "SKILL.md": docs},
        context="Deterministic manifest executor replacing failed subagent approach",
        model="gpt-5.3-codex",
    )
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

# Handle both import modes
try:
    from ..providers.scillm import build_review_prompt, send_review
except ImportError:
    _SCRIPT_DIR = Path(__file__).resolve().parent.parent
    if str(_SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPT_DIR))
    from providers.scillm import build_review_prompt, send_review


async def quick_review_files(
    files: dict[str, str],
    context: str = "",
    focus: str = "",
    model: str = "gpt-5.3-codex",
    system_prompt: str = "You are a critical code reviewer. Be skeptical. Challenge assumptions. Call out missing evidence. Do not be agreeable for politeness.",
    max_tokens: int = 4000,
) -> dict:
    """Send all files with context for review in one call.

    Args:
        files: {filepath: content} — all files to review
        context: What this code does, why it was built, what it replaces
        focus: Specific review focus (security, correctness, etc.)
        model: scillm model (gpt-5.3-codex, text-gemini, text, etc.)

    Returns:
        {"review": str, "model": str, "ok": bool, "error": str | None}
    """
    prompt = build_review_prompt(files, context=context, focus=focus)

    logger.info(f"Sending {len(files)} files ({sum(len(v) for v in files.values())} chars) to {model}")

    result = await send_review(
        prompt=prompt,
        model=model,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
    )

    return {
        "review": result["content"],
        "model": result["model"],
        "usage": result["usage"],
        "ok": result["ok"],
        "error": result["error"],
        "files_reviewed": list(files.keys()),
        "prompt_chars": len(prompt),
    }


def quick_review(
    files: list[str] = typer.Option(..., "--file", "-f", help="File paths to review (repeatable)"),
    context: str = typer.Option("", "--context", "-c", help="Architectural context for the review"),
    focus: str = typer.Option("", "--focus", help="Specific review focus areas"),
    model: str = typer.Option("gpt-5.3-codex", "--model", "-m", help="scillm model to use"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write review to file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Bundle files with context and send for review in one call.

    No request.md needed. The project agent reads files, provides context,
    and gets a review back. All files are sent in one prompt with full context.

    Examples:
        # Review with Codex
        quick-review -f src/executor.ts -f SKILL.md --context "New manifest executor" --model gpt-5.3-codex

        # Review with Gemini
        quick-review -f src/*.py --context "Training harness" --model text-gemini

        # Review with DeepSeek (cheapest)
        quick-review -f run.sh --focus "shell injection" --model text
    """
    # Read all files
    file_contents: dict[str, str] = {}
    for filepath in files:
        p = Path(filepath)
        if not p.exists():
            logger.error(f"File not found: {filepath}")
            raise typer.Exit(1)
        file_contents[filepath] = p.read_text()

    logger.info(f"Reviewing {len(file_contents)} files with {model}")

    result = asyncio.run(quick_review_files(
        files=file_contents,
        context=context,
        focus=focus,
        model=model,
    ))

    if json_output:
        out = json.dumps(result, indent=2)
    elif result["ok"]:
        out = result["review"]
    else:
        out = f"Review failed: {result['error']}"
        raise typer.Exit(1)

    if output:
        output.write_text(out)
        logger.info(f"Review written to {output}")
    else:
        print(out)
