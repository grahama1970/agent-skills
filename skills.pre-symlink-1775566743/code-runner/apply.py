"""Path authorization, file context, and hunk review for code-runner.

tool_use (v4) is the only code path — LLM writes files via structured tool calls.
v1-v3 text parsing has been removed. See .archive/skills/code-runner-v1v3/.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from loguru import logger

MAX_FILE_CONTENT_CHARS = 12000  # ~3K tokens per file, fits in most context windows

# Paths that should NEVER be overwritten by an LLM
DENYLIST = {".git", ".gitignore", ".env", "SKILL.md", "run.sh", "sanity.sh", "pyproject.toml", "package.json"}


def _is_path_authorized(rel_path: str, cwd: str, allowlist: list[str] | None) -> str | None:
    """Central path authorization: denylist + boundary + allowlist check.

    Returns the corrected path (may differ from input on fuzzy extension match),
    or None if the path is not authorized.
    """
    clean_path = rel_path.lstrip("/")

    # Denylist
    if any(clean_path == d or clean_path.startswith(d + "/") for d in DENYLIST):
        logger.warning("Rejected denylisted path: {}", rel_path)
        return None

    # Path boundary (safe against /repo2 startswith /repo bug)
    cwd_path = Path(cwd).resolve()
    target = (cwd_path / clean_path).resolve()
    try:
        target.relative_to(cwd_path)
    except ValueError:
        logger.warning("Rejected path traversal: {} resolves outside {}", rel_path, cwd_path)
        return None

    # No allowlist — anything under cwd is fine
    if allowlist is None:
        return clean_path

    rel_from_cwd = str(target.relative_to(cwd_path))
    # Exact match
    if clean_path in allowlist or rel_from_cwd in allowlist or rel_path in allowlist:
        return clean_path
    # Directory scope: "scripts/" allows "scripts/foo.py"
    if any(
        (clean_path.startswith(a.rstrip("/") + "/") or rel_from_cwd.startswith(a.rstrip("/") + "/"))
        for a in allowlist if a.endswith("/") or (cwd_path / a).is_dir()
    ):
        return clean_path
    # Extension-fuzzy match: LLMs confuse .ts/.tsx, .js/.jsx, .c/.h
    # Return the ALLOWLIST entry's path (correct extension), not the LLM's path
    clean_stem = Path(clean_path).with_suffix("")
    for a in allowlist:
        if Path(a).with_suffix("") == clean_stem:
            logger.info("Allowlist fuzzy match: {} → {} (correcting extension)", clean_path, a)
            return a  # use allowlist entry's extension
    return None


def apply_file_blocks(blocks: list[tuple[str, str]], cwd: str, allowlist: list[str] | None = None) -> list[str]:
    """Write parsed file blocks to disk. Returns list of files written.

    Safety:
    - Only writes to paths under cwd (path boundary check, not string prefix)
    - Denylists sensitive files (.git, .env, SKILL.md, run.sh, etc.)
    - If allowlist is provided, ONLY writes to listed paths (default-deny)
    """
    written: list[str] = []
    validated: list[tuple[Path, str, str]] = []  # (target, clean_path, content)
    cwd_path = Path(cwd).resolve()

    for rel_path, content in blocks:
        if rel_path == "__unnamed__":
            continue

        # Normalize: strip leading slashes for relative resolution
        clean_path = rel_path.lstrip("/")

        # Denylist check
        if any(clean_path == d or clean_path.startswith(d + "/") for d in DENYLIST):
            logger.warning("Rejected denylisted path: {}", rel_path)
            continue

        # Path boundary check (safe against /repo2 startswith /repo bug)
        target = (cwd_path / clean_path).resolve()
        try:
            target.relative_to(cwd_path)
        except ValueError:
            logger.warning("Rejected path traversal: {} resolves outside {}", rel_path, cwd_path)
            continue

        # Allowlist enforcement — may correct extension (.ts → .tsx)
        corrected = _is_path_authorized(rel_path, cwd, allowlist)
        if not corrected:
            continue
        if corrected != clean_path:
            logger.info("  Correcting path {} → {}", clean_path, corrected)
            clean_path = corrected
            target = (cwd_path / clean_path).resolve()

        validated.append((target, clean_path, content))

    # Pre-write lint gate: reject Python files that can't even parse (SWE-agent pattern)
    # Catches syntax errors BEFORE writing to disk, saving a wasted round
    for target, clean_path, content in validated:
        if clean_path.endswith(".py"):
            try:
                compile(content, clean_path, "exec")
            except SyntaxError as e:
                logger.warning("  Pre-write lint REJECTED {}: {}", clean_path, e)
                return []  # Reject entire batch — partial writes are worse than none

    # Large file truncation guard: reject complete-file replacements that are
    # suspiciously smaller than the existing file (LLM output got truncated)
    for target, clean_path, content in validated:
        if target.exists():
            existing_lines = len(target.read_text(errors="replace").splitlines())
            new_lines = len(content.splitlines())
            if existing_lines > 500 and new_lines < existing_lines * 0.5:
                logger.warning(
                    "  REJECTED truncated replacement: {} has {} lines, "
                    "replacement has {} lines ({:.0f}% of original)",
                    clean_path, existing_lines, new_lines,
                    new_lines / existing_lines * 100)
                return []  # Reject entire batch

    # Atomic apply: write to temp files first, then move all into place
    temp_files: list[tuple[Path, Path]] = []  # (temp_path, final_path)
    try:
        for target, clean_path, content in validated:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
            os.write(fd, content.encode())
            os.close(fd)
            temp_files.append((Path(tmp), target))

        # All writes succeeded — move into place
        for tmp_path, final_path in temp_files:
            tmp_path.rename(final_path)
            rel = str(final_path.relative_to(cwd_path))
            written.append(rel)
            logger.info("  Wrote: {} ({} bytes)", rel, final_path.stat().st_size)

    except Exception as e:
        # Rollback: remove any temp files that weren't moved yet
        logger.error("Atomic write failed at {}: {} — rolling back", clean_path, e)
        for tmp_path, _ in temp_files:
            tmp_path.unlink(missing_ok=True)
        return []

    return written


# ── Hunk Review Integration ──────────────────────────────────────────


def generate_hunk_review(output_dir: Path, task_id: str, cwd: str,
                         rounds_history: list[dict], snapshot: str) -> None:
    """Generate a hunk-compatible review file with inline annotations from the self-improvement loop.

    Creates {output_dir}/{task_id}.hunk.md with:
    - Git diff of all changes since snapshot
    - Inline annotations: round scores, strategy, errors per hunk
    - Summary of the self-improvement trajectory

    Run: hunk patch {task_id}.hunk.md  OR  hunk diff (if changes are in working tree)
    """
    # Check if hunk is available
    hunk_available = subprocess.run(
        ["which", "hunk"], capture_output=True, text=True,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    ).returncode == 0

    # Generate git diff since snapshot
    diff_proc = subprocess.run(
        ["git", "diff", snapshot or "HEAD", "--", "."],
        capture_output=True, text=True, cwd=cwd, timeout=30,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
    )
    if diff_proc.returncode != 0 or not diff_proc.stdout.strip():
        return  # No changes to review

    diff_text = diff_proc.stdout

    # Build trajectory summary as annotation
    trajectory_lines = [f"# Code Runner Review: {task_id}", ""]
    trajectory_lines.append(f"**Rounds:** {len(rounds_history)}")
    if rounds_history:
        best = max(rounds_history, key=lambda r: r.get("score", 0))
        trajectory_lines.append(f"**Best score:** {best.get('score', 0):.3f} (round {best.get('round', '?')})")
        trajectory_lines.append(f"**DoD passed:** {best.get('dod_passed', False)}")
        trajectory_lines.append("")
        trajectory_lines.append("## Round Trajectory")
        trajectory_lines.append("| Round | Score | Strategy | Status | Errors |")
        trajectory_lines.append("|-------|-------|----------|--------|--------|")
        for r in rounds_history:
            trajectory_lines.append(
                f"| {r.get('round', '?')} | {r.get('score', 0):.3f} | "
                f"{r.get('strategy', '?')} | {r.get('status', '?')} | "
                f"{r.get('error_count', 0)} ({r.get('error_severity', '?')}) |"
            )

    # Raw diff without fences — hunk parses diff lines directly, fences cause parse warnings
    trajectory_lines.extend(["", diff_text.rstrip()])

    hunk_file = output_dir / f"{task_id}.hunk.md"
    hunk_file.write_text("\n".join(trajectory_lines))

    if hunk_available:
        logger.info("Review with: hunk patch {}", hunk_file)
        # Also hint that hunk diff works directly if changes are uncommitted
        logger.info("  Or: cd {} && hunk diff", cwd)
    else:
        logger.info("Review diff at: {}", hunk_file)


def build_file_context(allowlist: list[str] | None, cwd: str,
                       read_context: list[str] | None = None,
                       escalated_files: set[str] | None = None) -> str:
    """Read allowlisted + read_context files and include in prompt.

    Delegates to common.file_bundler.bundle_files() for the actual work.
    Staged context escalation (research-validated):
      - read_context files: interface map only (signatures + types + line numbers)
      - escalated_files: promoted to full content after failure referenced them
      - allowlist files: always full content (LLM needs to edit these)
    """
    import sys
    skills_dir = str(Path(__file__).resolve().parent.parent)
    if skills_dir not in sys.path:
        sys.path.insert(0, skills_dir)

    from common.file_bundler import bundle_files

    all_files = list(allowlist or []) + list(read_context or [])
    if not all_files:
        return ""

    return bundle_files(
        files=all_files,
        cwd=cwd,
        read_only=set(read_context or []),
        escalated=escalated_files,
    )
