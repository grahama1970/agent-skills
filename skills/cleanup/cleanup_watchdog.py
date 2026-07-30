"""Project-watchdog registry context. Read-only: cleanup never ticks the watchdog, leases an issue, or treats issues as cleanup candidates."""

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


