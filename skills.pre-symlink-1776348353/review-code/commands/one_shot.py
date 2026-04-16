"""Quick review command — bundle files + context, send to scillm, get review back.

This is the "project agent sends all code with complete context in one call" path.
No request.md file, no CLI subprocess, no temp workspace. Just:

    review-code quick-review --files a.ts b.py --context "..." --model gpt-5.3-codex

Or programmatically:

    from commands.quick_review import one_shot_review
    result = await one_shot_review(
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


async def one_shot_review(
    files: dict[str, str],
    context: str,
    persona: str,
    focus: str = "",
    model: str = "gpt-5.3-codex",
    system_prompt: str = "",
) -> dict:
    """Send all files with context for review in one call.

    Args:
        files: {filepath: content} — all files to review
        context: What this code does, why it was built, what it replaces. REQUIRED.
        persona: Who is reviewing — role, expertise, perspective. REQUIRED.
        focus: Specific review focus (security, correctness, etc.)
        model: scillm model (gpt-5.3-codex, text-gemini, text, etc.)

    Returns:
        {"review": str, "model": str, "ok": bool, "error": str | None}
    """
    if not context.strip():
        raise ValueError("--context is required. Provide architectural context: what this code does, why, what it replaces.")
    if not persona.strip():
        raise ValueError("--persona is required. Specify reviewer identity: role, expertise, perspective (e.g. 'Senior security engineer specializing in binary analysis').")

    if not system_prompt:
        system_prompt = (
            f"You are: {persona}\n\n"
            "## Review Behavior\n\n"
            "- Review at senior engineer level. Be skeptical. Challenge assumptions.\n"
            "- Flag anything you would reject in a real PR review.\n"
            "- Every finding MUST cite a specific line number and quote the problematic code.\n"
            "- Every finding MUST include a concrete fix (not just 'fix this').\n"
            "- Do NOT report style preferences or hypothetical issues.\n"
            "- Output ONLY the JSON array of findings. No commentary.\n"
        )

    prompt = build_review_prompt(files, context=context, focus=focus)

    logger.info(f"Sending {len(files)} files ({sum(len(v) for v in files.values())} chars) to {model}")

    result = await send_review(
        prompt=prompt,
        model=model,
        system_prompt=system_prompt,
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


PERSONA_PRESETS: dict[str, str] = {
    "nico": (
        "Nico Bailon, Senior Embry OS Developer at the F-36 plant. Full-stack engineer "
        "who built half the stack and debugs the other half daily. Prior DARPA ARCOS "
        "principal data scientist (4 years) — thinks in graphs, statistical tests, and "
        "formal proofs. Reviews for: architecture correctness, skill composition errors, "
        "silent data corruption, graph/ArangoDB misuse, air-gapped deployment gotchas, "
        "and whether the code actually matches what SKILL.md claims."
    ),
    "brandon": (
        "Brandon Bailey, Principal Director of Cyber Assessments at The Aerospace Corporation. "
        "Creator of the SPARTA framework (4,017 controls, 77,528 relationships). Reviews for: "
        "NIST 800-171 compliance, CWE classification accuracy, supply chain risks, "
        "threat model gaps, countermeasure-to-attack-vector traceability, and whether "
        "every claim traces back to source material. 'I'm not here to validate your work — "
        "I'm here to find the gaps before an adversary does.'"
    ),
    "tim": (
        "Tim Blazytko, reverse engineering researcher, DEF CON trainer, pioneer of agentic "
        "binary analysis. Reviews for: exploitable patterns, injection vectors, unsafe "
        "subprocess calls, attack surface in tool integrations, command injection via "
        "user-controlled input, and whether automation hooks expose unintended capabilities. "
        "'If your tool makes me do MORE clicks to get the same answer I could get from a "
        "script, it's failed.'"
    ),
    "senior": (
        "Senior staff engineer with 15+ years experience. Reviews for architecture, "
        "maintainability, error handling, performance, and whether the code does what "
        "the docs claim. Rejects anything that smells like it was written without "
        "reading existing code first."
    ),
}


def one_shot(
    files: list[str] = typer.Option(..., "--file", "-f", help="File paths to review (repeatable)"),
    context: str = typer.Option(..., "--context", "-c", help="REQUIRED. Architectural context: what this code does, why, what it replaces"),
    persona: str = typer.Option(..., "--persona", "-p", help="REQUIRED. Reviewer identity OR preset name (nico, brandon, tim, senior)"),
    focus: str = typer.Option("", "--focus", help="Specific review focus areas"),
    model: str = typer.Option("gpt-5.3-codex", "--model", "-m", help="scillm model to use"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write review to file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Bundle files with context and send for review in one call.

    Both --context and --persona are REQUIRED. Context-free reviews are shallow.
    Persona-free reviews lack domain expertise.

    Persona presets: nico, brandon, tim, senior
    Or provide a custom persona string.

    Examples:
        # Senior engineer review with Codex
        quick-review -f src/executor.ts -f SKILL.md \\
          --context "Deterministic manifest executor replacing subagent approach" \\
          --persona senior --model gpt-5.3-codex

        # Security review with Tim Blazytko persona
        quick-review -f run.sh -f probe.py \\
          --context "Model integrity probes sent to LLM via scillm" \\
          --persona tim --focus "injection, command execution"

        # QA review with Nico persona
        quick-review -f collect.py --context "Passive signal collector from transcripts" \\
          --persona nico --model text-gemini
    """
    # Resolve persona preset
    resolved_persona = PERSONA_PRESETS.get(persona.lower().strip(), persona)

    # Read all files
    file_contents: dict[str, str] = {}
    for filepath in files:
        p = Path(filepath)
        if not p.exists():
            logger.error(f"File not found: {filepath}")
            raise typer.Exit(1)
        file_contents[filepath] = p.read_text()

    logger.info(f"Reviewing {len(file_contents)} files with {model} (persona: {persona})")

    result = asyncio.run(one_shot_review(
        files=file_contents,
        context=context,
        persona=resolved_persona,
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
