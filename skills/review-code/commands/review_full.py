"""Full iterative review pipeline command for code-review skill."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import typer

# Handle both import modes
try:
    from ..config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, SKILLS_DIR, get_timeout
    from ..diff_parser import extract_diff
    from ..prompts import STEP1_PROMPT, STEP2_PROMPT, STEP3_PROMPT
    from ..providers import find_provider_cli, run_provider_async
    from ..utils import create_workspace, get_effective_dirs
except ImportError:
    from config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, SKILLS_DIR, get_timeout
    from diff_parser import extract_diff
    from prompts import STEP1_PROMPT, STEP2_PROMPT, STEP3_PROMPT
    from providers import find_provider_cli, run_provider_async
    from utils import create_workspace, get_effective_dirs

# Import Task-Monitor adapter if available
try:
    if str(SKILLS_DIR / "task-monitor") not in sys.path:
        sys.path.append(str(SKILLS_DIR / "task-monitor"))
    from monitor_adapter import Monitor
except ImportError:
    Monitor = None


async def _review_full_async(
    request_content: str,
    model: str,
    add_dir: Optional[list[str]],
    rounds: int,
    previous_context: str,
    output_dir: Path,
    save_intermediate: bool,
    provider: str = DEFAULT_PROVIDER,
    reasoning: Optional[str] = None,
    monitor: Optional[Any] = None,
) -> dict:
    """Async implementation of iterative code review pipeline.

    For providers that support --continue (github, anthropic), session context
    is maintained across steps/rounds. For openai/google, each step is independent
    (warnings are emitted when --continue is attempted).
    """
    all_rounds = []
    final_output = ""
    final_diff = None
    is_first_call = True  # Track if this is the first copilot call

    for round_num in range(1, rounds + 1):
        typer.echo(f"\n{'#' * 60}", err=True)
        typer.echo(f"ROUND {round_num}/{rounds}", err=True)
        typer.echo(f"{'#' * 60}", err=True)

        # Step 1: Generate
        typer.echo("=" * 60, err=True)
        typer.echo(f"STEP 1/3: Generating initial review...", err=True)
        log_file = output_dir / f"round{round_num}_step1.log" if save_intermediate else None
        if log_file:
            typer.echo(f"Streaming to: {log_file}", err=True)
        if not is_first_call:
            typer.echo("(continuing session)", err=True)
        typer.echo("=" * 60, err=True)

        if monitor:
            monitor.update(0, item=f"R{round_num}: Generating")

        # First round: include any provided context in prompt
        # Subsequent rounds: context accumulates via --continue
        supports_continue = PROVIDERS[provider].get("supports_continue", True)
        should_continue = (not is_first_call) and supports_continue

        logging_context = []
        if is_first_call and previous_context:
            logging_context.append("initial context")
            step1_prompt = STEP1_PROMPT.format(request=request_content) + f"\n\n## Additional Context\n{previous_context}"
        elif (not supports_continue) and final_output:
            # Context Bridging: Inject previous round output into prompt since session is lost
            logging_context.append("bridged context")
            step1_prompt = STEP1_PROMPT.format(request=request_content) + f"\n\n## Previous Round Output (Context Bridging)\n{final_output}"
            typer.echo("(bridging context manually)", err=True)
        else:
            if should_continue:
                logging_context.append("session continued")
            step1_prompt = STEP1_PROMPT.format(request=request_content)

        step1_output, rc = await run_provider_async(
            step1_prompt, model, add_dir, log_file,
            continue_session=should_continue,
            provider=provider,
            step_name=f"[Round {round_num}] Step 1: Generating review",
            reasoning=reasoning,
        )
        is_first_call = False  # Track flow, though session continuity depends on provider

        if rc != 0:
            typer.echo(f"Step 1 failed (exit {rc})", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Step 1 complete ({len(step1_output)} chars)", err=True)

        if save_intermediate:
            step1_file = output_dir / f"round{round_num}_step1.md"
            header = f"> **Review Metadata**: Round {round_num} | Step 1 | Provider: {provider} | Model: {model}\n---\n\n"
            step1_file.write_text(header + step1_output)
            typer.echo(f"Saved: {step1_file}", err=True)

        # Step 2: Judge (always continues session)
        typer.echo("\n" + "=" * 60, err=True)
        typer.echo(f"STEP 2/3: Judging and answering questions...", err=True)
        log_file = output_dir / f"round{round_num}_step2.log" if save_intermediate else None
        if log_file:
            typer.echo(f"Streaming to: {log_file}", err=True)
        typer.echo("(continuing session)", err=True)
        typer.echo("=" * 60, err=True)

        if monitor:
            monitor.update(0, item=f"R{round_num}: Judging")

        step2_prompt = STEP2_PROMPT.format(request=request_content, step1_output=step1_output)
        step2_output, rc = await run_provider_async(
            step2_prompt, model, add_dir, log_file,
            continue_session=supports_continue,
            provider=provider,
            step_name=f"[Round {round_num}] Step 2: Judging review",
            reasoning=reasoning,
        )

        if rc != 0:
            typer.echo(f"Step 2 failed (exit {rc})", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Step 2 complete ({len(step2_output)} chars)", err=True)

        if save_intermediate:
            step2_file = output_dir / f"round{round_num}_step2.md"
            header = f"> **Review Metadata**: Round {round_num} | Step 2 | Provider: {provider} | Model: {model}\n---\n\n"
            step2_file.write_text(header + step2_output)
            typer.echo(f"Saved: {step2_file}", err=True)

        # Step 3: Regenerate (always continues session)
        typer.echo("\n" + "=" * 60, err=True)
        typer.echo(f"STEP 3/3: Generating final diff...", err=True)
        log_file = output_dir / f"round{round_num}_step3.log" if save_intermediate else None
        if log_file:
            typer.echo(f"Streaming to: {log_file}", err=True)
        typer.echo("(continuing session)", err=True)
        typer.echo("=" * 60, err=True)

        if monitor:
            monitor.update(0, item=f"R{round_num}: Finalizing")

        step3_prompt = STEP3_PROMPT.format(
            request=request_content,
            step1_output=step1_output,
            step2_output=step2_output,
        )
        step3_output, rc = await run_provider_async(
            step3_prompt, model, add_dir, log_file,
            continue_session=supports_continue,
            provider=provider,
            step_name=f"[Round {round_num}] Step 3: Finalizing diff",
            reasoning=reasoning,
        )

        if rc != 0:
            typer.echo(f"Step 3 failed (exit {rc})", err=True)
            raise typer.Exit(code=1)

        round_diff = extract_diff(step3_output)

        if save_intermediate:
            step3_file = output_dir / f"round{round_num}_final.md"
            header = f"> **Review Metadata**: Round {round_num} | Final Diff | Provider: {provider} | Model: {model}\n---\n\n"
            step3_file.write_text(header + step3_output)
            typer.echo(f"Saved: {step3_file}", err=True)

            if round_diff:
                diff_file = output_dir / f"round{round_num}.patch"
                diff_file.write_text(round_diff)
                typer.echo(f"Saved: {diff_file}", err=True)

        all_rounds.append({
            "round": round_num,
            "step1_length": len(step1_output),
            "step2_length": len(step2_output),
            "step3_length": len(step3_output),
            "diff": round_diff,
            "full_output": step3_output,
        })

        final_output = step3_output
        final_diff = round_diff

        typer.echo(f"\nRound {round_num} complete", err=True)
        if monitor:
            monitor.update(1, item=f"Round {round_num} Complete")

    return {
        "rounds": all_rounds,
        "final_diff": final_diff,
        "final_output": final_output,
    }


def review_full(
    file: Path = typer.Option(..., "--file", "-f", help="Markdown request file"),
    provider: str = typer.Option(DEFAULT_PROVIDER, "--provider", "-P", help="Provider: github, anthropic, openai, google"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model (provider-specific, uses default if not set)"),
    add_dir: Optional[list[str]] = typer.Option(None, "--add-dir", "-d", help="Add directory for file access"),
    workspace: Optional[list[str]] = typer.Option(None, "--workspace", "-w", help="Copy local paths to temp workspace (for uncommitted files)"),
    reasoning: Optional[str] = typer.Option(None, "--reasoning", "-R", help="Reasoning effort: low, medium, high (openai only)"),
    rounds: int = typer.Option(2, "--rounds", "-r", help="Iteration rounds (default: 2)"),
    context_file: Optional[Path] = typer.Option(None, "--context", "-c", help="Previous round output for context"),
    save_intermediate: bool = typer.Option(True, "--save-intermediate", "-s", help="Save intermediate outputs and logs (default: True)"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", "-o", help="Directory for output files (default: review_output/)"),
) -> None:
    """Run iterative code review pipeline (async with streaming logs).

    Step 1: Generate initial review with diff and clarifying questions
    Step 2: Judge reviews and answers questions, provides feedback
    Step 3: Regenerate final diff incorporating feedback

    No timeout - runs until completion. Use --save-intermediate to stream
    output to log files for real-time monitoring (tail -f).

    Use --workspace to copy uncommitted local files to a temp directory that
    the provider can access (auto-cleaned up after).

    Use --reasoning for OpenAI models that support reasoning effort (o3, gpt-5.2-codex).

    Providers: github (copilot), anthropic (claude), openai (codex), google (gemini)

    Examples:
        code_review.py review-full --file request.md
        code_review.py review-full --file request.md --workspace ./src --workspace ./tests
        code_review.py review-full --file request.md --provider github --model claude-sonnet-4.5  # FREE
        code_review.py review-full --file request.md --provider anthropic --model opus-4.5       # COSTS MONEY
        code_review.py review-full --file request.md --provider openai --model gpt-5.2-codex --reasoning high  # COSTS MONEY
    """
    if provider not in PROVIDERS:
        typer.echo(f"Error: Unknown provider '{provider}'. Valid: {', '.join(PROVIDERS.keys())}", err=True)
        raise typer.Exit(code=1)

    cli_path = find_provider_cli(provider)
    if not cli_path:
        typer.echo(f"Error: {PROVIDERS[provider]['cli']} CLI not found for provider {provider}", err=True)
        raise typer.Exit(code=1)

    if not file.exists():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(code=1)

    # Use provider's default model if not specified
    actual_model = model or PROVIDERS[provider]["default_model"]

    # Cost warning for expensive providers
    if PROVIDERS[provider].get("cost") == "paid":
        typer.echo(f"WARNING: Using {provider} provider costs money per API call!", err=True)
        typer.echo(f"TIP: Use --provider github --model {actual_model} for FREE access", err=True)

    request_content = file.read_text()
    t0 = time.time()

    # Initialize monitor
    monitor = None
    if Monitor:
        state_file = Path.home() / ".pi" / "code-review" / f"state_{file.stem}.json"
        monitor = Monitor(
            name=f"review-{file.stem}",
            total=rounds,
            desc=f"Reviewing: {file.name}",
            state_file=str(state_file)
        )
        # Register task
        try:
            subprocess.run([
                "python3", str(SKILLS_DIR / "task-monitor" / "monitor.py"),
                "register",
                "--name", f"review-{file.stem}",
                "--state", str(state_file),
                "--total", str(rounds),
                "--desc", f"Code Review: {file.name}"
            ], capture_output=True, check=False, timeout=get_timeout())
        except Exception as e:
            if os.environ.get("CODE_REVIEW_DEBUG"):
                typer.echo(f"Monitor register warning: {e}", err=True)

    typer.echo(f"Using provider: {provider} ({actual_model})", err=True)

    # Default output directory to skill's review_output/
    if output_dir is None:
        output_dir = SCRIPT_DIR / "review_output"
        typer.echo(f"Using default output directory: {output_dir}", err=True)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load previous context if provided
    previous_context = ""
    if context_file and context_file.exists():
        previous_context = context_file.read_text()
        typer.echo(f"Loaded context from: {context_file} ({len(previous_context)} chars)", err=True)

    # Determine effective directories for the provider CLI
    effective_dirs = get_effective_dirs(add_dir, workspace)

    def run_pipeline(effective_add_dir: Optional[list[str]]) -> dict:
        """Run the async pipeline with the given add_dir."""
        typer.echo(f"DEBUG: Running pipeline with add_dir={effective_add_dir}", err=True)
        return asyncio.run(_review_full_async(
            request_content=request_content,
            model=actual_model,
            add_dir=effective_add_dir,
            rounds=rounds,
            previous_context=previous_context,
            output_dir=output_dir,
            save_intermediate=save_intermediate,
            provider=provider,
            reasoning=reasoning,
            monitor=monitor,
        ))

    # Use workspace if provided (copies uncommitted files to temp dir)
    if workspace:
        workspace_paths = [Path(p) for p in workspace]
        with create_workspace(workspace_paths) as ws_path:
            # Combine workspace with any explicit add_dir paths
            combined_dirs = [str(ws_path)] + (add_dir or [])
            result = run_pipeline(combined_dirs)
    else:
        result = run_pipeline(effective_dirs)

    took_ms = int((time.time() - t0) * 1000)

    typer.echo("\n" + "=" * 60, err=True)
    typer.echo(f"ALL ROUNDS COMPLETE ({took_ms}ms total)", err=True)
    if result:
        typer.echo(f"Rounds: {len(result.get('rounds', []))}", err=True)
    typer.echo(f"Model used: {actual_model}", err=True)
    typer.echo("=" * 60, err=True)

    # Output
    print(json.dumps({
        "meta": {
            "provider": provider,
            "model": actual_model,
            "took_ms": took_ms,
            "rounds_completed": len(result["rounds"]),
        },
        **result,
    }, indent=2, ensure_ascii=False))
