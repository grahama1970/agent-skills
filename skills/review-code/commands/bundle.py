"""Bundle and find commands for code-review skill."""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

# Handle both import modes
try:
    from ..utils import check_git_status
except ImportError:
    from utils import check_git_status


def bundle(
    file: Path = typer.Option(..., "--file", "-f", help="Markdown request file"),
    repo_dir: Optional[Path] = typer.Option(None, "--repo-dir", "-d", help="Repository directory to check git status"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    skip_git_check: bool = typer.Option(False, "--skip-git-check", help="Skip git status verification"),
    clipboard: bool = typer.Option(False, "--clipboard", "-c", help="Copy to clipboard (requires xclip/pbcopy)"),
) -> None:
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
        git_status = check_git_status(repo_dir)

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


def find(
    pattern: str = typer.Option("*review*.md", "--pattern", "-p", help="Glob pattern for filenames"),
    directory: Path = typer.Option(".", "--dir", "-d", help="Directory to search"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", "-r", help="Search recursively"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results to show"),
    sort_by: str = typer.Option("modified", "--sort", "-s", help="Sort by: modified, name, size"),
    contains: Optional[str] = typer.Option(None, "--contains", "-c", help="Filter by content substring"),
) -> None:
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
