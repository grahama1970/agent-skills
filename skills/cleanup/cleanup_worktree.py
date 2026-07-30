"""Dirty-worktree triage. Classifies git status entries into ownership and risk buckets so agents do not blindly stage unrelated work."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import subprocess
import json
import sys
from collections import Counter
from pathlib import Path
from datetime import datetime
from typing import Any, List, Dict, Set, Tuple, Optional

from cleanup_core import *  # noqa: F401,F403  shared constants and helpers
from cleanup_core import (
    log_error, log_info, log_warning, run_command, read_file_content,
    get_all_tracked_files, is_cleanup_output,
)
from cleanup_watchdog import scan_project_watchdog_context


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

