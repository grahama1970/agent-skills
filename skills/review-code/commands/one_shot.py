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
    from ..providers.scillm import (
        build_review_prompt,
        reduce_contract_receipts,
        select_default_review_scopes,
        send_review,
        send_scoped_review,
    )
except ImportError:
    _SCRIPT_DIR = Path(__file__).resolve().parent.parent
    if str(_SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPT_DIR))
    from providers.scillm import (
        build_review_prompt,
        reduce_contract_receipts,
        select_default_review_scopes,
        send_review,
        send_scoped_review,
    )


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
        model: scillm model (gpt-5.5, gemini-flash, chutes-deepseek, oc-kimi, etc.)

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
            "- Output ONLY the JSON object review receipt requested by the prompt. No commentary.\n"
            "- Never return a bare empty array. If there are no blockers, return "
            "verdict=satisfied with empty finding arrays and a concrete rationale.\n"
        )

    prompt = build_review_prompt(files, context=context, focus=focus)

    logger.info(f"Sending {len(files)} files ({sum(len(v) for v in files.values())} chars) to {model}")

    result = await send_review(
        prompt=prompt,
        model=model,
        system_prompt=system_prompt,
        files_reviewed=list(files.keys()),
    )

    return {
        "review": result["content"],
        "model": result["model"],
        "usage": result["usage"],
        "ok": result["ok"],
        "error": result["error"],
        "prompt_sha256": result.get("prompt_sha256"),
        "raw_response": result.get("raw_response"),
        "raw_review_content": result.get("raw_review_content"),
        "files_reviewed": list(files.keys()),
        "prompt_chars": len(prompt),
    }


def _parse_scope_models(values: list[str] | None) -> dict[str, str]:
    models: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"--scope-model must use SCOPE=MODEL format, got: {value}")
        scope, model = value.split("=", 1)
        scope = scope.strip()
        model = model.strip()
        if not scope or not model:
            raise ValueError(f"--scope-model must use SCOPE=MODEL format, got: {value}")
        models[scope] = model
    return models


async def fanout_review(
    *,
    files: dict[str, str],
    context: str,
    focus: str,
    default_model: str,
    review_scopes: list[str] | None = None,
    scope_models: dict[str, str] | None = None,
    output_dir: Optional[Path] = None,
    max_concurrency: int = 3,
) -> dict:
    """Run scoped evidence-contract reviews concurrently and reduce them."""
    scopes = review_scopes or select_default_review_scopes(
        files_reviewed=list(files.keys()),
        context=context,
        focus=focus,
    )
    models = scope_models or {}
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "context.md").write_text(context)
        (output_dir / "scope-models.json").write_text(json.dumps({
            "default_model": default_model,
            "scopes": scopes,
            "scope_models": models,
            "max_concurrency": max_concurrency,
        }, indent=2) + "\n")

    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def run_scope(scope: str) -> dict:
        async with semaphore:
            model = models.get(scope, default_model)
            logger.info(f"Scoped review {scope} with {model}")
            result = await send_scoped_review(
                files=files,
                context=context,
                focus=focus,
                scope=scope,
                model=model,
            )
            if output_dir:
                scope_dir = output_dir / scope
                scope_dir.mkdir(parents=True, exist_ok=True)
                (scope_dir / "result.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
                if result.get("receipt"):
                    (scope_dir / "verdict.json").write_text(json.dumps(result["receipt"], indent=2) + "\n")
                if result.get("raw_review_content"):
                    (scope_dir / "raw-review-content.txt").write_text(str(result["raw_review_content"]))
            return result

    tasks = [asyncio.create_task(run_scope(scope)) for scope in scopes]
    scope_results = []
    for task in asyncio.as_completed(tasks):
        scope_results.append(await task)

    receipts = [result["receipt"] for result in scope_results if result.get("ok") and result.get("receipt")]
    aggregate = reduce_contract_receipts(receipts)
    failed_scopes = [
        {
            "scope": result.get("scope"),
            "model": result.get("model"),
            "error": result.get("error"),
        }
        for result in scope_results
        if not result.get("ok")
    ]
    if failed_scopes:
        aggregate["verdict"] = "BLOCKED"
        aggregate["failed_review_scopes"] = failed_scopes
        aggregate["summary"] = (
            f"{aggregate['summary']} {len(failed_scopes)} scoped reviewer calls failed."
        )

    response = {
        "schema": "review_code.fanout.v1",
        "ok": not failed_scopes,
        "verdict": aggregate["verdict"],
        "aggregate": aggregate,
        "scopes": scopes,
        "scope_models": {scope: models.get(scope, default_model) for scope in scopes},
        "scope_results": scope_results,
        "files_reviewed": list(files.keys()),
        "prompt_chars": sum(len(content) for content in files.values()) + len(context) + len(focus),
    }
    if output_dir:
        (output_dir / "aggregate_verdict.json").write_text(json.dumps(aggregate, indent=2) + "\n")
        (output_dir / "fanout_result.json").write_text(json.dumps(response, indent=2, default=str) + "\n")
    return response


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
    persona: str = typer.Option("", "--persona", "-p", help="Legacy --single reviewer identity OR preset name (nico, brandon, tim, senior)"),
    focus: str = typer.Option("", "--focus", help="Specific review focus areas"),
    model: str = typer.Option("gpt-5.5", "--model", "-m", help="scillm model to use"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write review to file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    fanout: bool = typer.Option(True, "--fanout/--single", help="Run scoped evidence-contract reviewer fan-out by default; use --single for the legacy one-call review."),
    review_scope: Optional[list[str]] = typer.Option(None, "--review-scope", help="Specific scoped reviewer to run; repeatable. Defaults are auto-selected from files/context."),
    scope_model: Optional[list[str]] = typer.Option(None, "--scope-model", help="Per-scope model override as SCOPE=MODEL, e.g. correctness_regression=oc-kimi. Repeatable."),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Directory for per-scope fan-out artifacts."),
    max_concurrency: int = typer.Option(3, "--max-concurrency", min=1, help="Maximum concurrent scoped scillm calls."),
) -> None:
    """Bundle files with context and run review-code through scillm.

    Fanout mode is the default: multiple scoped evidence-contract reviewers run
    concurrently, then a reducer accepts only evidence-backed findings. Use
    --single for the legacy one-call persona review.

    Examples:
        # Default scoped fanout
        quick-review -f src/executor.ts -f SKILL.md \\
          --context "Deterministic manifest executor replacing subagent approach" \\
          --model oc-kimi --scope-model evidence_closure_safety=gpt-5.5

        # Explicit security fanout
        quick-review -f run.sh -f probe.py \\
          --context "Model integrity probes sent to LLM via scillm" \\
          --review-scope correctness_regression --review-scope tests_validation \\
          --review-scope security --scope-model security=gpt-5.5

        # Legacy single-call persona review
        quick-review -f collect.py --context "Passive signal collector from transcripts" \\
          --single --persona nico --model gpt-5.5
    """
    # Resolve persona preset for the legacy single-call mode only.
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

    try:
        parsed_scope_models = _parse_scope_models(scope_model)
    except ValueError as exc:
        logger.error(str(exc))
        raise typer.Exit(2) from exc

    if fanout:
        fanout_output_dir = output_dir
        if output and fanout_output_dir is None:
            fanout_output_dir = output.parent / f"{output.stem}-reviewers"
        if fanout_output_dir is not None:
            fanout_output_dir = fanout_output_dir.expanduser().resolve()
        result = asyncio.run(fanout_review(
            files=file_contents,
            context=context,
            focus=focus,
            default_model=model,
            review_scopes=review_scope,
            scope_models=parsed_scope_models,
            output_dir=fanout_output_dir,
            max_concurrency=max_concurrency,
        ))
    else:
        if not resolved_persona.strip():
            logger.error("--persona is required with --single legacy review mode")
            raise typer.Exit(2)
        result = asyncio.run(one_shot_review(
            files=file_contents,
            context=context,
            persona=resolved_persona,
            focus=focus,
            model=model,
        ))

    failed = not result["ok"]
    if json_output:
        out = json.dumps(result, indent=2)
    elif result["ok"] and fanout:
        out = json.dumps(result["aggregate"], indent=2)
    elif result["ok"]:
        out = str(result["review"])
    else:
        out = f"Review failed: {result.get('error') or result.get('aggregate', {}).get('summary') or 'fanout failed'}"

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(out)
        logger.info(f"Review written to {output}")
    else:
        print(out)

    if failed:
        raise typer.Exit(1)
