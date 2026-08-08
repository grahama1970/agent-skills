#!/usr/bin/env python3
"""project_registry - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=False)
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parents[1]
EXPERIMENTS_ROOT = Path(os.environ.get("WORKSPACE_ROOT", REPO_ROOT.parent))
REGISTRY_PATH = SKILL_DIR / "projects.v1.json"


def load_registry() -> dict:
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schema") != "ux_lab.project_registry.v1":
        raise SystemExit("unsupported UX Lab project registry schema")
    projects = data.get("projects")
    if not isinstance(projects, list) or not projects:
        raise SystemExit("project registry must contain at least one project")
    seen: set[str] = set()
    for project in projects:
        project_id = project.get("id")
        if not project_id or project_id in seen:
            raise SystemExit(f"invalid or duplicate project id: {project_id!r}")
        seen.add(project_id)
        surfaces = project.get("surfaces")
        if not isinstance(surfaces, list) or not surfaces:
            raise SystemExit(f"project {project_id} must define at least one surface")
        surface_ids: set[str] = set()
        for surface in surfaces:
            surface_id = surface.get("id")
            if not surface_id or surface_id in surface_ids:
                raise SystemExit(f"project {project_id} has invalid surface id: {surface_id!r}")
            if not surface.get("url"):
                raise SystemExit(f"project {project_id} surface {surface_id} is missing url")
            surface_ids.add(surface_id)
    return data


def expand_url(url: str) -> str:
    port = os.environ.get("UX_LAB_PORT", "3002")
    return url.replace("${UX_LAB_PORT:-3002}", port)


def projects_by_id(registry: dict) -> dict[str, dict]:
    return {project["id"]: project for project in registry["projects"]}


def select_project(registry: dict, project_id: str | None) -> dict:
    chosen = project_id or registry.get("default_project")
    projects = projects_by_id(registry)
    if chosen not in projects:
        raise SystemExit(f"unknown UX Lab project: {chosen}")
    return projects[chosen]


def select_surface(project: dict, surface_id: str | None) -> dict:
    surfaces = {surface["id"]: surface for surface in project["surfaces"]}
    chosen = surface_id or "hub"
    if chosen not in surfaces:
        if surface_id is None:
            return project["surfaces"][0]
        raise SystemExit(f"unknown surface for {project['id']}: {chosen}")
    return surfaces[chosen]


def workspace_path(project: dict) -> Path:
    workspace = project.get("workspace", "")
    if workspace == "agent-skills":
        return REPO_ROOT.resolve()
    if workspace.startswith("agent-skills/"):
        return (REPO_ROOT / workspace.removeprefix("agent-skills/")).resolve()
    return (EXPERIMENTS_ROOT / workspace).resolve()


def cmd_list(args: argparse.Namespace) -> int:
    registry = load_registry()
    if args.json:
        payload = {
            "schema": "ux_lab.project_list.v1",
            "projects": [
                {
                    "id": project["id"],
                    "label": project.get("label", project["id"]),
                    "workspace": str(workspace_path(project)),
                    "surfaces": [
                        {
                            **surface,
                            "url": expand_url(surface["url"]),
                        }
                        for surface in project["surfaces"]
                    ],
                }
                for project in registry["projects"]
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    for project in registry["projects"]:
        print(f"{project['id']}\t{project.get('label', project['id'])}")
        for surface in project["surfaces"]:
            marker = "mounted" if surface.get("mounted") else "declared"
            print(f"  {surface['id']}\t{marker}\t{expand_url(surface['url'])}")
    return 0


def cmd_url(args: argparse.Namespace) -> int:
    registry = load_registry()
    project = select_project(registry, args.project)
    surface = select_surface(project, args.surface)
    print(expand_url(surface["url"]))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    registry = load_registry()
    projects = registry["projects"]
    if args.project:
        projects = [select_project(registry, args.project)]
    payload = {
        "schema": "ux_lab.project_status.v1",
        "projects": [
            {
                "id": project["id"],
                "workspace": str(workspace_path(project)),
                "workspace_exists": workspace_path(project).exists(),
                "surface_count": len(project["surfaces"]),
                "mounted_surface_count": sum(1 for s in project["surfaces"] if s.get("mounted")),
            }
            for project in projects
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    missing = [p for p in payload["projects"] if not p["workspace_exists"]]
    return 1 if missing else 0


def cmd_start_project(args: argparse.Namespace) -> int:
    registry = load_registry()
    project = select_project(registry, args.project)
    start = project.get("start")
    if not start:
        raise SystemExit(f"project {project['id']} does not declare a start command")
    cwd = (EXPERIMENTS_ROOT / start["cwd"]).resolve()
    if start["cwd"] == "agent-skills" or start["cwd"].startswith("agent-skills/"):
        cwd = (REPO_ROOT / start["cwd"].removeprefix("agent-skills/")).resolve()
    if not cwd.exists():
        raise SystemExit(f"project start cwd is missing: {cwd}")
    command = start.get("command")
    if not isinstance(command, list) or not command:
        raise SystemExit(f"project {project['id']} has invalid start command")
    os.execvp(command[0], command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UX Lab project registry")
    sub = parser.add_subparsers(dest="command", required=True)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=cmd_list)
    url_parser = sub.add_parser("url")
    url_parser.add_argument("project", nargs="?")
    url_parser.add_argument("surface", nargs="?")
    url_parser.set_defaults(func=cmd_url)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("project", nargs="?")
    status_parser.set_defaults(func=cmd_status)
    start_parser = sub.add_parser("start-project")
    start_parser.add_argument("project")
    start_parser.set_defaults(func=cmd_start_project)
    validate_parser = sub.add_parser("validate")
    validate_parser.set_defaults(func=lambda _args: 0 if load_registry() else 1)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
