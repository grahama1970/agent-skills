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

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# Rich console for styled output
console = Console(stderr=True)

# Rich help formatting
HELP_TEXT = """
Multi-Provider AI Code Review Skill

Submit structured code review requests to multiple AI providers and get unified diffs.

PROVIDERS:
  github    - GitHub Copilot (default, requires copilot CLI)
  anthropic - Anthropic Claude (requires claude CLI)
  openai    - OpenAI Codex (requires codex CLI, high reasoning default)
  google    - Google Gemini (requires gemini CLI)

QUICK START:
  code_review.py check                                    # Verify provider
  code_review.py review --file request.md                 # Submit review
  code_review.py review --file request.md -P anthropic    # Use Claude
  code_review.py review --file request.md -P openai       # Use Codex with high reasoning
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

app = typer.Typer(
    add_completion=False,
    help=HELP_TEXT,
    rich_markup_mode="markdown",
)

# Provider configurations
# Each provider has: cli (command), models (dict), default_model, and optional env vars
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


def _find_provider_cli(provider: str) -> Optional[str]:
    """Find CLI executable for the given provider."""
    if provider not in PROVIDERS:
        return None
    cli = PROVIDERS[provider]["cli"]
    return shutil.which(cli)


import tempfile
from contextlib import contextmanager


@contextmanager
def _create_workspace(paths: list[Path], base_dir: Optional[Path] = None):
    """Create a temporary workspace with copies of specified paths.

    Copies files/directories to a temp location so providers can access
    uncommitted local files without requiring git commits.

    Args:
        paths: List of file/directory paths to copy
        base_dir: Base directory for relative path preservation (default: cwd)

    Yields:
        Path to the temporary workspace directory

    Example:
        with _create_workspace([Path("src/"), Path("tests/")]) as workspace:
            # workspace contains copies of src/ and tests/
            run_provider(add_dir=workspace)
        # workspace is automatically cleaned up
    """
    import shutil as sh

    base = base_dir or Path.cwd()
    workspace = Path(tempfile.mkdtemp(prefix="code-review-workspace-"))

    try:
        console.print(f"[dim]Creating workspace: {workspace}[/dim]")
        for path in paths:
            path = Path(path)
            if not path.exists():
                console.print(f"[yellow]Warning: Path not found, skipping: {path}[/yellow]")
                continue

            # Preserve relative path structure
            try:
                rel_path = path.relative_to(base)
            except ValueError:
                # Out-of-tree path: use sanitized absolute path to avoid collisions
                # e.g., /home/user/foo.py -> _external/home/user/foo.py
                sanitized = str(path.resolve()).lstrip("/").replace("/", "_")
                rel_path = Path("_external") / sanitized
                console.print(f"[yellow]Note: {path} is outside workspace base, using {rel_path}[/yellow]")

            dest = workspace / rel_path

            if path.is_dir():
                sh.copytree(path, dest, dirs_exist_ok=True)
                console.print(f"[dim]  Copied dir: {path} -> {dest}[/dim]")
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                sh.copy2(path, dest)
                console.print(f"[dim]  Copied file: {path} -> {dest}[/dim]")

        yield workspace

    finally:
        # Cleanup
        console.print(f"[dim]Cleaning up workspace: {workspace}[/dim]")
        sh.rmtree(workspace, ignore_errors=True)


def _get_provider_model(provider: str, model: Optional[str] = None) -> str:
    """Get the actual model ID for a provider, resolving aliases."""
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown provider: {provider}")

    if model is None:
        model = cfg["default_model"]

    # Check if it's an alias or pass through as-is
    return cfg["models"].get(model, model)


def _build_provider_cmd(
    provider: str,
    prompt: str,
    model: str,
    add_dirs: Optional[list[str]] = None,
    continue_session: bool = False,
    reasoning: Optional[str] = None,
) -> list[str]:
    """Build command args for a given provider.

    Args:
        reasoning: Reasoning effort level for supported providers (low, medium, high).
                   Currently only openai supports this via -c reasoning_effort=<level>.
                   If not specified, uses provider's default_reasoning if available.
    """
    cfg = PROVIDERS[provider]
    cli = cfg["cli"]
    actual_model = _get_provider_model(provider, model)

    # Use provider's default reasoning if not specified
    effective_reasoning = reasoning or cfg.get("default_reasoning")

    if provider == "github":
        # GitHub Copilot CLI
        cmd = [cli]
        if continue_session:
            cmd.append("--continue")
        cmd.extend([
            "-p", prompt,
            "--allow-all-tools",
            "--model", actual_model,
            "--no-color",
        ])
        if add_dirs:
            for d in add_dirs:
                cmd.extend(["--add-dir", d])

    elif provider == "anthropic":
        # Claude CLI (Claude Code)
        # -p/--print is non-interactive mode
        # For long prompts with special chars, we pass via stdin (no positional arg)
        cmd = [cli, "--print"]
        if continue_session:
            cmd.append("--continue")
        cmd.extend([
            "--model", actual_model,
        ])
        if add_dirs:
            for d in add_dirs:
                cmd.extend(["--add-dir", d])
        # NOTE: prompt will be passed via stdin, not as positional arg
        # This handles long prompts with newlines and special characters

    elif provider == "openai":
        # OpenAI Codex CLI - uses exec subcommand with prompt via stdin
        cmd = [cli, "exec", "--model", actual_model]
        # Add reasoning effort (defaults to high for best results)
        if effective_reasoning:
            cmd.extend(["-c", f"reasoning_effort=\"{effective_reasoning}\""])
        # NOTE: prompt will be passed via stdin (same as anthropic)
        # NOTE: Codex supports --add-dir but not --continue
        if add_dirs:
            for d in add_dirs:
                cmd.extend(["--add-dir", d])
        if continue_session:
            import sys
            print(f"Warning: --continue not supported for openai provider", file=sys.stderr)

    elif provider == "google":
        # Gemini CLI: https://geminicli.com/docs/cli/headless/
        # Uses stdin for prompts, -m for model, --include-directories for dirs
        cmd = [cli, "-m", actual_model, "--yolo"]  # --yolo auto-approves actions
        if add_dirs:
            # Gemini uses comma-separated directories
            cmd.extend(["--include-directories", ",".join(add_dirs)])
        # NOTE: prompt will be passed via stdin (same as anthropic/openai)
        # Session continuation not supported via CLI flags
        if continue_session:
            import sys
            print(f"Warning: --continue not supported for google provider (use /chat save/resume)", file=sys.stderr)

    else:
        raise ValueError(f"Unknown provider: {provider}")

    return cmd


def _get_timeout(default: int = 30) -> int:
    """Get timeout from CODE_REVIEW_TIMEOUT env var with fallback default."""
    try:
        return int(os.environ.get("CODE_REVIEW_TIMEOUT", default))
    except (TypeError, ValueError):
        return default


def _check_gh_auth() -> dict:
    """Check GitHub CLI authentication status.

    Uses `gh auth token` for reliable auth check (returns token if authenticated).
    Uses `gh api user` to get username (reliable JSON output).

    Returns dict with:
        authenticated: bool
        user: Optional[str]
        error: Optional[str]
    """
    result = {
        "authenticated": False,
        "user": None,
        "error": None,
    }

    # Check if gh CLI is installed
    if not shutil.which("gh"):
        result["error"] = "gh CLI not found. Install: https://cli.github.com/"
        return result

    # Check auth by trying to get token (most reliable check)
    try:
        token_result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=_get_timeout(),
        )
        if token_result.returncode != 0:
            result["error"] = "Not logged in. Run: gh auth login"
            return result

        # Get username via API (reliable JSON)
        user_result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=_get_timeout(),
        )
        if user_result.returncode == 0:
            result["user"] = user_result.stdout.strip()

        result["authenticated"] = True

    except Exception as e:
        result["error"] = str(e)

    return result


async def _run_provider_async(
    prompt: str,
    model: str = DEFAULT_MODEL,
    add_dirs: Optional[list[str]] = None,
    log_file: Optional[Path] = None,
    continue_session: bool = False,
    provider: str = DEFAULT_PROVIDER,
    stream_to_stderr: bool = True,
    step_name: str = "Processing",
    reasoning: Optional[str] = None,
) -> tuple[str, int]:
    """Run provider CLI with real-time output streaming and rich progress.

    No timeout - process runs until completion.
    Output is streamed to:
      - log_file (if provided) for persistent logs
      - stderr (if stream_to_stderr=True) for live progress monitoring

    Use continue_session=True to maintain context from previous call.
    Use reasoning=high/medium/low for supported providers (openai).

    Returns: (output, return_code)
    """
    if provider not in PROVIDERS:
        return f"Unknown provider: {provider}", 1

    cli_path = _find_provider_cli(provider)
    if not cli_path:
        return f"{PROVIDERS[provider]['cli']} CLI not found for provider {provider}", 1

    cmd = _build_provider_cmd(provider, prompt, model, add_dirs, continue_session, reasoning)
    env = {**os.environ, **PROVIDERS[provider].get("env", {})}

    # Pass prompt via stdin for providers that support it (handles long prompts with special chars)
    # anthropic: claude reads from stdin
    # openai: codex reads from stdin
    # google: gemini reads from stdin (piped input)
    use_stdin = provider in ("anthropic", "openai", "google")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if use_stdin else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )

    # Send prompt via stdin for providers that need it
    if use_stdin:
        try:
            proc.stdin.write(prompt.encode())
            await proc.stdin.drain()
            proc.stdin.close()
            await proc.stdin.wait_closed()
        except (BrokenPipeError, ConnectionResetError) as e:
            # Provider closed stdin early - continue to read output for error message
            console.print(f"[yellow]Warning: stdin closed early: {e}[/yellow]")

    output_lines = []
    log_handle = open(log_file, 'w') if log_file else None
    line_count = 0
    char_count = 0

    # Use rich progress for visual feedback
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        TextColumn("[dim]{task.fields[status]}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(step_name, status="starting...", total=None)

        try:
            async for line in proc.stdout:
                text = line.decode(errors="replace")  # Handle non-UTF8 gracefully
                output_lines.append(text)
                line_count += 1
                char_count += len(text)

                # Update progress status
                status = f"{line_count} lines, {char_count:,} chars"
                # Show last meaningful line (skip empty/whitespace)
                stripped = text.strip()
                if stripped and len(stripped) < 60:
                    status = f"{status} | {stripped[:50]}"
                progress.update(task, status=status)

                # Stream to log file
                if log_handle:
                    log_handle.write(text)
                    log_handle.flush()
                # Optionally stream raw output to stderr
                if stream_to_stderr and os.environ.get("CODE_REVIEW_RAW_OUTPUT"):
                    sys.stderr.write(text)
                    sys.stderr.flush()
        except asyncio.CancelledError:
            progress.update(task, status="[red]CANCELLED[/red]")
            proc.kill()
            await proc.wait()
            raise
        finally:
            if log_handle:
                log_handle.close()

    await proc.wait()
    return ''.join(output_lines), proc.returncode


def _extract_diff(response: str) -> Optional[str]:
    """Extract unified diff/patch block from response.

    Prefers blocks containing unified diff markers (---/+++ or @@ hunks).
    """
    blocks = re.findall(r'```(?:diff|patch)?\s*\n(.*?)\n```', response, re.DOTALL)
    for b in blocks:
        text = b.strip()
        # Prefer blocks with file headers
        if re.search(r'^\s*---\s', text, re.MULTILINE) and re.search(r'^\s*\+\+\+\s', text, re.MULTILINE):
            return text
        # Or with hunk headers
        if re.search(r'^\s*@@\s*-\d+', text, re.MULTILINE):
            return text
    # Fall back to first code block if no diff markers found
    if blocks:
        return blocks[0].strip()
    return None


def _format_paths(paths: list[str]) -> str:
    """Format paths as markdown list."""
    if not paths:
        return "  - (to be determined)"
    return "\n".join(f"  - `{p}`" for p in paths)


def _format_numbered_list(items: list[str], prefix: str = "") -> str:
    """Format items as numbered markdown sections."""
    if not items:
        return "1. (to be specified)"
    result = []
    for i, item in enumerate(items, 1):
        result.append(f"### {i}. {prefix}{item.split(':')[0] if ':' in item else item}\n\n{item}")
    return "\n\n".join(result)


def _format_bullet_list(items: list[str]) -> str:
    """Format items as bullet list."""
    if not items:
        return "- (to be specified)"
    return "\n".join(f"- {item}" for item in items)


def _format_numbered_steps(items: list[str]) -> str:
    """Format items as numbered steps."""
    if not items:
        return "1. (to be specified)"
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))


@app.command()
def check(
    provider: str = typer.Option(DEFAULT_PROVIDER, "--provider", "-P", help="Provider to check: github, anthropic, openai, google"),
):
    """Check if provider CLI is available and authenticated.

    Verifies:
    - Provider CLI is installed (copilot, claude, codex, or gemini)
    - For github provider: gh CLI is installed and authenticated

    Examples:
        code_review.py check
        code_review.py check --provider anthropic
    """
    if provider not in PROVIDERS:
        typer.echo(f"Error: Unknown provider '{provider}'. Valid: {', '.join(PROVIDERS.keys())}", err=True)
        raise typer.Exit(code=1)

    errors = []
    cfg = PROVIDERS[provider]
    cli_name = cfg["cli"]

    # Check provider CLI
    cli_path = _find_provider_cli(provider)
    if not cli_path:
        errors.append(f"{cli_name} CLI not found for provider {provider}")

    # Check auth for github provider (uses gh CLI)
    auth_info = {"authenticated": False, "user": None}
    if provider == "github":
        auth_info = _check_gh_auth()
        if not auth_info["authenticated"]:
            errors.append(auth_info["error"] or "GitHub authentication failed")

    # Build output
    output = {
        "provider": provider,
        "cli": {
            "name": cli_name,
            "installed": bool(cli_path),
            "path": cli_path,
        },
        "auth": auth_info if provider == "github" else {"note": f"Auth check not implemented for {provider}"},
        "default_model": cfg["default_model"],
        "models": list(cfg["models"].keys()),
        "errors": errors,
        "status": "error" if errors else "ok",
    }

    if errors:
        typer.echo("❌ Prerequisites not met:", err=True)
        for err in errors:
            typer.echo(f"  • {err}", err=True)
        print(json.dumps(output, indent=2))
        raise typer.Exit(code=1)
    else:
        typer.echo(f"✓ {cli_name} CLI: {cli_path}", err=True)
        if provider == "github" and auth_info["user"]:
            typer.echo(f"✓ GitHub auth: {auth_info['user']}", err=True)
        print(json.dumps(output, indent=2))


@app.command()
def review(
    file: Path = typer.Option(..., "--file", "-f", help="Markdown request file (required)"),
    provider: str = typer.Option(DEFAULT_PROVIDER, "--provider", "-P", help="Provider: github, anthropic, openai, google"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model (provider-specific, uses default if not set)"),
    add_dir: Optional[list[str]] = typer.Option(None, "--add-dir", "-d", help="Add directory for file access"),
    workspace: Optional[list[str]] = typer.Option(None, "--workspace", "-w", help="Copy local paths to temp workspace (for uncommitted files)"),
    reasoning: Optional[str] = typer.Option(None, "--reasoning", "-R", help="Reasoning effort: low, medium, high (openai only)"),
    raw: bool = typer.Option(False, "--raw", help="Output raw response without JSON"),
    extract_diff: bool = typer.Option(False, "--extract-diff", help="Extract only the diff block"),
):
    """Submit a code review request to an AI provider.

    Requires a markdown file following the template structure.
    See: python code_review.py template

    Use --workspace to copy uncommitted local files to a temp directory that
    the provider can access (auto-cleaned up after).

    Use --reasoning for OpenAI models that support reasoning effort (o3, gpt-5.2-codex).

    Providers: github (copilot), anthropic (claude), openai (codex), google (gemini)

    Examples:
        code_review.py review --file request.md
        code_review.py review --file request.md --workspace ./src
        code_review.py review --file request.md --provider anthropic --model opus-4.5
        code_review.py review --file request.md --provider openai --model gpt-5.2-codex --reasoning high
    """
    t0 = time.time()

    if provider not in PROVIDERS:
        typer.echo(f"Error: Unknown provider '{provider}'. Valid: {', '.join(PROVIDERS.keys())}", err=True)
        raise typer.Exit(code=1)

    cli_path = _find_provider_cli(provider)
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

    async def run_review_async(effective_add_dirs: Optional[list[str]]) -> tuple[str, int]:
        """Run the review with the given add_dirs."""
        return await _run_provider_async(
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
        with _create_workspace(workspace_paths) as ws_path:
            effective_dirs = [str(ws_path)] + (add_dir or [])
            response, returncode = asyncio.run(run_review_async(effective_dirs))
    else:
        response, returncode = asyncio.run(run_review_async(add_dir))

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
    diff_block = _extract_diff(response) if extract_diff else None

    if raw:
        print(diff_block if extract_diff and diff_block else response)
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
        if extract_diff:
            out["diff"] = diff_block
        out["errors"] = []
        print(json.dumps(out, indent=2, ensure_ascii=False))


@app.command()
def build(
    title: str = typer.Option(..., "--title", "-t", help="Title describing the fix"),
    repo: str = typer.Option(..., "--repo", "-r", help="Repository (owner/repo)"),
    branch: str = typer.Option(..., "--branch", "-b", help="Branch name"),
    paths: Optional[list[str]] = typer.Option(None, "--path", "-p", help="Paths of interest"),
    summary: str = typer.Option("", "--summary", "-s", help="Problem summary"),
    objectives: Optional[list[str]] = typer.Option(None, "--objective", "-o", help="Objectives (repeatable)"),
    acceptance: Optional[list[str]] = typer.Option(None, "--acceptance", "-a", help="Acceptance criteria"),
    touch_points: Optional[list[str]] = typer.Option(None, "--touch", help="Known touch points"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write to file instead of stdout"),
):
    """Build a review request markdown file from options.

    Creates a file matching the COPILOT_REVIEW_REQUEST_EXAMPLE.md structure.

    Examples:
        code_review.py build -t "Fix null check" -r owner/repo -b main -p src/main.py
        code_review.py build -t "Fix bug" -r owner/repo -b fix-branch --output request.md
    """
    request = REQUEST_TEMPLATE.format(
        title=title,
        repo=repo,
        branch=branch,
        paths_formatted=_format_paths(paths or []),
        summary=summary or "(Describe the problem here)",
        objectives=_format_numbered_list(objectives or ["(Specify objectives)"]),
        acceptance_criteria=_format_bullet_list(acceptance or ["(Specify acceptance criteria)"]),
        test_before="(Describe how to reproduce the issue)",
        test_after=_format_numbered_steps(["(Specify test steps)"]),
        implementation_notes="(Add implementation hints here)",
        touch_points=_format_bullet_list(touch_points or ["(List files/functions to modify)"]),
        clarifying_questions="1. (Add any clarifying questions here)",
    )

    if output:
        output.write_text(request)
        typer.echo(f"Wrote request to {output}", err=True)
    else:
        print(request)


@app.command()
def models(
    provider: Optional[str] = typer.Option(None, "--provider", "-P", help="Show models for specific provider"),
):
    """List available models by provider.

    Examples:
        code_review.py models                      # All providers
        code_review.py models --provider anthropic # Just anthropic
    """
    if provider:
        if provider not in PROVIDERS:
            typer.echo(f"Error: Unknown provider '{provider}'. Valid: {', '.join(PROVIDERS.keys())}", err=True)
            raise typer.Exit(code=1)
        output = {
            "provider": provider,
            "cli": PROVIDERS[provider]["cli"],
            "default_model": PROVIDERS[provider]["default_model"],
            "models": PROVIDERS[provider]["models"],
        }
    else:
        output = {
            "providers": {
                name: {
                    "cli": cfg["cli"],
                    "default_model": cfg["default_model"],
                    "models": cfg["models"],
                }
                for name, cfg in PROVIDERS.items()
            }
        }
    print(json.dumps(output, indent=2))


@app.command()
def template():
    """Print the example review request template."""
    template_path = Path(__file__).parent / "docs" / "COPILOT_REVIEW_REQUEST_EXAMPLE.md"
    if template_path.exists():
        print(template_path.read_text())
    else:
        typer.echo("Template not found", err=True)
        raise typer.Exit(code=1)


def _check_git_status(repo_dir: Optional[Path] = None) -> dict:
    """Check git status for uncommitted/unpushed changes."""
    cwd = str(repo_dir) if repo_dir else None
    result = {
        "has_uncommitted": False,
        "has_unpushed": False,
        "current_branch": None,
        "remote_branch": None,
    }

    try:
        # Get current branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=cwd, timeout=_get_timeout()
        )
        if branch_result.returncode == 0:
            result["current_branch"] = branch_result.stdout.strip()

        # Check for uncommitted changes
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=cwd, timeout=_get_timeout()
        )
        if status_result.returncode == 0 and status_result.stdout.strip():
            result["has_uncommitted"] = True

        # Get remote tracking branch first (needed for unpushed check)
        remote_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            capture_output=True, text=True, cwd=cwd, timeout=_get_timeout()
        )
        if remote_result.returncode == 0:
            result["remote_branch"] = remote_result.stdout.strip()
            # Use machine-readable count instead of parsing git log output
            unpushed_result = subprocess.run(
                ["git", "rev-list", "--count", "@{u}.."],
                capture_output=True, text=True, cwd=cwd, timeout=_get_timeout()
            )
            if unpushed_result.returncode == 0:
                try:
                    if int(unpushed_result.stdout.strip()) > 0:
                        result["has_unpushed"] = True
                except ValueError:
                    pass

    except Exception:
        pass

    return result


@app.command()
def bundle(
    file: Path = typer.Option(..., "--file", "-f", help="Markdown request file"),
    repo_dir: Optional[Path] = typer.Option(None, "--repo-dir", "-d", help="Repository directory to check git status"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    skip_git_check: bool = typer.Option(False, "--skip-git-check", help="Skip git status verification"),
    clipboard: bool = typer.Option(False, "--clipboard", "-c", help="Copy to clipboard (requires xclip/pbcopy)"),
):
    """Bundle request for copy/paste into GitHub Copilot web.

    IMPORTANT: GitHub Copilot web can only see changes that are:
    1. Committed to git
    2. Pushed to a remote feature branch

    This command checks git status and warns if changes aren't pushed.

    Examples:
        # Bundle and check git status
        code_review.py bundle --file request.md --repo-dir /path/to/repo

        # Bundle to file
        code_review.py bundle --file request.md --output copilot_request.txt

        # Bundle to clipboard
        code_review.py bundle --file request.md --clipboard

        # Skip git check (if you know it's pushed)
        code_review.py bundle --file request.md --skip-git-check
    """
    if not file.exists():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(code=1)

    # Check git status if repo_dir provided
    if repo_dir and not skip_git_check:
        git_status = _check_git_status(repo_dir)

        typer.echo("--- Git Status Check ---", err=True)
        typer.echo(f"Branch: {git_status['current_branch'] or 'unknown'}", err=True)
        typer.echo(f"Remote: {git_status['remote_branch'] or 'not tracking'}", err=True)

        if git_status["has_uncommitted"]:
            typer.echo("WARNING: Uncommitted changes detected!", err=True)
            typer.echo("  -> Copilot web won't see these changes", err=True)
            typer.echo("  -> Run: git add . && git commit -m 'message'", err=True)

        if git_status["has_unpushed"]:
            typer.echo("WARNING: Unpushed commits detected!", err=True)
            typer.echo("  -> Copilot web won't see these changes", err=True)
            typer.echo(f"  -> Run: git push origin {git_status['current_branch']}", err=True)

        if not git_status["has_uncommitted"] and not git_status["has_unpushed"]:
            typer.echo("OK: All changes committed and pushed", err=True)

        typer.echo("------------------------", err=True)

    # Read and prepare the bundle
    request_content = file.read_text()

    # Add header for Copilot web
    bundle_content = f"""=== CODE REVIEW REQUEST FOR GITHUB COPILOT WEB ===

INSTRUCTIONS:
1. Ensure your changes are committed and pushed to the feature branch
2. Open GitHub Copilot web (copilot.github.com)
3. Paste this entire content as your prompt
4. Copilot will analyze the repo/branch and generate a patch

--- BEGIN REQUEST ---

{request_content}

--- END REQUEST ---
"""

    # Output
    if clipboard:
        try:
            # Try xclip (Linux) or pbcopy (macOS)
            if shutil.which("xclip"):
                proc = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
                proc.communicate(bundle_content.encode())
                typer.echo("Copied to clipboard (xclip)", err=True)
            elif shutil.which("pbcopy"):
                proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                proc.communicate(bundle_content.encode())
                typer.echo("Copied to clipboard (pbcopy)", err=True)
            else:
                typer.echo("Error: No clipboard tool found (install xclip or pbcopy)", err=True)
                print(bundle_content)
        except Exception as e:
            typer.echo(f"Clipboard error: {e}", err=True)
            print(bundle_content)
    elif output:
        output.write_text(bundle_content)
        typer.echo(f"Wrote bundle to {output}", err=True)
    else:
        print(bundle_content)


@app.command()
def find(
    pattern: str = typer.Option("*review*.md", "--pattern", "-p", help="Glob pattern for filenames"),
    directory: Path = typer.Option(".", "--dir", "-d", help="Directory to search"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", "-r", help="Search recursively"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results to show"),
    sort_by: str = typer.Option("modified", "--sort", "-s", help="Sort by: modified, name, size"),
    contains: Optional[str] = typer.Option(None, "--contains", "-c", help="Filter by content substring"),
):
    """Find review request markdown files.

    Search for code review request files by pattern, with optional content filtering.

    Examples:
        # Find all review files
        code_review.py find

        # Find in specific directory
        code_review.py find --dir ./reviews --pattern "*.md"

        # Find files containing specific text
        code_review.py find --contains "Repository and branch"

        # Find recent files, sorted by modification time
        code_review.py find --sort modified --limit 10

        # Non-recursive search
        code_review.py find --no-recursive
    """
    if not directory.exists():
        typer.echo(f"Error: Directory not found: {directory}", err=True)
        raise typer.Exit(code=1)

    # Collect matching files
    matches = []
    search_paths = directory.rglob(pattern) if recursive else directory.glob(pattern)

    for path in search_paths:
        if not path.is_file():
            continue

        # Content filter
        if contains:
            try:
                content = path.read_text(errors="ignore")
                if contains.lower() not in content.lower():
                    continue
            except Exception:
                continue

        try:
            stat = path.stat()
            matches.append({
                "path": str(path),
                "name": path.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "modified_str": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
        except Exception:
            continue

    # Sort results
    if sort_by == "modified":
        matches.sort(key=lambda x: x["modified"], reverse=True)
    elif sort_by == "name":
        matches.sort(key=lambda x: x["name"].lower())
    elif sort_by == "size":
        matches.sort(key=lambda x: x["size"], reverse=True)

    # Limit results
    matches = matches[:limit]

    if not matches:
        typer.echo(f"No files matching '{pattern}' found in {directory}", err=True)
        raise typer.Exit(code=0)

    # Output
    typer.echo(f"Found {len(matches)} file(s):\n", err=True)
    for m in matches:
        size_kb = m["size"] / 1024
        typer.echo(f"  {m['modified_str']}  {size_kb:6.1f}KB  {m['path']}", err=True)

    # JSON output
    print(json.dumps({
        "pattern": pattern,
        "directory": str(directory),
        "count": len(matches),
        "files": matches,
    }, indent=2))


@app.command()
def login(
    refresh: bool = typer.Option(False, "--refresh", "-r", help="Refresh existing auth"),
):
    """Login to GitHub for Copilot CLI access.

    Opens a browser for GitHub OAuth authentication.
    This is a convenience wrapper around `gh auth login`.

    Examples:
        # Initial login
        code_review.py login

        # Refresh existing auth
        code_review.py login --refresh
    """
    if not shutil.which("gh"):
        typer.echo("Error: gh CLI not found", err=True)
        typer.echo("Install from: https://cli.github.com/", err=True)
        raise typer.Exit(code=1)

    # Build command
    if refresh:
        cmd = ["gh", "auth", "refresh"]
        typer.echo("Refreshing GitHub auth...", err=True)
    else:
        cmd = ["gh", "auth", "login", "-w"]
        typer.echo("Starting GitHub OAuth login...", err=True)

    typer.echo("This will open your browser for authentication.\n", err=True)

    # Run interactively
    try:
        result = subprocess.run(cmd)
        if result.returncode == 0:
            typer.echo("\n✓ Authentication successful!", err=True)

            # Verify the login
            auth_info = _check_gh_auth()
            if auth_info["authenticated"]:
                typer.echo(f"✓ Logged in as: {auth_info['user']}", err=True)
            print(json.dumps({
                "status": "ok",
                "user": auth_info["user"],
            }, indent=2))
        else:
            typer.echo("\n❌ Authentication failed", err=True)
            raise typer.Exit(code=1)
    except KeyboardInterrupt:
        typer.echo("\nCancelled", err=True)
        raise typer.Exit(code=130)


STEP1_PROMPT = """You are a code review generator. Analyze the repository and branch specified below, then generate:

1. A unified diff that addresses the objectives
2. Any clarifying questions you have about requirements or implementation choices

{request}

---
OUTPUT FORMAT:
First, list any clarifying questions (if none, write "No clarifying questions").
Then provide the unified diff in a fenced code block.
"""

STEP2_PROMPT = """You are a code review judge. Review the generated code review below and:

1. Answer any clarifying questions based on the original request context
2. Critique the proposed diff - identify issues, missing cases, or improvements
3. Provide specific feedback for improving the diff

ORIGINAL REQUEST:
{request}

---
GENERATED REVIEW (Step 1):
{step1_output}

---
OUTPUT FORMAT:
## Answers to Clarifying Questions
(Answer each question or state N/A)

## Critique
(Issues found, missing cases, suggestions)

## Feedback for Revision
(Specific actionable items for the final diff)
"""

STEP3_PROMPT = """You are a code review finalizer. Generate the final unified diff incorporating the judge's feedback.

ORIGINAL REQUEST:
{request}

---
INITIAL REVIEW:
{step1_output}

---
JUDGE FEEDBACK:
{step2_output}

---
OUTPUT FORMAT:
Provide ONLY a single fenced code block containing the final unified diff.
The diff should:
- Address all feedback from the judge
- Apply cleanly to the specified branch
- Include a one-line commit subject on the first line
No commentary before or after the code block.
"""


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

        # First round: include any provided context in prompt
        # Subsequent rounds: context accumulates via --continue
        if is_first_call and previous_context:
            step1_prompt = STEP1_PROMPT.format(request=request_content) + f"\n\n## Additional Context\n{previous_context}"
        else:
            step1_prompt = STEP1_PROMPT.format(request=request_content)

        step1_output, rc = await _run_provider_async(
            step1_prompt, model, add_dir, log_file,
            continue_session=not is_first_call,
            provider=provider,
            step_name=f"[Round {round_num}] Step 1: Generating review",
            reasoning=reasoning,
        )
        is_first_call = False  # All subsequent calls continue the session

        if rc != 0:
            typer.echo(f"Step 1 failed (exit {rc})", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Step 1 complete ({len(step1_output)} chars)", err=True)

        if save_intermediate:
            step1_file = output_dir / f"round{round_num}_step1.md"
            step1_file.write_text(step1_output)
            typer.echo(f"Saved: {step1_file}", err=True)

        # Step 2: Judge (always continues session)
        typer.echo("\n" + "=" * 60, err=True)
        typer.echo(f"STEP 2/3: Judging and answering questions...", err=True)
        log_file = output_dir / f"round{round_num}_step2.log" if save_intermediate else None
        if log_file:
            typer.echo(f"Streaming to: {log_file}", err=True)
        typer.echo("(continuing session)", err=True)
        typer.echo("=" * 60, err=True)

        step2_prompt = STEP2_PROMPT.format(request=request_content, step1_output=step1_output)
        step2_output, rc = await _run_provider_async(
            step2_prompt, model, add_dir, log_file,
            continue_session=True,
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
            step2_file.write_text(step2_output)
            typer.echo(f"Saved: {step2_file}", err=True)

        # Step 3: Regenerate (always continues session)
        typer.echo("\n" + "=" * 60, err=True)
        typer.echo(f"STEP 3/3: Generating final diff...", err=True)
        log_file = output_dir / f"round{round_num}_step3.log" if save_intermediate else None
        if log_file:
            typer.echo(f"Streaming to: {log_file}", err=True)
        typer.echo("(continuing session)", err=True)
        typer.echo("=" * 60, err=True)

        step3_prompt = STEP3_PROMPT.format(
            request=request_content,
            step1_output=step1_output,
            step2_output=step2_output,
        )
        step3_output, rc = await _run_provider_async(
            step3_prompt, model, add_dir, log_file,
            continue_session=True,
            provider=provider,
            step_name=f"[Round {round_num}] Step 3: Finalizing diff",
            reasoning=reasoning,
        )

        if rc != 0:
            typer.echo(f"Step 3 failed (exit {rc})", err=True)
            raise typer.Exit(code=1)

        round_diff = _extract_diff(step3_output)

        if save_intermediate:
            step3_file = output_dir / f"round{round_num}_final.md"
            step3_file.write_text(step3_output)
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

    return {
        "rounds": all_rounds,
        "final_diff": final_diff,
        "final_output": final_output,
    }


@app.command()
def review_full(
    file: Path = typer.Option(..., "--file", "-f", help="Markdown request file"),
    provider: str = typer.Option(DEFAULT_PROVIDER, "--provider", "-P", help="Provider: github, anthropic, openai, google"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model (provider-specific, uses default if not set)"),
    add_dir: Optional[list[str]] = typer.Option(None, "--add-dir", "-d", help="Add directory for file access"),
    workspace: Optional[list[str]] = typer.Option(None, "--workspace", "-w", help="Copy local paths to temp workspace (for uncommitted files)"),
    reasoning: Optional[str] = typer.Option(None, "--reasoning", "-R", help="Reasoning effort: low, medium, high (openai only)"),
    rounds: int = typer.Option(2, "--rounds", "-r", help="Iteration rounds (default: 2)"),
    context_file: Optional[Path] = typer.Option(None, "--context", "-c", help="Previous round output for context"),
    save_intermediate: bool = typer.Option(False, "--save-intermediate", "-s", help="Save intermediate outputs and logs"),
    output_dir: Path = typer.Option(".", "--output-dir", "-o", help="Directory for output files"),
):
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
        code_review.py review-full --file request.md --provider anthropic --model opus-4.5
        code_review.py review-full --file request.md --provider openai --model gpt-5.2-codex --reasoning high
    """
    if provider not in PROVIDERS:
        typer.echo(f"Error: Unknown provider '{provider}'. Valid: {', '.join(PROVIDERS.keys())}", err=True)
        raise typer.Exit(code=1)

    cli_path = _find_provider_cli(provider)
    if not cli_path:
        typer.echo(f"Error: {PROVIDERS[provider]['cli']} CLI not found for provider {provider}", err=True)
        raise typer.Exit(code=1)

    if not file.exists():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(code=1)

    # Use provider's default model if not specified
    actual_model = model or PROVIDERS[provider]["default_model"]

    request_content = file.read_text()
    t0 = time.time()

    typer.echo(f"Using provider: {provider} ({actual_model})", err=True)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load previous context if provided
    previous_context = ""
    if context_file and context_file.exists():
        previous_context = context_file.read_text()
        typer.echo(f"Loaded context from: {context_file} ({len(previous_context)} chars)", err=True)

    def run_pipeline(effective_add_dir: Optional[list[str]]):
        """Run the async pipeline with the given add_dir."""
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
        ))

    # Use workspace if provided (copies uncommitted files to temp dir)
    if workspace:
        workspace_paths = [Path(p) for p in workspace]
        with _create_workspace(workspace_paths) as ws_path:
            # Combine workspace with any explicit add_dir paths
            effective_dirs = [str(ws_path)] + (add_dir or [])
            result = run_pipeline(effective_dirs)
    else:
        result = run_pipeline(add_dir)

    took_ms = int((time.time() - t0) * 1000)

    typer.echo("\n" + "=" * 60, err=True)
    typer.echo(f"ALL ROUNDS COMPLETE ({took_ms}ms total)", err=True)
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


if __name__ == "__main__":
    app()
