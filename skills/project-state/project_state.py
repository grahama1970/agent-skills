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

from dotenv import load_dotenv
from loguru import logger

# Ensure sibling modules are importable when run as a script
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import typer

load_dotenv()

# ── Re-exports (backwards compatibility) ─────────────────────────────────────
# Any external code that did ``from project_state import collect_daemons`` etc.
# will continue to work.

from best_practices import collect_best_practices  # noqa: F401
from components import collect_components  # noqa: F401
from constants import (  # noqa: F401
    BEST_PRACTICE_SKILLS,
    BRAVE_SEARCH_SKILL,
    CLASSIFIERS_DIR,
    CREATE_FIGURE_SKILL,
    DAEMON_SOCKETS,
    DOC_FILES,
    DOGPILE_SKILL,
    EMBRY_OS,
    EMBRY_YAML,
    GITHUB_SEARCH_SKILL,
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

app = typer.Typer(help="Project state and readiness reporting")
config_app = typer.Typer(help="Configuration helpers")


@app.command("report")
def cmd_report(
    quick: bool = typer.Option(False, "--quick", help="Phase 1 only (infra metrics)"),
    full: bool = typer.Option(False, "--full", help="All phases including competitive research"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Write to file instead of stdout"),
    figures: Optional[str] = typer.Option(None, "--figures", help="Generate figures to this directory"),
    cached: bool = typer.Option(False, "--cached", help="Return cached checkpoint if fresh (< 1 hour), otherwise run live and save"),
    force: bool = typer.Option(False, "--force", help="Always run live and save a checkpoint after collection"),
    cleanup_tail: bool = typer.Option(False, "--cleanup-tail", help="Generate post-cleanup readiness state instead of the default report"),
    cleanup_receipt: Optional[Path] = typer.Option(None, "--cleanup-receipt", exists=True, file_okay=True, dir_okay=False, readable=True, help="Cleanup receipt JSON for --cleanup-tail"),
    project_root: Optional[Path] = typer.Option(None, "--project-root", exists=True, file_okay=False, dir_okay=True, readable=True, help="Project root to inspect for --cleanup-tail; defaults to cwd"),
    project_sanity_cmd: Optional[str] = typer.Option(None, "--project-sanity-cmd", help="Optional project-native sanity command to run from --project-root"),
    best_practices_check: list[str] = typer.Option([], "--best-practices-check", help="Best-practices command actually run during cleanup; repeatable"),
):
    if cleanup_tail:
        if cleanup_receipt is None:
            raise typer.BadParameter("--cleanup-receipt is required with --cleanup-tail")
        _emit_cleanup_tail(
            cleanup_receipt=cleanup_receipt,
            output_dir=None,
            output_file=Path(output) if output else None,
            json_output=json_output,
            quick=quick,
            project_root=project_root or Path.cwd(),
            project_sanity_cmd=project_sanity_cmd,
            best_practices_checks=best_practices_check,
        )
        return

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


def _run_id() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _html_escape(value: object) -> str:
    import html

    return html.escape(str(value), quote=True)


def _load_cleanup_receipt(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"cleanup receipt is not valid JSON: {exc}") from exc


def _extract_cleanup_counts(receipt: dict) -> dict[str, int]:
    def _count_any(*keys: str) -> int:
        for key in keys:
            value = receipt.get(key)
            if isinstance(value, list):
                return len(value)
            if isinstance(value, dict):
                return len(value)
            if isinstance(value, int):
                return value
        return 0

    return {
        "moved": _count_any("moved", "moved_files", "quarantined", "quarantined_files"),
        "kept": _count_any("kept", "kept_files", "protected", "protected_files"),
        "review_required": _count_any("review_required", "needs_review", "manual_review"),
    }


def _extract_cleanup_paths(receipt: dict) -> dict[str, list[str]]:
    def _paths_for(*keys: str) -> list[str]:
        paths: list[str] = []
        for key in keys:
            value = receipt.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        paths.append(item)
                    elif isinstance(item, dict):
                        candidate = item.get("path") or item.get("source") or item.get("file")
                        if candidate:
                            paths.append(str(candidate))
            elif isinstance(value, dict):
                for item_key, item_value in value.items():
                    if isinstance(item_value, str):
                        paths.append(item_value)
                    elif isinstance(item_value, dict):
                        candidate = item_value.get("path") or item_value.get("source") or item_value.get("file")
                        paths.append(str(candidate or item_key))
                    else:
                        paths.append(str(item_key))
        return sorted(dict.fromkeys(paths))

    return {
        "moved": _paths_for("moved", "moved_files", "quarantined", "quarantined_files"),
        "kept": _paths_for("kept", "kept_files", "protected", "protected_files"),
        "review_required": _paths_for("review_required", "needs_review", "manual_review"),
        "deleted": _paths_for("deleted", "deleted_files", "removed", "removed_files"),
    }


def _git_status_summary(project_root: Path) -> dict:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return {"available": False, "status": "timeout", "dirty": None, "path": str(project_root)}
    except Exception as exc:
        return {"available": False, "status": "error", "error": str(exc)[:200], "path": str(project_root)}

    if out.returncode != 0:
        return {"available": False, "status": "error", "error": out.stderr[:200], "path": str(project_root)}

    lines = [line for line in out.stdout.splitlines() if line]
    counts = {"modified": 0, "deleted": 0, "untracked": 0, "renamed": 0, "other": 0}
    paths = []
    for line in lines:
        code = line[:2]
        path = line[3:] if len(line) > 3 else line
        paths.append(path)
        if code == "??":
            counts["untracked"] += 1
        elif "D" in code:
            counts["deleted"] += 1
        elif "R" in code:
            counts["renamed"] += 1
        elif "M" in code:
            counts["modified"] += 1
        else:
            counts["other"] += 1
    return {
        "available": True,
        "status": "ok",
        "dirty": bool(lines),
        "changed_count": len(lines),
        "counts": counts,
        "sample_paths": paths[:50],
        "path": str(project_root),
    }


def _run_project_sanity(project_root: Path, command: Optional[str]) -> dict:
    if not command:
        return {
            "execution_status": "not_run",
            "assertion_status": "not_established",
            "reason": "no --project-sanity-cmd supplied",
        }
    try:
        out = subprocess.run(
            command,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=120,
            shell=True,
        )
    except subprocess.TimeoutExpired:
        return {
            "execution_status": "timeout",
            "assertion_status": "fail",
            "command": command,
        }
    return {
        "execution_status": "pass" if out.returncode == 0 else "fail",
        "assertion_status": "pass" if out.returncode == 0 else "fail",
        "command": command,
        "returncode": out.returncode,
        "stdout_tail": out.stdout[-1000:],
        "stderr_tail": out.stderr[-1000:],
    }


def _project_knowledge_status(project_root: Path) -> dict:
    candidates = [
        project_root / "docs" / "PROJECT_KNOWLEDGE.md",
        project_root / "PROJECT_KNOWLEDGE.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return {"status": "found", "path": str(candidate)}
    return {
        "status": "not_established",
        "safe_default": "update project knowledge after cleanup lessons are accepted",
        "paths_checked": [str(path) for path in candidates],
    }


def _best_practices_from_receipt(receipt: dict, explicit: list[str]) -> list[str]:
    found = list(explicit)
    for key in ("best_practices_checks", "best_practices_run", "best_practices"):
        value = receipt.get(key)
        if isinstance(value, list):
            found.extend(str(item) for item in value)
        elif isinstance(value, dict):
            found.extend(str(item) for item in value.keys())
        elif isinstance(value, str):
            found.append(value)
    return sorted(dict.fromkeys(item for item in found if item))


def _build_cleanup_tail_report(
    cleanup_receipt: Path,
    quick: bool,
    project_root: Path,
    project_sanity_cmd: Optional[str],
    best_practices_checks: list[str],
) -> dict:
    run_id = _run_id()
    receipt = _load_cleanup_receipt(cleanup_receipt)
    state = generate_report(quick=quick, full=False)
    counts = _extract_cleanup_counts(receipt)
    paths = _extract_cleanup_paths(receipt)
    git_status = _git_status_summary(project_root)
    sanity = _run_project_sanity(project_root, project_sanity_cmd)
    best_practices_run = _best_practices_from_receipt(receipt, best_practices_checks)
    knowledge = _project_knowledge_status(project_root)

    needs_attention = []
    if counts["moved"] > 0:
        needs_attention.append({
            "reason": "cleanup_moved_files_require_human_review",
            "safe_default": "do_not_delete_cleanup_quarantine",
            "resume_hint": "inspect the cleanup receipt and .cleanup manifest before deleting anything",
        })
    if counts["review_required"] > 0:
        needs_attention.append({
            "reason": "cleanup_receipt_has_review_required_items",
            "safe_default": "keep files in place or quarantine only",
            "resume_hint": "resolve each review_required item with usage evidence before pruning",
        })
    if sanity["assertion_status"] != "pass":
        needs_attention.append({
            "reason": "project_native_sanity_not_passed",
            "safe_default": "do_not_claim_cleanup_safe",
            "resume_hint": "rerun with --project-sanity-cmd after cleanup",
        })
    if not best_practices_run:
        needs_attention.append({
            "reason": "best_practices_checks_not_recorded",
            "safe_default": "treat best-practices coverage as NOT_ESTABLISHED",
            "resume_hint": "pass --best-practices-check for each relevant best-practices-* command that ran",
        })
    if knowledge["status"] != "found":
        needs_attention.append({
            "reason": "project_knowledge_not_found",
            "safe_default": "do not infer memory/project-knowledge sync",
            "resume_hint": "update docs/PROJECT_KNOWLEDGE.md and memory with cleanup lessons",
        })

    doc_drift = state.get("phase_3_doc_drift") if not quick else None
    unresolved = paths["review_required"] + paths["moved"]
    introduced_gaps = []
    if sanity["assertion_status"] == "fail" and (paths["moved"] or paths["deleted"]):
        introduced_gaps.append("project sanity failed after cleanup candidates were moved or deleted")

    return {
        "schema": "skill.readiness_report.v1",
        "run_id": run_id,
        "profile": "cleanup-tail-smoke" if quick else "cleanup-tail",
        "overall_readiness": "USABLE_WITH_GAPS" if needs_attention else "READY",
        "release_readiness": "NOT_ESTABLISHED",
        "needs_attention": needs_attention,
        "source_receipts": {"cleanup": str(cleanup_receipt)},
        "project_root": str(project_root),
        "features": [
            {
                "id": "cleanup-receipt-ingest",
                "readiness": "ready",
                "required_cases": 1,
                "passed_cases": 1,
                "coverage_gaps": [],
                "evidence": [str(cleanup_receipt)],
            },
            {
                "id": "repo-dirty-state-after-cleanup",
                "readiness": "ready" if git_status.get("available") else "not_established",
                "required_cases": 1,
                "passed_cases": 1 if git_status.get("available") else 0,
                "coverage_gaps": [] if git_status.get("available") else ["git status unavailable"],
                "evidence": [f"changed_count={git_status.get('changed_count', 'unknown')}"],
            },
            {
                "id": "project-native-sanity",
                "readiness": "ready" if sanity["assertion_status"] == "pass" else "not_established",
                "required_cases": 1,
                "passed_cases": 1 if sanity["assertion_status"] == "pass" else 0,
                "coverage_gaps": [] if sanity["assertion_status"] == "pass" else [sanity.get("reason", "sanity did not pass")],
                "evidence": [sanity.get("command", "no project sanity command supplied")],
            },
            {
                "id": "best-practices-checks-run",
                "readiness": "ready" if best_practices_run else "not_established",
                "required_cases": 1,
                "passed_cases": 1 if best_practices_run else 0,
                "coverage_gaps": [] if best_practices_run else ["no best-practices command recorded"],
                "evidence": best_practices_run,
            },
            {
                "id": "cleanup-delete-authority",
                "readiness": "safe_failure_only",
                "required_cases": 1,
                "passed_cases": 1,
                "coverage_gaps": ["project-state never authorizes deletion"],
                "evidence": ["no mutation command is executed by cleanup-tail"],
            },
        ],
        "cases": [
            {
                "id": "cleanup-receipt-json-loads",
                "feature": "cleanup-receipt-ingest",
                "case_type": "positive-control",
                "execution_status": "pass",
                "assertion_status": "pass",
                "readiness_contribution": "receipt_loaded",
            },
            {
                "id": "repo-git-status",
                "feature": "repo-dirty-state-after-cleanup",
                "case_type": "positive-control",
                "execution_status": "pass" if git_status.get("available") else "fail",
                "assertion_status": "pass" if git_status.get("available") else "fail",
                "readiness_contribution": "state_snapshot_only",
            },
            {
                "id": "no-delete-or-move-authority",
                "feature": "cleanup-delete-authority",
                "case_type": "safety-boundary",
                "execution_status": "pass",
                "assertion_status": "pass",
                "readiness_contribution": "safe_failure_only",
            },
        ],
        "cleanup_counts": counts,
        "cleanup_paths": {key: value[:100] for key, value in paths.items()},
        "repo_dirty_state": git_status,
        "project_sanity": sanity,
        "best_practices_checks_run": best_practices_run,
        "doc_code_drift": doc_drift or {"status": "not_established", "reason": "quick cleanup-tail profile" if quick else "not reported"},
        "project_knowledge_sync": knowledge,
        "memory_sync": {"status": "not_established", "safe_default": "update memory after accepted cleanup lessons"},
        "new_gaps_introduced_by_cleanup": introduced_gaps,
        "unresolved_cleanup_candidates": unresolved[:100],
        "embedded_state_report": state,
    }


def _format_readiness_markdown(report: dict) -> str:
    lines = [
        f"# Project State Readiness - {report['run_id']}",
        "",
        f"- schema: `{report['schema']}`",
        f"- profile: `{report['profile']}`",
        f"- overall_readiness: `{report['overall_readiness']}`",
        f"- release_readiness: `{report['release_readiness']}`",
        "",
        "## Features",
        "",
        "| Feature | Readiness | Evidence |",
        "|---------|-----------|----------|",
    ]
    for feature in report["features"]:
        evidence = ", ".join(feature.get("evidence", [])) or "not established"
        lines.append(f"| {feature['id']} | {feature['readiness']} | {evidence} |")
    lines.extend(["", "## Needs Attention", ""])
    if report["needs_attention"]:
        for item in report["needs_attention"]:
            lines.append(f"- {item['reason']}: {item['resume_hint']}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _format_readiness_html(report: dict) -> str:
    features = "\n".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            _html_escape(feature["id"]),
            _html_escape(feature["readiness"]),
            _html_escape(", ".join(feature.get("evidence", []))),
        )
        for feature in report["features"]
    )
    attention = "\n".join(
        "<li><strong>{}</strong>: {}</li>".format(
            _html_escape(item["reason"]),
            _html_escape(item["resume_hint"]),
        )
        for item in report["needs_attention"]
    ) or "<li>none</li>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Project State Readiness</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.45; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
    th {{ background: #f4f4f4; }}
    code {{ background: #f4f4f4; padding: 0.1rem 0.25rem; }}
  </style>
</head>
<body>
  <h1>Project State Readiness</h1>
  <p><strong>Profile:</strong> <code>{_html_escape(report['profile'])}</code></p>
  <p><strong>Overall readiness:</strong> <code>{_html_escape(report['overall_readiness'])}</code></p>
  <p><strong>Release readiness:</strong> <code>{_html_escape(report['release_readiness'])}</code></p>
  <h2>Features</h2>
  <table>
    <thead><tr><th>Feature</th><th>Readiness</th><th>Evidence</th></tr></thead>
    <tbody>{features}</tbody>
  </table>
  <h2>Needs Attention</h2>
  <ul>{attention}</ul>
</body>
</html>
"""


def _write_readiness_artifacts(report: dict, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_json = output_dir / "report.json"
    report_md = output_dir / "report.md"
    index_html = output_dir / "index.html"
    report_json.write_text(json.dumps(report, indent=2) + "\n")
    report_md.write_text(_format_readiness_markdown(report))
    index_html.write_text(_format_readiness_html(report))
    return {
        "report_json": str(report_json),
        "report_md": str(report_md),
        "index_html": str(index_html),
    }


def _emit_cleanup_tail(
    cleanup_receipt: Path,
    output_dir: Optional[Path],
    output_file: Optional[Path],
    json_output: bool,
    quick: bool,
    project_root: Path,
    project_sanity_cmd: Optional[str],
    best_practices_checks: list[str],
) -> None:
    report = _build_cleanup_tail_report(
        cleanup_receipt=cleanup_receipt,
        quick=quick,
        project_root=project_root,
        project_sanity_cmd=project_sanity_cmd,
        best_practices_checks=best_practices_checks,
    )
    out_dir = output_dir or (Path.cwd() / "artifacts" / "project-state" / "readiness" / report["run_id"])
    artifacts = _write_readiness_artifacts(report, out_dir)
    report["artifacts"] = artifacts
    Path(artifacts["report_json"]).write_text(json.dumps(report, indent=2) + "\n")

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        if json_output or output_file.suffix.lower() == ".json":
            output_file.write_text(json.dumps(report, indent=2) + "\n")
        else:
            output_file.write_text(_format_readiness_markdown(report))

    if json_output and not output_file:
        print(json.dumps(report, indent=2))
    elif output_file:
        print(f"Project-state cleanup-tail readiness written to {output_file}")
        print(f"Readiness bundle written to {artifacts['report_json']}")
    else:
        print(f"Project-state cleanup-tail readiness written to {artifacts['report_json']}")


@app.command("cleanup-tail")
def cmd_cleanup_tail(
    cleanup_receipt: Path = typer.Option(..., "--cleanup-receipt", exists=True, file_okay=True, dir_okay=False, readable=True, help="Existing cleanup receipt JSON to summarize"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Artifact directory; defaults to artifacts/project-state/readiness/<run-id>"),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Optional JSON/Markdown copy to write"),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable readiness report"),
    quick: bool = typer.Option(False, "--quick", help="Smoke profile: skip memory/doc-drift/best-practices collectors"),
    project_root: Optional[Path] = typer.Option(None, "--project-root", exists=True, file_okay=False, dir_okay=True, readable=True, help="Project root to inspect; defaults to cwd"),
    project_sanity_cmd: Optional[str] = typer.Option(None, "--project-sanity-cmd", help="Optional project-native sanity command to run from --project-root"),
    best_practices_check: list[str] = typer.Option([], "--best-practices-check", help="Best-practices command actually run during cleanup; repeatable"),
):
    """Create a post-cleanup readiness receipt without moving or deleting files."""
    _emit_cleanup_tail(
        cleanup_receipt=cleanup_receipt,
        output_dir=output_dir,
        output_file=output,
        json_output=json_output,
        quick=quick,
        project_root=project_root or Path.cwd(),
        project_sanity_cmd=project_sanity_cmd,
        best_practices_checks=best_practices_check,
    )


@config_app.command("doctor")
def cmd_config_doctor(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Report missing non-secret configuration without prompting."""
    checks = []
    for label, path in (
        ("EMBRY_OS_ROOT", EMBRY_OS),
        ("PI_SKILLS_ROOT", PI_SKILLS),
        ("memory_run_sh", MEMORY_SKILL),
        ("brave_search_run_sh", BRAVE_SEARCH_SKILL),
        ("github_search_run_sh", GITHUB_SEARCH_SKILL),
        ("dogpile_run_sh", DOGPILE_SKILL),
        ("create_figure_run_sh", CREATE_FIGURE_SKILL),
    ):
        exists = path.exists()
        checks.append({"id": label, "path": str(path), "status": "pass" if exists else "missing"})

    needs_attention = [
        {
            "reason": f"{check['id']}_missing",
            "safe_default": "mark dependent report section NOT_ESTABLISHED",
            "resume_hint": f"set {check['id']} or install the companion skill at {check['path']}",
        }
        for check in checks
        if check["status"] != "pass"
    ]
    result = {
        "schema": "project_state.config_doctor.v1",
        "status": "pass" if not needs_attention else "needs_attention",
        "checks": checks,
        "needs_attention": needs_attention,
    }
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        for check in checks:
            print(f"{check['id']}: {check['status']} {check['path']}")
        if needs_attention:
            raise typer.Exit(code=1)


app.add_typer(config_app, name="config")


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
