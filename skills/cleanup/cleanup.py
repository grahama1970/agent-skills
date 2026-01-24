#!/usr/bin/env python3
"""
Cleanup Skill - Deep codebase assessment and technical debt cleanup.

This script performs a thorough assessment of the codebase to identify:
- Untracked "junk" files (logs, temp images, etc.)
- Tracked files that are no longer referenced
- Outdated documentation
- Project structure inconsistencies

The workflow:
1. Assessment (--dry-run): Scan and generate findings
2. Planning (--plan): Generate a Cleanup Plan markdown
3. Execution (--execute): Perform git operations (with confirmation)
4. Finalization: Record cleanup in local/CLEANUP_LOG.md
"""

import os
import subprocess
import json
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set, Tuple, Optional


# Patterns that typically indicate junk files
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
    """Print error message to stderr."""
    print(f"[ERROR] {message}", file=sys.stderr)


def log_warning(message: str) -> None:
    """Print warning message to stderr."""
    print(f"[WARNING] {message}", file=sys.stderr)


def log_info(message: str) -> None:
    """Print info message."""
    print(f"[INFO] {message}")


def run_command(cmd: List[str], check: bool = True) -> Tuple[bool, str]:
    """
    Run a shell command and return success status and output.
    
    Args:
        cmd: Command list to execute
        check: If True, raise exception on failure
        
    Returns:
        Tuple of (success, stdout)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stdout
    except FileNotFoundError as e:
        log_error(f"Command not found: {cmd[0]}")
        return False, ""
    except Exception as e:
        log_error(f"Unexpected error running command: {e}")
        return False, ""


def get_git_status() -> List[str]:
    """Get git status output as list of lines."""
    success, output = run_command(["git", "status", "--porcelain=v1"], check=False)
    if success:
        return output.strip().split("\n") if output.strip() else []
    log_warning("Could not get git status - not in a git repository?")
    return []


def get_untracked_files() -> List[str]:
    """Get list of untracked files (excluding ignored files)."""
    success, output = run_command(["git", "ls-files", "--others", "--exclude-standard"], check=False)
    if success:
        return output.strip().split("\n") if output.strip() else []
    log_warning("Could not get untracked files")
    return []


def get_all_tracked_files() -> Set[str]:
    """Get set of all tracked files in the repository."""
    success, output = run_command(["git", "ls-files"], check=False)
    if success:
        return set(output.strip().split("\n")) if output.strip() else set()
    log_warning("Could not get tracked files")
    return set()


def is_junk_file(filepath: str) -> bool:
    """Check if a file matches junk patterns."""
    filename = os.path.basename(filepath)
    for pattern in JUNK_PATTERNS:
        if pattern.startswith("*"):
            # Simple glob matching for * patterns
            suffix = pattern[1:]
            if filename.endswith(suffix):
                return True
        else:
            # Directory pattern
            if pattern in filepath.split(os.sep):
                return True
    return False


def read_file_content(filepath: str) -> str:
    """Read file content safely."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        log_warning(f"Could not read {filepath}: {e}")
        return ""


def find_file_references(filepath: str, search_paths: List[str]) -> List[str]:
    """
    Find files that reference the given filepath.
    
    Args:
        filepath: Path to search for references to
        search_paths: List of directories to search in
        
    Returns:
        List of files that reference the filepath
    """
    references = []
    filename = os.path.basename(filepath)
    stem = os.path.splitext(filename)[0]
    
    for search_path in search_paths:
        if not os.path.exists(search_path):
            continue
        
        for root, dirs, files in os.walk(search_path):
            # Skip certain directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            
            for file in files:
                if file.endswith((".md", ".py", ".ts", ".js", ".json", ".yaml", ".yml")):
                    full_path = os.path.join(root, file)
                    try:
                        content = read_file_content(full_path)
                        # Check for various reference patterns
                        if (filename in content or 
                            stem in content or 
                            filepath in content or
                            filepath.replace("/", ".") in content or
                            filepath.replace("/", "_") in content):
                            references.append(full_path)
                    except Exception:
                        continue
    
    return references


def scan_for_dead_files() -> List[Dict[str, str]]:
    """
    Scan for tracked files that appear to be dead/unreferenced.
    
    Returns:
        List of dicts with file info
    """
    dead_files = []
    tracked_files = get_all_tracked_files()
    
    # Get README content for quick check
    readme_content = ""
    if os.path.exists("README.md"):
        readme_content = read_file_content("README.md")
    
    # Directories to search for references
    search_dirs = [".", "src", "lib", "packages", "docs"]
    search_dirs = [d for d in search_dirs if os.path.exists(d)]
    
    for filepath in tracked_files:
        # Skip certain file types
        if filepath.endswith((".lock", ".gitignore", ".gitattributes")):
            continue
        
        # Skip files in SKILL.md directories (skills are self-contained)
        if ".pi/skills/" in filepath or ".kilocode/skills/" in filepath:
            continue
        
        # Check if file is in README
        if filepath in readme_content or os.path.basename(filepath) in readme_content:
            continue
        
        # Find references
        references = find_file_references(filepath, search_dirs)
        
        # If no references found, consider it potentially dead
        if not references:
            # Additional heuristics
            full_path = os.path.join(os.getcwd(), filepath)
            if not os.path.exists(full_path):
                # File doesn't exist on disk - definitely dead
                dead_files.append({
                    "path": filepath,
                    "status": "missing",
                    "reason": "Tracked but not found on disk"
                })
            else:
                # File exists but no references
                dead_files.append({
                    "path": filepath,
                    "status": "unreferenced",
                    "reason": "No references found in codebase"
                })
    
    return dead_files


def scan_for_outdated_docs() -> List[Dict[str, str]]:
    """
    Scan for potentially outdated documentation files.
    
    Returns:
        List of dicts with file info
    """
    outdated = []
    
    # Check for common outdated patterns
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        
        for file in files:
            if file.endswith(".md") and file != "README.md":
                filepath = os.path.join(root, file)
                content = read_file_content(filepath)
                
                # Check for TODO/FIXME that might indicate incomplete docs
                if "TODO" in content or "FIXME" in content:
                    outdated.append({
                        "path": filepath,
                        "status": "incomplete",
                        "reason": "Contains TODO/FIXME markers"
                    })
                
                # Check for very old files (no recent git activity)
                # This is a simple heuristic
                success, output = run_command(
                    ["git", "log", "-1", "--format=%ct", filepath],
                    check=False
                )
                if success and output.strip():
                    try:
                        timestamp = int(output.strip())
                        age_days = (datetime.now().timestamp() - timestamp) / 86400
                        if age_days > 365:  # More than a year old
                            outdated.append({
                                "path": filepath,
                                "status": "stale",
                                "reason": f"Not modified in {int(age_days)} days"
                            })
                    except (ValueError, TypeError):
                        pass
    
    return outdated


def generate_cleanup_plan(findings: Dict) -> str:
    """
    Generate a markdown cleanup plan from findings.
    
    Args:
        findings: Dictionary of assessment findings
        
    Returns:
        Markdown formatted cleanup plan
    """
    plan = []
    plan.append("# Cleanup Plan")
    plan.append("")
    plan.append(f"Generated: {datetime.now().isoformat()}")
    plan.append("")
    
    # Uncommitted changes
    if findings.get("uncommitted_changes"):
        plan.append("## Uncommitted Changes")
        plan.append("")
        plan.append("The following files have uncommitted changes:")
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
            plan.append("These files match junk patterns and can be safely removed:")
            plan.append("")
            for f in junk_files:
                plan.append(f"- `{f}`")
            plan.append("")
        
        if other_files:
            plan.append("### Other Untracked Files")
            plan.append("")
            plan.append("Review these files - they may be important:")
            plan.append("")
            for f in other_files:
                plan.append(f"- `{f}`")
            plan.append("")
    
    # Dead files
    if findings.get("dead_files"):
        plan.append("## Potentially Dead Files")
        plan.append("")
        plan.append("The following tracked files appear to be unreferenced:")
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
    plan.append(f"- Uncommitted changes: {len(findings.get('uncommitted_changes', []))}")
    plan.append(f"- Untracked files: {len(findings.get('untracked_files', []))}")
    plan.append(f"- Potentially dead files: {len(findings.get('dead_files', []))}")
    plan.append(f"- Potentially outdated docs: {len(findings.get('outdated_docs', []))}")
    plan.append("")
    
    return "\n".join(plan)


def log_cleanup(findings: Dict, actions_taken: List[str]) -> None:
    """
    Record cleanup actions to local/CLEANUP_LOG.md.
    
    Args:
        findings: Dictionary of assessment findings
        actions_taken: List of actions that were performed
    """
    log_dir = Path("local")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "CLEANUP_LOG.md"
    
    entry = []
    entry.append(f"## Cleanup: {datetime.now().isoformat()}")
    entry.append("")
    
    if findings.get("uncommitted_changes"):
        entry.append(f"### Uncommitted Changes ({len(findings['uncommitted_changes'])})")
        for change in findings["uncommitted_changes"]:
            entry.append(f"- {change}")
        entry.append("")
    
    if findings.get("untracked_files"):
        entry.append(f"### Untracked Files ({len(findings['untracked_files'])})")
        for f in findings["untracked_files"]:
            entry.append(f"- {f}")
        entry.append("")
    
    if actions_taken:
        entry.append("### Actions Taken")
        for action in actions_taken:
            entry.append(f"- {action}")
        entry.append("")
    
    entry.append("---")
    entry.append("")
    
    # Append to existing log or create new
    if log_file.exists():
        existing = log_file.read_text()
        log_file.write_text(existing + "\n".join(entry))
    else:
        log_file.write_text("# Cleanup Log\n\n" + "\n".join(entry))


def confirm_action(action: str) -> bool:
    """
    Ask user for confirmation before performing an action.
    
    Args:
        action: Description of the action to confirm
        
    Returns:
        True if user confirms, False otherwise
    """
    response = input(f"{action} [y/N]: ").strip().lower()
    return response in ("y", "yes")


def execute_cleanup(findings: Dict, force: bool = False) -> List[str]:
    """
    Execute cleanup actions based on findings.
    
    Args:
        findings: Dictionary of assessment findings
        force: If True, skip confirmation prompts
        
    Returns:
        List of actions taken
    """
    actions_taken = []
    
    # Handle untracked junk files
    untracked = findings.get("untracked_files", [])
    junk_files = [f for f in untracked if is_junk_file(f)]
    
    if junk_files:
        log_info(f"Found {len(junk_files)} junk files to clean")
        
        if not force:
            for f in junk_files:
                if not confirm_action(f"Remove junk file: {f}"):
                    log_warning(f"Skipping: {f}")
                    continue
        
        for f in junk_files:
            try:
                if os.path.isfile(f):
                    os.remove(f)
                    actions_taken.append(f"Removed file: {f}")
                    log_info(f"Removed: {f}")
                elif os.path.isdir(f):
                    import shutil
                    shutil.rmtree(f)
                    actions_taken.append(f"Removed directory: {f}")
                    log_info(f"Removed: {f}")
            except Exception as e:
                log_error(f"Failed to remove {f}: {e}")
    
    # Handle dead files - ALWAYS require confirmation, never auto-delete
    dead_files = findings.get("dead_files", [])
    if dead_files:
        log_warning(f"Found {len(dead_files)} potentially dead files")
        log_warning("These files require manual review before removal")
        
        for file_info in dead_files:
            filepath = file_info["path"]
            log_info(f"Dead file: {filepath} - {file_info['reason']}")
            
            # Always ask for confirmation, even with --force
            if confirm_action(f"Remove dead file: {filepath}?"):
                success, _ = run_command(["git", "rm", filepath], check=False)
                if success:
                    actions_taken.append(f"Removed from git: {filepath}")
                    log_info(f"Removed from git: {filepath}")
                else:
                    log_error(f"Failed to remove from git: {filepath}")
            else:
                log_warning(f"Skipping: {filepath}")
    
    # Git clean for other untracked files (interactive)
    other_untracked = [f for f in untracked if not is_junk_file(f)]
    if other_untracked:
        log_info(f"Found {len(other_untracked)} other untracked files")
        log_info("Review these files - use 'git clean -i' for interactive cleanup")
    
    return actions_taken


def main():
    parser = argparse.ArgumentParser(
        description="Cleanup Skill - Deep codebase assessment and technical debt cleanup"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print findings without making changes (JSON output)"
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Generate a Cleanup Plan markdown file"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform cleanup actions (with confirmation)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompts for junk files (dead files still require confirmation)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="CLEANUP_PLAN.md",
        help="Output file for plan (default: CLEANUP_PLAN.md)"
    )
    
    args = parser.parse_args()
    
    # Step 1: Assessment
    log_info("Starting assessment...")
    
    findings = {
        "uncommitted_changes": get_git_status(),
        "untracked_files": get_untracked_files(),
        "dead_files": scan_for_dead_files(),
        "outdated_docs": scan_for_outdated_docs(),
    }
    
    # Dry run mode - JSON output
    if args.dry_run:
        print(json.dumps(findings, indent=2))
        return
    
    # Plan mode - Generate markdown
    if args.plan:
        log_info("Generating cleanup plan...")
        plan = generate_cleanup_plan(findings)
        
        with open(args.output, "w") as f:
            f.write(plan)
        
        log_info(f"Cleanup plan written to: {args.output}")
        log_info(f"Review the plan and run with --execute when ready")
        return
    
    # Execute mode - Perform cleanup
    if args.execute:
        # Check for uncommitted changes first
        if findings["uncommitted_changes"]:
            log_warning("You have uncommitted changes!")
            log_warning("Please commit or stash them before running cleanup.")
            log_warning("Uncommitted changes:")
            for change in findings["uncommitted_changes"]:
                log_warning(f"  {change}")
            
            if not args.force:
                if not confirm_action("Continue anyway?"):
                    log_info("Cleanup aborted.")
                    return
        
        # Show summary
        log_info("=" * 50)
        log_info("Cleanup Summary")
        log_info("=" * 50)
        log_info(f"Uncommitted changes: {len(findings['uncommitted_changes'])}")
        log_info(f"Untracked files: {len(findings['untracked_files'])}")
        log_info(f"Potentially dead files: {len(findings['dead_files'])}")
        log_info(f"Potentially outdated docs: {len(findings['outdated_docs'])}")
        log_info("=" * 50)
        
        # Execute cleanup
        log_info("Starting cleanup...")
        actions_taken = execute_cleanup(findings, force=args.force)
        
        # Log cleanup
        if actions_taken:
            log_cleanup(findings, actions_taken)
            log_info(f"Cleanup logged to: local/CLEANUP_LOG.md")
        
        log_info(f"Cleanup complete. {len(actions_taken)} actions taken.")
        return
    
    # Default: Show summary
    log_info("=" * 50)
    log_info("Cleanup Assessment")
    log_info("=" * 50)
    log_info(f"Uncommitted changes: {len(findings['uncommitted_changes'])}")
    log_info(f"Untracked files: {len(findings['untracked_files'])}")
    log_info(f"Potentially dead files: {len(findings['dead_files'])}")
    log_info(f"Potentially outdated docs: {len(findings['outdated_docs'])}")
    log_info("=" * 50)
    log_info("")
    log_info("Use --dry-run for JSON output")
    log_info("Use --plan to generate a cleanup plan")
    log_info("Use --execute to perform cleanup (with confirmation)")


if __name__ == "__main__":
    main()
