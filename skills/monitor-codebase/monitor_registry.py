#!/usr/bin/env python3
"""Registry helpers for monitor-codebase."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY = Path.home() / ".agent-inbox" / "projects.json"


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _registry_entries(path: Path, *, source: str, default_enabled: bool) -> list[dict[str, Any]]:
    data = _load_json(path)
    entries: list[dict[str, Any]] = []

    if isinstance(data, dict) and isinstance(data.get("projects"), list):
        for item in data["projects"]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            project_path = item.get("path")
            if not name or not project_path:
                continue
            entries.append(
                {
                    "name": name,
                    "path": str(project_path),
                    "enabled": bool(item.get("enabled", default_enabled)),
                    "source": source,
                }
            )
        return entries

    if isinstance(data, dict):
        for name, project_path in data.items():
            if isinstance(project_path, dict):
                raw_path = project_path.get("path")
                enabled = bool(project_path.get("enabled", default_enabled))
            else:
                raw_path = project_path
                enabled = default_enabled
            if not raw_path:
                continue
            entries.append(
                {
                    "name": str(name),
                    "path": str(raw_path),
                    "enabled": enabled,
                    "source": source,
                }
            )

    return entries


def _git_root(path: Path) -> Path:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return path.resolve()
    return Path(proc.stdout.strip()).resolve()


def audit_registry(
    registry: Path,
    inbox: Path | None = None,
    *,
    include_agent_inbox: bool = False,
) -> dict[str, Any]:
    entries = _registry_entries(registry, source="monitor-registry", default_enabled=True)

    if include_agent_inbox:
        entries.extend(
            _registry_entries(
                inbox or DEFAULT_REGISTRY,
                source="agent-inbox",
                default_enabled=False,
            )
        )

    seen_roots: dict[str, str] = {}
    projects: list[dict[str, Any]] = []
    counts = {"enabled": 0, "disabled": 0, "missing": 0, "duplicates": 0}

    for entry in entries:
        project_path = Path(os.path.expanduser(str(entry["path"]))).resolve()
        exists = project_path.exists()
        enabled = bool(entry["enabled"])
        duplicate_of: str | None = None
        root = project_path

        if exists:
            root = _git_root(project_path)
            root_key = str(root)
            if root_key in seen_roots:
                duplicate_of = seen_roots[root_key]
                enabled = False
            elif enabled:
                seen_roots[root_key] = str(entry["name"])
        else:
            enabled = False

        if not exists:
            counts["missing"] += 1
        elif duplicate_of:
            counts["duplicates"] += 1
        elif enabled:
            counts["enabled"] += 1
        else:
            counts["disabled"] += 1

        item = {
            "name": str(entry["name"]),
            "path": str(project_path),
            "root": str(root),
            "enabled": enabled,
            "exists": exists,
            "source": str(entry["source"]),
        }
        if duplicate_of:
            item["duplicate_of"] = duplicate_of
        projects.append(item)

    return {
        "registry": str(registry),
        "projects": projects,
        "enabled_projects": [item["name"] for item in projects if item["enabled"]],
        "counts": counts,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect monitor-codebase registry")
    parser.add_argument("command", choices=("audit", "list-enabled"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--inbox", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--include-agent-inbox", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    audit = audit_registry(
        args.registry,
        inbox=args.inbox,
        include_agent_inbox=args.include_agent_inbox,
    )

    if args.command == "list-enabled":
        for name in audit["enabled_projects"]:
            print(name)
    else:
        print(json.dumps(audit, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
