#!/usr/bin/env python3
"""
Cleanup Skill - Deep codebase assessment and technical debt cleanup.

This script performs a thorough assessment of the codebase to identify:
- Untracked "junk" files (logs, temp images, etc.)
- Large binary/media artifacts that should be archived
- Tracked files that are no longer referenced
- Outdated documentation
- Project structure inconsistencies

The workflow:
1. Assessment (--dry-run): Scan and generate findings
2. Planning (--plan): Generate a Cleanup Plan markdown
3. Execution (--execute): Perform cleanup (archive or remove, with confirmation)
4. Finalization: Record cleanup in local/CLEANUP_LOG.md
"""

import fnmatch
import os
import shutil
import subprocess
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set, Tuple, Optional

import typer


# ── Archive destination (12TB storage) ──────────────────────────────────────
ARCHIVE_ROOT = Path(os.getenv(
    "CLEANUP_ARCHIVE_ROOT",
    "/mnt/storage12tb/artifacts",
))

# Patterns that typically indicate junk files (safe to delete)
JUNK_PATTERNS = [
    "*.log",
    "*.tmp",
    "*~",
    ".DS_Store",
    "Thumbs.db",
    "*.swp",
    "*.swo",
    "*.pyc",
    "__pycache__",
    "*.pyo",
    "*.pyd",
    ".pytest_cache",
    ".mypy_cache",
    "*.egg-info",
    ".coverage",
    "htmlcov",
    "*.bak",
    "*.orig",
]

# Large binary / media artifacts — archive, don't just delete
ARTIFACT_EXTENSIONS = {
    # Audio
    ".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus",
    # Video
    ".mp4", ".avi", ".mkv", ".mov", ".webm", ".wmv", ".flv",
    # Model weights / checkpoints
    ".bin", ".pt", ".pth", ".ckpt", ".safetensors", ".gguf", ".onnx",
    # Archives
    ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".zip", ".7z", ".rar",
    # Data
    ".parquet", ".arrow", ".h5", ".hdf5", ".npy", ".npz",
    # Images (large batches at root are usually artifacts)
    ".tif", ".tiff", ".bmp", ".raw",
}

# Size threshold: files larger than this in root are suspect (bytes)
ROOT_SIZE_THRESHOLD = 50 * 1024  # 50 KB

# Directories to skip during scanning
SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    ".cache",
}

def log_error(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)


def log_warning(message: str) -> None:
    print(f"[WARNING] {message}", file=sys.stderr)


def log_info(message: str) -> None:
    print(f"[INFO] {message}")


def run_command(cmd: List[str], check: bool = True) -> Tuple[bool, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stdout
    except FileNotFoundError:
        log_error(f"Command not found: {cmd[0]}")
        return False, ""
    except Exception as e:
        log_error(f"Unexpected error running command: {e}")
        return False, ""


def get_expected_root_dirs() -> Set[str]:
    """Auto-detect expected root dirs from git-tracked top-level directories."""
    success, output = run_command(["git", "ls-files"], check=False)
    tracked_tops = set()
    if success and output.strip():
        for f in output.strip().split("\n"):
            if "/" in f:
                tracked_tops.add(f.split("/")[0])
    # Add universal dotdir expectations
    tracked_tops |= {
        ".git", ".github", ".venv", ".claude", ".pi", ".codex",
        ".gemini", ".kilocode", ".agent",
    }
    return tracked_tops


def get_git_status() -> List[str]:
    success, output = run_command(["git", "status", "--porcelain=v1"], check=False)
    if success:
        return output.strip().split("\n") if output.strip() else []
    log_warning("Could not get git status - not in a git repository?")
    return []


def get_untracked_files() -> List[str]:
    success, output = run_command(["git", "ls-files", "--others", "--exclude-standard"], check=False)
    if success:
        return output.strip().split("\n") if output.strip() else []
    log_warning("Could not get untracked files")
    return []


def get_all_tracked_files() -> Set[str]:
    success, output = run_command(["git", "ls-files"], check=False)
    if success:
        return set(output.strip().split("\n")) if output.strip() else set()
    log_warning("Could not get tracked files")
    return set()


def is_junk_file(filepath: str) -> bool:
    """Check if a file matches junk patterns."""
    filename = os.path.basename(filepath)
    parts = Path(filepath).parts
    for pattern in JUNK_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return True
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
    return False


def is_artifact_file(filepath: str) -> bool:
    """Check if a file is a large binary/media artifact that should be archived."""
    ext = Path(filepath).suffix.lower()
    return ext in ARTIFACT_EXTENSIONS


def get_file_size(filepath: str) -> int:
    """Get file size in bytes, 0 if not found."""
    try:
        return os.path.getsize(filepath)
    except OSError:
        return 0


def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f}{unit}"
        nbytes /= 1024
    return f"{nbytes:.1f}TB"


EXPECTED_ROOT_FILES = {
    "README.md", "LICENSE", "LICENSE.md", "CHANGELOG.md",
    "pyproject.toml", "setup.py", "setup.cfg", "uv.lock", "poetry.lock",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
    "Makefile", "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".gitignore", ".gitattributes", ".editorconfig", ".prettierrc",
    ".env.example", ".env.template",
    "AGENTS.md", "CLAUDE.md", "CODEX.md",
    "conftest.py", "pytest.ini", "tox.ini", "mypy.ini",
    "tsconfig.json", "vite.config.ts", "vitest.config.ts",
    "requirements.txt", "requirements-dev.txt",
}


def scan_root_strays() -> List[Dict[str, str]]:
    """
    Find files/dirs at project root that don't belong.

    Checks BOTH untracked AND tracked files. Flags:
    - Binary/media artifacts (any size)
    - Large files (>50KB) that aren't code
    - Directories not in expected root dirs
    - Tracked root files that aren't project infrastructure (e.g. task plans,
      scratch files, logs, .env secrets)
    """
    strays = []

    # ── Untracked root entries ──────────────────────────────────────────
    untracked = get_untracked_files()
    root_entries: Dict[str, List[str]] = {}
    for f in untracked:
        top = f.split("/")[0]
        root_entries.setdefault(top, []).append(f)

    for top, files in root_entries.items():
        full = Path(top)

        # Root-level artifact files
        if full.is_file() and is_artifact_file(top):
            sz = get_file_size(top)
            strays.append({
                "path": top,
                "status": "artifact",
                "size": sz,
                "reason": f"Binary/media artifact at root ({_human_size(sz)})",
                "action": "archive",
            })
        # Root-level large files
        elif full.is_file() and not is_junk_file(top):
            sz = get_file_size(top)
            if sz > ROOT_SIZE_THRESHOLD:
                strays.append({
                    "path": top,
                    "status": "large_root_file",
                    "size": sz,
                    "reason": f"Large file at root ({_human_size(sz)})",
                    "action": "review",
                })
        # Root-level directories that aren't expected
        elif full.is_dir() and top not in get_expected_root_dirs():
            total = sum(get_file_size(f) for f in files)
            strays.append({
                "path": top + "/",
                "status": "stray_dir",
                "size": total,
                "reason": f"Untracked directory at root ({_human_size(total)}, {len(files)} files)",
                "action": "archive",
            })

    # ── Tracked root-level files that aren't infrastructure ─────────────
    tracked = get_all_tracked_files()
    already_flagged = {s["path"] for s in strays}
    for filepath in sorted(tracked):
        if "/" in filepath:
            continue  # not root-level
        if filepath in already_flagged:
            continue
        if filepath in EXPECTED_ROOT_FILES:
            continue
        if filepath.startswith("."):
            # .env is a security concern — flag it specifically
            if filepath == ".env":
                strays.append({
                    "path": filepath,
                    "status": "tracked_secret",
                    "size": get_file_size(filepath),
                    "reason": "Secrets file tracked in git — should be .gitignored",
                    "action": "untrack",
                })
            continue  # other dotfiles are usually fine
        sz = get_file_size(filepath)
        strays.append({
            "path": filepath,
            "status": "tracked_root_stray",
            "size": sz,
            "reason": f"Tracked file at root that isn't project infrastructure ({_human_size(sz)})",
            "action": "review",
        })

    return strays


def get_project_name() -> str:
    """Derive project name from git remote or cwd."""
    success, output = run_command(["git", "remote", "get-url", "origin"], check=False)
    if success and output.strip():
        # Extract repo name from URL
        url = output.strip().rstrip("/")
        name = url.split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name
    return Path.cwd().name


def archive_file(filepath: str, project: str) -> str:
    """
    Move a file or directory to the archive drive.

    Returns the archive destination path.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    dest_dir = ARCHIVE_ROOT / project / today
    dest_dir.mkdir(parents=True, exist_ok=True)

    src = Path(filepath)
    dest = dest_dir / src.name

    # Avoid overwriting
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.move(str(src), str(dest))
    return str(dest)


def read_file_content(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        log_warning(f"Could not read {filepath}: {e}")
        return ""


def find_file_references(filepath: str, search_paths: List[str]) -> List[str]:
    references = []
    filename = os.path.basename(filepath)
    stem = os.path.splitext(filename)[0]

    for search_path in search_paths:
        if not os.path.exists(search_path):
            continue

        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for file in files:
                if file.endswith((".md", ".py", ".ts", ".js", ".json", ".yaml", ".yml")):
                    full_path = os.path.join(root, file)
                    try:
                        content = read_file_content(full_path)
                        if (filename in content or
                            stem in content or
                            filepath in content or
                            filepath.replace("/", ".") in content or
                            filepath.replace("/", "_") in content):
                            references.append(full_path)
                    except Exception:
                        continue

    return references


def build_reference_index(search_dirs: List[str]) -> Dict[str, Set[str]]:
    """Walk codebase once, return {term: set_of_files_containing_it}."""
    index: Dict[str, Set[str]] = {}
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            continue
        for root, dirs, files in os.walk(search_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for file in files:
                if not file.endswith((".md", ".py", ".ts", ".js", ".json", ".yaml", ".yml")):
                    continue
                full_path = os.path.join(root, file)
                content = read_file_content(full_path)
                if not content:
                    continue
                # Index all words/identifiers that appear
                for term in set(content.split()):
                    index.setdefault(term, set()).add(full_path)
                # Also index the content itself for substring checks
                index.setdefault(full_path, set()).add("__self__")
    return index


def scan_for_dead_files() -> List[Dict[str, str]]:
    dead_files = []
    tracked_files = get_all_tracked_files()

    readme_content = ""
    if os.path.exists("README.md"):
        readme_content = read_file_content("README.md")

    search_dirs = [".", "src", "lib", "packages", "docs"]
    search_dirs = [d for d in search_dirs if os.path.exists(d)]

    # Build index once
    log_info("Building reference index...")
    index = build_reference_index(search_dirs)

    for filepath in tracked_files:
        if filepath.endswith((".lock", ".gitignore", ".gitattributes")):
            continue
        if ".pi/skills/" in filepath or ".kilocode/skills/" in filepath:
            continue

        filename = os.path.basename(filepath)

        # Check README directly
        if filepath in readme_content or filename in readme_content:
            continue

        # Check index for filename or filepath references
        found = False
        if filename in index or filepath in index:
            found = True
        if not found:
            # Check filepath with different separators
            for variant in [filepath, filepath.replace("/", "."), filepath.replace("/", "_")]:
                if variant in index:
                    found = True
                    break

        if not found:
            full_path = os.path.join(os.getcwd(), filepath)
            if not os.path.exists(full_path):
                dead_files.append({
                    "path": filepath,
                    "status": "missing",
                    "reason": "Tracked but not found on disk"
                })
            else:
                dead_files.append({
                    "path": filepath,
                    "status": "unreferenced",
                    "reason": "No references found in codebase"
                })

    return dead_files


def scan_for_outdated_docs() -> List[Dict[str, str]]:
    outdated = []

    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in files:
            if file.endswith(".md") and file != "README.md":
                filepath = os.path.join(root, file)
                content = read_file_content(filepath)

                if "TODO" in content or "FIXME" in content:
                    outdated.append({
                        "path": filepath,
                        "status": "incomplete",
                        "reason": "Contains TODO/FIXME markers"
                    })

                success, output = run_command(
                    ["git", "log", "-1", "--format=%ct", filepath],
                    check=False
                )
                if success and output.strip():
                    try:
                        timestamp = int(output.strip())
                        age_days = (datetime.now().timestamp() - timestamp) / 86400
                        if age_days > 365:
                            outdated.append({
                                "path": filepath,
                                "status": "stale",
                                "reason": f"Not modified in {int(age_days)} days"
                            })
                    except (ValueError, TypeError):
                        pass

    return outdated


def generate_cleanup_plan(findings: Dict) -> str:
    plan = []
    plan.append("# Cleanup Plan")
    plan.append("")
    plan.append(f"Generated: {datetime.now().isoformat()}")
    plan.append(f"Archive root: `{ARCHIVE_ROOT}`")
    plan.append("")

    # Root strays (artifacts)
    if findings.get("root_strays"):
        plan.append("## Root-Level Strays (Archive to 12TB)")
        plan.append("")
        plan.append("These files/dirs don't belong at project root and should be archived:")
        plan.append("")
        for s in findings["root_strays"]:
            plan.append(f"- `{s['path']}` — {s['reason']} → **{s['action']}**")
        plan.append("")

    # Uncommitted changes
    if findings.get("uncommitted_changes"):
        plan.append("## Uncommitted Changes")
        plan.append("")
        for change in findings["uncommitted_changes"]:
            plan.append(f"- `{change}`")
        plan.append("")
        plan.append("**Action Required**: Review and commit or stash these changes.")
        plan.append("")

    # Untracked files
    if findings.get("untracked_files"):
        plan.append("## Untracked Files")
        plan.append("")

        junk_files = [f for f in findings["untracked_files"] if is_junk_file(f)]
        other_files = [f for f in findings["untracked_files"] if not is_junk_file(f)]

        if junk_files:
            plan.append("### Junk Files (Safe to Remove)")
            plan.append("")
            for f in junk_files:
                plan.append(f"- `{f}`")
            plan.append("")

        if other_files:
            plan.append("### Other Untracked Files")
            plan.append("")
            for f in other_files:
                plan.append(f"- `{f}`")
            plan.append("")

    # Dead files
    if findings.get("dead_files"):
        plan.append("## Potentially Dead Files")
        plan.append("")
        for file_info in findings["dead_files"]:
            plan.append(f"- `{file_info['path']}` - {file_info['status']}: {file_info['reason']}")
        plan.append("")
        plan.append("**WARNING**: Review carefully before removing these files.")
        plan.append("")

    # Outdated docs
    if findings.get("outdated_docs"):
        plan.append("## Potentially Outdated Documentation")
        plan.append("")
        for file_info in findings["outdated_docs"]:
            plan.append(f"- `{file_info['path']}` - {file_info['status']}: {file_info['reason']}")
        plan.append("")

    # Summary
    plan.append("## Summary")
    plan.append("")
    plan.append(f"- Root strays to archive: {len(findings.get('root_strays', []))}")
    plan.append(f"- Uncommitted changes: {len(findings.get('uncommitted_changes', []))}")
    plan.append(f"- Untracked files: {len(findings.get('untracked_files', []))}")
    plan.append(f"- Potentially dead files: {len(findings.get('dead_files', []))}")
    plan.append(f"- Potentially outdated docs: {len(findings.get('outdated_docs', []))}")
    plan.append("")

    return "\n".join(plan)


def log_cleanup(findings: Dict, actions_taken: List[str]) -> None:
    log_dir = Path("local")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "CLEANUP_LOG.md"

    entry = []
    entry.append(f"## Cleanup: {datetime.now().isoformat()}")
    entry.append("")

    if findings.get("root_strays"):
        entry.append(f"### Root Strays ({len(findings['root_strays'])})")
        for s in findings["root_strays"]:
            entry.append(f"- {s['path']} ({s['reason']})")
        entry.append("")

    if findings.get("uncommitted_changes"):
        entry.append(f"### Uncommitted Changes ({len(findings['uncommitted_changes'])})")
        for change in findings["uncommitted_changes"]:
            entry.append(f"- {change}")
        entry.append("")

    if actions_taken:
        entry.append("### Actions Taken")
        for action in actions_taken:
            entry.append(f"- {action}")
        entry.append("")

    entry.append("---")
    entry.append("")

    if not log_file.exists():
        log_file.write_text("# Cleanup Log\n\n")
    with log_file.open("a") as f:
        f.write("\n".join(entry))


def confirm_action(action: str) -> bool:
    response = input(f"{action} [y/N]: ").strip().lower()
    return response in ("y", "yes")


def execute_cleanup(findings: Dict, force: bool = False) -> List[str]:
    actions_taken = []
    project = get_project_name()

    # ── 1. Archive root strays ───────────────────────────────────────────
    strays = findings.get("root_strays", [])
    archivable = [s for s in strays if s.get("action") == "archive"]
    if archivable:
        if not ARCHIVE_ROOT.exists():
            log_error(f"Archive root {ARCHIVE_ROOT} does not exist. Mount the drive first.")
        else:
            log_info(f"Found {len(archivable)} items to archive → {ARCHIVE_ROOT}/{project}/")
            for s in archivable:
                path = s["path"].rstrip("/")
                if not os.path.exists(path):
                    continue
                if force or confirm_action(f"Archive {path} ({s['reason']}) to 12TB?"):
                    try:
                        dest = archive_file(path, project)
                        actions_taken.append(f"Archived: {path} → {dest}")
                        log_info(f"Archived: {path} → {dest}")
                    except Exception as e:
                        log_error(f"Failed to archive {path}: {e}")

    # ── 2. Remove junk files ─────────────────────────────────────────────
    untracked = findings.get("untracked_files", [])
    junk_files = [f for f in untracked if is_junk_file(f)]

    if junk_files:
        log_info(f"Found {len(junk_files)} junk files to clean")

        for f in junk_files:
            if not force and not confirm_action(f"Remove junk file: {f}"):
                log_warning(f"Skipping: {f}")
                continue
            try:
                if os.path.isfile(f):
                    os.remove(f)
                    actions_taken.append(f"Removed file: {f}")
                    log_info(f"Removed: {f}")
                elif os.path.isdir(f):
                    shutil.rmtree(f)
                    actions_taken.append(f"Removed directory: {f}")
                    log_info(f"Removed: {f}")
            except Exception as e:
                log_error(f"Failed to remove {f}: {e}")

    # ── 3. Dead files (always require confirmation) ──────────────────────
    dead_files = findings.get("dead_files", [])
    if dead_files:
        log_warning(f"Found {len(dead_files)} potentially dead files")
        log_warning("These files require manual review before removal")

        for file_info in dead_files:
            filepath = file_info["path"]
            log_info(f"Dead file: {filepath} - {file_info['reason']}")

            if confirm_action(f"Remove dead file: {filepath}?"):
                success, _ = run_command(["git", "rm", filepath], check=False)
                if success:
                    actions_taken.append(f"Removed from git: {filepath}")
                    log_info(f"Removed from git: {filepath}")
                else:
                    log_error(f"Failed to remove from git: {filepath}")
            else:
                log_warning(f"Skipping: {filepath}")

    # ── 4. Remaining untracked ───────────────────────────────────────────
    other_untracked = [f for f in untracked if not is_junk_file(f)]
    if other_untracked:
        log_info(f"Found {len(other_untracked)} other untracked files")
        log_info("Review these files - use 'git clean -i' for interactive cleanup")

    return actions_taken


app = typer.Typer(help="Cleanup Skill - Deep codebase assessment and technical debt cleanup")


@app.command()
def main(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print findings without making changes (JSON output)"),
    plan: bool = typer.Option(False, "--plan", help="Generate a Cleanup Plan markdown file"),
    execute: bool = typer.Option(False, "--execute", help="Perform cleanup actions (with confirmation)"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompts for junk/archive (dead files still require confirmation)"),
    output: str = typer.Option("CLEANUP_PLAN.md", "--output", help="Output file for plan"),
    archive_root: Optional[str] = typer.Option(None, "--archive-root", help="Override archive destination path"),
) -> None:
    """Deep codebase assessment and technical debt cleanup."""
    global ARCHIVE_ROOT
    if archive_root:
        ARCHIVE_ROOT = Path(archive_root)

    log_info("Starting assessment...")

    findings = {
        "root_strays": scan_root_strays(),
        "uncommitted_changes": get_git_status(),
        "untracked_files": get_untracked_files(),
        "dead_files": scan_for_dead_files(),
        "outdated_docs": scan_for_outdated_docs(),
    }

    if dry_run:
        print(json.dumps(findings, indent=2, default=str))
        return

    if plan:
        log_info("Generating cleanup plan...")
        cleanup_plan = generate_cleanup_plan(findings)

        with open(output, "w") as f:
            f.write(cleanup_plan)

        log_info(f"Cleanup plan written to: {output}")
        log_info("Review the plan and run with --execute when ready")
        return

    if execute:
        if findings["uncommitted_changes"]:
            log_warning("You have uncommitted changes!")
            for change in findings["uncommitted_changes"]:
                log_warning(f"  {change}")

            if not force:
                if not confirm_action("Continue anyway?"):
                    log_info("Cleanup aborted.")
                    return

        log_info("=" * 50)
        log_info("Cleanup Summary")
        log_info("=" * 50)
        log_info(f"Root strays to archive:    {len(findings['root_strays'])}")
        log_info(f"Uncommitted changes:       {len(findings['uncommitted_changes'])}")
        log_info(f"Untracked files:           {len(findings['untracked_files'])}")
        log_info(f"Potentially dead files:    {len(findings['dead_files'])}")
        log_info(f"Potentially outdated docs: {len(findings['outdated_docs'])}")
        log_info("=" * 50)

        log_info("Starting cleanup...")
        actions_taken = execute_cleanup(findings, force=force)

        if actions_taken:
            log_cleanup(findings, actions_taken)
            log_info("Cleanup logged to: local/CLEANUP_LOG.md")

        log_info(f"Cleanup complete. {len(actions_taken)} actions taken.")
        return

    # Default: Show summary
    log_info("=" * 50)
    log_info("Cleanup Assessment")
    log_info("=" * 50)
    log_info(f"Root strays to archive:    {len(findings['root_strays'])}")
    log_info(f"Uncommitted changes:       {len(findings['uncommitted_changes'])}")
    log_info(f"Untracked files:           {len(findings['untracked_files'])}")
    log_info(f"Potentially dead files:    {len(findings['dead_files'])}")
    log_info(f"Potentially outdated docs: {len(findings['outdated_docs'])}")
    log_info("=" * 50)
    log_info("")
    log_info("Use --dry-run for JSON output")
    log_info("Use --plan to generate a cleanup plan")
    log_info("Use --execute to perform cleanup (with confirmation)")
    log_info("Use --execute --force to auto-archive artifacts")


if __name__ == "__main__":
    app()
