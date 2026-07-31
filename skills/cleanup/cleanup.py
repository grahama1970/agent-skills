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
import ast
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

from cleanup_memory_index import run_memory_indexing
from cleanup_bp import best_practices_skill_for, evaluate_best_practices_gate
from cleanup_docs import (
    DOC_STALE_DAYS,
    _current_repo_slugs,
    _foreign_repo_reference,
    scan_doc_organization,
)
from cleanup_public import (
    append_public_readiness_markdown,
    classify_gitleaks_finding,
    scan_public_readiness,
)
from cleanup_quality import append_quality_gate_markdown, scan_quality_gates
from cleanup_worktree import (
    build_registered_worktree_audit,
    write_registered_worktree_audit_outputs,
)


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
AGENTIC_EVAL_GATE_CONTRACT = "cleanup.agentic_eval_gate.v1"
DEFAULT_RECEIPT_PATH = "artifacts/cleanup/cleanup_receipt.json"
DEFAULT_AGENTIC_EVAL_TIMEOUT_SECONDS = 120.0
AGENTIC_EVAL_UV_ENVIRONMENT = "/tmp/agentic-evals-skill-venv"
AGENTIC_EVAL_PYCACHEPREFIX = "/tmp/agentic-evals-skill-pycache"
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

SCRIPT_SCANABILITY_SUFFIXES = {".py", ".sh", ".bash", ".zsh"}
SCRIPT_SCANABILITY_DIRS = {"scripts", "tools", "bin"}
SCRIPT_SCANABILITY_ENTRYPOINTS = {"run.sh", "sanity.sh"}
MIN_USEFUL_DOCSTRING_CHARS = 20


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


def _project_watchdog_registry_dir() -> Path:
    """Return the sibling project-watchdog registry directory, if installed."""
    return Path(__file__).resolve().parents[1] / "project-watchdog" / "registry"


def _read_json_document(path: Path) -> Tuple[Optional[Any], Optional[str]]:
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text()), None
    except Exception as exc:
        return None, str(exc)


def _normalize_repo_identifier(value: Any) -> str:
    """Normalize GitHub repo strings and URLs to owner/repo where possible."""
    if not value:
        return ""
    text = str(value).strip().removesuffix(".git")
    ssh_match = re.match(r"git@([^:]+):(.+)$", text)
    if ssh_match:
        text = f"{ssh_match.group(1)}/{ssh_match.group(2)}"
    github_match = re.search(r"github\.com[:/]+([^/\s]+/[^/\s]+)$", text)
    if github_match:
        text = github_match.group(1)
    return text.strip("/").lower()


def _current_repo_identifier() -> str:
    success, output = run_command(["git", "remote", "get-url", "origin"], check=False)
    if not success:
        return ""
    return _normalize_repo_identifier(output.strip())


def _iter_watchdog_projects(projects_doc: Any) -> List[Dict[str, Any]]:
    if not isinstance(projects_doc, dict):
        return []
    projects = projects_doc.get("projects", [])
    if isinstance(projects, list):
        return [p for p in projects if isinstance(p, dict)]
    if isinstance(projects, dict):
        entries = []
        for key, value in projects.items():
            if isinstance(value, dict):
                entry = dict(value)
                entry.setdefault("project_id", str(key))
                entries.append(entry)
        return entries
    return []


def _watchdog_project_id(project: Dict[str, Any]) -> str:
    for key in ("project_id", "id", "name"):
        if project.get(key):
            return str(project[key])
    return ""


def _path_matches_current_repo(candidate: Any, cwd: Path) -> bool:
    if not candidate:
        return False
    try:
        return Path(str(candidate)).expanduser().resolve() == cwd
    except Exception:
        return False


def scan_project_watchdog_context(registry_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Read project-watchdog registry/state as advisory cleanup context.

    This is intentionally read-only: cleanup must not tick the watchdog, lease
    GitHub issues, relabel issues, or infer issue completion.
    """
    registry = Path(registry_dir) if registry_dir else _project_watchdog_registry_dir()
    projects_path = registry / "projects.json"
    state_path = registry / "state.json"
    base: Dict[str, Any] = {
        "status": "registry_missing",
        "registry_dir": str(registry),
        "projects_path": str(projects_path),
        "state_path": str(state_path),
        "repository_path": str(Path.cwd().resolve()),
        "repository_remote": _current_repo_identifier(),
        "project_name": get_project_name(),
        "ready_label": PROJECT_WATCHDOG_READY_LABEL,
        "hold_labels": PROJECT_WATCHDOG_HOLD_LABELS,
        "issue_mutation_allowed": False,
        "cleanup_may_dispatch_watchdog": False,
        "blocks_cleanup_execution": False,
        "requires_coordination": False,
        "warnings": [],
        "matches": [],
    }

    projects_doc, projects_error = _read_json_document(projects_path)
    state_doc, state_error = _read_json_document(state_path)
    if projects_error == "missing":
        base["warnings"].append("project-watchdog registry/projects.json is not installed")
        return base
    if projects_error:
        base["status"] = "registry_corrupt"
        base["warnings"].append(f"project-watchdog projects.json is unreadable: {projects_error}")
        return base
    if state_error == "missing":
        state_doc = {}
        base["warnings"].append("project-watchdog registry/state.json is not installed")
    elif state_error:
        base["status"] = "registry_corrupt"
        base["warnings"].append(f"project-watchdog state.json is unreadable: {state_error}")
        return base

    defaults = projects_doc.get("defaults", {}) if isinstance(projects_doc, dict) else {}
    default_labels = defaults.get("labels", {}) if isinstance(defaults, dict) else {}
    if default_labels.get("ready"):
        base["ready_label"] = default_labels["ready"]

    global_state = "unknown"
    project_states: Dict[str, Any] = {}
    if isinstance(state_doc, dict):
        global_state = str(state_doc.get("global", {}).get("state", "unknown"))
        raw_project_states = state_doc.get("projects", {})
        if isinstance(raw_project_states, dict):
            project_states = raw_project_states
    base["global_state"] = global_state

    cwd = Path.cwd().resolve()
    current_repo = base["repository_remote"]
    current_name = base["project_name"]
    matches: List[Dict[str, Any]] = []
    for project in _iter_watchdog_projects(projects_doc):
        project_id = _watchdog_project_id(project)
        repo_id = _normalize_repo_identifier(
            project.get("repo") or project.get("github_repo") or project.get("remote")
        )
        runner = project.get("runner", {}) if isinstance(project.get("runner", {}), dict) else {}
        reasons = []
        if _path_matches_current_repo(project.get("worktree") or runner.get("cwd"), cwd):
            reasons.append("worktree")
        if current_repo and repo_id and current_repo == repo_id:
            reasons.append("remote")
        if project_id and project_id == current_name and not reasons:
            reasons.append("project_id")
        if not reasons:
            continue
        state_record = project_states.get(project_id, {}) if project_id else {}
        state = "unknown"
        if isinstance(state_record, dict):
            state = str(state_record.get("state", "unknown"))
        if state == "unknown":
            state_policy = project.get("state_policy", {})
            if isinstance(state_policy, dict):
                state = str(state_policy.get("default_state", "unknown"))
        matches.append({
            "project_id": project_id,
            "display_name": project.get("display_name", project_id),
            "repo": repo_id,
            "worktree": project.get("worktree"),
            "runner_kind": project.get("runner_kind"),
            "dispatch_backend": project.get("dispatch_backend", "local"),
            "state": state,
            "match_reasons": reasons,
        })

    base["matches"] = matches
    if not matches:
        base["status"] = "not_registered"
        base["coordination_risk"] = "none"
        return base

    active_matches = [
        match for match in matches
        if global_state == "active" and match.get("state") == "active"
    ]
    base["status"] = "registered"
    base["project_ids"] = [m["project_id"] for m in matches if m.get("project_id")]
    base["project_states"] = {m["project_id"]: m.get("state") for m in matches if m.get("project_id")}
    base["dispatch_backends"] = {m["project_id"]: m.get("dispatch_backend") for m in matches if m.get("project_id")}
    base["runner_kinds"] = {m["project_id"]: m.get("runner_kind") for m in matches if m.get("project_id")}
    if active_matches:
        base["requires_coordination"] = True
        base["blocks_cleanup_execution"] = True
        base["coordination_risk"] = "active_dispatch_possible"
        base["warnings"].append(
            "project-watchdog is active for this project; cleanup must not mutate until dispatch/routing state is coordinated"
        )
    else:
        base["coordination_risk"] = "registered_not_active"
    return base


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


def _top_path(path: str) -> str:
    return path.split("/", 1)[0] if path else ""


def _is_root_file(path: str) -> bool:
    return bool(path) and "/" not in path.rstrip("/")


def _is_cache_or_build(path: str) -> bool:
    parts = set(Path(path).parts)
    return bool(parts & {
        "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
        ".cache", "dist", "build", "htmlcov",
    })


def _is_agent_runtime_path(path: str) -> bool:
    return _top_path(path) in {
        ".agent", ".agents", ".claude", ".codex", ".gemini", ".kilocode", ".pi",
    }


def _is_archive_or_artifact_path(path: str) -> bool:
    top = _top_path(path)
    return (
        top in {"artifacts", ".artifacts", "logs", "transcripts", "messages", "run"}
        or path.startswith("docs/archive/")
        or path.startswith("docs/deprecated/")
        or path.startswith("scripts/archive/")
        or path.startswith("local/CLEANUP_LOG")
    )


def _is_source_or_project_path(path: str) -> bool:
    top = _top_path(path)
    return top in {
        "src", "tests", "scripts", "docker", "docs", "configs", "mcp",
        ".github", "pyproject.toml", "uv.lock", "README.md", "AGENTS.md",
        "PROJECT_KNOWLEDGE.md", "CHANGELOG.md", "Makefile", "docker-compose.yml",
        "docker-compose.override.yml",
    }


def _is_source_dependency_candidate(path: str) -> bool:
    """Return True for untracked files that can satisfy tracked runtime imports."""
    suffix = Path(path).suffix.lower()
    if suffix not in {".py", ".pyi", ".toml", ".yaml", ".yml", ".json", ".sh"}:
        return False
    return _top_path(path) in {"src", "tests", "scripts", "configs", "docker", ".github"}


def classify_worktree_entry(entry: Dict[str, str]) -> Dict[str, Any]:
    """Classify one dirty worktree entry for cleanup/worktree triage.

    The classification is intentionally conservative. It recommends review for
    source, tests, tracked deletions, and agent runtime state rather than trying
    to infer ownership.
    """
    path = entry.get("path", "")
    xy = entry.get("xy", "")
    tracked = xy != "??"
    status = "untracked" if not tracked else "tracked"
    bucket = "requires_human_review"
    action = "review"
    risk = "medium"
    reason = "dirty worktree entry requires review"

    if _is_cache_or_build(path) or is_junk_file(path):
        bucket = "generated_or_cache"
        action = "remove_or_ignore"
        risk = "low"
        reason = "cache, build output, or junk-pattern file"
    elif _is_archive_or_artifact_path(path) or is_artifact_file(path):
        bucket = "generated_or_archive"
        action = "commit_if_evidence_or_archive_else_ignore"
        risk = "low" if not tracked else "medium"
        reason = "artifact/archive/proof/log path"
    elif _is_agent_runtime_path(path):
        bucket = "agent_runtime_state"
        action = "review_or_ignore"
        risk = "medium"
        reason = "agent runtime/config path may be local state or real config"
    elif tracked and "D" in xy:
        bucket = "tracked_deletion_review"
        action = "review_before_commit_or_restore"
        risk = "high"
        reason = "tracked deletion must not be accepted without owner intent"
    elif not tracked and _is_source_dependency_candidate(path):
        bucket = "project_dependency_review"
        action = "do_not_quarantine_run_readiness_then_commit_or_leave"
        risk = "high"
        reason = "untracked source/config can satisfy tracked imports or runtime contracts"
    elif _is_root_file(path) and path not in EXPECTED_ROOT_FILES:
        bucket = "root_stray_review"
        action = "archive_or_move_before_commit"
        risk = "medium"
        reason = "root-level file outside project infrastructure allowlist"
    elif _is_source_or_project_path(path):
        bucket = "project_work_review"
        action = "commit_only_with_coherent_change_set"
        risk = "high" if tracked else "medium"
        reason = "source, test, docs, or project infrastructure path"

    return {
        **entry,
        "status": status,
        "bucket": bucket,
        "recommended_action": action,
        "risk": risk,
        "reason": reason,
    }


def build_worktree_audit() -> Dict[str, Any]:
    """Build a deterministic worktree audit for commit-safe cleanup."""
    entries = [classify_worktree_entry(e) for e in parse_porcelain_status(get_git_status())]
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        buckets.setdefault(entry["bucket"], []).append(entry)

    summary = {
        "total": len(entries),
        "by_bucket": {name: len(items) for name, items in sorted(buckets.items())},
        "high_risk": sum(1 for entry in entries if entry.get("risk") == "high"),
        "tracked": sum(1 for entry in entries if entry.get("status") == "tracked"),
        "untracked": sum(1 for entry in entries if entry.get("status") == "untracked"),
    }
    return {
        "generated_at": datetime.now().isoformat(),
        "project": get_project_name(),
        "cwd": str(Path.cwd()),
        "summary": summary,
        "project_watchdog": scan_project_watchdog_context(),
        "buckets": buckets,
        "entries": entries,
    }


def _append_project_watchdog_markdown(lines: List[str], context: Dict[str, Any]) -> None:
    lines.append("## Project Watchdog Coordination")
    lines.append("")
    lines.append(f"- Status: `{context.get('status', 'unknown')}`")
    lines.append(f"- Registry: `{context.get('registry_dir', 'unknown')}`")
    lines.append(f"- Global state: `{context.get('global_state', 'unknown')}`")
    project_states = context.get("project_states") or {}
    if project_states:
        lines.append(
            "- Project states: "
            + ", ".join(f"`{project}`=`{state}`" for project, state in sorted(project_states.items()))
        )
    if context.get("matches"):
        project_ids = ", ".join(
            f"`{match.get('project_id', 'unknown')}`" for match in context["matches"]
        )
        lines.append(f"- Matched project entries: {project_ids}")
    lines.append(f"- Coordination risk: `{context.get('coordination_risk', 'unknown')}`")
    lines.append(f"- Blocks cleanup execution: `{context.get('blocks_cleanup_execution', False)}`")
    lines.append("- Cleanup issue mutation: `disabled`")
    lines.append("- Cleanup watchdog dispatch: `disabled`")
    lines.append(f"- Routable label: `{context.get('ready_label', PROJECT_WATCHDOG_READY_LABEL)}`")
    lines.append(
        "- Hold labels: "
        + ", ".join(f"`{label}`" for label in context.get("hold_labels", PROJECT_WATCHDOG_HOLD_LABELS))
    )
    for warning in context.get("warnings", []) or []:
        lines.append(f"- Warning: {warning}")
    lines.append("")


def generate_worktree_audit_markdown(audit: Dict[str, Any]) -> str:
    lines = [
        "# Worktree Cleanup Audit",
        "",
        f"Generated: {audit['generated_at']}",
        f"Project: `{audit['project']}`",
        f"CWD: `{audit['cwd']}`",
        "",
        "## Summary",
        "",
    ]
    summary = audit["summary"]
    for key in ("total", "tracked", "untracked", "high_risk"):
        lines.append(f"- {key}: {summary.get(key, 0)}")
    lines.append("")
    for bucket, count in summary.get("by_bucket", {}).items():
        lines.append(f"- {bucket}: {count}")
    lines.append("")
    _append_project_watchdog_markdown(lines, audit.get("project_watchdog", {}))
    lines.append("## Buckets")
    lines.append("")
    for bucket, entries in sorted(audit.get("buckets", {}).items()):
        lines.append(f"### {bucket} ({len(entries)})")
        lines.append("")
        for entry in entries:
            lines.append(
                f"- `{entry['xy']} {entry['path']}` — {entry['recommended_action']} "
                f"({entry['risk']}): {entry['reason']}"
            )
        lines.append("")
    lines.append("## Commit Safety Rule")
    lines.append("")
    lines.append(
        "Only commit entries that form a coherent reviewed change set. Do not "
        "auto-stage `project_work_review`, `tracked_deletion_review`, or "
        "`agent_runtime_state` entries. Do not quarantine "
        "`project_dependency_review` entries until package import and project "
        "readiness checks have passed before and after the move."
    )
    lines.append("")
    return "\n".join(lines)


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


def scan_ingest_code_evidence(marker_path: str = ".ingest-code.json") -> Dict[str, Any]:
    """Summarize the local ingest-code marker without overstating its proof."""
    path = Path(marker_path)
    base: Dict[str, Any] = {
        "marker_path": str(path),
        "proves": "the recorded ingest-code workflow completed with the reported scope",
        "does_not_prove": "that any file is unused or safe to move/delete",
        "recommended_command": (
            f"{Path(__file__).resolve().parent.parent / 'ingest-code' / 'run.sh'} "
            f"scan {Path.cwd()} --treesitter"
        ),
    }
    if not path.exists():
        return {**base, "status": "missing"}

    try:
        marker = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {**base, "status": "invalid", "error": str(exc)}

    completed = marker.get("completed") is True and marker.get("run_status") == "complete"
    code_index = marker.get("code_index") if isinstance(marker.get("code_index"), dict) else {}
    files_scanned = marker.get("files_scanned")
    symbols_stored = code_index.get("symbols_stored", 0)
    marker_warnings: List[str] = []
    if completed and (not isinstance(files_scanned, int) or files_scanned <= 0):
        marker_warnings.append(
            "marker claims completion but files_scanned is zero or missing"
        )
    if completed and not code_index.get("enabled", False):
        marker_warnings.append("marker claims completion but code_index.enabled is false")
    if completed and code_index.get("treesitter", False) and symbols_stored == 0:
        marker_warnings.append(
            "marker claims Tree-sitter mode but stored zero structured symbols"
        )
    status = "complete" if completed and not marker_warnings else "incomplete"
    return {
        **base,
        "status": status,
        "marker_claimed_complete": completed,
        "marker_warnings": marker_warnings,
        "repository_path": marker.get("path"),
        "ingested_at": marker.get("ingested_at"),
        "scope": marker.get("scope"),
        "files_scanned": files_scanned,
        "edges_stored": marker.get("edges_stored"),
        "scan_roots": marker.get("scan_roots", []),
        "completed_scan_roots": marker.get("completed_scan_roots", []),
        "code_index": {
            "enabled": code_index.get("enabled", False),
            "treesitter": code_index.get("treesitter", False),
            "symbols_stored": code_index.get("symbols_stored", 0),
            "content_hashes": code_index.get("content_hashes", False),
        },
    }


def validate_ingest_code_precondition(evidence: Dict[str, Any]) -> List[str]:
    """Require a current, repository-wide Tree-sitter scan before execution."""
    errors: List[str] = []
    repo_root = Path.cwd().resolve()

    if evidence.get("status") != "complete":
        return ["ingest-code marker is not complete"]

    marker_repo = evidence.get("repository_path")
    if not marker_repo:
        errors.append("ingest-code marker does not identify its repository")
    else:
        try:
            if Path(str(marker_repo)).resolve() != repo_root:
                errors.append("ingest-code marker belongs to a different repository")
        except OSError:
            errors.append("ingest-code repository path cannot be resolved")

    code_index = evidence.get("code_index", {})
    if not code_index.get("enabled") or not code_index.get("treesitter"):
        errors.append("ingest-code Tree-sitter code index is not complete")

    completed_roots = {
        Path(str(root)).resolve()
        for root in evidence.get("completed_scan_roots", [])
        if root
    }
    if repo_root not in completed_roots:
        errors.append("ingest-code did not complete a repository-root scan")

    tracked_code_files = [
        path
        for path in get_all_tracked_files()
        if Path(path).suffix.lower() in DEAD_FILE_CANDIDATE_EXTENSIONS
    ]
    files_scanned = evidence.get("files_scanned")
    if not isinstance(files_scanned, int) or files_scanned < len(tracked_code_files):
        errors.append(
            "ingest-code marker does not cover all tracked code files "
            f"({files_scanned!r} scanned, {len(tracked_code_files)} tracked)"
        )

    marker_time = evidence.get("ingested_at")
    try:
        ingested_at = datetime.fromisoformat(str(marker_time)).timestamp()
    except (TypeError, ValueError):
        errors.append("ingest-code marker has no valid ingestion timestamp")
    else:
        newer_files = []
        for filepath in tracked_code_files:
            try:
                if Path(filepath).stat().st_mtime > ingested_at:
                    newer_files.append(filepath)
            except OSError:
                continue
        if newer_files:
            errors.append(
                f"{len(newer_files)} tracked code files changed after ingest-code completed"
            )

    return errors


def describe_ingest_proof_limits(evidence: Dict[str, Any]) -> List[str]:
    """State what the aggregate ingest marker can and cannot establish.

    The marker holds scalar counters only. Reporting them beside cleanup
    candidates without saying what they omit is how counts get mistaken for
    per-file safety evidence.
    """
    limits = [
        "coverage_proof=count_only: the marker compares a scanned-file count "
        "against tracked code files; it does not prove which paths were scanned",
        "freshness_proof=mtime_only: staleness is judged by filesystem mtime, "
        "which is unreliable after checkout, copy, rebase, or clock change",
        "edge_scope=python_imports_only: $ingest-code resolves dependency edges "
        "from Python static imports; other languages, dynamic imports, CLI "
        "entrypoints, and configuration references contribute no edges",
        f"aggregate_only: edges_stored={evidence.get('edges_stored', 'unknown')} "
        "is a storage count and says nothing about any individual candidate",
    ]
    for warning in evidence.get("marker_warnings", []) or []:
        limits.append(f"marker_warning={warning}")
    return limits


def _working_tree_sha256(filepath: str) -> Optional[str]:
    """Return the sha256 of a working-tree file, or None if unreadable."""
    try:
        return hashlib.sha256(Path(filepath).read_bytes()).hexdigest()
    except OSError:
        return None


def find_current_skill_dir(cwd: Optional[Path] = None) -> Optional[Path]:
    """Return the nearest enclosing skill directory, if this cleanup targets one."""
    path = (cwd or Path.cwd()).resolve()
    for candidate in [path, *path.parents]:
        if (candidate / "SKILL.md").is_file():
            return candidate
    return None


def _agentic_evals_runner_path() -> Path:
    return Path(__file__).resolve().parents[1] / "agentic-evals" / "run.sh"


def run_agentic_eval_gate(
    cwd: Optional[Path] = None,
    *,
    receipt_dir: Optional[Path] = None,
    write_receipt: bool = True,
    timeout_seconds: float = DEFAULT_AGENTIC_EVAL_TIMEOUT_SECONDS,
    runner_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run the target skill's agentic eval fixture and summarize readiness."""
    skill_dir = find_current_skill_dir(cwd)
    base: Dict[str, Any] = {
        "contract": AGENTIC_EVAL_GATE_CONTRACT,
        "generated_at": datetime.now().isoformat(),
        "mocked": False,
        "live": False,
        "checked": 0,
        "skipped_unchanged": 0,
        "failed": 0,
        "not_applicable": 0,
        "what_was_exercised": "the nearest skill fixtures/agentic_eval.json via $agentic-evals",
        "what_remains_unverified": (
            "semantic correctness, live services, LLM judge behavior, and release readiness"
        ),
    }
    if skill_dir is None:
        return {
            **base,
            "status": "not_applicable",
            "not_applicable": 1,
            "reason": "current working directory is not inside a skill directory",
        }

    fixture = skill_dir / "fixtures" / "agentic_eval.json"
    skill_name = skill_dir.name
    base.update({
        "skill": skill_name,
        "skill_dir": str(skill_dir),
        "fixture": str(fixture),
        "checked": 1,
    })
    if not fixture.is_file():
        return {
            **base,
            "status": "blocked",
            "failed": 1,
            "readiness": "NOT_ESTABLISHED",
            "reason": "missing fixtures/agentic_eval.json",
            "resume_command": (
                f"bash {_agentic_evals_runner_path()} scaffold-fixture {skill_dir} "
                f"--output {fixture}"
            ),
        }

    runner = runner_path or _agentic_evals_runner_path()
    if not runner.is_file():
        return {
            **base,
            "status": "blocked",
            "failed": 1,
            "readiness": "NOT_ESTABLISHED",
            "reason": f"$agentic-evals runner not found at {runner}",
        }

    receipt_path: Optional[Path] = None
    cmd = [
        str(runner),
        "run",
        str(fixture),
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    if write_receipt:
        target_dir = receipt_dir or Path(DEFAULT_RECEIPT_PATH).parent
        if not target_dir.is_absolute():
            target_dir = Path.cwd() / target_dir
        receipt_path = target_dir / "agentic-evals" / f"{skill_name}.json"
        cmd.extend(["--output", str(receipt_path)])

    try:
        env = os.environ.copy()
        env["UV_PROJECT_ENVIRONMENT"] = AGENTIC_EVAL_UV_ENVIRONMENT
        env["PYTHONPYCACHEPREFIX"] = AGENTIC_EVAL_PYCACHEPREFIX
        completed = subprocess.run(
            cmd,
            cwd=str(skill_dir),
            capture_output=True,
            text=True,
            env=env,
            timeout=max(60.0, timeout_seconds * 5),
        )
    except subprocess.TimeoutExpired as exc:
        return {
            **base,
            "status": "blocked",
            "failed": 1,
            "readiness": "NOT_READY",
            "command": cmd,
            "reason": f"$agentic-evals timed out after {exc.timeout} seconds",
        }

    report: Optional[Dict[str, Any]] = None
    parse_error: Optional[str] = None
    try:
        if receipt_path is not None and receipt_path.exists():
            report = json.loads(receipt_path.read_text(encoding="utf-8"))
        else:
            report = json.loads(completed.stdout)
    except Exception as exc:  # noqa: BLE001 - receipt parsing errors are reported data.
        parse_error = str(exc)

    readiness = report.get("readiness") if isinstance(report, dict) else "NOT_ESTABLISHED"
    passed = completed.returncode == 0 and readiness == "READY"
    result: Dict[str, Any] = {
        **base,
        "status": "complete" if passed else "blocked",
        "failed": 0 if passed else 1,
        "readiness": readiness,
        "command": cmd,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }
    if receipt_path is not None:
        result["receipt"] = str(receipt_path)
    if report is not None:
        result["report"] = report
    if parse_error:
        result["parse_error"] = parse_error
        result["reason"] = "agentic eval report could not be parsed"
    elif not passed:
        result["reason"] = (
            f"agentic eval readiness is {readiness}; cleanup requires READY"
        )
    return result


def scan_cleanup_evidence_artifact(
    artifact_path: str = CLEANUP_EVIDENCE_FILENAME,
) -> Dict[str, Any]:
    """Read the per-candidate dependency evidence artifact.

    This artifact — not the aggregate marker — is the only evidence source that
    can support tracked-file mutation, because it carries exact scanned paths,
    content hashes, parse outcomes, resolved edges, and per-candidate inbound
    references. See references/cleanup-evidence-contract.md for the schema.
    """
    path = Path(artifact_path)
    base: Dict[str, Any] = {
        "artifact_path": str(path),
        "contract": CLEANUP_EVIDENCE_CONTRACT,
        "proves": (
            "per-candidate inbound references, parse outcomes, and proof scope "
            "for exactly the paths and content hashes it lists"
        ),
        "does_not_prove": (
            "anything about paths it omits, languages outside its proof scope, "
            "or references that exist only at runtime"
        ),
        "producer_command": (
            f"{Path(__file__).resolve().parent.parent / 'ingest-code' / 'run.sh'} "
            f"scan {Path.cwd()} --treesitter --cleanup-evidence"
        ),
    }
    if not path.exists():
        return {**base, "status": "missing"}

    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {**base, "status": "invalid", "error": str(exc)}

    if not isinstance(payload, dict):
        return {**base, "status": "invalid", "error": "artifact must be a JSON object"}
    if payload.get("contract") != CLEANUP_EVIDENCE_CONTRACT:
        return {
            **base,
            "status": "invalid",
            "error": f"unsupported contract: {payload.get('contract')!r}",
        }
    files = payload.get("files")
    if not isinstance(files, dict):
        return {**base, "status": "invalid", "error": "artifact must contain a files object"}

    return {
        **base,
        "status": "complete" if payload.get("analysis_complete") is True else "incomplete",
        "repository_path": payload.get("repository_path"),
        "generated_at": payload.get("generated_at"),
        "proof_scope": payload.get("proof_scope", {}),
        "scan_failures": payload.get("scan_failures", []),
        "files": files,
    }


def evaluate_candidate_dependency_evidence(
    filepath: str,
    artifact: Dict[str, Any],
) -> Dict[str, Any]:
    """Join one cleanup candidate against the dependency evidence artifact.

    Static evidence never authorizes mutation on its own. Even a candidate with
    zero inbound references still requires project-native before/after readiness
    proof, so ``mutation_allowed`` is False in every branch.
    """
    verdict: Dict[str, Any] = {
        "path": filepath,
        "evidence_source": artifact.get("artifact_path", CLEANUP_EVIDENCE_FILENAME),
        "mutation_allowed": False,
    }

    if artifact.get("status") != "complete":
        return {
            **verdict,
            "verdict": "no_dependency_evidence",
            "reason": (
                "cleanup evidence artifact status is "
                f"{artifact.get('status', 'missing')!r}"
            ),
        }

    record = artifact.get("files", {}).get(filepath)
    if not isinstance(record, dict):
        return {
            **verdict,
            "verdict": "outside_proof_scope",
            "reason": "candidate is not covered by the evidence artifact",
        }

    recorded_hash = record.get("content_sha256")
    if not recorded_hash or _working_tree_sha256(filepath) != recorded_hash:
        return {
            **verdict,
            "verdict": "stale_evidence",
            "reason": "working-tree content hash does not match the analyzed content",
        }

    parse_status = record.get("parse_status")
    if parse_status == "not_analyzed":
        return {
            **verdict,
            "verdict": "outside_analysis_scope",
            "reason": (
                f"language {record.get('language', 'unknown')!r} is outside the "
                "edge-resolution scope, so an empty reference set proves nothing"
            ),
        }
    if parse_status != "ok":
        return {
            **verdict,
            "verdict": "parse_failed",
            "reason": f"parse_status={parse_status!r}; edges are incomplete",
        }

    inbound = list(record.get("inbound_references", []))
    entrypoints = list(record.get("entrypoint_references", []))
    entry_kinds = list(record.get("entry_kinds", []))
    dynamic = list(record.get("dynamic_reference_warnings", []))
    verdict.update({
        "inbound_references": inbound,
        "entrypoint_references": entrypoints,
        "entry_kinds": entry_kinds,
        "dynamic_reference_warnings": dynamic,
    })

    # A pytest module or a `__main__` script runs without anything importing
    # it, so an empty reference set says nothing about whether it is used.
    if entry_kinds:
        return {
            **verdict,
            "verdict": "entry_root",
            "reason": f"file is an entry root by convention: {', '.join(entry_kinds)}",
        }

    if inbound or entrypoints:
        return {
            **verdict,
            "verdict": "referenced",
            "reason": "candidate has resolved inbound or entrypoint references",
        }
    if dynamic:
        return {
            **verdict,
            "verdict": "unresolved_dynamic_references",
            "reason": "analysis recorded dynamic references it could not resolve",
        }
    unresolved_sites = artifact.get("proof_scope", {}).get("unresolved_dynamic_site_count", 0)
    return {
        **verdict,
        "verdict": "no_inbound_references",
        "reason": (
            "no inbound references inside the proof scope; mutation still "
            "requires project-native before/after readiness proof"
        ),
        "proof_scope_caveats": (
            [
                f"{unresolved_sites} dynamic import sites in this repository "
                "resolve no target, so any file could be reached at runtime"
            ]
            if unresolved_sites
            else []
        ),
        "readiness_required": [
            "run the project's sanity command before the move",
            "run import/entrypoint smoke checks for the owning package",
            "rerun both after the move and restore on failure",
        ],
    }


def find_literal_references(needles: Set[str]) -> Dict[str, List[str]]:
    """Return tracked text files that literally contain each needle path."""
    if not needles:
        return {}
    _, hits = scan_repository_references(["."], literal_needles=needles)
    return hits


def junk_candidate_needles(untracked_files: List[str]) -> Set[str]:
    """Return the literal paths whose provenance must be checked."""
    return {f.rstrip("/") for f in untracked_files if is_junk_file(f)}


def evaluate_junk_candidates(
    untracked_files: List[str],
    literal_hits: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Decide, per path, whether an untracked junk-pattern file may be removed.

    Dependency edges are irrelevant to this class: the mutation only ever
    touches paths git does not track. The relevant evidence is untracked status,
    the junk pattern that nominated the path, and the absence of a literal
    reference from tracked code or configuration.
    """
    candidates = [f for f in untracked_files if is_junk_file(f)]
    if not candidates:
        return {}

    tracked_files = get_all_tracked_files()
    references = (
        literal_hits
        if literal_hits is not None
        else find_literal_references(junk_candidate_needles(untracked_files))
    )

    verdicts: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates:
        needle = candidate.rstrip("/")
        referenced_by = references.get(needle, [])
        if candidate in tracked_files or needle in tracked_files:
            verdicts[candidate] = {
                "path": candidate,
                "removal_allowed": False,
                "reason": "path is tracked by git; junk removal only covers untracked paths",
                "referenced_by": referenced_by,
            }
        elif referenced_by:
            verdicts[candidate] = {
                "path": candidate,
                "removal_allowed": False,
                "reason": "tracked files reference this path literally; review before removal",
                "referenced_by": referenced_by,
            }
        else:
            verdicts[candidate] = {
                "path": candidate,
                "removal_allowed": True,
                "reason": "untracked, matches a junk pattern, and no tracked file names it",
                "referenced_by": [],
            }
    return verdicts


def evaluate_mutation_readiness(
    findings: Dict[str, Any],
    ingest_evidence: Dict[str, Any],
    evidence_artifact: Dict[str, Any],
    junk_verdicts: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Report phase states and per-class mutation authority.

    Assessment never depends on indexing. Local dependency analysis, Memory
    indexing, assessment, and mutation are tracked as separate states so a
    Memory outage blocks only what it actually invalidates.
    """
    artifact_status = evidence_artifact.get("status", "missing")
    marker_complete = ingest_evidence.get("status") == "complete"
    marker_claimed_complete = ingest_evidence.get("marker_claimed_complete") is True
    agentic_eval_gate = findings.get("agentic_evals_gate", {})
    agentic_eval_status = agentic_eval_gate.get("status", "not_applicable")

    if artifact_status == "complete":
        local_analysis = "complete"
    elif artifact_status in {"incomplete", "invalid"}:
        local_analysis = "incomplete"
    elif marker_complete or marker_claimed_complete:
        local_analysis = "unavailable_legacy_marker"
    else:
        local_analysis = "unavailable"

    if marker_complete:
        memory_indexing = "complete"
    elif local_analysis == "complete":
        memory_indexing = "blocked"
    else:
        memory_indexing = "unknown"

    junk_allowed = [v["path"] for v in junk_verdicts.values() if v["removal_allowed"]]
    junk_blocked = [v["path"] for v in junk_verdicts.values() if not v["removal_allowed"]]

    if junk_allowed:
        junk_status = "allowed"
    elif junk_verdicts:
        # Candidates existed and every one failed provenance. That is a blocked
        # class, not an empty one; collapsing the two hides withheld paths.
        junk_status = "blocked"
    else:
        junk_status = "no_candidates"

    classes: Dict[str, Any] = {
        "junk_untracked_removal": {
            "status": junk_status,
            "evidence_required": "untracked status + junk pattern + no literal tracked reference",
            "allowed_paths": sorted(junk_allowed),
            "blocked_paths": sorted(junk_blocked),
            "note": (
                "this class never touches tracked files, so it does not require "
                "dependency edges or a repository-wide index"
            ),
        },
        "tracked_file_mutation": {
            "status": "blocked",
            "evidence_required": (
                "per-candidate dependency evidence from the cleanup evidence "
                "artifact plus project-native before/after readiness proof"
            ),
            "reasons": [],
            "candidate_count": len(findings.get("dead_files", [])),
        },
        "root_stray_mutation": {
            "status": "review_only",
            "evidence_required": "human owner decision; root paths may be runtime inputs",
        },
        "artifact_archive": {
            "status": "review_only",
            "evidence_required": "human owner decision; artifacts may be runtime inputs",
        },
        "project_watchdog_coordination": {
            "status": "read_only",
            "evidence_required": (
                "read-only project-watchdog registry/state observation; cleanup "
                "must not tick, lease, relabel, close, or dispatch GitHub issues"
            ),
        },
        "agentic_evaluation": {
            "status": agentic_eval_status,
            "evidence_required": (
                "target skill fixtures/agentic_eval.json run through $agentic-evals "
                "with readiness READY"
            ),
            "checked": agentic_eval_gate.get("checked", 0),
            "skipped_unchanged": agentic_eval_gate.get("skipped_unchanged", 0),
            "failed": agentic_eval_gate.get("failed", 0),
            "not_applicable": agentic_eval_gate.get("not_applicable", 0),
            "receipt": agentic_eval_gate.get("receipt"),
            "readiness": agentic_eval_gate.get("readiness"),
            "reason": agentic_eval_gate.get("reason"),
        },
    }

    watchdog_context = findings.get("project_watchdog", {})
    if watchdog_context:
        classes["project_watchdog_coordination"].update({
            "watchdog_status": watchdog_context.get("status", "unknown"),
            "global_state": watchdog_context.get("global_state", "unknown"),
            "project_states": watchdog_context.get("project_states", {}),
            "coordination_risk": watchdog_context.get("coordination_risk", "unknown"),
            "blocks_cleanup_execution": watchdog_context.get("blocks_cleanup_execution", False),
        })
    if watchdog_context.get("blocks_cleanup_execution"):
        classes["project_watchdog_coordination"]["status"] = "blocked"
        classes["project_watchdog_coordination"]["reason"] = (
            "project-watchdog may dispatch active issue work in this repo; "
            "coordinate or pause watchdog state before cleanup mutates files"
        )
        if junk_allowed:
            classes["junk_untracked_removal"]["status"] = "blocked"
            classes["junk_untracked_removal"]["blocked_paths"] = sorted(
                set(classes["junk_untracked_removal"]["blocked_paths"]) | set(junk_allowed)
            )
            classes["junk_untracked_removal"]["allowed_paths"] = []
            classes["junk_untracked_removal"]["note"] += (
                "; active project-watchdog coordination currently blocks execution"
            )
            junk_allowed = []

    tracked_reasons = classes["tracked_file_mutation"]["reasons"]
    if artifact_status != "complete":
        tracked_reasons.append(
            f"cleanup evidence artifact is {artifact_status}; run "
            f"{evidence_artifact.get('producer_command', 'ingest-code with --cleanup-evidence')}"
        )
    candidate_verdicts = findings.get("candidate_dependency_evidence", [])
    verdict_counts = Counter(
        str(verdict.get("verdict", "unknown")) for verdict in candidate_verdicts
    )
    no_reference_candidates = verdict_counts.get("no_inbound_references", 0)
    unusable_evidence_count = sum(
        verdict_counts.get(verdict, 0)
        for verdict in (
            "no_dependency_evidence",
            "outside_proof_scope",
            "stale_evidence",
            "parse_failed",
            "outside_analysis_scope",
        )
    )
    dependency_blocked_count = max(
        len(candidate_verdicts) - no_reference_candidates - unusable_evidence_count,
        0,
    )
    if candidate_verdicts:
        classes["tracked_file_mutation"]["verdict_counts"] = dict(sorted(verdict_counts.items()))
    if unusable_evidence_count:
        tracked_reasons.append(
            f"{unusable_evidence_count} candidates have missing, stale, failed, "
            "or out-of-scope dependency evidence"
        )
    if dependency_blocked_count:
        tracked_reasons.append(
            f"{dependency_blocked_count} candidates have dependency evidence that "
            "blocks mutation"
        )
    if no_reference_candidates:
        tracked_reasons.append(
            f"{no_reference_candidates} candidates have no inbound references "
            "inside the current proof scope but still require readiness proof"
        )
    tracked_reasons.append(
        "readiness proof is a separate project-native check and is never inferred "
        "from static analysis"
    )

    mutation = "allowed_limited" if junk_allowed else "no_authorized_mutations"

    return {
        "phases": {
            "local_dependency_analysis": local_analysis,
            "memory_indexing": memory_indexing,
            "assessment": "complete",
            "agentic_evaluation": agentic_eval_status,
            "mutation": mutation,
        },
        "mutation_classes": classes,
        "proof_limits": describe_ingest_proof_limits(ingest_evidence)
        + [
            f"evidence_artifact_status={artifact_status}",
            "unresolved_dynamic_sites="
            + str(evidence_artifact.get("proof_scope", {}).get("unresolved_dynamic_site_count", 0))
            + ": each one is a runtime path static analysis cannot follow",
            "artifact_proof_scope="
            + json.dumps(evidence_artifact.get("proof_scope", {}), sort_keys=True),
        ],
    }


def unusable_evidence_errors(findings: Dict[str, Any]) -> List[str]:
    """Return conditions under which cleanup cannot judge its own evidence.

    Absent evidence is a known state that blocks mutation and exits 0. Corrupt
    or foreign evidence is different: cleanup was handed something it cannot
    trust, and continuing would mean guessing. That is the only exit-2 case.
    """
    errors: List[str] = []

    artifact = findings.get("cleanup_evidence_artifact", {})
    if artifact.get("status") == "invalid":
        errors.append(
            f"cleanup evidence artifact is unreadable: {artifact.get('error', 'unknown error')}"
        )
    else:
        artifact_repo = artifact.get("repository_path")
        if artifact_repo and Path(str(artifact_repo)).resolve() != Path.cwd().resolve():
            errors.append(
                f"cleanup evidence artifact belongs to {artifact_repo}, not this repository"
            )

    marker = findings.get("ingest_code_evidence", {})
    if marker.get("status") == "invalid":
        errors.append(f"ingest-code marker is unreadable: {marker.get('error', 'unknown error')}")

    if not get_all_tracked_files() and findings.get("untracked_files"):
        errors.append("git reported no tracked files; cleanup cannot establish provenance")

    return errors


def build_phase_receipt(
    findings: Dict[str, Any],
    readiness: Dict[str, Any],
    actions_taken: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build the resumable phase receipt for this cleanup invocation."""
    ingest_evidence = findings.get("ingest_code_evidence", {})
    evidence_artifact = findings.get("cleanup_evidence_artifact", {})
    agentic_eval_gate = findings.get("agentic_evals_gate", {})
    return {
        "contract": CLEANUP_RECEIPT_CONTRACT,
        "generated_at": datetime.now().isoformat(),
        "repository_path": str(Path.cwd().resolve()),
        "phases": readiness["phases"],
        "mutation_classes": readiness["mutation_classes"],
        "proof_limits": readiness["proof_limits"],
        "inputs": {
            "ingest_marker": {
                "path": ingest_evidence.get("marker_path"),
                "status": ingest_evidence.get("status"),
                "marker_claimed_complete": ingest_evidence.get("marker_claimed_complete"),
                "marker_warnings": ingest_evidence.get("marker_warnings", []),
                "files_scanned": ingest_evidence.get("files_scanned"),
                "code_index": ingest_evidence.get("code_index", {}),
            },
            "cleanup_evidence_artifact": {
                "path": evidence_artifact.get("artifact_path"),
                "status": evidence_artifact.get("status"),
                "scan_failures": evidence_artifact.get("scan_failures", []),
            },
            "agentic_evals": {
                "skill": agentic_eval_gate.get("skill"),
                "fixture": agentic_eval_gate.get("fixture"),
                "status": agentic_eval_gate.get("status"),
                "readiness": agentic_eval_gate.get("readiness"),
                "receipt": agentic_eval_gate.get("receipt"),
                "reason": agentic_eval_gate.get("reason"),
                "command": agentic_eval_gate.get("command"),
                "counts": {
                    "checked": agentic_eval_gate.get("checked", 0),
                    "skipped_unchanged": agentic_eval_gate.get("skipped_unchanged", 0),
                    "failed": agentic_eval_gate.get("failed", 0),
                    "not_applicable": agentic_eval_gate.get("not_applicable", 0),
                },
            },
            "project_watchdog": findings.get("project_watchdog", {}),
        },
        "counts": {
            "root_strays": len(findings.get("root_strays", [])),
            "untracked_files": len(findings.get("untracked_files", [])),
            "lexical_review_candidates": len(findings.get("dead_files", [])),
            "outdated_docs": len(findings.get("outdated_docs", [])),
            "script_scanability": len(findings.get("script_scanability", [])),
        },
        "actions_taken": actions_taken or [],
        "unusable_evidence": unusable_evidence_errors(findings),
        "resume_commands": [
            evidence_artifact.get("producer_command", ""),
            ingest_evidence.get("recommended_command", ""),
            agentic_eval_gate.get("resume_command", ""),
        ],
    }


def write_phase_receipt(receipt: Dict[str, Any], receipt_path: str) -> Path:
    """Persist the phase receipt so a blocked run stays resumable."""
    path = Path(receipt_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, default=str))
    return path


def get_last_commit_times() -> Dict[str, int]:
    """Return the last commit timestamp for every path, in one git call.

    Asking `git log -1 <file>` per file forks once per document; on a repo with
    a few thousand tracked docs that dominates the entire run. One history walk
    answers the same question for every path at once.
    """
    success, output = run_command(
        ["git", "log", "--format=@%ct", "--name-only", "--no-renames"],
        check=False,
    )
    if not success:
        log_warning("Could not read git history for document staleness")
        return {}

    times: Dict[str, int] = {}
    current: Optional[int] = None
    for line in output.splitlines():
        if line.startswith("@"):
            try:
                current = int(line[1:])
            except ValueError:
                current = None
            continue
        path = line.strip()
        if path and current is not None and path not in times:
            # History is newest-first, so the first sighting is the newest.
            times[path] = current
    return times


def scan_for_outdated_docs() -> List[Dict[str, str]]:
    outdated = []

    tracked_docs = sorted(
        filepath
        for filepath in get_all_tracked_files()
        if filepath.endswith(".md") and Path(filepath).name != "README.md"
    )
    commit_times = get_last_commit_times()
    now = datetime.now().timestamp()

    for filepath in tracked_docs:
        content = read_file_content(filepath)

        if "TODO" in content or "FIXME" in content:
            outdated.append({
                "path": filepath,
                "status": "incomplete",
                "reason": "Contains TODO/FIXME markers"
            })

        timestamp = commit_times.get(filepath)
        if timestamp is None:
            continue
        age_days = (now - timestamp) / 86400
        if age_days > 365:
            outdated.append({
                "path": filepath,
                "status": "stale",
                "reason": f"Not modified in {int(age_days)} days"
            })

    return outdated


def _is_script_like_path(filepath: str, content: str) -> bool:
    path = Path(filepath)
    if path.name in SCRIPT_SCANABILITY_ENTRYPOINTS:
        return True
    if path.suffix not in SCRIPT_SCANABILITY_SUFFIXES:
        return False
    if SCRIPT_SCANABILITY_DIRS.intersection(path.parts):
        return True
    return content.startswith("#!")


def _docstring_is_useful(value: Optional[str]) -> bool:
    if not value:
        return False
    text = " ".join(value.split())
    return len(text) >= MIN_USEFUL_DOCSTRING_CHARS


def _python_scanability_gaps(filepath: str, content: str) -> List[str]:
    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError as exc:
        return [f"python_parse_error:{exc.lineno or 'unknown'}"]

    gaps: List[str] = []
    if not _docstring_is_useful(ast.get_docstring(tree)):
        gaps.append("missing_file_purpose_docstring")

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            if not _docstring_is_useful(ast.get_docstring(node)):
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                gaps.append(f"missing_public_{kind}_docstring:{node.name}")

    if "argparse.ArgumentParser" in content and "description=" not in content:
        gaps.append("argparse_missing_description")

    return gaps


def _shell_scanability_gaps(content: str) -> List[str]:
    gaps: List[str] = []
    header_lines = []
    for line in content.splitlines()[:12]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#!"):
            continue
        header_lines.append(stripped)
    has_header_comment = any(
        line.startswith("#") and len(line.lstrip("#").strip()) >= MIN_USEFUL_DOCSTRING_CHARS
        for line in header_lines
    )
    if not has_header_comment:
        gaps.append("missing_file_purpose_comment")

    lines = content.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(?:function\s+)?([A-Za-z_][\w.-]*)\s*(?:\(\))?\s*\{", line)
        if not match:
            continue
        name = match.group(1)
        if name.startswith("_"):
            continue
        previous = lines[max(0, index - 3):index]
        if not any(
            prev.strip().startswith("#") and not prev.strip().startswith("#!")
            for prev in previous
        ):
            gaps.append(f"missing_function_comment:{name}")

    return gaps


def scan_script_scanability(tracked: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """Flag script files that are hard for humans or agents to scan quickly.

    This is readability debt, not unused-code or deletion evidence. The repair
    path is a separate documentation-only cleanup slice that adds useful
    purpose, usage, and side-effect notes without changing behavior.
    """
    tracked = get_all_tracked_files() if tracked is None else tracked
    findings: List[Dict[str, Any]] = []

    for filepath in sorted(tracked):
        content = read_file_content(filepath)
        if not content or not _is_script_like_path(filepath, content):
            continue

        suffix = Path(filepath).suffix
        if suffix == ".py":
            gaps = _python_scanability_gaps(filepath, content)
        elif suffix in {".sh", ".bash", ".zsh"}:
            gaps = _shell_scanability_gaps(content)
        else:
            gaps = ["unsupported_script_language_scanability"]

        if not gaps:
            continue

        findings.append({
            "path": filepath,
            "verdict": "script_scanability_repair",
            "reason": "Script is missing purpose, usage, or public API scanability notes",
            "missing": gaps,
            "repair_class": "readability_only",
            "automatic_cleanup_mutation_allowed": False,
            "proof_required": "parse/compile plus the script's --help or narrow sanity command",
        })

    return findings


def append_cleanup_report_preamble(plan: List[str], findings: Dict[str, Any]) -> None:
    """Append evidence-first report sections before detailed cleanup evidence."""
    root_strays_count = len(findings.get("root_strays", []))
    uncommitted_count = len(findings.get("uncommitted_changes", []))
    untracked_count = len(findings.get("untracked_files", []))
    dead_count = len(findings.get("dead_files", []))
    outdated_count = len(findings.get("outdated_docs", []))
    scanability = findings.get("script_scanability") or []
    artifact = findings.get("cleanup_evidence_artifact") or {}
    evidence_status = artifact.get("status", "missing")
    agentic_eval_gate = findings.get("agentic_evals_gate") or {}
    agentic_eval_status = agentic_eval_gate.get("status", "not_applicable")
    public_readiness = findings.get("public_readiness") or {}
    public_blockers = public_readiness.get("blockers", [])
    quality_gate = findings.get("quality_gate") or {}
    quality_blockers = quality_gate.get("blockers", [])

    risk_items = []
    if uncommitted_count:
        risk_items.append("`[F-001]` Dirty worktree requires ownership triage before mutation")
    if root_strays_count:
        risk_items.append("`[F-002]` Root-level strays require owner review")
    if dead_count and evidence_status != "complete":
        risk_items.append("`[F-003]` Tracked-file candidates lack complete dependency evidence")
    if scanability:
        risk_items.append("`[F-004]` Script scanability gaps make maintenance harder")
    if public_blockers:
        risk_items.append("`[F-005]` Public-readiness security blockers prevent a public release claim")
    if quality_blockers:
        risk_items.append("`[F-006]` Quality-gate blockers prevent a proven cleanup slice")
    if agentic_eval_status == "blocked":
        risk_items.append("`[F-007]` Target skill agentic eval is missing or not READY")
    if not risk_items:
        risk_items.append("No high-risk cleanup finding was produced by this assessment.")

    has_findings = any([
        root_strays_count, uncommitted_count, untracked_count, dead_count,
        outdated_count, scanability, public_blockers, quality_blockers,
        agentic_eval_status == "blocked",
    ])
    overall = "Needs Changes" if has_findings else "Partially Verified"

    plan.extend([
        "## Report Summary",
        "",
        f"**Overall Finding:** {overall}",
        "",
        (
            "**Core Conclusion:** This report identifies cleanup candidates and "
            "mutation boundaries from local repository evidence. Automatic "
            "execution is limited to untracked junk paths that clear provenance; "
            "tracked files, root strays, artifacts, documentation findings, and "
            "script scanability repairs require explicit review or a separate "
            "repair slice. Public-readiness findings require deterministic "
            "gitleaks and maintainer-setting receipts before a public-release "
            "claim, and quality-gate findings require scoped parse/lint/type/test "
            "receipts before a cleanup slice is treated as proven."
        ),
        "",
        (
            "**Evidence Basis:** The report uses git status, tracked/untracked "
            "file inventory, lexical reference scans, cleanup evidence artifacts, "
            "ingest markers, project-watchdog state, documentation scans, and "
            "script scanability, public-readiness, and quality-gate checks where "
            "available."
        ),
        "",
        "**Highest-Risk Issues:**",
        "",
    ])
    for item in risk_items:
        plan.append(f"1. {item}")
    plan.extend([
        "",
        "**Immediate Next Steps:**",
        "",
        "1. `[A-001]` Run or review `--worktree-audit` before mutating a dirty repository.",
        "2. `[A-002]` Refresh `.cleanup-evidence.json` before proposing tracked-file moves.",
        "3. `[A-003]` Handle script scanability as readability-only documentation repair.",
        "4. `[A-004]` Resolve public-readiness blockers before making a public-release claim.",
        "5. `[A-005]` Run selected quality gates for the cleanup slice.",
        "",
        (
            "**Non-Claims:** This report does not prove unused code, runtime "
            "safety, public-release readiness, semantic correctness, or that any "
            "tracked file is safe to delete."
        ),
        "",
        "## Scope",
        "",
        "- Reviewed: repository file inventory, cleanup candidates, evidence states, documentation staleness, script scanability, public-readiness blockers, quality-gate blockers, and mutation authority.",
        "- Not reviewed: product correctness, full runtime behavior, external service health, semantic code ownership, maintainer acceptance of GitHub settings, and human acceptance of moves or repairs.",
        "- Mutation policy: only untracked junk with per-path provenance may be removed by `--execute`; all other classes require explicit review or a separate repair slice.",
        "",
        "## Source-of-Truth Inventory",
        "",
        "| Source ID | Source Name | Type | Recency | Used For | Limitations |",
        "|---|---|---|---|---|---|",
        "| S-001 | `git status --porcelain=v1` | git inventory | fresh for this run | F-001, worktree risk | Does not identify semantic ownership |",
        "| S-002 | tracked/untracked file lists | git inventory | fresh for this run | cleanup candidate discovery | Does not prove runtime usage |",
        "| S-003 | lexical reference scan | local static scan | fresh for this run | dead-file nomination, junk provenance | Lexical absence is not dependency proof |",
        "| S-004 | `.cleanup-evidence.json` | dependency evidence artifact | status shown below | tracked candidate verdicts | Missing or stale evidence blocks tracked mutation |",
        "| S-005 | `.ingest-code.json` | aggregate ingest marker | status shown below | context only | Aggregate counters are not per-file safety evidence |",
        "| S-006 | documentation and script scans | local static scan | fresh for this run | doc/readability findings | Findings require review before repair |",
        "| S-007 | `$agentic-evals` report | local fixture runner | fresh for this run | target skill eval readiness | Fixture smoke does not prove semantic correctness or live service behavior |",
        "| S-008 | gitleaks/GitHub readiness receipts | local security/readiness artifacts | status shown below | public-readiness blockers | Missing receipts block release claims |",
        "| S-009 | project-native quality gates | local validation commands | status shown below | parse/lint/type/test blockers | Missing selected receipts block cleanup proof |",
        "",
        "## Finding Index",
        "",
        "| Finding ID | Status | Evidence | Valid Next Action | Non-Claim |",
        "|---|---|---|---|---|",
        f"| F-001 | {'Needs Changes' if uncommitted_count else 'Partially Verified'} | `{uncommitted_count}` dirty entries | Run `--worktree-audit` and isolate owner-approved changes | Does not prove entries are disposable |",
        f"| F-002 | {'Needs Decision' if root_strays_count else 'Partially Verified'} | `{root_strays_count}` root strays | Ask owner before moving or archiving | Does not authorize mutation |",
        f"| F-003 | {'Blocked' if dead_count and evidence_status != 'complete' else 'Partially Verified'} | `{dead_count}` lexical candidates; evidence `{evidence_status}` | Refresh per-candidate evidence and run readiness checks | Does not prove unused code |",
        f"| F-004 | {'Needs Changes' if scanability else 'Partially Verified'} | `{len(scanability)}` script scanability candidates | Apply readability-only repair slice | Does not prove behavior is wrong |",
        f"| F-005 | {'Blocked' if public_blockers else 'Partially Verified'} | `{len(public_blockers)}` public-readiness blockers | Triage gitleaks findings and maintainer settings receipts | Does not prove public release safety |",
        f"| F-006 | {'Blocked' if quality_blockers else 'Partially Verified'} | `{len(quality_blockers)}` quality-gate blockers | Run `--quality-gate` or mark missing gates not applicable with rationale | Does not replace full CI |",
        f"| F-007 | {'Blocked' if agentic_eval_status == 'blocked' else 'Partially Verified'} | agentic eval `{agentic_eval_status}`; readiness `{agentic_eval_gate.get('readiness', 'n/a')}` | Run or repair `fixtures/agentic_eval.json` with `$agentic-evals` | Does not prove semantic readiness |",
        "",
    ])


def generate_cleanup_plan(findings: Dict) -> str:
    plan = []
    plan.append("# Cleanup Report")
    plan.append("")
    plan.append(f"Generated: {datetime.now().isoformat()}")
    plan.append("")
    append_cleanup_report_preamble(plan, findings)

    scanability = findings.get("script_scanability") or []
    public_readiness = findings.get("public_readiness") or {}
    quality_gate = findings.get("quality_gate") or {}
    evidence_status = (findings.get("cleanup_evidence_artifact") or {}).get("status", "missing")

    ingest_evidence = findings.get("ingest_code_evidence", {})
    plan.append("## Ingest-Code Evidence")
    plan.append("")
    plan.append(f"- Status: `{ingest_evidence.get('status', 'missing')}`")
    plan.append(f"- Marker: `{ingest_evidence.get('marker_path', '.ingest-code.json')}`")
    plan.append(f"- Files scanned: `{ingest_evidence.get('files_scanned', 'unknown')}`")
    plan.append(f"- Dependency edges stored: `{ingest_evidence.get('edges_stored', 'unknown')}`")
    plan.append(
        f"- Structured symbols stored: "
        f"`{ingest_evidence.get('code_index', {}).get('symbols_stored', 'unknown')}`"
    )
    if ingest_evidence.get("marker_claimed_complete") is True and ingest_evidence.get("status") != "complete":
        plan.append("- Marker claim: `completed`, but aggregate proof is degraded")
    for warning in ingest_evidence.get("marker_warnings", []) or []:
        plan.append(f"- Warning: {warning}")
    plan.append(f"- Proves: {ingest_evidence.get('proves', 'ingest status only')}")
    plan.append(
        f"- Does not prove: "
        f"{ingest_evidence.get('does_not_prove', 'that files are safe to remove')}"
    )
    plan.append(
        f"- Refresh command: `{ingest_evidence.get('recommended_command', 'not available')}`"
    )
    plan.append("")

    agentic_eval_gate = findings.get("agentic_evals_gate", {})
    plan.append("## Agentic Eval Gate")
    plan.append("")
    plan.append(f"- Status: `{agentic_eval_gate.get('status', 'not_applicable')}`")
    plan.append(f"- Skill: `{agentic_eval_gate.get('skill', 'not_applicable')}`")
    plan.append(f"- Fixture: `{agentic_eval_gate.get('fixture', 'not_applicable')}`")
    plan.append(f"- Readiness: `{agentic_eval_gate.get('readiness', 'not_applicable')}`")
    if agentic_eval_gate.get("receipt"):
        plan.append(f"- Receipt: `{agentic_eval_gate['receipt']}`")
    if agentic_eval_gate.get("command"):
        plan.append(
            "- Command: `"
            + " ".join(str(part) for part in agentic_eval_gate["command"])
            + "`"
        )
    if agentic_eval_gate.get("reason"):
        plan.append(f"- Reason: {agentic_eval_gate['reason']}")
    plan.append(
        "- Counts: "
        f"checked `{agentic_eval_gate.get('checked', 0)}`, "
        f"skipped_unchanged `{agentic_eval_gate.get('skipped_unchanged', 0)}`, "
        f"failed `{agentic_eval_gate.get('failed', 0)}`, "
        f"not_applicable `{agentic_eval_gate.get('not_applicable', 0)}`"
    )
    plan.append(
        "- Does not prove: semantic correctness, live services, LLM judge behavior, or release readiness."
    )
    plan.append("")

    artifact = findings.get("cleanup_evidence_artifact", {})
    readiness = findings.get("mutation_readiness", {})
    plan.append("## Per-Candidate Dependency Evidence")
    plan.append("")
    plan.append(f"- Artifact: `{artifact.get('artifact_path', CLEANUP_EVIDENCE_FILENAME)}`")
    plan.append(f"- Status: `{artifact.get('status', 'missing')}`")
    plan.append(f"- Producer: `{artifact.get('producer_command', 'not available')}`")
    if artifact.get("scan_failures"):
        plan.append(f"- Scan failures: `{len(artifact['scan_failures'])}`")
    plan.append("")
    if readiness.get("phases"):
        plan.append("| Phase | State |")
        plan.append("|---|---|")
        for phase, state in readiness["phases"].items():
            plan.append(f"| `{phase}` | `{state}` |")
        plan.append("")
    if readiness.get("proof_limits"):
        plan.append("Proof limits:")
        plan.append("")
        for limit in readiness["proof_limits"]:
            plan.append(f"- {limit}")
        plan.append("")

    _append_project_watchdog_markdown(plan, findings.get("project_watchdog", {}))

    candidate_evidence = findings.get("candidate_dependency_evidence", [])
    if candidate_evidence:
        plan.append("### Candidate Verdicts")
        plan.append("")
        plan.append("| Candidate | Verdict | Inbound refs | Mutation |")
        plan.append("|---|---|---|---|")
        for verdict in candidate_evidence:
            inbound = len(verdict.get("inbound_references", []))
            plan.append(
                f"| `{verdict['path']}` | `{verdict['verdict']}` | {inbound} | "
                f"`{'allowed' if verdict.get('mutation_allowed') else 'blocked'}` |"
            )
        plan.append("")

    # Root strays (review only)
    if findings.get("root_strays"):
        plan.append("## Root-Level Strays (Review Only)")
        plan.append("")
        plan.append(
            "These paths need owner, dependency, ingest-code, and readiness review. "
            "The cleanup CLI will not archive them automatically:"
        )
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
        plan.append(
            "**Action Required**: Run `--worktree-audit` and resolve these by "
            "bucket. Commit only the coherent cleanup slice by explicit path. Do "
            "not blanket-stash or blanket-commit a dirty worktree."
        )
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
        plan.append("## Lexically Unreferenced Candidates (Review Only)")
        plan.append("")
        for file_info in findings["dead_files"]:
            plan.append(f"- `{file_info['path']}` - {file_info['status']}: {file_info['reason']}")
        plan.append("")
        plan.append(
            "**NON-MUTATING**: Lexical absence is not unused-code proof. Confirm "
            "with language-aware references, ingest-code relationships, package "
            "entrypoints/configuration, and before/after project sanity checks."
        )
        plan.append("")

    # Outdated docs
    if findings.get("outdated_docs"):
        plan.append("## Potentially Outdated Documentation")
        plan.append("")
        for file_info in findings["outdated_docs"]:
            plan.append(f"- `{file_info['path']}` - {file_info['status']}: {file_info['reason']}")
        plan.append("")

    if scanability:
        plan.append("## Script Scanability (Readability Repair)")
        plan.append("")
        plan.append(
            "These script files are hard for humans or agents to scan quickly. "
            "This finding is not unused-code evidence and does not authorize "
            "deletion, quarantine, or archival. Repairs must be a separate "
            "readability-only slice that adds useful purpose, usage, side-effect, "
            "function, or class notes without changing behavior."
        )
        plan.append("")
        plan.append("| Script | Missing scanability evidence | Repair class |")
        plan.append("| --- | --- | --- |")
        for item in scanability:
            missing = ", ".join(f"`{gap}`" for gap in item.get("missing", []))
            plan.append(
                f"| `{item['path']}` | {missing} | `{item['repair_class']}` |"
            )
        plan.append("")
        plan.append(
            "Proof for a repair slice: parse/compile the touched scripts and run "
            "each script's `--help`, entrypoint smoke, or narrow sanity command."
        )
        plan.append("")

    append_public_readiness_markdown(plan, public_readiness)
    append_quality_gate_markdown(plan, quality_gate)

    uncommitted_count = len(findings.get("uncommitted_changes", []))
    root_strays_count = len(findings.get("root_strays", []))

    plan.append("## Outstanding / Broken / Unknown")
    plan.append("")
    if evidence_status != "complete":
        plan.append(
            f"- `Blocked`: tracked-file mutation evidence is `{evidence_status}`; "
            "tracked moves/removals remain unauthorized."
        )
    if uncommitted_count:
        plan.append("- `Needs Changes`: dirty worktree entries need owner-safe triage.")
    if root_strays_count:
        plan.append("- `Needs Decision`: root strays need human owner disposition.")
    if scanability:
        plan.append("- `Needs Changes`: script scanability repairs are unimplemented.")
    if agentic_eval_gate.get("status") == "blocked":
        plan.append(
            "- `Blocked`: target skill agentic eval is missing or did not reach `READY`."
        )
    if public_readiness.get("blockers"):
        plan.append("- `Blocked`: public-readiness security triage has unresolved blockers.")
    if quality_gate.get("blockers"):
        plan.append("- `Blocked`: selected quality gates are missing, failed, or not established.")
    if not any([
        evidence_status != "complete",
        uncommitted_count,
        root_strays_count,
        scanability,
        agentic_eval_gate.get("status") == "blocked",
        public_readiness.get("blockers"),
        quality_gate.get("blockers"),
    ]):
        plan.append("- No outstanding cleanup blocker was detected by this report scope.")
    plan.append("")

    plan.append("## Plan-Ready Next Actions")
    plan.append("")
    plan.append("| Action ID | Related Finding | Action | Owner Persona | Primary Object | Acceptance Check | Dependencies | Priority |")
    plan.append("|---|---|---|---|---|---|---|---|")
    plan.append("| A-001 | F-001 | Classify dirty entries with `--worktree-audit` | project agent | git worktree | JSON and Markdown audit exist | none | P0 |")
    plan.append("| A-002 | F-003 | Refresh per-candidate cleanup evidence | project agent | `.cleanup-evidence.json` | artifact schema loads and candidate verdicts are present | ingest-code available | P1 |")
    plan.append("| A-003 | F-004 | Add readability-only script docstrings/comments | project agent | listed script files | parse/compile plus help or narrow sanity proof passes | explicit readability slice | P2 |")
    plan.append("| A-004 | F-005 | Repair or add `fixtures/agentic_eval.json` and rerun `$agentic-evals` | project agent | target skill eval fixture | agentic eval report readiness is `READY` | agentic-evals available | P0 |")
    plan.append("| A-005 | Public-readiness | Triage gitleaks and GitHub settings blockers | maintainer/project agent | public-release evidence | findings are triaged or allowlisted with maintainer settings receipt | explicit public-readiness slice | P0 |")
    plan.append("| A-006 | Quality gate | Run or establish project-native parse/lint/type/test gates | project agent | quality receipt | selected gates pass or blockers are explicit | explicit quality-gate slice | P0 |")
    plan.append("")

    plan.append("## Non-Claims")
    plan.append("")
    plan.append("- This report does not prove that lexically unreferenced files are unused.")
    plan.append("- This report does not prove that root artifacts or root strays are safe to archive.")
    plan.append("- This report does not prove runtime, release, UI, compliance, or production readiness.")
    plan.append("- Script scanability findings do not prove behavior is wrong; they identify readability debt for humans and agents.")
    plan.append("- Agentic eval fixture success proves local declared command expectations only; it is not semantic or live-service proof.")
    plan.append("- Public-readiness and quality-gate findings are scoped evidence; they do not change GitHub visibility or claim full CI readiness.")
    plan.append("")

    # Summary
    plan.append("## Summary")
    plan.append("")
    plan.append(f"- Root strays requiring review: {len(findings.get('root_strays', []))}")
    plan.append(f"- Uncommitted changes: {len(findings.get('uncommitted_changes', []))}")
    plan.append(f"- Untracked files: {len(findings.get('untracked_files', []))}")
    plan.append(f"- Lexically unreferenced review candidates: {len(findings.get('dead_files', []))}")
    plan.append(f"- Potentially outdated docs: {len(findings.get('outdated_docs', []))}")
    plan.append(f"- Script scanability repairs proposed: {len(scanability)}")
    plan.append(f"- Agentic eval gate: {agentic_eval_gate.get('status', 'not_applicable')}")
    plan.append(f"- Public-readiness blockers: {len(public_readiness.get('blockers', []))}")
    plan.append(f"- Quality-gate blockers: {len(quality_gate.get('blockers', []))}")
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
    """Ask for confirmation, declining safely when there is nobody to ask.

    Nightly and CI runs have no stdin. Prompting there used to raise EOFError,
    which surfaced as a bare "Aborted." and exit 1 — a scheduler reads that as a
    failed job rather than "declined, nothing was touched".
    """
    if not sys.stdin.isatty():
        log_warning(f"{action} — declined automatically (no interactive stdin)")
        log_warning("Pass --force to authorize this without a prompt")
        return False
    try:
        response = input(f"{action} [y/N]: ").strip().lower()
    except EOFError:
        log_warning(f"{action} — declined automatically (stdin closed)")
        return False
    return response in ("y", "yes")


def execute_cleanup(findings: Dict, force: bool = False) -> List[str]:
    actions_taken = []
    watchdog_context = findings.get("project_watchdog", {})
    if watchdog_context.get("blocks_cleanup_execution"):
        log_warning(
            "Project-watchdog coordination blocks cleanup execution; no files were removed"
        )
        log_warning(
            "Cleanup only observes watchdog state and will not tick, lease, relabel, or close issues"
        )
        return actions_taken

    # ── 1. Root strays are assessment-only ──────────────────────────────
    strays = findings.get("root_strays", [])
    if strays:
        log_warning(
            f"Found {len(strays)} root-level review candidates; automatic archival is disabled"
        )

    # ── 2. Remove junk files with per-path provenance ───────────────────
    untracked = findings.get("untracked_files", [])
    junk_verdicts = findings.get("junk_verdicts") or {}
    pattern_matches = [f for f in untracked if is_junk_file(f)]
    junk_files = [f for f in pattern_matches if junk_verdicts.get(f, {}).get("removal_allowed")]
    withheld = [f for f in pattern_matches if f not in junk_files]

    if withheld:
        log_warning(f"{len(withheld)} junk-pattern paths withheld by provenance")
        for f in withheld:
            reason = junk_verdicts.get(f, {}).get(
                "reason", "no provenance verdict was computed for this path"
            )
            log_warning(f"  {f}: {reason}")

    if junk_files:
        log_info(f"Found {len(junk_files)} junk files cleared for removal")

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

    # ── 3. Lexical candidates are assessment-only ───────────────────────
    dead_files = findings.get("dead_files", [])
    if dead_files:
        log_warning(
            f"Found {len(dead_files)} lexically unreferenced candidates; "
            "tracked-file removal is disabled"
        )

    # ── 4. Remaining untracked ───────────────────────────────────────────
    other_untracked = [f for f in untracked if f not in junk_files]
    if other_untracked:
        log_info(f"Found {len(other_untracked)} other untracked files")
        log_info("Review these files - use 'git clean -i' for interactive cleanup")

    return actions_taken


app = typer.Typer(help="Cleanup Skill - Deep codebase assessment and technical debt cleanup")


@app.command()
def main(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print findings without making changes (JSON output)"),
    plan: bool = typer.Option(False, "--plan", help="Generate a Cleanup Report markdown file"),
    execute: bool = typer.Option(False, "--execute", help="Perform cleanup actions (with confirmation)"),
    worktree_audit: bool = typer.Option(False, "--worktree-audit", help="Write a commit-safe dirty worktree ownership/risk audit"),
    registered_worktree_audit: bool = typer.Option(False, "--registered-worktree-audit", help="Write an all-registered-worktree rescue/prune audit"),
    script_scanability: bool = typer.Option(False, "--script-scanability", help="Run only the non-mutating script scanability pass"),
    public_readiness: bool = typer.Option(False, "--public-readiness", help="Run only the non-mutating public-readiness/security cleanup lane"),
    quality_gate: bool = typer.Option(False, "--quality-gate", help="Run only the non-mutating project-native quality gate lane"),
    memory_index: bool = typer.Option(False, "--memory-index", help="Run ingest-code --treesitter and write a local indexing receipt"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompts for junk removal only; cannot authorize any other mutation class"),
    output: str = typer.Option("CLEANUP_PLAN.md", "--output", help="Output file for plan"),
    receipt: str = typer.Option(DEFAULT_RECEIPT_PATH, "--receipt", help="Path for the resumable phase receipt"),
    agentic_eval_timeout: float = typer.Option(
        DEFAULT_AGENTIC_EVAL_TIMEOUT_SECONDS,
        "--agentic-eval-timeout",
        min=0.1,
        help="Per-trial timeout passed to $agentic-evals for the target skill fixture",
    ),
) -> None:
    """Deep codebase assessment and technical debt cleanup."""
    if worktree_audit:
        audit = build_worktree_audit()
        output_path = Path(output)
        if output_path.suffix.lower() not in {".json", ".md"}:
            output_path = output_path.with_suffix(".json")
        json_path = output_path if output_path.suffix.lower() == ".json" else output_path.with_suffix(".json")
        md_path = output_path if output_path.suffix.lower() == ".md" else output_path.with_suffix(".md")
        json_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(audit, indent=2, default=str))
        md_path.write_text(generate_worktree_audit_markdown(audit))
        log_info(f"Worktree audit JSON written to: {json_path}")
        log_info(f"Worktree audit Markdown written to: {md_path}")
        if audit["summary"].get("high_risk", 0):
            log_warning(f"High-risk dirty entries: {audit['summary']['high_risk']}")
        return

    if registered_worktree_audit:
        audit = build_registered_worktree_audit()
        paths = write_registered_worktree_audit_outputs(audit, output)
        log_info(f"Registered worktree audit JSON written to: {paths['json']}")
        log_info(f"Registered worktree audit Markdown written to: {paths['markdown']}")
        if audit["summary"].get("blockers", 0):
            log_warning(f"Registered worktree blockers: {audit['summary']['blockers']}")
        return

    if script_scanability:
        print(json.dumps({
            "script_scanability": scan_script_scanability(),
            "mutation": "not_authorized",
            "repair_contract": (
                "readability-only edits are allowed only as an explicit cleanup "
                "slice and must be proven with parse/compile plus script help "
                "or a narrow sanity command"
            ),
        }, indent=2, default=str))
        return

    if public_readiness:
        print(json.dumps(scan_public_readiness(run_scans=True), indent=2, default=str))
        return

    if quality_gate:
        print(json.dumps(scan_quality_gates(run_checks=True), indent=2, default=str))
        return

    if memory_index:
        receipt_data = run_memory_indexing(dry_run=dry_run, output=output)
        print(json.dumps(receipt_data, indent=2, default=str))
        return

    log_info("Starting assessment...")

    all_untracked = get_untracked_files()
    own_outputs = [f for f in all_untracked if is_cleanup_output(f)]
    untracked_files = [f for f in all_untracked if not is_cleanup_output(f)]

    # One pass over tracked text files answers both the dead-file token index
    # and the junk-provenance literal search.
    search_dirs = [d for d in [".", "src", "lib", "packages", "docs"] if os.path.exists(d)]
    log_info("Scanning repository references...")
    reference_index, literal_hits = scan_repository_references(
        search_dirs, literal_needles=junk_candidate_needles(untracked_files)
    )

    findings = {
        "root_strays": scan_root_strays(),
        "uncommitted_changes": get_git_status(),
        "untracked_files": untracked_files,
        "own_cleanup_outputs": own_outputs,
        "dead_files": scan_for_dead_files(reference_index),
        "outdated_docs": scan_for_outdated_docs(),
        "doc_organization": scan_doc_organization(),
        "script_scanability": scan_script_scanability(),
        "public_readiness": scan_public_readiness(run_scans=False),
        "quality_gate": scan_quality_gates(run_checks=False),
        "ingest_code_evidence": scan_ingest_code_evidence(),
        "cleanup_evidence_artifact": scan_cleanup_evidence_artifact(),
        "project_watchdog": scan_project_watchdog_context(),
    }
    findings["agentic_evals_gate"] = run_agentic_eval_gate(
        receipt_dir=Path(receipt).parent,
        write_receipt=not dry_run,
        timeout_seconds=agentic_eval_timeout,
    )

    # Join each candidate against per-file dependency evidence. Assessment
    # never depends on Memory: a blocked index degrades the verdicts, it does
    # not stop the scan.
    artifact = findings["cleanup_evidence_artifact"]
    findings["candidate_dependency_evidence"] = [
        evaluate_candidate_dependency_evidence(candidate["path"], artifact)
        for candidate in findings["dead_files"]
    ]
    findings["junk_verdicts"] = evaluate_junk_candidates(
        findings["untracked_files"], literal_hits=literal_hits
    )
    findings["ingest_proof_limits"] = describe_ingest_proof_limits(
        findings["ingest_code_evidence"]
    )
    findings["mutation_readiness"] = evaluate_mutation_readiness(
        findings,
        findings["ingest_code_evidence"],
        artifact,
        findings["junk_verdicts"],
    )

    receipt_payload = build_phase_receipt(findings, findings["mutation_readiness"])

    # Surfaced in every mode, not just --execute. Warnings go to stderr so
    # --dry-run keeps a clean JSON stdout.
    for error in receipt_payload["unusable_evidence"]:
        log_warning(f"Unusable evidence: {error}")

    if dry_run:
        # --dry-run makes no changes. The receipt is returned inline instead of
        # written, so the mode keeps its "no writes" contract.
        findings["phase_receipt"] = receipt_payload
        print(json.dumps(findings, indent=2, default=str))
        return

    receipt_path = write_phase_receipt(receipt_payload, receipt)

    if plan:
        log_info("Generating cleanup plan...")
        cleanup_plan = generate_cleanup_plan(findings)

        with open(output, "w") as f:
            f.write(cleanup_plan)

        log_info(f"Cleanup plan written to: {output}")
        log_info(f"Phase receipt written to: {receipt_path}")
        log_info("Review the plan and run with --execute when ready")
        return

    if execute:
        readiness = findings["mutation_readiness"]
        junk_class = readiness["mutation_classes"]["junk_untracked_removal"]

        log_info("Mutation authority by class:")
        for name, detail in readiness["mutation_classes"].items():
            log_info(f"  {name}: {detail['status']}")

        # Withholding a candidate is cleanup working, not cleanup failing;
        # execute_cleanup reports each withheld path. Exit 2 is reserved for
        # evidence this run could not evaluate at all.
        unusable = unusable_evidence_errors(findings)
        if unusable:
            log_error("Cleanup cannot evaluate the evidence it was given")
            for error in unusable:
                log_error(f"  {error}")
            log_error(f"Phase receipt: {receipt_path}")
            raise typer.Exit(code=2)

        # The guard exists to protect work cleanup is not responsible for.
        # Counting the junk it is about to remove, or its own receipts, makes it
        # ask permission because of the very files it was invoked to handle.
        # `git status` collapses an untracked directory to `?? dir/`, so a
        # membership test against file paths misses it. An entry is unrelated
        # only if some path under it is something cleanup does not own.
        unowned = {
            path
            for path in findings["untracked_files"]
            if path not in set(junk_class.get("allowed_paths", []))
        }
        unrelated_changes = []
        for change in findings["uncommitted_changes"]:
            status, _, raw = change.partition(" ")
            path = raw.strip().strip('"')
            if status == "??":
                if any(p == path or p.startswith(path.rstrip("/") + "/") for p in unowned):
                    unrelated_changes.append(change)
            else:
                unrelated_changes.append(change)

        if unrelated_changes:
            log_warning(
                f"{len(unrelated_changes)} uncommitted changes are unrelated to this cleanup"
            )
            for change in unrelated_changes:
                log_warning(f"  {change}")

            if not force:
                if not confirm_action("Continue anyway?"):
                    log_info("Cleanup aborted; nothing was changed.")
                    return

        log_info("=" * 50)
        log_info("Cleanup Summary")
        log_info("=" * 50)
        log_info(f"Root strays for review:    {len(findings['root_strays'])}")
        log_info(f"Uncommitted changes:       {len(findings['uncommitted_changes'])}")
        log_info(f"Untracked files:           {len(findings['untracked_files'])}")
        log_info(f"Lexical review candidates: {len(findings['dead_files'])}")
        log_info(f"Potentially outdated docs: {len(findings['outdated_docs'])}")
        log_info(f"Script scanability repairs: {len(findings['script_scanability'])}")
        log_info(f"Public-readiness blockers: {len(findings['public_readiness'].get('blockers', []))}")
        log_info(f"Quality-gate blockers: {len(findings['quality_gate'].get('blockers', []))}")
        log_info("=" * 50)

        log_info("Starting cleanup...")
        actions_taken = execute_cleanup(findings, force=force)

        if actions_taken:
            log_cleanup(findings, actions_taken)
            log_info("Cleanup logged to: local/CLEANUP_LOG.md")

        receipt_path = write_phase_receipt(
            build_phase_receipt(findings, readiness, actions_taken), receipt
        )
        log_info(f"Phase receipt written to: {receipt_path}")
        log_info(f"Cleanup complete. {len(actions_taken)} actions taken.")
        return

    # Default: Show summary
    log_info("=" * 50)
    log_info("Cleanup Assessment")
    log_info("=" * 50)
    log_info(f"Root strays for review:    {len(findings['root_strays'])}")
    log_info(f"Uncommitted changes:       {len(findings['uncommitted_changes'])}")
    log_info(f"Untracked files:           {len(findings['untracked_files'])}")
    log_info(f"Lexical review candidates: {len(findings['dead_files'])}")
    log_info(f"Potentially outdated docs: {len(findings['outdated_docs'])}")
    log_info(f"Script scanability repairs: {len(findings['script_scanability'])}")
    log_info(f"Public-readiness blockers: {len(findings['public_readiness'].get('blockers', []))}")
    log_info(f"Quality-gate blockers: {len(findings['quality_gate'].get('blockers', []))}")
    log_info("=" * 50)
    for phase_name, state in findings["mutation_readiness"]["phases"].items():
        log_info(f"{phase_name}: {state}")
    log_info(f"Phase receipt: {receipt_path}")
    log_info("=" * 50)
    log_info("")
    log_info("Use --dry-run for JSON output")
    log_info("Use --plan to generate a cleanup plan")
    log_info("Use --worktree-audit to classify dirty worktree entries before commit")
    log_info("Use --registered-worktree-audit to audit every registered secondary worktree")
    log_info("Use --script-scanability to run only the script readability pass")
    log_info("Use --public-readiness to run only the security/public-readiness pass")
    log_info("Use --quality-gate to run only selected parse/lint/type/test checks")
    log_info("Use --memory-index to refresh ingest-code search artifacts")
    log_info("Use --execute to remove cleared untracked junk (with confirmation)")
    log_info("Use --execute --force to skip junk confirmation prompts")
    log_info("Root artifacts, root strays, and tracked candidates are review-only")


if __name__ == "__main__":
    app()
