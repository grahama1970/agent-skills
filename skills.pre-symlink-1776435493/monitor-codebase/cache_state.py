#!/usr/bin/env python3
"""Hourly project-state cache job for monitor-codebase.

Reads registered projects from ~/.agent-inbox/projects.json, compares
git HEAD hashes against stored values in ~/.pi/monitor-codebase/state_hashes.json,
and only runs `project-state report --quick --json` for projects whose HEAD changed.
"""

import os
import json
import subprocess
import sys
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(help="Cache project state only when git HEAD changes.")

PROJECTS_FILE = Path.home() / ".agent-inbox" / "projects.json"
STATE_DIR = Path.home() / ".pi" / "monitor-codebase"
HASHES_FILE = STATE_DIR / "state_hashes.json"
SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent
PROJECT_STATE_SCRIPT = SKILLS_DIR / "project-state" / "run.sh"


def _load_projects() -> dict[str, str]:
    """Load project name -> path mapping from projects.json."""
    if not PROJECTS_FILE.exists():
        logger.error("Projects registry not found: {}", PROJECTS_FILE)
        return {}
    with open(PROJECTS_FILE) as f:
        return json.load(f)


def _load_hashes() -> dict[str, str]:
    """Load previously stored git hashes."""
    if not HASHES_FILE.exists():
        return {}
    with open(HASHES_FILE) as f:
        return json.load(f)


def _save_hashes(hashes: dict[str, str]) -> None:
    """Persist git hashes to disk."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(HASHES_FILE, "w") as f:
        json.dump(hashes, f, indent=2)
        f.write("\n")


def _get_git_head(project_path: str) -> str | None:
    """Return git HEAD hash for a project, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=10,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _run_project_state(project_name: str, project_path: str) -> dict | None:
    """Run project-state report --quick --json and return parsed output."""
    if not PROJECT_STATE_SCRIPT.exists():
        logger.warning("project-state skill not found at {}", PROJECT_STATE_SCRIPT)
        return None
    try:
        result = subprocess.run(
            [str(PROJECT_STATE_SCRIPT), "report", "--quick", "--json"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        logger.warning(
            "project-state returned code {} for {}",
            result.returncode,
            project_name,
        )
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        logger.error("project-state failed for {}: {}", project_name, exc)
        return None


def _save_checkpoint(project_name: str, data: dict) -> Path:
    """Save a project-state checkpoint to the state dir."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out = STATE_DIR / f"{project_name}_checkpoint.json"
    with open(out, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return out


@app.command()
def cache_state(
    project: list[str] | None = typer.Argument(
        None, help="Specific project(s) to check. Omit to check all."
    ),
    force: bool = typer.Option(False, "--force", help="Force refresh even if hash unchanged."),
) -> None:
    """Compare git HEAD hashes and refresh project-state for changed projects."""
    projects = _load_projects()
    if not projects:
        logger.error("No projects loaded — nothing to do.")
        raise typer.Exit(1)

    stored_hashes = _load_hashes()
    updated_hashes = dict(stored_hashes)

    # Filter to requested projects if specified
    if project:
        filtered = {}
        for p in project:
            if p in projects:
                filtered[p] = projects[p]
            else:
                logger.warning("Project '{}' not found in registry — skipping", p)
        projects = filtered

    changed = 0
    skipped = 0

    for name, path in sorted(projects.items()):
        if not Path(path).is_dir():
            logger.warning("{}: path does not exist ({}), skipping", name, path)
            skipped += 1
            continue

        current_hash = _get_git_head(path)
        if current_hash is None:
            logger.info("{}: not a git repo, skipping", name)
            skipped += 1
            continue

        previous_hash = stored_hashes.get(name)

        if current_hash == previous_hash and not force:
            logger.info("{}: no changes ({})", name, current_hash[:8])
            skipped += 1
            continue

        logger.info(
            "{}: hash changed {} -> {}",
            name,
            (previous_hash or "none")[:8],
            current_hash[:8],
        )
        state_data = _run_project_state(name, path)
        if state_data is not None:
            checkpoint = _save_checkpoint(name, state_data)
            logger.info("{}: checkpoint saved to {}", name, checkpoint)
        else:
            logger.warning("{}: project-state produced no output, hash still updated", name)

        updated_hashes[name] = current_hash
        changed += 1

    _save_hashes(updated_hashes)
    logger.info("Done: {} changed, {} skipped", changed, skipped)


if __name__ == "__main__":
    app()
