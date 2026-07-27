"""Repo-parameterised ``gh`` CLI wrappers for issue comments, labels, and closure.

Purpose
    Every GitHub mutation the watchdog performs, with the target repository
    passed in explicitly.

Inputs
    A ``owner/name`` repo slug, an issue number, and the mutation payload.

Outputs
    ``run_cmd``-shaped result dictionaries recorded verbatim in tick receipts.

Failure modes
    Non-zero ``gh`` exits are returned, not raised, so a partial dispatch still
    produces a receipt showing exactly which call failed.

History
    Until 2026-07-27 these helpers hardcoded ``grahama1970/tau``. In a registry
    that holds five projects, that meant any non-Tau dispatch would have
    commented on, relabelled, and closed an unrelated Tau issue. The ``repo``
    parameter is required and has no default for exactly that reason.
"""

from __future__ import annotations

import json
from typing import Any

from .core import run_cmd


def watchdog_comment(title: str, payload: dict[str, Any]) -> str:
    """Render a watchdog comment body with an embedded machine-readable block."""
    return (
        f"## Project Watchdog: {title}\n\n"
        "<!-- project-watchdog:v1 -->\n"
        "```json\n"
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n"
        "```\n"
    )


def issue_comment(repo: str, issue_number: int, body: str) -> dict[str, Any]:
    return run_cmd(
        ["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body", body],
        timeout_s=60,
    )


def issue_edit(
    repo: str,
    issue_number: int,
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> dict[str, Any]:
    command = ["gh", "issue", "edit", str(issue_number), "--repo", repo]
    for label in add or []:
        command.extend(["--add-label", label])
    for label in remove or []:
        command.extend(["--remove-label", label])
    return run_cmd(command, timeout_s=60)


def issue_close(repo: str, issue_number: int, *, reason: str = "completed") -> dict[str, Any]:
    return run_cmd(
        ["gh", "issue", "close", str(issue_number), "--repo", repo, "--reason", reason],
        timeout_s=60,
    )
