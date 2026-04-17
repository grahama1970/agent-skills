"""Deep review orchestration for high-risk skills.

Generates review requests, identifies workspace targets, and invokes the
review-code skill for skills that exceed risk thresholds.
"""
from __future__ import annotations
import os

import json
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from checkers import AuditResult
from config import (
    REVIEW_CODE_PY,
    REVIEW_CODE_RUN,
    REVIEW_WORKSPACE_FILE_LIMIT,
    SEVERITY_ORDER,
    THIS_SKILL_DIR,
)


def create_review_request(run_dir: Path, result: AuditResult) -> Path:
    """Write a markdown review request for a high-risk skill."""
    review_dir = run_dir / "deep_reviews" / result.skill
    review_dir.mkdir(parents=True, exist_ok=True)
    request_file = review_dir / "request.md"

    issues = sorted(
        result.needs_fix + result.aspirational_gaps,
        key=lambda item: SEVERITY_ORDER.get(str(item.get("severity", "low")), 0),
        reverse=True,
    )

    issue_lines = []
    for issue in issues[:20]:
        issue_lines.append(
            f"- [{issue.get('severity', 'low')}] {issue.get('rule', 'rule')} "
            f"at `{issue.get('file', 'unknown')}`: {issue.get('message', '')}"
        )

    request = (
        f"# Deep Review Request: {result.skill}\n\n"
        "Perform a deep code review focused on correctness regressions, missing tests, risk, and\n"
        "implementation gaps relative to repo best practices.\n\n"
        f"Target skill path: `{result.path}`\n\n"
        "## High-risk findings from monitor-skill-health\n"
        f"{chr(10).join(issue_lines) if issue_lines else '- No specific findings captured.'}\n\n"
        "## Output requirements\n"
        "- Prioritize findings by severity.\n"
        "- Include concrete file references.\n"
        "- Propose actionable fixes and minimal tests.\n"
        "- Provide unified diff suggestions where possible.\n"
    )

    request_file.write_text(request, encoding="utf-8")
    return request_file


def review_workspace_targets(
    result: AuditResult, limit: int = REVIEW_WORKSPACE_FILE_LIMIT
) -> list[Path]:
    """Select the most relevant workspace files for deep review."""
    skill_dir = Path(result.path)
    targets: list[Path] = []
    seen: set[str] = set()
    issues = sorted(
        result.needs_fix + result.aspirational_gaps,
        key=lambda item: SEVERITY_ORDER.get(str(item.get("severity", "low")), 0),
        reverse=True,
    )

    def _add_target(path: Path) -> None:
        if len(targets) >= limit:
            return
        key = str(path.resolve())
        if key in seen:
            return
        if not path.exists():
            return
        seen.add(key)
        targets.append(path)

    for issue in issues:
        location = str(issue.get("file", "")).strip()
        if not location or location == "unknown":
            continue
        location = location.split(":", 1)[0]
        candidate = Path(location)
        if not candidate.is_absolute():
            candidate = skill_dir / candidate
        _add_target(candidate)
        if len(targets) >= limit:
            break

    _add_target(skill_dir / "SKILL.md")
    return targets


def run_high_risk_review(
    run_dir: Path,
    result: AuditResult,
    provider: str,
    model: str,
    rounds: int,
    reasoning: str,
) -> dict[str, Any]:
    """Execute a deep review-code check for a high-risk skill."""
    request_file = create_review_request(run_dir, result)
    workspace_targets = review_workspace_targets(result)
    review_output_dir = request_file.parent / "output"
    review_output_dir.mkdir(parents=True, exist_ok=True)
    stdout_file = request_file.parent / "stdout.log"
    stderr_file = request_file.parent / "stderr.log"

    base_args = [
        "review-full",
        "--file",
        str(request_file),
        "--provider",
        provider,
        "--model",
        model,
        "--rounds",
        str(rounds),
        "--output-dir",
        str(review_output_dir),
    ]
    if workspace_targets:
        for workspace_path in workspace_targets:
            base_args.extend(["--workspace", str(workspace_path)])
    else:
        base_args.extend(["--add-dir", result.path])
    if provider == "openai" and reasoning:
        base_args.extend(["--reasoning", reasoning])

    attempted: list[str] = []

    proc = None
    if REVIEW_CODE_RUN.exists():
        run_cmd = [str(REVIEW_CODE_RUN), *base_args]
        attempted.append("review-code/run.sh")
        proc = subprocess.run(run_cmd, capture_output=True, text=True, check=False, timeout=5400,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

    if (proc is None or proc.returncode != 0) and REVIEW_CODE_PY.exists():
        fallback_cmd = [
            "uv",
            "run",
            "--project",
            str(THIS_SKILL_DIR),
            "python",
            str(REVIEW_CODE_PY),
            *base_args,
        ]
        attempted.append("uv run --project monitor-skill-health code_review.py")
        proc = subprocess.run(fallback_cmd, capture_output=True, text=True, check=False, timeout=5400,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )

    if proc is None:
        return {
            "status": "failed",
            "provider": provider,
            "model": model,
            "reason": "review-code skill is unavailable",
            "attempted": attempted,
        }

    stdout_file.write_text(proc.stdout or "", encoding="utf-8")
    stderr_file.write_text(proc.stderr or "", encoding="utf-8")

    if proc.returncode != 0:
        return {
            "status": "failed",
            "provider": provider,
            "model": model,
            "reason": f"review-code failed with exit {proc.returncode}",
            "attempted": attempted,
            "stderr_preview": (proc.stderr or "").strip()[:300],
            "request_file": str(request_file),
            "workspace_targets": [str(path) for path in workspace_targets],
        }

    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        parsed = {"raw_stdout": (proc.stdout or "")[:1000]}

    return {
        "status": "completed",
        "provider": provider,
        "model": model,
        "attempted": attempted,
        "request_file": str(request_file),
        "output_dir": str(review_output_dir),
        "workspace_targets": [str(path) for path in workspace_targets],
        "meta": parsed.get("meta", {}),
    }
