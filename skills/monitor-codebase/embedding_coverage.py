#!/usr/bin/env python3
"""Audit code symbol embedding coverage for monitor-codebase.

This checks the operational contract between /monitor-codebase and /ingest-code:
source files that should be indexed must have code_symbols records whose
semantic sync metadata points at Qdrant.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

SCHEMA_VERSION = 1
MEMORY_SOCKET_PATH = os.environ.get("MEMORY_SOCKET_PATH", "/run/user/1000/embry/memory.sock")

SCRIPT_SUFFIXES = {
    ".py",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".rs",
    ".go",
    ".java",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
}

SKIP_DIRS = {
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".git",
    ".tox",
    "dist",
    "build",
    "egg-info",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    "site-packages",
    ".uv",
    ".cache",
    "target",
}


def _load_monitor_config(project_root: Path) -> dict[str, Any]:
    config_path = project_root / ".monitor-codebase.json"
    if not config_path.exists():
        return {}

    try:
        data = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _scan_roots(project_root: Path) -> list[Path]:
    config = _load_monitor_config(project_root)
    roots = []
    for include_dir in config.get("include_dirs", []) or []:
        root = project_root / include_dir
        if root.is_dir():
            roots.append(root.resolve())
    return roots or [project_root.resolve()]


def _exclude_dirs(project_root: Path) -> set[str]:
    config = _load_monitor_config(project_root)
    extra = config.get("exclude_dirs", []) or []
    return SKIP_DIRS | {str(item) for item in extra}


def _is_git_repo(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(path),
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _is_relevant_script(path: Path, exclude_dirs: set[str]) -> bool:
    if path.name.endswith(".d.ts"):
        return False
    if path.suffix not in SCRIPT_SUFFIXES:
        return False
    return not (set(path.parts) & exclude_dirs)


def _is_in_scan_roots(path: Path, roots: list[Path]) -> bool:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _relative_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def collect_expected_files(project_root: Path) -> list[str]:
    """Collect files expected to have semantic code-symbol coverage."""
    roots = _scan_roots(project_root)
    exclude_dirs = _exclude_dirs(project_root)
    files: set[str] = set()

    if _is_git_repo(project_root):
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                candidate = (project_root / line).resolve()
                if _is_in_scan_roots(candidate, roots) and _is_relevant_script(candidate, exclude_dirs):
                    files.add(_relative_path(candidate, project_root))
            return sorted(files)

    for root in roots:
        for candidate in root.rglob("*"):
            if candidate.is_file() and _is_relevant_script(candidate, exclude_dirs):
                files.add(_relative_path(candidate, project_root))

    return sorted(files)


def _normalize_indexed_path(value: object, project_root: Path) -> str | None:
    if not value:
        return None
    path = Path(str(value))
    if path.is_absolute():
        return _relative_path(path, project_root)
    return path.as_posix()


def _fetch_code_symbols(scope: str, project_root: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Fetch code_symbols records for a monitor scope from memory."""
    socket_path = Path(MEMORY_SOCKET_PATH)
    if not socket_path.exists():
        return {}, {
            "queried": False,
            "error": f"memory socket not found: {socket_path}",
            "collection": "code_symbols",
        }

    docs_by_path: dict[str, list[dict[str, Any]]] = {}
    total = None
    offset = 0
    limit = 500
    pages = 0

    transport = httpx.HTTPTransport(uds=str(socket_path))
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
        while True:
            response = client.post(
                "/list",
                json={
                    "collection": "code_symbols",
                    "filters": {"scope": scope},
                    "return_fields": [
                        "path",
                        "symbol_name",
                        "qdrant_point_id",
                        "semantic_sync_state",
                        "qdrant_collection",
                    ],
                    "limit": limit,
                    "offset": offset,
                },
            )
            if response.status_code == 404:
                return {}, {
                    "queried": False,
                    "error": "code_symbols collection not found",
                    "collection": "code_symbols",
                }
            response.raise_for_status()
            payload = response.json()
            total = int(payload.get("total", 0) or 0)
            pages += 1

            for doc in payload.get("documents", []) or []:
                if not isinstance(doc, dict):
                    continue
                rel_path = _normalize_indexed_path(doc.get("path"), project_root)
                if not rel_path:
                    continue
                docs_by_path.setdefault(rel_path, []).append(doc)

            offset += limit
            if offset >= total:
                break

    return docs_by_path, {
        "queried": True,
        "collection": "code_symbols",
        "scope": scope,
        "total_symbols": total or 0,
        "pages": pages,
    }


def audit_embedding_coverage(project_root: Path, project_name: str, scope: str | None = None) -> dict[str, Any]:
    """Compare expected source files with Qdrant-synced code symbol records."""
    root = project_root.resolve()
    effective_scope = scope or f"monitor-{project_name}"
    expected_files = collect_expected_files(root)
    docs_by_path, memory = _fetch_code_symbols(effective_scope, root)

    indexed_files = sorted(set(docs_by_path) & set(expected_files))
    embedded_files = []
    unsynced_files = []
    for rel_path in indexed_files:
        docs = docs_by_path.get(rel_path, [])
        if any(doc.get("qdrant_point_id") and doc.get("semantic_sync_state") == "synced" for doc in docs):
            embedded_files.append(rel_path)
        else:
            unsynced_files.append(rel_path)

    missing_files = sorted(set(expected_files) - set(indexed_files))
    expected_count = len(expected_files)
    embedded_count = len(embedded_files)
    coverage_pct = (embedded_count / expected_count * 100.0) if expected_count else 100.0

    if not memory.get("queried"):
        status = "warn"
    elif expected_count == 0:
        status = "pass"
    elif embedded_count == 0:
        status = "fail"
    elif missing_files or unsynced_files:
        status = "warn"
    else:
        status = "pass"

    return {
        "schema_version": SCHEMA_VERSION,
        "project": str(root),
        "project_name": project_name,
        "scope": effective_scope,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "expected_files": expected_count,
        "indexed_files": len(indexed_files),
        "embedded_files": embedded_count,
        "missing_files_count": len(missing_files),
        "unsynced_files_count": len(unsynced_files),
        "coverage_pct": round(coverage_pct, 2),
        "missing_files": missing_files[:100],
        "unsynced_files": unsynced_files[:100],
        "memory": memory,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Qdrant code-symbol embedding coverage.")
    parser.add_argument("project_path", help="Project root to audit")
    parser.add_argument("--project-name", default="", help="Registered project name")
    parser.add_argument("--scope", default="", help="Memory scope; defaults to monitor-<project-name>")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    project_path = Path(args.project_path)
    project_name = args.project_name or project_path.resolve().name
    result = audit_embedding_coverage(
        project_path,
        project_name=project_name,
        scope=args.scope or None,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"{result['project_name']}: {result['coverage_pct']:.2f}% embedded "
            f"({result['embedded_files']}/{result['expected_files']} files, status={result['status']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
