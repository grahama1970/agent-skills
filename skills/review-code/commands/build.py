"""Build command for creating review request markdown files."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

# Handle both import modes
try:
    from ..config import REQUEST_TEMPLATE
    from ..utils import (
        format_bullet_list,
        format_numbered_list,
        format_numbered_steps,
        format_paths,
        gather_repo_context,
    )
except ImportError:
    from config import REQUEST_TEMPLATE
    from utils import (
        format_bullet_list,
        format_numbered_list,
        format_numbered_steps,
        format_paths,
        gather_repo_context,
    )


def build(
    title: str = typer.Option(..., "--title", "-t", help="Title describing the fix"),
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Repository (owner/repo)"),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Branch name"),
    paths: Optional[list[str]] = typer.Option(None, "--path", "-p", help="Paths of interest"),
    summary: str = typer.Option("", "--summary", "-s", help="Problem summary"),
    objectives: Optional[list[str]] = typer.Option(None, "--objective", "-o", help="Objectives (repeatable)"),
    acceptance: Optional[list[str]] = typer.Option(None, "--acceptance", "-a", help="Acceptance criteria"),
    touch_points: Optional[list[str]] = typer.Option(None, "--touch", help="Known touch points"),
    output: Optional[Path] = typer.Option(None, "--output", help="Write to file instead of stdout"),
    auto_context: bool = typer.Option(False, "--auto-context", "-A", help="Auto-detect repo, branch, modified files, and context"),
) -> None:
    """Build a review request markdown file from options.

    Creates a file matching the COPILOT_REVIEW_REQUEST_EXAMPLE.md structure.

    Use --auto-context to automatically fill repo info and modified files.

    Examples:
        code_review.py build -t "Fix null check" -r owner/repo -b main -p src/main.py
        code_review.py build -A -t "Quick Fix" --output request.md
    """
    # Auto-context override
    impl_notes = "(Add implementation hints here)"

    if auto_context:
        ctx = gather_repo_context()
        if not repo and ctx["repo"]:
            repo = ctx["repo"]
            typer.echo(f"Auto-detected repo: {repo}", err=True)

        if not branch and ctx["branch"]:
            branch = ctx["branch"]
            typer.echo(f"Auto-detected branch: {branch}", err=True)

        if not paths and ctx["modified_files"]:
            paths = ctx["modified_files"]
            typer.echo(f"Auto-detected modified paths: {len(paths)} files", err=True)

        if ctx["context_content"]:
            impl_notes = f"## Auto-Gathered Context\n\n{ctx['context_content']}\n\n" + impl_notes

    # Fallbacks if still missing
    if not repo:
        repo = "owner/repo"
    if not branch:
        branch = "main"

    request = REQUEST_TEMPLATE.format(
        title=title,
        repo=repo,
        branch=branch,
        paths_formatted=format_paths(paths or []),
        summary=summary or "(Describe the problem here)",
        objectives=format_numbered_list(objectives or ["(Specify objectives)"]),
        acceptance_criteria=format_bullet_list(acceptance or ["(Specify acceptance criteria)"]),
        test_before="(Describe how to reproduce the issue)",
        test_after=format_numbered_steps(["(Specify test steps)"]),
        implementation_notes=impl_notes,
        touch_points=format_bullet_list(touch_points or ["(List files/functions to modify)"]),
        clarifying_questions="1. (Add any clarifying questions here)",
    )

    if output:
        output.write_text(request)
        typer.echo(f"Wrote request to {output}", err=True)
    else:
        print(request)
