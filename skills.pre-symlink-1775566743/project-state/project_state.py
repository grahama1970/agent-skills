#!/usr/bin/env python3
"""Comprehensive Embry OS project state report.

Full assessment pipeline:
  Phase 1: Infrastructure -- daemons, tests, cascade, classifiers, skills
  Phase 1b: Component Projects -- health of registered helper repos (embry.yaml)
  Phase 2: Memory -- query /memory for known features, architecture, status
  Phase 3: Doc-Code Drift -- compare doc claims vs actual codebase
  Phase 4: Best Practices -- scan for anti-patterns (Python, React, Skills)
  Phase 5: Competitive Landscape -- /dogpile for external research (--full only)
  Phase 6: Gap Analysis -- synthesize all phases into actionable gaps

Usage:
    python project_state.py                  # Phases 1-4 + 6
    python project_state.py --quick          # Phase 1 only (infra metrics)
    python project_state.py --full           # All phases including dogpile
    python project_state.py --json           # JSON output
    python project_state.py --output FILE    # Write to file

This file is the CLI entry point.  All logic lives in sub-modules:
  constants, infrastructure, components, memory_recall, doc_drift,
  best_practices, research, gap_analysis, report, figures.
"""

from __future__ import annotations
import os

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from loguru import logger

# Ensure sibling modules are importable when run as a script
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import typer

# ── Re-exports (backwards compatibility) ─────────────────────────────────────
# Any external code that did ``from project_state import collect_daemons`` etc.
# will continue to work.

from best_practices import collect_best_practices  # noqa: F401
from components import collect_components  # noqa: F401
from constants import (  # noqa: F401
    BEST_PRACTICE_SKILLS,
    CLASSIFIERS_DIR,
    CREATE_FIGURE_SKILL,
    DAEMON_SOCKETS,
    DOC_FILES,
    EMBRY_OS,
    EMBRY_YAML,
    MEMORY_SKILL,
    PI_SKILLS,
    REGISTRY_PATH,
    SHADOW_JSONL,
    TRAINING_DIR,
)
from doc_drift import collect_doc_drift  # noqa: F401
from figures import generate_figures  # noqa: F401
from gap_analysis import compute_gaps  # noqa: F401
from infrastructure import (  # noqa: F401
    collect_cascade,
    collect_daemon_cascade_wiring,
    collect_daemons,
    collect_deploy,
    collect_frontend,
    collect_skills,
    collect_tests,
)
from memory_recall import collect_memory  # noqa: F401
from report import format_markdown, generate_report  # noqa: F401
from research import collect_competitive  # noqa: F401

# ── Checkpoint integration ───────────────────────────────────────────────────

_CHECKPOINT_CACHE_MAX_AGE = 3600  # 1 hour in seconds


def _find_checkpoint_path() -> Optional[Path]:
    """Locate the checkpoint skill's run.sh."""
    candidates = [
        _THIS_DIR.parent / "checkpoint" / "run.sh",  # .pi/skills/checkpoint/run.sh
        Path.home() / ".claude" / "skills" / "checkpoint" / "run.sh",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _detect_project_name() -> str:
    """Derive project name from git remote or directory name."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            name = result.stdout.strip().rstrip("/").rsplit("/", 1)[-1]
            if name.endswith(".git"):
                name = name[:-4]
            return name
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return Path.cwd().name


def _checkpoint_save(report_json: str, project_name: str) -> bool:
    """Save a project-state checkpoint via the checkpoint skill."""
    cp_path = _find_checkpoint_path()
    if not cp_path:
        logger.warning("Checkpoint skill not found, skipping save")
        return False

    topic = f"project-state {project_name}"
    try:
        result = subprocess.run(
            [str(cp_path), "save", "--topic", topic, "--summary", report_json],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            logger.info("Checkpoint saved for topic '{}'", topic)
            return True
        logger.warning("Checkpoint save failed: {}", result.stderr.strip())
        return False
    except subprocess.TimeoutExpired:
        logger.warning("Checkpoint save timed out")
        return False


def _checkpoint_recall(project_name: str) -> Optional[str]:
    """Recall the latest project-state checkpoint. Returns the summary if fresh (< 1h), else None."""
    cp_path = _find_checkpoint_path()
    if not cp_path:
        logger.warning("Checkpoint skill not found, skipping recall")
        return None

    topic = f"project-state {project_name}"
    try:
        result = subprocess.run(
            [str(cp_path), "recall", "--topic", topic, "--limit", "1", "--json"],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            logger.debug("Checkpoint recall failed: {}", result.stderr.strip())
            return None

        # Parse the JSON output from stderr (Rich console prints to stderr)
        output = result.stderr.strip() or result.stdout.strip()
        if not output:
            return None

        # Find the JSON in the output
        for i, ch in enumerate(output):
            if ch in ("{", "["):
                try:
                    data = json.loads(output[i:])
                    break
                except json.JSONDecodeError:
                    continue
        else:
            return None

        # Handle list (array of checkpoints) or single dict
        if isinstance(data, list):
            if not data:
                return None
            data = data[0]

        # Check freshness via timestamp
        timestamp = data.get("timestamp", "")
        if not timestamp:
            return None

        try:
            from datetime import datetime, timezone
            # Parse ISO 8601 timestamp
            cp_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            age = time.time() - cp_time.timestamp()
            if age > _CHECKPOINT_CACHE_MAX_AGE:
                logger.info("Cached checkpoint is {:.0f}s old (> {}s), stale", age, _CHECKPOINT_CACHE_MAX_AGE)
                return None
        except (ValueError, TypeError):
            logger.debug("Could not parse checkpoint timestamp: {}", timestamp)
            return None

        # Return the summary (which is the full report JSON)
        summary = data.get("summary", "")
        return summary if summary else None

    except subprocess.TimeoutExpired:
        logger.warning("Checkpoint recall timed out")
        return None


# ── CLI ──────────────────────────────────────────────────────────────────────

app = typer.Typer(help="Embry OS comprehensive project state")


@app.command("report")
def cmd_report(
    quick: bool = typer.Option(False, "--quick", help="Phase 1 only (infra metrics)"),
    full: bool = typer.Option(False, "--full", help="All phases including competitive research"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Write to file instead of stdout"),
    figures: Optional[str] = typer.Option(None, "--figures", help="Generate figures to this directory"),
    cached: bool = typer.Option(False, "--cached", help="Return cached checkpoint if fresh (< 1 hour), otherwise run live and save"),
    force: bool = typer.Option(False, "--force", help="Always run live and save a checkpoint after collection"),
):
    # --cached: try to return a fresh cached checkpoint first
    if cached:
        project_name = _detect_project_name()
        cached_result = _checkpoint_recall(project_name)
        if cached_result:
            logger.info("Returning cached project-state checkpoint")
            # Try to parse as JSON for --json or markdown formatting
            try:
                report = json.loads(cached_result)
                if json_output:
                    text = json.dumps(report, indent=2)
                else:
                    text = format_markdown(report)
            except (json.JSONDecodeError, TypeError):
                # Raw text fallback
                text = cached_result

            if output:
                Path(output).write_text(text + "\n")
                print(f"Report written to {output} (from cache)")
            else:
                print(text)
            return
        logger.info("No fresh cached checkpoint, running live")

    report = generate_report(quick=quick, full=full)

    if json_output:
        text = json.dumps(report, indent=2)
    else:
        text = format_markdown(report)

    if output:
        Path(output).write_text(text + "\n")
        print(f"Report written to {output}")
    else:
        print(text)

    if figures:
        generated = generate_figures(report, figures)
        if generated:
            print(f"\nFigures generated ({len(generated)}):")
            for fig in generated:
                print(f"  {fig}")

    # --cached (cache miss) or --force: save checkpoint after live collection
    if cached or force:
        if not cached:
            project_name = _detect_project_name()
        report_json = json.dumps(report, indent=2)
        saved = _checkpoint_save(report_json, project_name)
        if saved:
            logger.info("Project-state checkpoint saved")
        else:
            logger.warning("Failed to save project-state checkpoint")


@app.command("figures")
def cmd_figures(
    input_file: str = typer.Argument(..., help="Path to JSON report from --json --output"),
    output_dir: str = typer.Option("./figures", "-o", "--output-dir", help="Output directory for figures"),
):
    """Generate figures from an existing JSON report."""
    data = json.loads(Path(input_file).read_text())
    generated = generate_figures(data, output_dir)
    if generated:
        print(f"Figures generated ({len(generated)}):")
        for fig in generated:
            print(f"  {fig}")
    else:
        print("No figures generated.")


if __name__ == "__main__":
    app()
