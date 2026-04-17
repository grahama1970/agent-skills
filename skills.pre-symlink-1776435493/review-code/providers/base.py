"""Base provider functionality for code-review skill.

Contains:
- Abstract base class for providers
- Common provider utilities (CLI finding, model resolution)
- Async provider execution with streaming
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# Handle both import modes
try:
    from ..config import PROVIDERS
except ImportError:
    from config import PROVIDERS

# Rich console for styled output
console = Console(stderr=True)


def find_provider_cli(provider: str) -> Optional[str]:
    """Find CLI executable for the given provider."""
    if provider not in PROVIDERS:
        return None
    cli = PROVIDERS[provider]["cli"]
    return shutil.which(cli)


def get_provider_model(provider: str, model: Optional[str] = None) -> str:
    """Get the actual model ID for a provider, resolving aliases."""
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown provider: {provider}")

    if model is None:
        model = cfg["default_model"]

    # Check if it's an alias or pass through as-is
    return cfg["models"].get(model, model)


def build_provider_cmd(
    provider: str,
    prompt: Optional[str],
    model: str,
    add_dirs: Optional[list[str]] = None,
    continue_session: bool = False,
    reasoning: Optional[str] = None,
) -> list[str]:
    """Build command args for a given provider.

    Args:
        provider: Provider name (github, anthropic, openai, google)
        prompt: The prompt to send
        model: Model identifier
        add_dirs: Directories to add for file access
        continue_session: Whether to continue previous session
        reasoning: Reasoning effort level for supported providers (low, medium, high)

    Returns:
        Command arguments list
    """
    cfg = PROVIDERS[provider]
    cli = cfg["cli"]
    actual_model = get_provider_model(provider, model)

    # Use provider's default reasoning if not specified
    effective_reasoning = reasoning or cfg.get("default_reasoning")

    if provider == "github":
        cmd = _build_github_cmd(cli, actual_model, prompt, add_dirs, continue_session)
    elif provider == "anthropic":
        cmd = _build_anthropic_cmd(cli, actual_model, add_dirs, continue_session)
    elif provider == "openai":
        cmd = _build_openai_cmd(cli, actual_model, add_dirs, continue_session, effective_reasoning)
    elif provider == "google":
        cmd = _build_google_cmd(cli, actual_model, add_dirs, continue_session)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    return cmd


def _build_github_cmd(
    cli: str, model: str, prompt: Optional[str],
    add_dirs: Optional[list[str]], continue_session: bool
) -> list[str]:
    """Build GitHub Copilot CLI command."""
    cmd = [cli]
    if continue_session:
        cmd.append("--continue")
    
    # Only use -p if provided (legacy/single-call support)
    # Most calls now use stdin for robustness
    if prompt:
        cmd.extend(["-p", prompt])
        
    cmd.extend([
        "--allow-all-tools",
        "--allow-all-paths",
        "--model", model,
        "--no-color",
    ])
    if add_dirs:
        for d in add_dirs:
            cmd.extend(["--add-dir", d])
    return cmd


def _build_anthropic_cmd(
    cli: str, model: str,
    add_dirs: Optional[list[str]], continue_session: bool
) -> list[str]:
    """Build Claude CLI command.

    NOTE: prompt will be passed via stdin, not as positional arg.
    This handles long prompts with newlines and special characters.
    """
    cmd = [cli, "--print"]
    if continue_session:
        cmd.append("--continue")
    cmd.extend(["--model", model])
    if add_dirs:
        for d in add_dirs:
            cmd.extend(["--add-dir", d])
    return cmd


def _build_openai_cmd(
    cli: str, model: str,
    add_dirs: Optional[list[str]], continue_session: bool,
    reasoning: Optional[str]
) -> list[str]:
    """Build OpenAI Codex CLI command.

    Uses exec subcommand with prompt via stdin.
    NOTE: Codex supports --add-dir but not --continue.
    """
    cmd = [cli, "exec", "--model", model]
    # Add reasoning effort (defaults to high for best results)
    if reasoning:
        cmd.extend(["-c", f"reasoning_effort=\"{reasoning}\""])
    if add_dirs:
        for d in add_dirs:
            cmd.extend(["--add-dir", d])
    if continue_session:
        print("Warning: --continue not supported for openai provider", file=sys.stderr)
    return cmd


def _build_google_cmd(
    cli: str, model: str,
    add_dirs: Optional[list[str]], continue_session: bool
) -> list[str]:
    """Build Gemini CLI command.

    Uses stdin for prompts, -m for model, --include-directories for dirs.
    Session continuation not supported via CLI flags.
    """
    cmd = [cli, "-m", model, "--yolo"]  # --yolo auto-approves actions
    if add_dirs:
        # Gemini uses comma-separated directories
        cmd.extend(["--include-directories", ",".join(add_dirs)])
    if continue_session:
        print("Warning: --continue not supported for google provider (use /chat save/resume)", file=sys.stderr)
    return cmd


async def run_provider_async(
    prompt: str,
    model: str,
    add_dirs: Optional[list[str]] = None,
    log_file: Optional[Path] = None,
    continue_session: bool = False,
    provider: str = "github",
    stream_to_stderr: bool = True,
    step_name: str = "Processing",
    reasoning: Optional[str] = None,
) -> tuple[str, int]:
    """Run provider CLI with real-time output streaming.

    No timeout - process runs until completion.
    Output is streamed to:
      - log_file (if provided) for persistent logs
      - stderr (if stream_to_stderr=True) for live progress monitoring

    Returns: (output, return_code)
    """
    if provider not in PROVIDERS:
        return f"Unknown provider: {provider}", 1

    cli_path = find_provider_cli(provider)
    if not cli_path:
        return f"{PROVIDERS[provider]['cli']} CLI not found for provider {provider}", 1

    # Pass prompt via stdin for ALL providers (handles long prompts and formatting)
    use_stdin = True
    
    # If using stdin, we don't pass the prompt as an argument
    cmd_prompt = None if use_stdin else prompt
    cmd = build_provider_cmd(provider, cmd_prompt, model, add_dirs, continue_session, reasoning)
    
    # Use absolute CLI path if found
    if cli_path:
        cmd[0] = str(cli_path)
        
    env = {**os.environ, **PROVIDERS[provider].get("env", {}), "PYTHONUNBUFFERED": "1"}

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
    except (FileNotFoundError, PermissionError, OSError) as e:
        return f"Failed to start provider CLI: {e}", 1

    # Send prompt via stdin for providers that need it
    if use_stdin:
        try:
            proc.stdin.write(prompt.encode())
            await proc.stdin.drain()
            proc.stdin.close()
            await proc.stdin.wait_closed()
        except (BrokenPipeError, ConnectionResetError) as e:
            console.print(f"[yellow]Warning: stdin closed early: {e}[/yellow]")

    output_lines = []
    log_handle = open(log_file, 'w', buffering=1) if log_file else None
    line_count = 0
    char_count = 0

    try:
        sys.stderr.write(f"[review-code] {step_name} started...\n")
        async for line in proc.stdout:
            text = line.decode(errors="replace")
            output_lines.append(text)
            line_count += 1
            char_count += len(text)

            # Stream to log file
            if log_handle:
                log_handle.write(text)
                log_handle.flush()
            
            # Optionally stream raw output to stderr
            if stream_to_stderr and os.environ.get("CODE_REVIEW_RAW_OUTPUT"):
                sys.stderr.write(text)
                sys.stderr.flush()
            elif line_count % 50 == 0:
                sys.stderr.write(f"\r[review-code] {step_name}: {line_count} lines...")
                sys.stderr.flush()

    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    finally:
        if log_handle:
            log_handle.close()

    await proc.wait()
    if line_count > 0:
        sys.stderr.write(f"\r[review-code] {step_name}: Complete ({line_count} lines)\n")
    else:
        sys.stderr.write(f"[review-code] {step_name}: Finished with no output (RC: {proc.returncode})\n")
        
    return ''.join(output_lines), proc.returncode

