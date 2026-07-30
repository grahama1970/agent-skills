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
3. Execution (--execute): Remove untracked junk cleared by per-path provenance
4. Finalization: Record cleanup in local/CLEANUP_LOG.md and the phase receipt

Evidence model: assessment, planning, and worktree audit never depend on an
index and always run. Each mutation class carries its own evidence requirement.
Untracked junk removal needs untracked status plus per-path provenance, not
dependency edges. Tracked-file mutation needs per-candidate evidence from the
cleanup evidence artifact (references/cleanup-evidence-contract.md) plus
project-native readiness proof, and is blocked until that artifact exists.
"""

import fnmatch
import hashlib
import os
import shutil
import subprocess
import json
import re
import sys
from collections import Counter
from pathlib import Path
from datetime import datetime
from typing import Any, List, Dict, Set, Tuple, Optional

from dotenv import load_dotenv
import typer


load_dotenv(override=False)

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

REFERENCE_TEXT_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".go", ".h", ".hpp", ".java", ".js", ".jsx",
    ".json", ".md", ".py", ".pyi", ".rs", ".sh", ".toml", ".ts", ".tsx",
    ".yaml", ".yml",
}

DEAD_FILE_CANDIDATE_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".go", ".h", ".hpp", ".java", ".js", ".jsx",
    ".py", ".pyi", ".rs", ".ts", ".tsx",
}

# Files whose mention of a path configures ignoring it, not depending on it.
IGNORE_CONFIG_BASENAMES = {
    ".gitignore",
    ".dockerignore",
    ".npmignore",
    ".eslintignore",
    ".prettierignore",
}

# Per-candidate dependency evidence produced by $ingest-code from local
# Tree-sitter analysis. Independent of Memory persistence; see
# references/cleanup-evidence-contract.md.
CLEANUP_EVIDENCE_FILENAME = ".cleanup-evidence.json"
CLEANUP_EVIDENCE_CONTRACT = "cleanup.evidence.v1"
CLEANUP_RECEIPT_CONTRACT = "cleanup.phase_receipt.v1"

# Root-level markdown that GitHub and package tooling resolve by exact name.
# Moving any of these breaks a convention a reader or tool depends on, so doc
# organization never proposes relocating them.
CONVENTIONAL_ROOT_DOCS = {
    "README.md",
    "LICENSE.md",
    "LICENCE.md",
    "COPYING.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "SUPPORT.md",
    "CHANGELOG.md",
    "GOVERNANCE.md",
    "MAINTAINERS.md",
    "AUTHORS.md",
    "NOTICE.md",
    "CITATION.md",
    "CLAUDE.md",
    "AGENTS.md",
    # Resolved by name at the repo root by agent skills. /project-knowledge
    # reads Path.cwd() / "PROJECT_KNOWLEDGE.md"; relocating it does not move the
    # file the skill reads, it just makes the skill recreate an empty one.
    "PROJECT_KNOWLEDGE.md",
}

# Where a relocated root doc is proposed to live, by filename stem. Anything
# unmatched is proposed under docs/ rather than guessed into a subdirectory.
DOC_RELOCATION_HINTS = (
    ({"design", "architecture", "adr", "rfc", "spec"}, "docs/architecture"),
    ({"goal", "goals", "roadmap", "plan", "product", "vision"}, "docs/product"),
    ({"knowledge", "context", "notes", "research"}, "docs/research"),
    ({"deploy", "deployment", "install", "setup", "operations", "runbook"}, "docs/operations"),
)

DOC_DEPRECATION_DIR = "docs/deprecated"

# Named grammars for foreign-repo detection. Both describe specified formats --
# a github.com URL and an explicit repository-declaration line -- not prose.
GITHUB_SLUG_PATTERN = r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?[\s\)\]`,]"
REPO_DECLARATION_PATTERN = r"(?:Fork/Repo|Repository|Repo)\s*[:=]\s*`?([\w.-]+/[\w.-]+)`?"

# Age past which an unreferenced doc is proposed for deprecation.
DOC_STALE_DAYS = 365

# Filename shapes produced by a copy rather than authored deliberately.
DOC_DUPLICATE_PATTERNS = (
    " copy",
    " copy 2",
    " (copy)",
    " (1)",
    "-copy",
    ".orig",
    ".bak",
)

# File-extension -> best-practices skill. A cleanup that changes a file is
# expected to run the skill that governs that file type.
BEST_PRACTICES_BY_SUFFIX = {
    ".py": "best-practices-python",
    ".rs": "best-practices-rust",
    ".tsx": "best-practices-react",
    ".jsx": "best-practices-react",
    ".ts": "best-practices-react",
    ".js": "best-practices-react",
    ".md": "best-practices-readme",
}

# Path-shape rules that win over the extension map, most specific first.
BEST_PRACTICES_BY_PATH = (
    ("SKILL.md", "best-practices-skills"),
    ("skills/", "best-practices-skills"),
    ("README.md", "best-practices-readme"),
)
DEFAULT_RECEIPT_PATH = "artifacts/cleanup/cleanup_receipt.json"
PROJECT_WATCHDOG_READY_LABEL = "agent-work"
PROJECT_WATCHDOG_HOLD_LABELS = [
    "agent-active",
    "agent-blocked",
    "needs-human",
    "maintainer-blocked",
    "next:human",
    "blocked:upstream",
    "status:deferred",
]

# Paths this skill and its evidence producer create. Without this, a successful
# run leaves artifacts that the next run reports as findings — cleanup
# generating work for itself.
CLEANUP_OUTPUT_PREFIXES = ("artifacts/cleanup/", "local/CLEANUP_LOG")
CLEANUP_OUTPUT_FILES = {
    ".cleanup-evidence.json",
    ".ingest-code.json",
    "CLEANUP_PLAN.md",
}


def is_cleanup_output(filepath: str) -> bool:
    """True when a path is something cleanup or its producer wrote."""
    normalized = filepath.removeprefix("./").rstrip("/")
    if normalized in CLEANUP_OUTPUT_FILES:
        return True
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in CLEANUP_OUTPUT_PREFIXES
    )

def log_error(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)


def log_warning(message: str) -> None:
    print(f"[WARNING] {message}", file=sys.stderr)


def log_info(message: str) -> None:
    print(f"[INFO] {message}", file=sys.stderr)


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
        ".git", ".github", ".venv", ".claude", ".agents", ".pi", ".codex",
        ".gemini", ".kilocode", ".agent",
    }
    return tracked_tops


def get_git_status() -> List[str]:
    success, output = run_command(["git", "status", "--porcelain=v1"], check=False)
    if success:
        return [line for line in output.splitlines() if line]
    log_warning("Could not get git status - not in a git repository?")
    return []


def parse_porcelain_status(lines: List[str]) -> List[Dict[str, str]]:
    """Parse `git status --porcelain=v1` into stable records."""
    records: List[Dict[str, str]] = []
    for raw in lines:
        if not raw:
            continue
        if len(raw) < 3:
            records.append({"raw": raw, "xy": "", "path": raw})
            continue
        xy = raw[:2]
        path = raw[3:]
        old_path = ""
        if " -> " in path:
            old_path, path = path.split(" -> ", 1)
        records.append({
            "raw": raw,
            "xy": xy,
            "path": path,
            "old_path": old_path,
        })
    return records


def get_untracked_files() -> List[str]:
    success, output = run_command(["git", "ls-files", "--others", "--exclude-standard"], check=False)
    if success:
        return output.strip().split("\n") if output.strip() else []
    log_warning("Could not get untracked files")
    return []


def get_all_tracked_files() -> Set[str]:
    """Return tracked paths, queried fresh every call.

    Deliberately uncached: a cached snapshot goes stale the moment anything
    commits, and a wrong tracked set silently breaks junk provenance and the
    coverage gate. `git ls-files` is cheap next to the file-content pass.
    """
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
        if is_cleanup_output(f):
            continue  # Never report our own receipts, logs, or evidence.
        top = f.split("/")[0]
        root_entries.setdefault(top, []).append(f)

    for top, files in root_entries.items():
        full = Path(top)

        # Root-level artifacts may be runtime inputs, fixtures, or deployment
        # assets. Classification alone never grants mutation authority.
        if full.is_file() and is_artifact_file(top):
            sz = get_file_size(top)
            strays.append({
                "path": top,
                "status": "artifact",
                "size": sz,
                "reason": f"Binary/media artifact at root ({_human_size(sz)})",
                "action": "review",
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
        # Untracked root directories can satisfy dynamic imports, deployment
        # mounts, or local service contracts. Never archive them heuristically.
        elif full.is_dir() and top not in get_expected_root_dirs():
            total = sum(get_file_size(f) for f in files)
            strays.append({
                "path": top + "/",
                "status": "stray_dir",
                "size": total,
                "reason": f"Untracked directory at root ({_human_size(total)}, {len(files)} files)",
                "action": "review",
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


def read_file_content(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        log_warning(f"Could not read {filepath}: {e}")
        return ""


def find_file_references(filepath: str, search_paths: List[str]) -> List[str]:
    """Walk `search_paths` looking for any mention of one file.

    Retained for callers that need a single-file answer. The assessment path
    uses `scan_repository_references` instead: this walks the tree once per
    file, so using it per candidate is quadratic.
    """
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


def scan_repository_references(
    search_dirs: List[str],
    literal_needles: Optional[Set[str]] = None,
) -> Tuple[Dict[str, Set[str]], Dict[str, List[str]]]:
    """Read every tracked text file once and answer both reference questions.

    Returns the lexical token index used to nominate dead-file candidates, and
    literal-path hits used for untracked-junk provenance. Both need a full pass
    over the same files; doing them separately doubles the I/O for no gain.

    The token index is candidate-generation evidence only. It is not a language
    server, import resolver, or proof that an absent term means a file is unused.
    """
    index: Dict[str, Set[str]] = {}
    needles = literal_needles or set()
    literal_hits: Dict[str, List[str]] = {needle: [] for needle in needles}
    normalized_roots = {
        str(Path(search_dir)).removeprefix("./").rstrip("/")
        for search_dir in search_dirs
    }

    for filepath in sorted(get_all_tracked_files()):
        path = Path(filepath)
        if path.suffix.lower() not in REFERENCE_TEXT_EXTENSIONS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue

        content = read_file_content(filepath)
        if not content:
            continue

        # Ignore-configuration mentions a path in order to exclude it, which is
        # not a dependency on it.
        if needles and path.name not in IGNORE_CONFIG_BASENAMES:
            for needle in needles:
                if needle in content:
                    literal_hits[needle].append(filepath)

        in_scope = not normalized_roots or "." in normalized_roots or any(
            filepath == root or filepath.startswith(f"{root}/") for root in normalized_roots
        )
        if not in_scope:
            continue
        for term in set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", content)):
            index.setdefault(term, set()).add(filepath)
        index.setdefault(filepath, set()).add(filepath)

    return index, literal_hits


def build_reference_index(search_dirs: List[str]) -> Dict[str, Set[str]]:
    """Return the lexical token index alone, for callers that need only it."""
    index, _ = scan_repository_references(search_dirs)
    return index


def scan_for_dead_files(
    index: Optional[Dict[str, Set[str]]] = None,
) -> List[Dict[str, str]]:
    """Generate review-only candidates from weak lexical evidence.

    A missing lexical reference cannot prove that code is unused. Dynamic
    imports, framework discovery, package entrypoints, build manifests, and
    runtime configuration all require separate dependency and readiness proof.
    """
    dead_files = []
    tracked_files = get_all_tracked_files()

    readme_content = ""
    if os.path.exists("README.md"):
        readme_content = read_file_content("README.md")

    if index is None:
        search_dirs = [".", "src", "lib", "packages", "docs"]
        search_dirs = [d for d in search_dirs if os.path.exists(d)]
        log_info("Building reference index...")
        index = build_reference_index(search_dirs)

    for filepath in tracked_files:
        path = Path(filepath)
        if path.suffix.lower() not in DEAD_FILE_CANDIDATE_EXTENSIONS:
            continue
        if ".pi/skills/" in filepath or ".kilocode/skills/" in filepath:
            continue
        if path.name in {"__init__.py", "__main__.py", "conftest.py"}:
            continue
        if path.parts and path.parts[0] in {"tests", "scripts", "migrations"}:
            continue

        filename = os.path.basename(filepath)
        stem = path.stem

        # Check README directly
        if filepath in readme_content or filename in readme_content or stem in readme_content:
            continue

        # Require a reference from another tracked text file. The result is
        # still heuristic because lexical references do not model runtime use.
        reference_files: Set[str] = set()
        for variant in {
            filename,
            stem,
            filepath,
            filepath.replace("/", "."),
            filepath.replace("/", "_"),
        }:
            reference_files.update(index.get(variant, set()))
        reference_files.discard(filepath)

        if not reference_files:
            full_path = os.path.join(os.getcwd(), filepath)
            if not os.path.exists(full_path):
                dead_files.append({
                    "path": filepath,
                    "status": "missing",
                    "reason": "Tracked but not found on disk",
                    "evidence_level": "git_state",
                    "mutation_allowed": False,
                })
            else:
                dead_files.append({
                    "path": filepath,
                    "status": "lexically_unreferenced_candidate",
                    "reason": "No lexical reference found in another tracked text file",
                    "evidence_level": "heuristic_only",
                    "mutation_allowed": False,
                })

    return dead_files


