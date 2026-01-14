#!/usr/bin/env python3
"""GitHub Copilot CLI code review skill.

Submits structured code review requests via `copilot -p` in non-interactive mode.
Follows the format in docs/COPILOT_REVIEW_REQUEST_EXAMPLE.md exactly.

Commands:
    check     - Verify copilot CLI and GitHub authentication
    login     - OAuth device code login for GitHub Copilot
    review    - Submit code review request via copilot CLI
    build     - Generate review request markdown from options
    bundle    - Package request for GitHub Copilot web
    find      - Search for review request files
    template  - Print example template
    models    - List available models

Usage:
    python code_review.py check
    python code_review.py login
    python code_review.py review --file request.md
    python code_review.py review --file request.md --model claude-sonnet-4
    python code_review.py build --title "Fix bug" --repo owner/repo --branch main
    python code_review.py find --pattern "*.md" --dir ./reviews
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

# Rich help formatting
HELP_TEXT = """
GitHub Copilot CLI Code Review Skill

Submit structured code review requests to GitHub Copilot and get unified diffs.

AUTHENTICATION:
  Uses GitHub CLI (gh) OAuth. Ensure you have:
  1. gh CLI installed: https://cli.github.com/
  2. copilot CLI installed: npm install -g @githubnext/github-copilot-cli
  3. Authenticated: gh auth login (with 'copilot' scope)

WORKFLOW:
  1. Create request:  code_review.py build -t "Fix bug" -r owner/repo -b main
  2. Edit request:    $EDITOR request.md
  3. Submit review:   code_review.py review --file request.md
  4. Apply patch:     git apply < patch.diff

For Copilot Web (often better results):
  1. Commit & push:   git add . && git commit && git push
  2. Bundle request:  code_review.py bundle --file request.md --clipboard
  3. Paste at:        https://copilot.github.com
"""

app = typer.Typer(
    add_completion=False,
    help=HELP_TEXT,
    rich_markup_mode="markdown",
)

# Available models in copilot CLI
MODELS = {
    "gpt-5": "gpt-5",
    "claude-sonnet-4": "claude-sonnet-4",
    "claude-sonnet-4.5": "claude-sonnet-4.5",
    "claude-haiku-4.5": "claude-haiku-4.5",
}

DEFAULT_MODEL = "gpt-5"

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


def _find_copilot() -> Optional[str]:
    """Find copilot CLI executable."""
    return shutil.which("copilot")


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


def _run_copilot(
    prompt: str,
    model: str = DEFAULT_MODEL,
    add_dirs: Optional[list[str]] = None,
    timeout: int = 300,
) -> tuple[Optional[str], Optional[str], int]:
    """Run copilot CLI with prompt.

    Returns: (stdout, stderr, return_code)
    """
    cmd = [
        "copilot",
        "-p", prompt,
        "--allow-all-tools",
        "--model", MODELS.get(model, model),
        "--no-color",
    ]

    # Add directories for file access
    if add_dirs:
        for d in add_dirs:
            cmd.extend(["--add-dir", d])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "COPILOT_ALLOW_ALL": "1"},
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return None, f"Timed out after {timeout}s", 124
    except Exception as e:
        return None, str(e), -1


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
def check():
    """Check if copilot CLI is available and authenticated.

    Verifies:
    - copilot CLI is installed
    - gh CLI is installed
    - GitHub authentication is valid

    Examples:
        code_review.py check
    """
    errors = []

    # Check copilot CLI
    copilot_path = _find_copilot()
    if not copilot_path:
        errors.append("copilot CLI not found. Install: npm install -g @githubnext/github-copilot-cli")

    # Check gh auth
    auth_info = _check_gh_auth()
    if not auth_info["authenticated"]:
        errors.append(auth_info["error"] or "GitHub authentication failed")

    # Build output
    output = {
        "copilot": {
            "installed": bool(copilot_path),
            "path": copilot_path,
        },
        "github_auth": {
            "authenticated": auth_info["authenticated"],
            "user": auth_info["user"],
        },
        "models": list(MODELS.keys()),
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
        typer.echo(f"✓ copilot CLI: {copilot_path}", err=True)
        typer.echo(f"✓ GitHub auth: {auth_info['user']}", err=True)
        print(json.dumps(output, indent=2))


@app.command()
def review(
    file: Path = typer.Option(..., "--file", "-f", help="Markdown request file (required)"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model: gpt-5, claude-sonnet-4, etc"),
    add_dir: Optional[list[str]] = typer.Option(None, "--add-dir", "-d", help="Add directory for file access"),
    timeout: int = typer.Option(300, "--timeout", "-t", help="Timeout in seconds"),
    raw: bool = typer.Option(False, "--raw", help="Output raw response without JSON"),
    extract_diff: bool = typer.Option(False, "--extract-diff", help="Extract only the diff block"),
):
    """Submit a code review request to GitHub Copilot CLI.

    Requires a markdown file following the template structure.
    See: python code_review.py template

    Examples:
        code_review.py review --file request.md
        code_review.py review --file request.md --model claude-sonnet-4 --extract-diff --raw
    """
    t0 = time.time()

    if not _find_copilot():
        typer.echo("Error: copilot CLI not found", err=True)
        raise typer.Exit(code=1)

    if not file.exists():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(code=1)

    prompt = file.read_text()
    typer.echo(f"Loaded request from {file} ({len(prompt)} chars)", err=True)
    typer.echo(f"Submitting to copilot CLI ({model})...", err=True)

    stdout, stderr, returncode = _run_copilot(
        prompt=prompt,
        model=model,
        add_dirs=add_dir,
        timeout=timeout,
    )

    took_ms = int((time.time() - t0) * 1000)

    if returncode != 0:
        error_msg = stderr or "Unknown error"
        if raw:
            print(f"Error: {error_msg}")
        else:
            print(json.dumps({
                "error": error_msg,
                "return_code": returncode,
                "took_ms": took_ms,
            }, indent=2))
        raise typer.Exit(code=1)

    response = stdout or ""
    diff_block = _extract_diff(response) if extract_diff else None

    if raw:
        print(diff_block if extract_diff and diff_block else response)
    else:
        out = {
            "meta": {
                "model": model,
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
def models():
    """List available models."""
    print(json.dumps(MODELS, indent=2))


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


@app.command()
def review_full(
    file: Path = typer.Option(..., "--file", "-f", help="Markdown request file"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model for all steps"),
    add_dir: Optional[list[str]] = typer.Option(None, "--add-dir", "-d", help="Add directory for file access"),
    timeout: int = typer.Option(300, "--timeout", "-t", help="Timeout per step in seconds"),
    rounds: int = typer.Option(2, "--rounds", "-r", help="Iteration rounds (default: 2)"),
    context_file: Optional[Path] = typer.Option(None, "--context", "-c", help="Previous round output for context"),
    save_intermediate: bool = typer.Option(False, "--save-intermediate", "-s", help="Save step 1 and 2 outputs"),
    output_dir: Path = typer.Option(".", "--output-dir", "-o", help="Directory for output files"),
):
    """Run iterative code review pipeline.

    Step 1: Generate initial review with diff and clarifying questions
    Step 2: Judge reviews and answers questions, provides feedback
    Step 3: Regenerate final diff incorporating feedback

    Multiple rounds allow refinement. Use --context to pass previous output.

    Examples:
        code_review.py review-full --file request.md
        code_review.py review-full --file request.md --rounds 3
        code_review.py review-full --file request.md --context prev_output.md
    """
    if not _find_copilot():
        typer.echo("Error: copilot CLI not found", err=True)
        raise typer.Exit(code=1)

    if not file.exists():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(code=1)

    request_content = file.read_text()
    t0 = time.time()

    # Ensure output directory exists
    if save_intermediate:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Load previous context if provided
    previous_context = ""
    if context_file and context_file.exists():
        previous_context = context_file.read_text()
        typer.echo(f"Loaded context from: {context_file} ({len(previous_context)} chars)", err=True)

    # Track all rounds
    all_rounds = []
    final_output = ""
    final_diff = None

    for round_num in range(1, rounds + 1):
        typer.echo(f"\n{'#' * 60}", err=True)
        typer.echo(f"ROUND {round_num}/{rounds}", err=True)
        typer.echo(f"{'#' * 60}", err=True)

        # Build context for this round
        round_context = previous_context
        if round_num > 1 and all_rounds:
            # Include previous round's output as context
            prev_round = all_rounds[-1]
            round_context += f"\n\n## Previous Round Output\n{prev_round['full_output']}"

        # Step 1: Generate
        typer.echo("=" * 60, err=True)
        typer.echo(f"STEP 1/3: Generating initial review...", err=True)
        typer.echo("=" * 60, err=True)

        if round_context:
            step1_prompt = STEP1_PROMPT.format(request=request_content) + f"\n\n## Additional Context\n{round_context}"
        else:
            step1_prompt = STEP1_PROMPT.format(request=request_content)

        stdout, stderr, rc = _run_copilot(step1_prompt, model, add_dir, timeout)

        if rc != 0:
            typer.echo(f"Step 1 failed: {stderr}", err=True)
            raise typer.Exit(code=1)

        step1_output = stdout or ""
        typer.echo(f"Step 1 complete ({len(step1_output)} chars)", err=True)

        if save_intermediate:
            step1_file = output_dir / f"round{round_num}_step1.md"
            step1_file.write_text(step1_output)
            typer.echo(f"Saved: {step1_file}", err=True)

        # Step 2: Judge
        typer.echo("\n" + "=" * 60, err=True)
        typer.echo(f"STEP 2/3: Judging and answering questions...", err=True)
        typer.echo("=" * 60, err=True)

        step2_prompt = STEP2_PROMPT.format(request=request_content, step1_output=step1_output)
        stdout, stderr, rc = _run_copilot(step2_prompt, model, add_dir, timeout)

        if rc != 0:
            typer.echo(f"Step 2 failed: {stderr}", err=True)
            raise typer.Exit(code=1)

        step2_output = stdout or ""
        typer.echo(f"Step 2 complete ({len(step2_output)} chars)", err=True)

        if save_intermediate:
            step2_file = output_dir / f"round{round_num}_step2.md"
            step2_file.write_text(step2_output)
            typer.echo(f"Saved: {step2_file}", err=True)

        # Step 3: Regenerate
        typer.echo("\n" + "=" * 60, err=True)
        typer.echo(f"STEP 3/3: Generating final diff...", err=True)
        typer.echo("=" * 60, err=True)

        step3_prompt = STEP3_PROMPT.format(
            request=request_content,
            step1_output=step1_output,
            step2_output=step2_output,
        )
        stdout, stderr, rc = _run_copilot(step3_prompt, model, add_dir, timeout)

        if rc != 0:
            typer.echo(f"Step 3 failed: {stderr}", err=True)
            raise typer.Exit(code=1)

        step3_output = stdout or ""
        round_diff = _extract_diff(step3_output)

        if save_intermediate:
            step3_file = output_dir / f"round{round_num}_final.md"
            step3_file.write_text(step3_output)
            typer.echo(f"Saved: {step3_file}", err=True)

            if round_diff:
                diff_file = output_dir / f"round{round_num}.patch"
                diff_file.write_text(round_diff)
                typer.echo(f"Saved: {diff_file}", err=True)

        # Store round results
        all_rounds.append({
            "round": round_num,
            "step1_length": len(step1_output),
            "step2_length": len(step2_output),
            "step3_length": len(step3_output),
            "diff": round_diff,
            "full_output": step3_output,
        })

        # Update final output
        final_output = step3_output
        final_diff = round_diff

        typer.echo(f"\nRound {round_num} complete", err=True)

    took_ms = int((time.time() - t0) * 1000)

    typer.echo("\n" + "=" * 60, err=True)
    typer.echo(f"ALL ROUNDS COMPLETE ({took_ms}ms total)", err=True)
    typer.echo("=" * 60, err=True)

    # Output
    print(json.dumps({
        "meta": {
            "model": model,
            "took_ms": took_ms,
            "rounds_completed": len(all_rounds),
        },
        "rounds": all_rounds,
        "final_diff": final_diff,
        "final_output": final_output,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
