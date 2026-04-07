"""
Detection and scanning utilities for create-context.

All detect_* functions gather information from the environment (git, filesystem,
processes, logs) to populate ContextData for CONTEXT.md generation.
"""

import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from loguru import logger


def run_command(
    cmd: list[str], timeout: int = 30, cwd: str | None = None, project_root: Path | None = None
) -> str:
    """Run a shell command and return output.

    Args:
        cmd: Command and arguments to run.
        timeout: Max seconds to wait.
        cwd: Explicit working directory (takes precedence over project_root).
        project_root: Fallback working directory if cwd is not provided.
    """
    try:
        effective_cwd = cwd or (str(project_root) if project_root else None)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=effective_cwd,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception as e:
        logger.debug("detector failed: {}", e)
        return ""


def detect_git_info(project_root: Path) -> tuple[str, str, str, str]:
    """Detect git branch, status, diff, and recent commits."""
    cwd = str(project_root)
    branch = run_command(["git", "branch", "--show-current"], cwd=cwd)
    status = run_command(["git", "status", "--short"], cwd=cwd)
    diff_stat = run_command(["git", "diff", "--stat", "HEAD~5"], cwd=cwd)
    commits = run_command(["git", "log", "--oneline", "-10"], cwd=cwd)
    return branch, status, diff_stat, commits


def detect_modified_files(project_root: Path) -> list[str]:
    """Get list of modified files from git status."""
    status = run_command(["git", "status", "--porcelain"], cwd=str(project_root))
    files = []
    for line in status.split("\n"):
        if line.strip():
            # Parse git status format: "XY filename"
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                files.append(parts[1].strip())
    return files


def detect_key_code_snippets(project_root: Path) -> list[dict]:
    """Find code marked with special comments for context."""
    snippets = []
    # Look for CONTEXT:, KEY:, IMPORTANT: markers in recent changes
    markers = ["# CONTEXT:", "# KEY:", "# IMPORTANT:", "// CONTEXT:", "// KEY:"]

    for marker in markers:
        result = run_command(
            ["git", "diff", "HEAD~5", "-U3", f"-G{marker}"], cwd=str(project_root)
        )
        if result:
            # Parse diff to extract snippets
            current_file = ""
            for line in result.split("\n"):
                if line.startswith("+++ b/"):
                    current_file = line[6:]
                elif marker in line and line.startswith("+"):
                    snippets.append({
                        "file": current_file,
                        "marker": marker.strip("# /"),
                        "content": line[1:].strip(),
                    })

    return snippets[:10]  # Limit to 10


def detect_test_coverage(project_root: Path) -> dict:
    """Run tests and capture coverage summary."""
    coverage = {"passed": 0, "failed": 0, "skipped": 0, "coverage_pct": None, "details": ""}

    # Try pytest collect (fast, just lists tests)
    result = run_command(["pytest", "--collect-only", "-q"], timeout=15, cwd=str(project_root))
    if result:
        # Count test items
        lines = [line for line in result.split("\n") if line.strip() and "::" in line]
        coverage["details"] = f"{len(lines)} tests collected"

    # Check for sanity.sh in skill directories (only first 10, with short timeout)
    sanity_results = []
    skills_dir = project_root / ".pi" / "skills"
    if skills_dir.exists():
        skill_dirs = sorted(skills_dir.iterdir())[:10]  # Limit to 10
        for skill_dir in skill_dirs:
            if not skill_dir.is_dir():
                continue
            sanity_sh = skill_dir / "sanity.sh"
            if sanity_sh.exists():
                result = run_command([str(sanity_sh)], timeout=10)
                status = "pass" if result else "fail"
                sanity_results.append(f"{skill_dir.name}: {status}")

    if sanity_results:
        coverage["sanity_checks"] = sanity_results

    return coverage


def detect_dependency_graph(project_root: Path) -> list[dict]:
    """Parse SKILL.md files to build dependency graph."""
    dependencies = []
    skills_dir = project_root / ".pi" / "skills"

    if not skills_dir.exists():
        return dependencies

    for skill_dir in skills_dir.iterdir():
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            try:
                content = skill_md.read_text()
                skill_name = skill_dir.name

                # Parse allowed-tools from frontmatter
                if "allowed-tools:" in content:
                    for line in content.split("\n"):
                        if line.strip().startswith("allowed-tools:"):
                            tools = line.split(":", 1)[1].strip()
                            tools = tools.strip("[]").replace(" ", "").split(",")
                            for tool in tools:
                                if tool and tool not in ["Bash", "Read", "Write", "Grep", "Glob", "Task"]:
                                    dependencies.append({
                                        "skill": skill_name,
                                        "depends_on": tool,
                                        "type": "tool",
                                    })

                # Look for skill references like /skill-name
                refs = re.findall(r'/([a-z][a-z0-9-]+)', content)
                for ref in set(refs):
                    if ref != skill_name and (skills_dir / ref).exists():
                        dependencies.append({
                            "skill": skill_name,
                            "depends_on": ref,
                            "type": "reference",
                        })
            except Exception as e:
                logger.debug("detector failed: {}", e)

    return dependencies


def detect_error_log_summary(project_root: Path) -> list[str]:
    """Summarize recent errors from common log locations."""
    errors = []

    # Check common log files
    log_paths = [
        project_root / "logs" / "error.log",
        project_root / ".pi" / "logs" / "error.log",
        Path.home() / ".claude" / "logs" / "error.log",
    ]

    for log_path in log_paths:
        if log_path.exists():
            try:
                content = log_path.read_text()
                # Get last 20 error lines
                lines = [line for line in content.split("\n") if "error" in line.lower() or "Error" in line]
                errors.extend(lines[-10:])
            except Exception as e:
                logger.debug("detector failed: {}", e)

    # Check dogpile errors
    dogpile_errors = project_root / ".agent" / "skills" / "dogpile" / "dogpile_errors.json"
    if dogpile_errors.exists():
        try:
            data = json.loads(dogpile_errors.read_text())
            if isinstance(data, dict) and "recent_errors" in data:
                for err in data["recent_errors"][-5:]:
                    errors.append(f"dogpile: {err.get('type', 'unknown')} - {err.get('message', '')[:100]}")
        except Exception as e:
            logger.debug("detector failed: {}", e)

    return errors[:20]  # Limit


def detect_environment_snapshot() -> dict:
    """Capture relevant environment variables."""
    relevant_vars = [
        # API keys (masked)
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PERPLEXITY_API_KEY",
        "BRAVE_API_KEY", "GITHUB_TOKEN",
        # Paths
        "VOICE_STORAGE", "PERSONAPLEX_CACHE", "QWEN3_MODEL",
        # Config
        "CLAUDE_MODEL", "DEFAULT_MODEL", "PI_SKILLS_DIR",
        # Python
        "VIRTUAL_ENV", "PYTHONPATH",
    ]

    env = {}
    for var in relevant_vars:
        value = os.environ.get(var)
        if value:
            # Mask API keys
            if "KEY" in var or "TOKEN" in var or "SECRET" in var:
                env[var] = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
            else:
                env[var] = value

    return env


def detect_session_transcript() -> str:
    """Find the current session transcript file."""
    claude_dir = Path.home() / ".claude" / "projects"

    if not claude_dir.exists():
        return ""

    try:
        jsonl_files = list(claude_dir.rglob("*.jsonl"))
        if not jsonl_files:
            return ""
        # Filter out subagent files
        main_files = [f for f in jsonl_files if "subagent" not in str(f)]
        candidates = main_files if main_files else jsonl_files
        most_recent = max(candidates, key=lambda f: f.stat().st_mtime)
        return str(most_recent)
    except Exception as e:
        logger.debug("detector failed: {}", e)

    return ""


def detect_architecture_diagram(files_modified: list[str]) -> str:
    """Generate ASCII architecture diagram from modified files."""
    if not files_modified:
        return ""

    # Group files by directory
    dirs = {}
    for f in files_modified:
        parts = Path(f).parts
        if len(parts) > 1:
            top = parts[0]
            if top not in dirs:
                dirs[top] = []
            dirs[top].append(f)

    if not dirs:
        return ""

    # Generate simple tree
    lines = ["```", "Modified Structure:"]
    for dir_name, files in sorted(dirs.items())[:5]:  # Limit to 5 dirs
        lines.append(f"├── {dir_name}/")
        for f in files[:5]:  # Limit to 5 files per dir
            fname = Path(f).name
            lines.append(f"│   ├── {fname}")
        if len(files) > 5:
            lines.append(f"│   └── ... ({len(files) - 5} more)")
    lines.append("```")

    return "\n".join(lines)


def detect_claude_md(project_root: Path) -> dict:
    """Read CLAUDE.md for project identity, purpose, and instructions.

    Checks project root and parent directories for CLAUDE.md files.
    Returns structured dict with project metadata.
    """
    result = {"purpose": "", "type": "", "status": "", "instructions": [], "raw": ""}

    claude_md = project_root / "CLAUDE.md"
    if not claude_md.exists():
        return result

    try:
        content = claude_md.read_text()
        result["raw"] = content[:3000]  # Cap for context window

        # Extract purpose/type/status from common patterns
        for line in content.split("\n"):
            line_stripped = line.strip()
            if line_stripped.startswith("**Purpose:**"):
                result["purpose"] = line_stripped.split("**Purpose:**", 1)[1].strip()
            elif line_stripped.startswith("**Type:**"):
                result["type"] = line_stripped.split("**Type:**", 1)[1].strip()
            elif line_stripped.startswith("**Status:**"):
                result["status"] = line_stripped.split("**Status:**", 1)[1].strip()
    except Exception as e:
        logger.debug("detector failed: {}", e)

    return result


def detect_memory_md(project_root: Path) -> str:
    """Find and read the project's MEMORY.md from Claude memory directory.

    Searches:
    1. ~/.claude/projects/<sanitized-path>/memory/MEMORY.md
    2. ~/.claude/projects/<sanitized-path>/memory/*.md (all memory files)
    3. project_root/local/docs/CONTEXT.md (existing handoff doc)
    """
    # Build the sanitized Claude project path
    claude_projects = Path.home() / ".claude" / "projects"
    if not claude_projects.exists():
        return ""

    # Claude sanitizes paths: /home/user/foo/bar -> -home-user-foo-bar
    sanitized = str(project_root).replace("/", "-").lstrip("-")

    memory_dir = claude_projects / sanitized / "memory"
    if not memory_dir.exists():
        # Try partial match (project path might be a prefix)
        for d in claude_projects.iterdir():
            if d.is_dir() and sanitized in d.name:
                candidate = d / "memory"
                if candidate.exists():
                    memory_dir = candidate
                    break

    if not memory_dir.exists():
        return ""

    parts = []
    memory_md = memory_dir / "MEMORY.md"
    if memory_md.exists():
        try:
            content = memory_md.read_text()
            parts.append(f"### MEMORY.md\n\n{content[:4000]}")
        except Exception as e:
            logger.debug("detector failed: {}", e)

    # Also read other memory files (context docs, topic files)
    # But only list them -- don't embed full content to avoid bloat
    try:
        other_files = []
        for md_file in sorted(memory_dir.glob("*.md")):
            if md_file.name == "MEMORY.md":
                continue
            try:
                content = md_file.read_text()
                if len(content) > 100:
                    other_files.append(f"- `{md_file.name}` ({len(content)} bytes)")
            except Exception as e:
                logger.debug("detector failed: {}", e)
        if other_files:
            parts.append("### Other Memory Files\n\n" + "\n".join(other_files))
    except Exception as e:
        logger.debug("detector failed: {}", e)

    return "\n\n".join(parts)


def detect_agent_inbox(project_name: str) -> list[str]:
    """Check agent-inbox for pending messages for this project.

    Returns list of message summaries.
    """
    inbox_script = Path.home() / ".claude" / "skills" / "agent-inbox" / "inbox.py"
    if not inbox_script.exists():
        return []

    try:
        result = subprocess.run(
            [sys.executable, str(inbox_script), "check", "--project", project_name],
            capture_output=True, text=True, timeout=15,
        )
        output = result.stdout.strip() + result.stderr.strip()
        if "No pending" in output:
            return []
        # Parse message summaries
        messages = []
        for line in output.split("\n"):
            line = line.strip()
            if line and not line.startswith("==="):
                messages.append(line)
        return messages[:10]  # Cap at 10
    except Exception:
        return []


def detect_existing_context(output_path: Path) -> dict:
    """Read existing CONTEXT.md and extract structured sections.

    Used to preserve manually-written content when regenerating.
    Returns dict of section_name -> content.
    """
    if not output_path.exists():
        return {}

    try:
        content = output_path.read_text()
    except Exception as e:
        logger.debug("detector failed: {}", e)
        return {}

    sections = {}
    current_section = None
    current_lines = []

    for line in content.split("\n"):
        if line.startswith("## "):
            if current_section:
                sections[current_section] = "\n".join(current_lines).strip()
            current_section = line.strip("# ").strip()
            current_lines = []
        elif current_section:
            current_lines.append(line)

    if current_section:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections


def infer_focus_from_git(project_root: Path) -> str:
    """Infer session focus from recent git commit messages."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-5", "--no-decorate"],
            capture_output=True, text=True, timeout=10,
            cwd=str(project_root),
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ""

        commits = result.stdout.strip().split("\n")
        # Extract the messages (skip hash)
        messages = [c.split(" ", 1)[1] if " " in c else c for c in commits]

        # Find common theme
        # If all commits share a prefix pattern like "fix(s04):", use that
        prefixes = []
        for msg in messages:
            match = re.match(r'^(feat|fix|docs|refactor|test|chore)\(([^)]+)\)', msg)
            if match:
                prefixes.append(f"{match.group(1)}({match.group(2)})")

        if prefixes:
            common = Counter(prefixes).most_common(1)[0][0]
            return f"Recent work: {common} -- {messages[0]}"

        return f"Recent: {messages[0]}"
    except Exception as e:
        logger.debug("detector failed: {}", e)
        return ""


def detect_companion_repos(project_root: Path, claude_md: dict, memory_content: str) -> list[dict]:
    """Detect companion repositories from CLAUDE.md and MEMORY.md content.

    Returns list of {name, path, relationship} dicts.
    """
    repos = []
    combined = (claude_md.get("raw", "") + "\n" + memory_content)

    # Look for absolute paths that look like repo roots
    # Match /home/<user>/workspace/<group>/<project> or similar structures
    path_pattern = re.compile(r'(/home/[^/\s`]+/workspace/[^/\s`]+(?:/[^/\s`]+)?)')
    seen = set()

    for match in path_pattern.finditer(combined):
        path_str = match.group(1).rstrip(")")
        path = Path(path_str)
        if path.exists() and path.is_dir() and path != project_root and path_str not in seen:
            seen.add(path_str)
            # Check if it's a git repo
            if (path / ".git").exists():
                repos.append({
                    "name": path.name,
                    "path": str(path),
                    "relationship": "companion",
                })

    return repos[:5]  # Cap at 5


def detect_running_processes(project_root: Path) -> list[str]:
    """Detect running processes related to this project.

    Checks for supervisors, pipelines, servers, etc.
    """
    processes = []
    project_name = project_root.name

    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []

        for line in result.stdout.split("\n"):
            if project_name in line and "grep" not in line and "context.py" not in line:
                # Extract the command part (field 11+)
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    cmd = parts[10][:120]
                    cpu = parts[2]
                    mem = parts[3]
                    try:
                        cpu_val = float(cpu)
                    except ValueError:
                        continue
                    if cpu_val > 0.5 or "supervisor" in cmd.lower() or "pipeline" in cmd.lower():
                        processes.append(f"CPU={cpu}% MEM={mem}% {cmd}")
    except Exception as e:
        logger.debug("detector failed: {}", e)

    return processes[:10]


def detect_assessment(project_root: Path) -> list[str]:
    """Assess code health: outstanding issues, doc misalignments, stale artifacts.

    Checks:
    1. TODO/FIXME/HACK/XXX counts in source code
    2. Stale test files (tests that import deleted modules)
    3. README/doc freshness vs code changes
    4. Untracked large files that might be accidental
    5. Broken symlinks
    6. Git conflicts markers left in files
    """
    issues = []

    # 1. Count TODO/FIXME/HACK in source
    for pattern, label in [("TODO", "TODO"), ("FIXME", "FIXME"), ("HACK", "HACK"), ("XXX", "XXX")]:
        try:
            result = subprocess.run(
                ["git", "grep", "-c", pattern, "--", "*.py"],
                capture_output=True, text=True, timeout=15,
                cwd=str(project_root),
            )
            if result.returncode == 0 and result.stdout.strip():
                count = sum(int(line.split(":")[-1]) for line in result.stdout.strip().split("\n") if ":" in line)
                if count > 0:
                    issues.append(f"{label}: {count} occurrences across Python files")
        except Exception as e:
            logger.debug("detector failed: {}", e)

    # 2. Git conflict markers
    try:
        result = subprocess.run(
            ["git", "grep", "-l", "<<<<<<< ", "--", "*.py", "*.md", "*.json"],
            capture_output=True, text=True, timeout=10,
            cwd=str(project_root),
        )
        if result.returncode == 0 and result.stdout.strip():
            files = result.stdout.strip().split("\n")
            issues.append(f"Unresolved merge conflicts in {len(files)} files: {', '.join(files[:3])}")
    except Exception as e:
        logger.debug("detector failed: {}", e)

    # 3. Doc freshness -- README.md or docs/ older than 30 days vs active code changes
    readme = project_root / "README.md"
    if readme.exists():
        try:
            readme_mtime = readme.stat().st_mtime
            age_days = (datetime.now().timestamp() - readme_mtime) / 86400
            if age_days > 30:
                # Check if code was modified recently
                result = subprocess.run(
                    ["git", "log", "-1", "--format=%ct", "--", "src/"],
                    capture_output=True, text=True, timeout=10,
                    cwd=str(project_root),
                )
                if result.returncode == 0 and result.stdout.strip():
                    code_mtime = int(result.stdout.strip())
                    code_age_days = (datetime.now().timestamp() - code_mtime) / 86400
                    if code_age_days < 7 and age_days > 30:
                        issues.append(f"README.md is {int(age_days)} days old but src/ was modified {int(code_age_days)} days ago -- may be stale")
        except Exception as e:
            logger.debug("detector failed: {}", e)

    # 4. Large untracked files (>10MB)
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=15,
            cwd=str(project_root),
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if line.startswith("??"):
                    fpath = project_root / line[3:].strip()
                    try:
                        if fpath.is_file() and fpath.stat().st_size > 10_000_000:
                            size_mb = fpath.stat().st_size / 1_000_000
                            issues.append(f"Large untracked file: {line[3:].strip()} ({size_mb:.1f}MB)")
                    except Exception as e:
                        logger.debug("detector failed: {}", e)
    except Exception as e:
        logger.debug("detector failed: {}", e)

    # 5. Dirty working tree size
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=15,
            cwd=str(project_root),
        )
        if result.returncode == 0:
            lines = [line for line in result.stdout.strip().split("\n") if line.strip()]
            if len(lines) > 50:
                modified = sum(1 for line in lines if line[0] == "M" or line[1] == "M")
                untracked = sum(1 for line in lines if line.startswith("??"))
                issues.append(f"Dirty working tree: {len(lines)} files ({modified} modified, {untracked} untracked) -- needs triage")
    except Exception as e:
        logger.debug("detector failed: {}", e)

    # 6. Deleted files still imported (quick heuristic)
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
            cwd=str(project_root),
        )
        if result.returncode == 0:
            deleted = []
            for line in result.stdout.split("\n"):
                if line.strip() and line[0] == "D":
                    deleted.append(line[3:].strip())
            if deleted:
                issues.append(f"{len(deleted)} deleted files in git -- verify no stale imports remain")
    except Exception as e:
        logger.debug("detector failed: {}", e)

    return issues[:15]
