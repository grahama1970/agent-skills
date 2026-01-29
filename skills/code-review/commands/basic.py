"""Basic CLI commands: check, login, models, template.

These are simple commands that don't run reviews.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import typer

# Handle both import modes
try:
    from ..config import DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, get_timeout
    from ..providers import check_gh_auth, find_provider_cli
except ImportError:
    from config import DEFAULT_PROVIDER, PROVIDERS, SCRIPT_DIR, get_timeout
    from providers import check_gh_auth, find_provider_cli


def check(
    provider: str = typer.Option(DEFAULT_PROVIDER, "--provider", "-P", help="Provider to check: github, anthropic, openai, google"),
) -> None:
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
    cli_path = find_provider_cli(provider)
    if not cli_path:
        errors.append(f"{cli_name} CLI not found for provider {provider}")

    # Check auth for github provider (uses gh CLI)
    auth_info = {"authenticated": False, "user": None}
    if provider == "github":
        auth_info = check_gh_auth()
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
        typer.echo("Prerequisites not met:", err=True)
        for err in errors:
            typer.echo(f"  - {err}", err=True)
        print(json.dumps(output, indent=2))
        raise typer.Exit(code=1)
    else:
        typer.echo(f"OK {cli_name} CLI: {cli_path}", err=True)
        if provider == "github" and auth_info["user"]:
            typer.echo(f"OK GitHub auth: {auth_info['user']}", err=True)
        print(json.dumps(output, indent=2))


def models(
    provider: Optional[str] = typer.Option(None, "--provider", "-P", help="Show models for specific provider"),
) -> None:
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


def template() -> None:
    """Print the example review request template."""
    template_path = SCRIPT_DIR / "docs" / "COPILOT_REVIEW_REQUEST_EXAMPLE.md"
    if template_path.exists():
        print(template_path.read_text())
    else:
        typer.echo("Template not found", err=True)
        raise typer.Exit(code=1)


def login(
    refresh: bool = typer.Option(False, "--refresh", "-r", help="Refresh existing auth"),
) -> None:
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
        result = subprocess.run(cmd, timeout=get_timeout())
        if result.returncode == 0:
            typer.echo("\nAuthentication successful!", err=True)

            # Verify the login
            auth_info = check_gh_auth()
            if auth_info["authenticated"]:
                typer.echo(f"Logged in as: {auth_info['user']}", err=True)
            print(json.dumps({
                "status": "ok",
                "user": auth_info["user"],
            }, indent=2))
        else:
            typer.echo("\nAuthentication failed", err=True)
            raise typer.Exit(code=1)
    except KeyboardInterrupt:
        typer.echo("\nCancelled", err=True)
        raise typer.Exit(code=130)
