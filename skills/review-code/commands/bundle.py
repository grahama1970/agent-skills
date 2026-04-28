"""Bundle command for code-review skill."""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

# Handle both import modes
try:
    from ..utils import check_git_status
except ImportError:
    from utils import check_git_status


DEFAULT_MAX_DIFF_CHARS = 120_000
DEFAULT_MAX_FILE_CHARS = 30_000


def _run_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30)


def _git_output(args: list[str], cwd: Path) -> str:
    try:
        result = _run_command(["git", *args], cwd)
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _resolve_repo_dir(repo_dir: Optional[Path]) -> Path:
    start = (repo_dir or Path.cwd()).resolve()
    root = _git_output(["rev-parse", "--show-toplevel"], start)
    return Path(root).resolve() if root else start


def _git_path_args(paths: list[str]) -> list[str]:
    return ["--", *paths] if paths else []


def _collect_changed_files(repo_dir: Path, paths: list[str]) -> list[str]:
    path_args = _git_path_args(paths)
    tracked = _git_output(["diff", "--name-only", "HEAD", *path_args], repo_dir).splitlines()
    untracked = _git_output(["ls-files", "--others", "--exclude-standard", *path_args], repo_dir).splitlines()
    return sorted({path for path in [*tracked, *untracked] if path})


def _git_status(repo_dir: Path, paths: list[str]) -> str:
    return _git_output(["status", "--short", *_git_path_args(paths)], repo_dir) or "(clean)"


def _collect_git_metadata(repo_dir: Path, paths: list[str], all_changed: bool) -> dict[str, str | list[str]]:
    include_worktree_scope = all_changed or bool(paths)
    status = _git_status(repo_dir, paths) if include_worktree_scope else (
        "(omitted: pass --review-file for selected files or --all-changed to include every changed file)"
    )
    changed_files = _collect_changed_files(repo_dir, paths) if include_worktree_scope else []
    return {
        "root": str(repo_dir),
        "branch": _git_output(["branch", "--show-current"], repo_dir) or "(unknown)",
        "remote": _git_output(["remote", "get-url", "origin"], repo_dir) or "(none)",
        "status": status,
        "changed_files": changed_files,
    }


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}\n\n[truncated: omitted {omitted} characters]\n"


def _selected_diff(repo_dir: Path, paths: list[str], all_changed: bool) -> str:
    diff_paths = [] if all_changed else paths
    changed_files = _collect_changed_files(repo_dir, diff_paths)
    tracked_diff = _git_output(["diff", "--binary", "HEAD", *_git_path_args(diff_paths)], repo_dir)
    untracked = set(_git_output(["ls-files", "--others", "--exclude-standard", *_git_path_args(diff_paths)], repo_dir).splitlines())
    untracked_diffs = []
    for rel_path in changed_files:
        if rel_path not in untracked:
            continue
        path = repo_dir / rel_path
        if not path.is_file():
            continue
        result = subprocess.run(
            ["git", "diff", "--no-index", "--", "/dev/null", rel_path],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode in {0, 1} and result.stdout:
            untracked_diffs.append(result.stdout)
    return "\n".join(part for part in [tracked_diff, *untracked_diffs] if part).strip()


def _read_optional_file(path: Optional[Path], label: str) -> str:
    if not path:
        return ""
    if not path.exists():
        typer.echo(f"Error: {label} not found: {path}", err=True)
        raise typer.Exit(code=1)
    return path.read_text(errors="replace").strip()


def _read_context(context: Optional[str], context_file: Optional[Path]) -> str:
    parts = []
    if context:
        parts.append(context.strip())
    file_content = _read_optional_file(context_file, "context file")
    if file_content:
        parts.append(file_content)
    return "\n\n".join(parts).strip()


def _read_list_section(values: Optional[list[str]], file: Optional[Path], label: str) -> str:
    parts = [value.strip() for value in values or [] if value.strip()]
    file_content = _read_optional_file(file, label)
    if file_content:
        parts.append(file_content)
    return "\n\n".join(parts).strip()


def _normalize_review_files(repo_dir: Path, review_files: Optional[list[Path]]) -> list[str]:
    if not review_files:
        return []

    normalized: list[str] = []
    for review_file in review_files:
        path = review_file.expanduser()
        if not path.is_absolute():
            path = repo_dir / path
        try:
            rel_path = path.resolve().relative_to(repo_dir)
        except ValueError:
            typer.echo(f"Error: review file is outside repo: {review_file}", err=True)
            raise typer.Exit(code=1)
        rel = rel_path.as_posix()
        if rel not in normalized:
            normalized.append(rel)
    return normalized


def _safe_changed_file_contents(repo_dir: Path, changed_files: list[str], max_file_chars: int) -> str:
    sections = []
    for rel_path in changed_files:
        path = (repo_dir / rel_path).resolve()
        try:
            path.relative_to(repo_dir)
        except ValueError:
            continue
        if not path.is_file():
            continue
        try:
            content = path.read_text(errors="replace")
        except Exception as exc:
            sections.append(f"### `{rel_path}`\n\n[unable to read file: {exc}]\n")
            continue
        sections.append(
            f"### `{rel_path}`\n\n"
            f"```text\n{_truncate(content, max_file_chars)}\n```\n"
        )
    return "\n".join(sections) if sections else "(No changed file contents included.)"


def _copy_to_clipboard(content: str, require_clipboard: bool) -> None:
    tool = shutil.which("xclip")
    if tool:
        try:
            proc = subprocess.Popen(
                [tool, "-selection", "clipboard"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            assert proc.stdin is not None
            proc.stdin.write(content)
            proc.stdin.close()
            typer.echo("Copied bundle text to clipboard with xclip", err=True)
            return
        except Exception as exc:
            if require_clipboard:
                typer.echo(f"Error: clipboard copy failed: {exc}", err=True)
                raise typer.Exit(code=1)
            typer.echo(f"Warning: clipboard copy failed: {exc}", err=True)
            return

    if require_clipboard:
        typer.echo("Error: xclip not found; install xclip or use --no-clipboard", err=True)
        raise typer.Exit(code=1)
    typer.echo("Warning: xclip not found; wrote markdown file but did not copy clipboard", err=True)


def _copy_file_uri_to_clipboard(path: Path, require_clipboard: bool) -> None:
    tool = shutil.which("xclip")
    if tool:
        payload = f"file://{path.resolve()}\r\n"
        try:
            proc = subprocess.Popen(
                [tool, "-selection", "clipboard", "-t", "text/uri-list"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            assert proc.stdin is not None
            proc.stdin.write(payload)
            proc.stdin.close()
            typer.echo(f"Copied bundle file URI to clipboard: {payload.strip()}", err=True)
            return
        except Exception as exc:
            if require_clipboard:
                typer.echo(f"Error: file clipboard copy failed: {exc}", err=True)
                raise typer.Exit(code=1)
            typer.echo(f"Warning: file clipboard copy failed: {exc}", err=True)
            return

    if require_clipboard:
        typer.echo("Error: xclip not found; install xclip or use --no-clipboard", err=True)
        raise typer.Exit(code=1)
    typer.echo("Warning: xclip not found; wrote markdown file but did not copy file URI", err=True)


def _default_output_path(output_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return output_dir / f"review-code-request-{stamp}.md"


def _optional_section(title: str, content: str) -> str:
    if not content:
        return ""
    return f"\n## {title}\n\n{content}\n"


def _required_output_section(include: bool) -> str:
    if not include:
        return ""
    return """
## Required Output Format

Return:

# Merge-blocking findings

## High severity

### H1. <title>
- Evidence:
- Impact:
- Exact fix:
- Test that should fail before the fix:

## Medium severity

Only include if it should block merge or materially affect safety.

# Important test gaps

List only tests required before merge.

# Merge recommendation

Use exactly one:
- SAFE_TO_MERGE
- SAFE_WITH_CONDITIONS
- CHANGES_REQUESTED
- NOT_SAFE
"""


def _build_review_bundle(
    *,
    title: str,
    request_content: str,
    repo_dir: Path,
    git_metadata: dict[str, str | list[str]],
    rationale: str,
    decision: str,
    expected_contract: str,
    prior_critique: str,
    non_goals: str,
    include_required_output_format: bool,
    include_diff: bool,
    include_file_contents: bool,
    selected_paths: list[str],
    all_changed: bool,
    max_diff_chars: int,
    max_file_chars: int,
) -> str:
    changed_files = git_metadata["changed_files"]
    assert isinstance(changed_files, list)
    diff = ""
    if include_diff:
        if selected_paths or all_changed:
            diff = _selected_diff(repo_dir, selected_paths, all_changed)
            diff = _truncate(diff or "(No tracked-file diff available for selected files.)", max_diff_chars)
        else:
            diff = "(Diff omitted: pass --review-file for selected files or --all-changed to include every changed file.)"

    file_contents = ""
    if include_file_contents:
        file_contents = _safe_changed_file_contents(repo_dir, changed_files, max_file_chars)

    selected_paths_md = "\n".join(f"- `{path}`" for path in selected_paths) or "- (none selected)"
    changed_files_md = "\n".join(f"- `{path}`" for path in changed_files) or "- (none detected in selected scope)"
    generated_at = datetime.now(timezone.utc).isoformat()

    return f"""# {title}

## Reviewer Instructions

Review this as a code review request for Web GPT or another external reviewer.
Focus on correctness, regression risk, security, maintainability, test coverage, and mismatches between the stated intent and the actual diff.
Do not rewrite the entire implementation unless the diff is fundamentally unsafe.
Return findings first, grouped by severity, with concrete file/function references where possible.

{_optional_section("Decision Needed", decision)}
## Rationale And Context

{rationale or "(No additional rationale/context supplied.)"}

{_optional_section("Expected Safety Contract", expected_contract)}
{_optional_section("Prior Critique Being Rechecked", prior_critique)}
{_optional_section("Non-goals For This Review", non_goals)}

## Original Review Request

{request_content or "(No request file supplied; review the current repository changes.)"}

## Repository Snapshot

- Generated at: `{generated_at}`
- Working directory: `{os.getcwd()}`
- Repository root: `{git_metadata["root"]}`
- Branch: `{git_metadata["branch"]}`
- Remote: `{git_metadata["remote"]}`

## Git Status

```text
{git_metadata["status"]}
```

## Selected Review Files

These are the files intentionally selected for external review. Do not expand scope just because other files are changed in the worktree.

{selected_paths_md if selected_paths else "(No selected files. This bundle includes request/context only unless --all-changed was used.)"}

## Changed Files In Selected Scope

{changed_files_md}

## Diff

```diff
{diff if include_diff else "(Diff omitted by --no-diff.)"}
```

## Changed File Contents

{file_contents if include_file_contents else "(File contents omitted by --no-file-contents.)"}

## Review Questions

1. Are there correctness bugs or edge cases in the implementation?
2. Are there security, data-loss, concurrency, or rollback risks?
3. Are the tests or validation steps sufficient for the stated change?
4. Is the change scoped tightly, or does it introduce unrelated behavior?
5. What exact fixes should be made before this is committed?
{_required_output_section(include_required_output_format)}
"""


def bundle(
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Optional existing markdown request file"),
    repo_dir: Optional[Path] = typer.Option(None, "--repo-dir", "-d", help="Repository directory to check git status"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output markdown file (default: /tmp/review-code-request-*.md)"),
    output_dir: Path = typer.Option(Path("/tmp"), "--output-dir", help="Directory for default bundle output"),
    title: str = typer.Option("Code review request", "--title", "-t", help="Review bundle title"),
    context: Optional[str] = typer.Option(None, "--context", help="Rationale/context to include in the bundle"),
    context_file: Optional[Path] = typer.Option(None, "--context-file", help="Markdown/text file with rationale/context"),
    decision: Optional[str] = typer.Option(None, "--decision", help="Specific decision the reviewer should answer"),
    expected_contract: Optional[list[str]] = typer.Option(
        None,
        "--expected-contract",
        help="Expected invariant/contract for the implementation (repeatable)",
    ),
    expected_contract_file: Optional[Path] = typer.Option(None, "--expected-contract-file", help="File containing expected invariants/contracts"),
    prior_critique: Optional[list[str]] = typer.Option(
        None,
        "--prior-critique",
        help="Prior finding/risk the reviewer should re-check (repeatable)",
    ),
    prior_critique_file: Optional[Path] = typer.Option(None, "--prior-critique-file", help="File containing prior critique to re-check"),
    non_goals: Optional[list[str]] = typer.Option(
        None,
        "--non-goal",
        help="Topic the reviewer should explicitly avoid (repeatable)",
    ),
    non_goals_file: Optional[Path] = typer.Option(None, "--non-goals-file", help="File containing review non-goals"),
    include_required_output_format: bool = typer.Option(
        True,
        "--required-output-format/--no-required-output-format",
        help="Include a strict merge-gate output schema",
    ),
    review_files: Optional[list[Path]] = typer.Option(
        None,
        "--review-file",
        "-R",
        help="Specific file to include in the review scope (repeatable)",
    ),
    all_changed: bool = typer.Option(False, "--all-changed", help="Include every changed file in diff/status/content scope"),
    include_diff: bool = typer.Option(True, "--diff/--no-diff", help="Include current git diff"),
    include_file_contents: bool = typer.Option(False, "--file-contents/--no-file-contents", help="Include selected changed file contents"),
    max_diff_chars: int = typer.Option(DEFAULT_MAX_DIFF_CHARS, "--max-diff-chars", help="Maximum diff characters to include"),
    max_file_chars: int = typer.Option(DEFAULT_MAX_FILE_CHARS, "--max-file-chars", help="Maximum characters per changed file"),
    skip_git_check: bool = typer.Option(False, "--skip-git-check", help="Skip git status verification"),
    clipboard: bool = typer.Option(True, "--clipboard/--no-clipboard", "-c", help="Copy bundle to clipboard with xclip"),
    clipboard_file: bool = typer.Option(False, "--clipboard-file", help="Copy output file URI to clipboard with text/uri-list for KDE/browser upload flows"),
    require_clipboard: bool = typer.Option(False, "--require-clipboard", help="Fail if xclip copy fails"),
) -> None:
    """Create a complete markdown review bundle in /tmp and optionally copy it with xclip.

    Examples:
        # Bundle a targeted review scope into /tmp and copy with xclip
        code_review.py bundle --context "Runtime status protocol changes" -R src/runtime.py -R tests/test_runtime.py

        # State intended behavior explicitly so the reviewer does not infer it
        code_review.py bundle -R src/runtime.py --decision "Is this safe to merge?" \
          --expected-contract "Plain ask degrades if artifacts are unwritable" \
          --prior-critique "Prune must not delete unrelated directories" \
          --non-goal "Do not review generated artifacts"

        # Include an existing request file
        code_review.py bundle --file request.md --repo-dir /path/to/repo -R src/runtime.py

        # Write to a specific file without clipboard
        code_review.py bundle --output /tmp/review.md --no-clipboard

        # Copy the generated markdown file itself for browser/file-picker paste flows
        code_review.py bundle --output /tmp/review.md --clipboard-file

        # Explicitly include all changed files when that broad scope is intentional
        code_review.py bundle --all-changed --file-contents

        # Skip git warning/check output
        code_review.py bundle --file request.md --skip-git-check
    """
    repo_root = _resolve_repo_dir(repo_dir)
    request_content = _read_optional_file(file, "request file")
    rationale = _read_context(context, context_file)
    expected_contract_content = _read_list_section(expected_contract, expected_contract_file, "expected contract file")
    prior_critique_content = _read_list_section(prior_critique, prior_critique_file, "prior critique file")
    non_goals_content = _read_list_section(non_goals, non_goals_file, "non-goals file")
    selected_paths = _normalize_review_files(repo_root, review_files)
    scope_paths = [] if all_changed else selected_paths

    if not skip_git_check:
        git_status = check_git_status(repo_root)

        typer.echo("--- Git Status Check ---", err=True)
        typer.echo(f"Branch: {git_status['current_branch'] or 'unknown'}", err=True)
        typer.echo(f"Remote: {git_status['remote_branch'] or 'not tracking'}", err=True)

        if git_status["has_uncommitted"]:
            typer.echo("Note: Uncommitted changes detected; bundle will include local diff/context.", err=True)

        if git_status["has_unpushed"]:
            typer.echo("Note: Unpushed commits detected; external web tools may not see them unless included here.", err=True)

        if not git_status["has_uncommitted"] and not git_status["has_unpushed"]:
            typer.echo("OK: All changes committed and pushed", err=True)

        typer.echo("------------------------", err=True)

    bundle_content = _build_review_bundle(
        title=title,
        request_content=request_content,
        repo_dir=repo_root,
        git_metadata=_collect_git_metadata(repo_root, scope_paths, all_changed),
        rationale=rationale,
        decision=decision.strip() if decision else "",
        expected_contract=expected_contract_content,
        prior_critique=prior_critique_content,
        non_goals=non_goals_content,
        include_required_output_format=include_required_output_format,
        include_diff=include_diff,
        include_file_contents=include_file_contents,
        selected_paths=selected_paths,
        all_changed=all_changed,
        max_diff_chars=max_diff_chars,
        max_file_chars=max_file_chars,
    )

    output_path = output or _default_output_path(output_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(bundle_content)
    typer.echo(f"Wrote review bundle to {output_path}", err=True)

    if clipboard_file:
        _copy_file_uri_to_clipboard(output_path, require_clipboard)
    elif clipboard:
        _copy_to_clipboard(bundle_content, require_clipboard)

    print(str(output_path))
