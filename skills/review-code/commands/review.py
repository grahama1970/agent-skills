"""Single review command for code-review skill."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

import typer

# Handle both import modes
try:
    from ..config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS
    from ..diff_parser import extract_diff
    from ..providers import find_provider_cli, run_provider_async
    from ..utils import create_workspace, get_effective_dirs
except ImportError:
    from config import DEFAULT_MODEL, DEFAULT_PROVIDER, PROVIDERS
    from diff_parser import extract_diff
    from providers import find_provider_cli, run_provider_async
    from utils import create_workspace, get_effective_dirs


def review(
    file: Path = typer.Option(..., "--file", "-f", help="Markdown request file (required)"),
    provider: str = typer.Option(DEFAULT_PROVIDER, "--provider", "-P", help="Provider: github, anthropic, openai, google"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model (provider-specific, uses default if not set)"),
    add_dir: Optional[list[str]] = typer.Option(None, "--add-dir", "-d", help="Add directory for file access"),
    workspace: Optional[list[str]] = typer.Option(None, "--workspace", "-w", help="Copy local paths to temp workspace (for uncommitted files)"),
    reasoning: Optional[str] = typer.Option(None, "--reasoning", "-R", help="Reasoning effort: low, medium, high (openai only)"),
    raw: bool = typer.Option(False, "--raw", help="Output raw response without JSON"),
    extract_diff_flag: bool = typer.Option(False, "--extract-diff", help="Extract only the diff block"),
    twin_id: Optional[str] = typer.Option(None, "--twin-id", help="Digital Twin container ID for isolated review"),
) -> None:
    """Submit a code review request to an AI provider.

    Requires a markdown file following the template structure.
    See: python code_review.py template

    Use --workspace to copy uncommitted local files to a temp directory that
    the provider can access (auto-cleaned up after).

    Use --twin-id to review code inside a Digital Twin container (from battle skill).

    Use --reasoning for OpenAI models that support reasoning effort (o3, gpt-5.2-codex).

    Providers: github (copilot), anthropic (claude), openai (codex), google (gemini)

    Examples:
        code_review.py review --file request.md
        code_review.py review --file request.md --workspace ./src
        code_review.py review --file request.md --twin-id battle_abc123
        code_review.py review --file request.md --provider github --model claude-sonnet-4.5  # FREE
        code_review.py review --file request.md --provider anthropic --model opus-4.5       # COSTS MONEY
        code_review.py review --file request.md --provider openai --model gpt-5.2-codex --reasoning high  # COSTS MONEY
    """
    import subprocess
    
    # If twin_id provided, delegate to container
    if twin_id:
        if not subprocess.run(["docker", "inspect", twin_id], capture_output=True).returncode == 0:
            typer.echo(f"Error: Digital Twin container not found: {twin_id}", err=True)
            raise typer.Exit(code=1)
        
        # Copy review request into container
        subprocess.run(["docker", "cp", str(file), f"{twin_id}:/workspace/review_request.md"], check=True)
        
        # Run review inside container
        result = subprocess.run([
            "docker", "exec", twin_id,
            "python3", "/workspace/.pi/skills/review-code/code_review.py",
            "review", "--file", "/workspace/review_request.md",
            "--provider", provider,
            *(["-m", model] if model else []),
            *(["-R", reasoning] if reasoning else []),
            *(["--raw"] if raw else []),
            *(["--extract-diff"] if extract_diff_flag else []),
        ], capture_output=True, text=True)
        
        print(result.stdout)
        if result.returncode != 0:
            typer.echo(result.stderr, err=True)
        raise typer.Exit(code=result.returncode)
    
    t0 = time.time()

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

    prompt = file.read_text()
    typer.echo(f"Loaded request from {file} ({len(prompt)} chars)", err=True)
    typer.echo(f"Submitting to {provider} ({actual_model})...", err=True)

    # Determine effective directories for the provider CLI
    effective_dirs = get_effective_dirs(add_dir, workspace)

    async def run_review_async(effective_add_dirs: Optional[list[str]]) -> tuple[str, int]:
        """Run the review with the given add_dirs."""
        return await run_provider_async(
            prompt=prompt,
            model=actual_model,
            add_dirs=effective_add_dirs,
            provider=provider,
            step_name=f"Review ({provider}/{actual_model})",
            reasoning=reasoning,
        )

    # Use workspace if provided (copies uncommitted files to temp dir)
    if workspace:
        workspace_paths = [Path(p) for p in workspace]
        with create_workspace(workspace_paths) as ws_path:
            effective_dirs = [str(ws_path)] + (add_dir or [])
            response, returncode = asyncio.run(run_review_async(effective_dirs))
    else:
        response, returncode = asyncio.run(run_review_async(effective_dirs))

    took_ms = int((time.time() - t0) * 1000)

    if returncode != 0:
        error_msg = response or "Unknown error"
        if raw:
            print(f"Error: {error_msg}")
        else:
            print(json.dumps({
                "error": error_msg,
                "return_code": returncode,
                "took_ms": took_ms,
            }, indent=2))
        raise typer.Exit(code=1)

    diff_block = extract_diff(response) if extract_diff_flag else None

    if raw:
        print(diff_block if extract_diff_flag and diff_block else response)
    else:
        out = {
            "meta": {
                "provider": provider,
                "model": actual_model,
                "took_ms": took_ms,
                "prompt_length": len(prompt),
                "response_length": len(response),
            },
            "response": response,
        }
        if extract_diff_flag:
            out["diff"] = diff_block
        out["errors"] = []
        print(json.dumps(out, indent=2, ensure_ascii=False))
