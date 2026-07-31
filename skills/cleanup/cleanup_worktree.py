"""Dirty-worktree triage. Classifies git status entries into ownership and risk buckets so agents do not blindly stage unrelated work."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import shutil
import subprocess
import json
import shlex
import sys
import time
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


def write_worktree_audit_outputs(audit: Dict[str, Any], output: str) -> Dict[str, str]:
    """Write current-checkout dirty-worktree audit JSON and Markdown."""
    output_path = Path(output)
    if output_path.suffix.lower() not in {".json", ".md"}:
        output_path = output_path.with_suffix(".json")
    json_path = output_path if output_path.suffix.lower() == ".json" else output_path.with_suffix(".json")
    md_path = output_path if output_path.suffix.lower() == ".md" else output_path.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(audit, indent=2, default=str))
    md_path.write_text(generate_worktree_audit_markdown(audit))
    return {"json": str(json_path), "markdown": str(md_path)}


def parse_registered_worktrees(porcelain: str) -> List[Dict[str, Any]]:
    """Parse `git worktree list --porcelain` records."""
    records: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    for raw in porcelain.splitlines() + [""]:
        line = raw.strip()
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line.removeprefix("worktree ")
        elif line.startswith("HEAD "):
            current["head"] = line.removeprefix("HEAD ")
        elif line.startswith("branch "):
            current["branch"] = line.removeprefix("branch ")
        elif line == "detached":
            current["detached"] = True
        elif line == "bare":
            current["bare"] = True
        elif line.startswith("prunable"):
            current["prunable"] = True
            current["prunable_reason"] = line.removeprefix("prunable").strip()
    return records


def _is_under_tmp(path: str) -> bool:
    try:
        return Path(path).resolve().is_relative_to(Path("/tmp").resolve())
    except (OSError, RuntimeError):
        return path.startswith("/tmp/")


def _shell_join(args: List[str]) -> str:
    return " ".join(shlex.quote(str(arg)) for arg in args)


def _rescue_branch_name(project: str, path: str) -> str:
    safe_project = re.sub(r"[^A-Za-z0-9._-]+", "-", project).strip("-") or "repo"
    digest = hashlib.sha1(path.encode("utf-8")).hexdigest()[:10]
    date = datetime.now().strftime("%Y%m%d")
    return f"cleanup-rescue/{safe_project}/{date}/{digest}"


def _worktree_status(path: str, prunable: bool) -> Dict[str, Any]:
    if prunable or not Path(path).is_dir():
        return {"available": False, "entries": [], "error": "missing_or_prunable"}
    ok, output = run_command(["git", "-C", path, "status", "--porcelain=v1"], check=False)
    if not ok:
        return {"available": False, "entries": [], "error": "git_status_failed"}
    entries = parse_porcelain_status([line for line in output.splitlines() if line])
    return {"available": True, "entries": entries, "error": ""}


def _active_cwd_snapshot(limit: int = 2000, timeout_seconds: float = 1.0) -> List[Dict[str, str]]:
    """Snapshot process cwd values once for all registered-worktree checks."""
    deadline = time.monotonic() + timeout_seconds
    processes: List[Dict[str, str]] = []
    proc = Path("/proc")
    if not proc.exists():
        return processes
    for pid_dir in proc.iterdir():
        if len(processes) >= limit or time.monotonic() > deadline or not pid_dir.name.isdigit():
            continue
        try:
            cwd = os.path.realpath(os.readlink(pid_dir / "cwd")).rstrip(os.sep)
            cmdline = (pid_dir / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            processes.append({"pid": pid_dir.name, "cwd": cwd, "command": cmdline[:240]})
        except (FileNotFoundError, PermissionError, OSError, RuntimeError):
            continue
    return processes


def _processes_under_path(processes: List[Dict[str, str]], path: str, limit: int = 8) -> List[Dict[str, str]]:
    root = os.path.realpath(path).rstrip(os.sep)
    found = [
        process for process in processes
        if process.get("cwd") == root or process.get("cwd", "").startswith(root + os.sep)
    ]
    return found[:limit]


def _active_cwd_processes(path: str, limit: int = 8, timeout_seconds: float = 1.0) -> List[Dict[str, str]]:
    """Return processes whose cwd is inside one registered worktree."""
    return _processes_under_path(_active_cwd_snapshot(timeout_seconds=timeout_seconds), path, limit=limit)


def _registered_worktree_commands(path: str, branch: str, clean_removal: bool) -> Dict[str, List[str]]:
    rescue = [
        _shell_join(["git", "-C", path, "switch", "-c", branch]),
        _shell_join(["git", "-C", path, "add", "-A"]),
        _shell_join(["git", "-C", path, "commit", "-m", f"Rescue worktree changes from {Path(path).name}"]),
        _shell_join(["git", "-C", path, "push", "origin", f"HEAD:refs/heads/{branch}"]),
    ]
    remove = [_shell_join(["git", "worktree", "remove", path]), "git worktree prune"] if clean_removal else []
    return {"rescue_branch": rescue, "remove_after_rescue_or_review": remove}


def build_registered_worktree_audit() -> Dict[str, Any]:
    """Audit every registered git worktree and produce rescue/prune guidance."""
    ok, repo_root = run_command(["git", "rev-parse", "--show-toplevel"], check=False)
    if not ok or not repo_root.strip():
        return {
            "schema": "cleanup.registered_worktrees.v1",
            "status": "error",
            "error": "not_a_git_repository",
            "worktrees": [],
            "blockers": [],
        }
    repo_root = repo_root.strip()
    ok, output = run_command(["git", "worktree", "list", "--porcelain"], check=False)
    if not ok:
        return {
            "schema": "cleanup.registered_worktrees.v1",
            "status": "error",
            "error": "git_worktree_list_failed",
            "repo_root": repo_root,
            "worktrees": [],
            "blockers": [],
        }

    project = get_project_name()
    worktrees: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []
    records = parse_registered_worktrees(output)
    process_snapshot = _active_cwd_snapshot()
    for record in records:
        path = record.get("path", "")
        prunable = bool(record.get("prunable"))
        status = _worktree_status(path, prunable)
        active = [] if prunable else _processes_under_path(process_snapshot, path)
        dirty_entries = status.get("entries", [])
        is_current = Path(path).resolve() == Path(repo_root).resolve()
        branch = _rescue_branch_name(project, path)
        remove_candidate = (
            not is_current and not active and not dirty_entries
            and (prunable or record.get("detached") or _is_under_tmp(path))
        )
        if prunable:
            bucket, action, risk = "prunable_registration", "git_worktree_prune_after_review", "medium"
        elif is_current:
            bucket, action, risk = "primary_checkout", "leave_in_place", "low"
        elif active:
            bucket, action, risk = "active_process_review", "do_not_remove_while_process_cwd_is_inside", "high"
        elif dirty_entries:
            bucket, action, risk = "dirty_secondary_rescue_required", "rescue_to_branch_before_remove", "high"
        elif remove_candidate:
            bucket, action, risk = "clean_secondary_remove_candidate", "remove_after_review_then_prune", "medium"
        else:
            bucket, action, risk = "secondary_review", "review_owner_before_remove", "medium"

        item = {
            **record,
            "is_current_checkout": is_current,
            "under_tmp": _is_under_tmp(path),
            "dirty_count": len(dirty_entries),
            "dirty_entries": dirty_entries[:50],
            "active_processes": active,
            "bucket": bucket,
            "recommended_action": action,
            "risk": risk,
            "rescue_branch": branch if dirty_entries else "",
            "commands": _registered_worktree_commands(path, branch, remove_candidate or bool(dirty_entries)),
        }
        worktrees.append(item)
        if dirty_entries and not is_current:
            blockers.append({
                "id": "dirty_secondary_worktree_requires_rescue",
                "path": path,
                "dirty_count": len(dirty_entries),
                "valid_next_action": "Commit to the proposed rescue branch and push before removing the worktree.",
            })
        if active and not is_current:
            blockers.append({
                "id": "active_process_in_registered_worktree",
                "path": path,
                "process_count": len(active),
                "valid_next_action": "Exclude this worktree until the owning process exits or hands off its work.",
            })

    counts = Counter(item["bucket"] for item in worktrees)
    summary = {
        "total": len(worktrees),
        "secondary": sum(1 for item in worktrees if not item["is_current_checkout"]),
        "dirty_secondary": sum(1 for item in worktrees if item["dirty_count"] and not item["is_current_checkout"]),
        "under_tmp": sum(1 for item in worktrees if item["under_tmp"] and not item["is_current_checkout"]),
        "detached": sum(1 for item in worktrees if item.get("detached")),
        "prunable": sum(1 for item in worktrees if item.get("prunable")),
        "active": sum(1 for item in worktrees if item["active_processes"]),
        "by_bucket": dict(sorted(counts.items())),
    }
    status = "blocked" if blockers else "ready_for_review"
    return {
        "schema": "cleanup.registered_worktrees.v1",
        "generated_at": datetime.now().isoformat(),
        "status": status,
        "mutation": "no_authorized_mutations",
        "repo_root": repo_root,
        "summary": summary,
        "blockers": blockers,
        "worktrees": worktrees,
        "non_claims": [
            "This audit does not prove uncommitted work belongs on main.",
            "This audit does not remove worktrees, prune registrations, or push rescue branches.",
        ],
    }


def generate_registered_worktree_audit_markdown(audit: Dict[str, Any]) -> str:
    lines = [
        "# Registered Worktree Rescue Audit",
        "",
        f"Generated: {audit.get('generated_at', '')}",
        f"Repo root: `{audit.get('repo_root', '')}`",
        f"Status: `{audit.get('status', 'unknown')}`",
        f"Mutation: `{audit.get('mutation', 'no_authorized_mutations')}`",
        "",
        "## Summary",
        "",
    ]
    summary = audit.get("summary", {})
    for key in ("total", "secondary", "dirty_secondary", "under_tmp", "detached", "prunable", "active"):
        lines.append(f"- {key}: {summary.get(key, 0)}")
    for bucket, count in summary.get("by_bucket", {}).items():
        lines.append(f"- {bucket}: {count}")
    lines.extend(["", "## Findings", ""])
    for item in audit.get("worktrees", []):
        lines.append(f"### `{item.get('path', '')}`")
        lines.append("")
        lines.append(f"- Bucket: `{item.get('bucket')}`")
        lines.append(f"- Risk: `{item.get('risk')}`")
        lines.append(f"- Dirty entries: `{item.get('dirty_count', 0)}`")
        lines.append(f"- Active cwd processes: `{len(item.get('active_processes') or [])}`")
        lines.append(f"- Recommended action: `{item.get('recommended_action')}`")
        if item.get("rescue_branch"):
            lines.append(f"- Rescue branch: `{item['rescue_branch']}`")
        commands = item.get("commands") or {}
        for label, command_list in commands.items():
            if command_list:
                lines.append(f"- {label}:")
                lines.extend(f"  - `{command}`" for command in command_list)
        lines.append("")
    lines.extend(["## Blockers", ""])
    blockers = audit.get("blockers") or []
    if not blockers:
        lines.append("- No dirty secondary or active-process blocker found.")
    for blocker in blockers:
        lines.append(
            f"- `{blocker.get('id')}` at `{blocker.get('path')}`: "
            f"{blocker.get('valid_next_action')}"
        )
    lines.extend([
        "",
        "## Non-Claims",
        "",
        "- This report does not prove uncommitted work belongs on `main`.",
        "- This report does not prove rescue commits pass project tests.",
        "- This report does not remove worktrees, prune registrations, or push rescue branches.",
        "",
    ])
    return "\n".join(lines)


def write_registered_worktree_audit_outputs(audit: Dict[str, Any], output: str) -> Dict[str, str]:
    """Write registered-worktree rescue audit JSON and Markdown."""
    output_path = Path(output)
    if output_path.suffix.lower() not in {".json", ".md"}:
        output_path = output_path.with_suffix(".json")
    json_path = output_path if output_path.suffix.lower() == ".json" else output_path.with_suffix(".json")
    md_path = output_path if output_path.suffix.lower() == ".md" else output_path.with_suffix(".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(audit, indent=2, default=str))
    md_path.write_text(generate_registered_worktree_audit_markdown(audit))
    return {"json": str(json_path), "markdown": str(md_path)}
