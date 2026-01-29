"""Coder-Reviewer loop command for code-review skill."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Optional

import typer

# Handle both import modes
try:
    from ..config import PROVIDERS
    from ..diff_parser import extract_diff
    from ..prompts import LOOP_CODER_FIX_PROMPT, LOOP_CODER_INIT_PROMPT, LOOP_REVIEWER_PROMPT
    from ..providers import run_provider_async
    from ..utils import create_workspace, get_effective_dirs
except ImportError:
    from config import PROVIDERS
    from diff_parser import extract_diff
    from prompts import LOOP_CODER_FIX_PROMPT, LOOP_CODER_INIT_PROMPT, LOOP_REVIEWER_PROMPT
    from providers import run_provider_async
    from utils import create_workspace, get_effective_dirs


async def _loop_async(
    request_content: str,
    coder_provider: str,
    coder_model: str,
    reviewer_provider: str,
    reviewer_model: str,
    add_dir: Optional[list[str]],
    rounds: int,
    output_dir: Path,
    save_intermediate: bool,
    reasoning: Optional[str] = None,
) -> dict:
    """Run iterative Coder-Reviewer loop with mixed providers."""
    history = []
    final_diff = None

    # 1. Coder generates initial solution
    typer.echo(f"\n[Coder] ({coder_provider}) Generating initial solution...", err=True)
    coder_prompt = LOOP_CODER_INIT_PROMPT.format(request=request_content)

    coder_output, rc = await run_provider_async(
        coder_prompt, coder_model, add_dir,
        log_file=output_dir / "coder_init.log" if save_intermediate else None,
        provider=coder_provider,
        step_name="[Coder] Initial generation"
    )
    if rc != 0:
        raise typer.Exit(code=1)

    if save_intermediate:
        header = f"> **Loop Metadata**: Initial Generation | Role: Coder | Provider: {coder_provider} | Model: {coder_model}\n---\n\n"
        (output_dir / "coder_init.md").write_text(header + coder_output)

    current_solution = coder_output
    final_diff = extract_diff(coder_output)
    changelog = []

    # Loop
    for i in range(1, rounds + 1):
        typer.echo(f"\n--- ROUND {i}/{rounds} ---", err=True)

        # 2. Reviewer critiques
        typer.echo(f"\n[Reviewer] ({reviewer_provider}) Reviewing...", err=True)
        reviewer_prompt = LOOP_REVIEWER_PROMPT.format(request=request_content, coder_output=current_solution)

        reviewer_output, rc = await run_provider_async(
            reviewer_prompt, reviewer_model, add_dir,
            log_file=output_dir / f"round{i}_review.log" if save_intermediate else None,
            provider=reviewer_provider,
            step_name=f"[Reviewer] Round {i}",
            reasoning=reasoning  # Only applies if reviewer is openai
        )
        if rc != 0:
            raise typer.Exit(code=1)

        if save_intermediate:
            header = f"> **Loop Metadata**: Round {i} | Role: Reviewer | Provider: {reviewer_provider} | Model: {reviewer_model}\n---\n\n"
            (output_dir / f"round{i}_review.md").write_text(header + reviewer_output)

        # LGTM Check: Look for explicit approval signal in first few lines
        first_lines = "\n".join(reviewer_output.strip().split("\n")[:3]).upper()
        # Check for LGTM but exclude "NOT LGTM" etc.
        positive_signal = ("LGTM" in first_lines or
                          "LOOKS GOOD TO ME" in first_lines or
                          ("LOOKS GOOD" in first_lines and "APPROVED" in first_lines))
        negative_signal = ("NOT LGTM" in first_lines or "ALMOST LGTM" in first_lines)

        is_lgtm = positive_signal and not negative_signal

        if is_lgtm:
            typer.echo("\n[Reviewer] APPROVED (LGTM detected)", err=True)
            break

        # Extract Changelog Entry
        match = re.search(r"CHANGELOG ENTRY:\s*(.*)", reviewer_output, re.IGNORECASE)
        summary = match.group(1).strip() if match else "No summary provided."

        # 3. Coder fixes
        typer.echo(f"\n[Coder] ({coder_provider}) Fixing...", err=True)
        changelog_str = "\n".join(f"- Round {c['round']}: {c['summary']}" for c in changelog) if changelog else "None."

        fix_prompt = LOOP_CODER_FIX_PROMPT.format(
            request=request_content,
            changelog=changelog_str,
            coder_output=current_solution,
            reviewer_output=reviewer_output
        )

        coder_output, rc = await run_provider_async(
            fix_prompt, coder_model, add_dir,
            log_file=output_dir / f"round{i}_fix.log" if save_intermediate else None,
            provider=coder_provider,
            step_name=f"[Coder] Round {i} Fix",
            continue_session=False,  # Stateless to enforce sliding window
        )

        changelog.append({"round": i, "summary": summary})

        if rc != 0:
            raise typer.Exit(code=1)

        if save_intermediate:
            header = f"> **Loop Metadata**: Round {i} | Role: Coder | Provider: {coder_provider} | Model: {coder_model}\n---\n\n"
            (output_dir / f"round{i}_fix.md").write_text(header + coder_output)
            diff = extract_diff(coder_output)
            if diff:
                (output_dir / f"round{i}.patch").write_text(diff)

        current_solution = coder_output
        final_diff = extract_diff(coder_output) or final_diff

        history.append({
            "round": i,
            "reviewer_output": reviewer_output,
            "coder_output": coder_output
        })

    return {
        "final_diff": final_diff,
        "history": history
    }


def loop(
    file: Path = typer.Option(..., "--file", "-f", help="Markdown request file"),
    coder_provider: str = typer.Option("anthropic", "--coder-provider", help="Provider for Coder (Runner)"),
    coder_model: Optional[str] = typer.Option(None, "--coder-model", help="Model for Coder"),
    reviewer_provider: str = typer.Option("openai", "--reviewer-provider", help="Provider for Reviewer"),
    reviewer_model: Optional[str] = typer.Option(None, "--reviewer-model", help="Model for Reviewer"),
    add_dir: Optional[list[str]] = typer.Option(None, "--add-dir", "-d", help="Add directory for file access"),
    workspace: Optional[list[str]] = typer.Option(None, "--workspace", "-w", help="Workspace paths"),
    rounds: int = typer.Option(3, "--rounds", "-r", help="Max retries"),
    save_intermediate: bool = typer.Option(False, "--save-intermediate", "-s", help="Save intermediate logs"),
    reasoning: Optional[str] = typer.Option("high", "--reasoning", help="Reasoning for Reviewer (openai)"),
    output_dir: Path = typer.Option("reviews", "--output-dir", "-o", help="Output directory"),
) -> None:
    """Run a feedback loop between a Coder Agent and a Reviewer Agent.

    Useful for "Opus (Coder) vs Codex (Reviewer)" loops.
    Stops early if Reviewer says "LGTM".
    """
    if not file.exists():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(code=1)

    # Validate providers
    for prov, label in [(coder_provider, "coder"), (reviewer_provider, "reviewer")]:
        if prov not in PROVIDERS:
            typer.echo(f"Error: Unknown {label} provider '{prov}'. Valid: {', '.join(PROVIDERS.keys())}", err=True)
            raise typer.Exit(code=1)

    request_content = file.read_text()

    # Defaults
    c_model = coder_model or PROVIDERS[coder_provider]["default_model"]
    r_model = reviewer_model or PROVIDERS[reviewer_provider]["default_model"]

    output_dir.mkdir(parents=True, exist_ok=True)

    effective_dirs = get_effective_dirs(add_dir, workspace)

    def _run(effective_add_dir: Optional[list[str]]) -> dict:
        return asyncio.run(_loop_async(
            request_content, coder_provider, c_model,
            reviewer_provider, r_model, effective_add_dir,
            rounds, output_dir, save_intermediate, reasoning
        ))

    if workspace:
        workspace_paths = [Path(p) for p in workspace]
        with create_workspace(workspace_paths) as ws_path:
            # Combine workspace with any explicit add_dir paths
            combined_dirs = [str(ws_path)] + (add_dir or [])
            result = _run(combined_dirs)
    else:
        result = _run(effective_dirs)

    if result["final_diff"]:
        print(result["final_diff"])
    else:
        typer.echo("No diff generated.", err=True)
