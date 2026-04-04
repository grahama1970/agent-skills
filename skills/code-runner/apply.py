"""Apply LLM output to filesystem — structured edit ops, file blocks, diffs, hunk review.

v3 structured edit operations (preferred): JSON with create_file, replace_file, edit_lines,
insert_lines, delete_lines. No diff parsing needed. Schema-validated.

v2 hybrid format (fallback): JSON metadata + ### FILE: blocks with diff + complete file.
v1 legacy (fallback): ### FILE: blocks or raw diffs.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from loguru import logger

MAX_FILE_CONTENT_CHARS = 12000  # ~3K tokens per file, fits in most context windows

# Paths that should NEVER be overwritten by an LLM
DENYLIST = {".git", ".gitignore", ".env", "SKILL.md", "run.sh", "sanity.sh", "pyproject.toml", "package.json"}

# ── v3 Structured Edit Operations (extracted to edit_ops.py) ────────
from edit_ops import parse_edit_ops, apply_edit_ops as _apply_edit_ops_raw

# File extensions recognized in ### FILE: headers
_FILE_EXT_RE = r'(?:py|ts|tsx|js|jsx|sh|json|yaml|yml|toml|md|txt|cfg|lean|rs|go|c|h|cpp|hpp|java|rb|lua|zig|v)'


def parse_v2_response(response: str) -> tuple[dict | None, list[dict]]:
    """Parse v2 hybrid format: JSON header + --- + ### FILE: blocks with diff + complete file.

    Returns:
        (metadata, file_blocks) where metadata is the JSON header dict (or None),
        and file_blocks is [{path, diff, content}, ...] for each ### FILE: block.
        Both diff and content may be present — caller decides which to use.
    """
    metadata = None
    body = response

    # Split on first --- separator to extract JSON header
    header_match = re.match(r'^(.*?)\n---\n(.*)', response, re.DOTALL)
    if header_match:
        header_line = header_match.group(1).strip()
        body = header_match.group(2)
        # Parse JSON metadata (first line should be a JSON object)
        if header_line.startswith('{'):
            try:
                metadata = json.loads(header_line)
            except json.JSONDecodeError:
                # Try extracting JSON from the header (may have extra text)
                json_match = re.search(r'(\{[^}]+\})', header_line)
                if json_match:
                    try:
                        metadata = json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        pass

    # Parse ### FILE: blocks — each may contain ```diff and ```python/etc
    file_blocks: list[dict] = []
    sections = re.split(r'(?:^|\n)#{1,4}\s*FILE:\s*', body)

    for section in sections[1:]:  # skip text before first FILE header
        lines = section.split('\n', 1)
        path_line = lines[0].strip().strip('`"\'')
        path_match = re.match(rf'(\S+\.{_FILE_EXT_RE})', path_line)
        if not path_match:
            continue
        path = path_match.group(1)
        rest = lines[1] if len(lines) > 1 else ""

        block: dict = {"path": path, "diff": None, "content": None}

        # Extract ALL fenced code blocks from the section
        fences = list(re.finditer(r'```(\w*)\n(.*?)(?:\n```)', rest, re.DOTALL))
        for fence in fences:
            lang = fence.group(1).lower()
            code = fence.group(2)
            if lang == "diff" or code.lstrip().startswith(("diff --git", "--- a/")):
                block["diff"] = code
            elif lang in ("python", "typescript", "javascript", "sh", "bash", "json",
                          "yaml", "toml", "rust", "go", "c", "cpp", "java", "ruby",
                          "lua", "zig", "lean", "") and block["content"] is None:
                # Take the first non-diff code block as complete file content
                block["content"] = code

        # Only include if we got at least one of diff or content
        if block["diff"] or block["content"]:
            file_blocks.append(block)

    return metadata, file_blocks


def parse_file_blocks(response: str) -> list[tuple[str, str]]:
    """Parse file blocks from LLM response. Returns [(path, content), ...].

    Supports:
      1. v2 hybrid format (JSON header + --- + ### FILE: with diff + complete file)
      2. ### FILE: path/to/file.py then fenced code (v1 format)
      3. "create file X" / "write to X" hints paired with code blocks
      4. Single unnamed code block as fallback
    """
    blocks: list[tuple[str, str]] = []

    # Format 1: FILE header → optional whitespace/prose → fenced code block
    file_sections = re.split(r'(?:^|\n)#{1,4}\s*FILE:\s*', response)
    for section in file_sections[1:]:
        lines = section.split('\n', 1)
        path_line = lines[0].strip().strip('`"\'')
        path_match = re.match(rf'(\S+\.{_FILE_EXT_RE})', path_line)
        if not path_match:
            continue
        path = path_match.group(1)

        rest = lines[1] if len(lines) > 1 else ""
        # Find all non-diff code blocks, take the last one (complete file in v2 format)
        fences = list(re.finditer(r'```(\w*)\n(.*?)(?:\n```)', rest, re.DOTALL))
        for fence in reversed(fences):
            lang = fence.group(1).lower()
            code = fence.group(2)
            if lang != "diff" and not code.lstrip().startswith(("diff --git", "--- a/")):
                blocks.append((path, code))
                break

    if blocks:
        return blocks

    # Format 2: path hints from prose + code blocks
    path_hints = re.findall(
        r'(?:create|write|save|output|modify)\s+(?:the\s+)?(?:file\s+)?[`"\']?(\S+\.(?:py|ts|js|json|yaml))[`"\']?',
        response, re.IGNORECASE,
    )
    code_blocks = re.findall(r'```\w*\n(.*?)(?:\n```)', response, re.DOTALL)

    if path_hints and code_blocks:
        blocks.append((path_hints[0], code_blocks[0]))
    elif code_blocks and len(code_blocks) == 1:
        blocks.append(("__unnamed__", code_blocks[0]))

    return blocks


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


def _extract_diff_paths(diff_text: str) -> list[str]:
    """Extract file paths from a unified diff."""
    paths = re.findall(r'^diff --git a/(\S+)', diff_text, re.MULTILINE)
    if not paths:
        paths = re.findall(r'^\+\+\+ b/(\S+)', diff_text, re.MULTILINE)
    return paths


def _detect_and_apply_diff(response: str, cwd: str, allowlist: list[str] | None = None) -> list[str]:
    """Detect unified diff in response and apply via git apply. Returns files changed.

    Enforces allowlist + denylist on diff paths BEFORE applying (codex review fix #1).
    """
    # Look for diff content in code fences or raw
    diff_text = ""
    # Check for fenced diff
    fence_match = re.search(r'```(?:diff)?\n((?:diff --git|--- ).*?)```', response, re.DOTALL)
    if fence_match:
        diff_text = fence_match.group(1)
    elif re.search(r'^diff --git |^--- a/', response, re.MULTILINE):
        # Raw diff in response — extract from first diff marker to end or next prose
        diff_start = re.search(r'^(diff --git |--- a/)', response, re.MULTILINE)
        if diff_start:
            diff_text = response[diff_start.start():]
            # Trim trailing prose after the diff
            end_match = re.search(r'\n(?![-+ @\\]|diff )\S', diff_text)
            if end_match:
                diff_text = diff_text[:end_match.start()]

    if not diff_text.strip():
        return []

    # Validate diff paths against allowlist + denylist BEFORE applying
    diff_paths = _extract_diff_paths(diff_text)
    cwd_path = Path(cwd).resolve()
    for dp in diff_paths:
        # Denylist
        if any(dp == d or dp.startswith(d + "/") for d in DENYLIST):
            logger.warning("  Diff rejected: {} is denylisted", dp)
            return []
        # Path boundary
        target = (cwd_path / dp).resolve()
        try:
            target.relative_to(cwd_path)
        except ValueError:
            logger.warning("  Diff rejected: {} escapes cwd", dp)
            return []
        # Allowlist
        if allowlist is not None:
            matches = (
                dp in allowlist
                or any(dp.startswith(a.rstrip("/") + "/") for a in allowlist if a.endswith("/") or (cwd_path / a).is_dir())
            )
            if not matches:
                logger.warning("  Diff rejected: {} not in allowlist", dp)
                return []

    # Write diff to temp file and apply
    fd, diff_path = tempfile.mkstemp(suffix=".patch")
    os.write(fd, diff_text.encode())
    os.close(fd)
    diff_file = Path(diff_path)
    try:
        # Try with increasing fuzz levels to handle LLM-generated approximate diffs
        applied = False
        for strategy_args in [
            ["git", "apply", "--3way", str(diff_file)],
            ["git", "apply", "--fuzz=3", str(diff_file)],
            ["git", "apply", "--fuzz=5", "--reject", str(diff_file)],
        ]:
            proc = subprocess.run(strategy_args, capture_output=True, text=True, cwd=cwd, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if proc.returncode == 0:
                applied = True
                break
        if applied:
            logger.info("  Applied diff to {} files: {}", len(diff_paths), diff_paths)
            return diff_paths
        else:
            logger.warning("  git apply failed (all strategies): {}", proc.stderr[:300])
            return []
    finally:
        diff_file.unlink(missing_ok=True)


_DIFF_FAILED_LAST_ROUND = False
_LAST_METADATA: dict | None = None


def _apply_single_diff(diff_text: str, cwd: str) -> bool:
    """Try to apply a single diff block via git apply. Returns True on success."""
    fd, diff_path = tempfile.mkstemp(suffix=".patch")
    os.write(fd, diff_text.encode())
    os.close(fd)
    diff_file = Path(diff_path)
    try:
        for strategy_args in [
            ["git", "apply", "--3way", str(diff_file)],
            ["git", "apply", "--fuzz=3", str(diff_file)],
            ["git", "apply", "--fuzz=5", "--reject", str(diff_file)],
        ]:
            proc = subprocess.run(
                strategy_args, capture_output=True, text=True, cwd=cwd, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if proc.returncode == 0:
                return True
        return False
    finally:
        diff_file.unlink(missing_ok=True)


def apply_llm_response(response: str, cwd: str, allowlist: list[str] | None = None) -> list[str]:
    """Parse LLM response and apply to disk. Tries formats in order:

    v3 structured edit ops (preferred): JSON with create_file/replace_file/edit_lines
    v2 hybrid format (fallback): JSON metadata + ### FILE: blocks with diff + complete file
    v1 legacy (fallback): file blocks → unified diff

    Tracks diff failures so build_fix_prompt can request complete files next round.
    """
    global _DIFF_FAILED_LAST_ROUND, _LAST_METADATA

    # Try v3 structured edit ops first (no diff parsing needed)
    v3_data = parse_edit_ops(response)
    if v3_data and v3_data.get("operations"):
        _LAST_METADATA = {
            "summary": v3_data.get("summary", ""),
            "approach": v3_data.get("approach", ""),
            "files_changed": list({op["file"] for op in v3_data["operations"]}),
        }
        # Wire path authorization into edit_ops
        def _authz(path: str) -> str | None:
            return _is_path_authorized(path, cwd, allowlist)
        written = _apply_edit_ops_raw(v3_data, cwd, path_authorizer=_authz)
        if written:
            _DIFF_FAILED_LAST_ROUND = False
            logger.info("  v3: Applied {} edit ops to {} files",
                        len(v3_data["operations"]), len(written))
            return written
        # v3 parsed but ops failed to apply — fall through to v2

    # Try v2 hybrid format
    metadata, v2_blocks = parse_v2_response(response)
    if v2_blocks:
        _LAST_METADATA = metadata
        written: list[str] = []
        diff_failed_any = False

        for block in v2_blocks:
            path = block["path"]
            diff_text = block["diff"]
            content = block["content"]

            # Unified path authorization — may correct extension (.ts → .tsx)
            corrected = _is_path_authorized(path, cwd, allowlist)
            if not corrected:
                logger.warning("  v2: {} not authorized, skipping", path)
                continue
            if corrected != path:
                logger.info("  v2: Correcting path {} → {}", path, corrected)
                path = corrected

            applied = False

            # Strategy 1: try diff (cheap, preserves untouched lines)
            if diff_text:
                if _apply_single_diff(diff_text, cwd):
                    written.append(path)
                    applied = True
                    logger.info("  v2: Applied diff for {}", path)
                else:
                    diff_failed_any = True
                    logger.warning("  v2: Diff failed for {}, trying complete file", path)

            # Strategy 2: fall back to complete file (guaranteed correct)
            if not applied and content:
                fallback_blocks = [(path, content)]
                fb_written = apply_file_blocks(fallback_blocks, cwd, allowlist)
                if fb_written:
                    written.extend(fb_written)
                    applied = True

            # Strategy 3: extract + lines from diff as complete file
            # When diff fails and no complete file was provided, reconstruct
            # the target file from the diff's added lines. This handles the
            # common case where LLM replaces a small stub with a full file.
            if not applied and diff_text and not content:
                plus_lines = [
                    line[1:] for line in diff_text.splitlines()
                    if line.startswith("+") and not line.startswith("+++")
                ]
                if plus_lines:
                    reconstructed = "\n".join(plus_lines) + "\n"
                    logger.info("  v2: Reconstructing {} from {} diff + lines", path, len(plus_lines))
                    fallback_blocks = [(path, reconstructed)]
                    fb_written = apply_file_blocks(fallback_blocks, cwd, allowlist)
                    if fb_written:
                        written.extend(fb_written)
                        applied = True

            if not applied:
                logger.warning("  v2: Could not apply changes for {}", path)

        _DIFF_FAILED_LAST_ROUND = diff_failed_any
        if written:
            return written
        # If v2 parse found blocks but none applied, fall through to v1

    # v1 fallback: file blocks → unified diff → warn
    blocks = parse_file_blocks(response)
    if blocks and any(p != "__unnamed__" for p, _ in blocks):
        _DIFF_FAILED_LAST_ROUND = False
        _LAST_METADATA = metadata  # preserve any metadata found
        return apply_file_blocks(blocks, cwd, allowlist)

    diff_files = _detect_and_apply_diff(response, cwd, allowlist)
    if diff_files:
        _DIFF_FAILED_LAST_ROUND = False
        _LAST_METADATA = metadata
        return diff_files

    # Check if there was a diff that failed to apply
    if re.search(r'```diff|^diff --git|^--- a/', response, re.MULTILINE):
        _DIFF_FAILED_LAST_ROUND = True
        logger.warning("Diff detected but git apply failed — next round will request complete file")
    elif blocks:
        logger.warning("LLM returned code block but no file path — cannot apply")
    else:
        logger.warning("No file blocks or diffs found in LLM response")
    return []


def get_last_metadata() -> dict | None:
    """Get JSON metadata from the last parsed v2 response (summary, approach, files_changed)."""
    return _LAST_METADATA


def diff_failed_last_round() -> bool:
    """Check if the last apply attempt had a diff that couldn't be applied."""
    return _DIFF_FAILED_LAST_ROUND


# ── Zero-Write Diagnostics ──────────────────────────────────────────


def diagnose_zero_writes(response: str, cwd: str, allowlist: list[str] | None) -> dict:
    """Diagnose why apply_llm_response wrote zero files. Returns structured trace.

    Checks each stage of the parsing pipeline and reports the first failure point.
    Saved to round_N_zero_write_diagnosis.json for project agent debugging.

    Possible reasons:
      empty_response     — LLM returned nothing (scillm failure)
      llm_error          — LLM returned an error string
      allowlist_blocked  — file paths not in allowlist
      empty_block        — ### FILE: block had neither diff nor content
      apply_failed       — diff failed + complete file had syntax error
      unnamed_code_block — code block but no ### FILE: header
      missing_file_header — code fences but no file path
      no_code_in_response — LLM returned prose instead of code
      parse_failure      — has code + headers but parser couldn't extract
    """
    diag: dict = {"reason": "unknown", "details": [], "response_length": len(response)}

    if not response or not response.strip():
        diag["reason"] = "empty_response"
        diag["details"].append("LLM returned empty response — scillm may have failed")
        return diag

    if response.startswith("ERROR:"):
        diag["reason"] = "llm_error"
        diag["details"].append(f"LLM returned error: {response[:200]}")
        return diag

    # v2 format
    metadata, v2_blocks = parse_v2_response(response)
    diag["v2_metadata"] = metadata is not None
    diag["v2_blocks_found"] = len(v2_blocks)

    if v2_blocks:
        for block in v2_blocks:
            path = block["path"]
            has_diff = block["diff"] is not None
            has_content = block["content"] is not None

            if not _is_path_authorized(path, cwd, allowlist):
                diag["details"].append(f"BLOCKED by allowlist: {path} (allowlist={allowlist})")
                diag["reason"] = "allowlist_blocked"
            elif not has_diff and not has_content:
                diag["details"].append(f"Block for {path} has neither diff nor content")
                diag["reason"] = "empty_block"
            else:
                diag["details"].append(
                    f"Block for {path}: diff={'yes' if has_diff else 'no'}, "
                    f"content={'yes' if has_content else 'no'} — "
                    f"diff failed to apply AND/OR complete file had syntax error")
                diag["reason"] = "apply_failed"
        return diag

    # v1 format
    v1_blocks = parse_file_blocks(response)
    diag["v1_blocks_found"] = len(v1_blocks)

    if v1_blocks:
        named = [(p, c) for p, c in v1_blocks if p != "__unnamed__"]
        unnamed = [(p, c) for p, c in v1_blocks if p == "__unnamed__"]
        if not named and unnamed:
            diag["reason"] = "unnamed_code_block"
            diag["details"].append(
                f"LLM returned {len(unnamed)} code block(s) but no ### FILE: header")
        elif named:
            for path, _ in named:
                if not _is_path_authorized(path, cwd, allowlist):
                    diag["details"].append(f"v1 BLOCKED by allowlist: {path}")
                    diag["reason"] = "allowlist_blocked"
        return diag

    # No parseable blocks
    has_fence = "```" in response
    has_header = "### FILE:" in response or "## FILE:" in response

    if has_fence and not has_header:
        diag["reason"] = "missing_file_header"
        diag["details"].append("Code fences found but no ### FILE: header — LLM didn't follow format")
    elif not has_fence:
        diag["reason"] = "no_code_in_response"
        diag["details"].append("No code fences — LLM returned prose instead of code")
        diag["details"].append(f"First 200 chars: {response[:200]}")
    else:
        diag["reason"] = "parse_failure"
        diag["details"].append("Has code fences + file headers but parser couldn't extract them")

    return diag


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
