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


def issue_reopen(repo: str, issue_number: int) -> dict[str, Any]:
    """Reopen a closed issue. Used when a closure does not survive review."""
    return run_cmd(
        ["gh", "issue", "reopen", str(issue_number), "--repo", repo],
        timeout_s=60,
    )


def issue_comments(repo: str, issue_number: int, limit: int = 6) -> list[dict[str, Any]]:
    """The last few comments on an issue, oldest first.

    The closure evidence lives here: proof files, verdicts, and whatever the
    closer asserted. The auditor reads it rather than trusting the closure.
    """
    result = run_cmd(
        ["gh", "issue", "view", str(issue_number), "--repo", repo, "--json", "comments"],
        timeout_s=60,
    )
    if result.get("exit_code") != 0:
        return []
    import json as _json  # noqa: PLC0415

    comments = _json.loads(result.get("stdout") or "{}").get("comments", [])
    return comments[-limit:]


def issue_close(repo: str, issue_number: int, *, reason: str = "completed") -> dict[str, Any]:
    return run_cmd(
        ["gh", "issue", "close", str(issue_number), "--repo", repo, "--reason", reason],
        timeout_s=60,
    )


def _rest_issue(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict) or "number" not in item:
        raise RuntimeError("GitHub returned an issue without an identity")
    return {**item, "url": item.get("html_url", ""),
            "state": str(item.get("state", "")).upper(),
            "createdAt": item.get("created_at"), "updatedAt": item.get("updated_at"),
            "closedAt": item.get("closed_at"),
            "stateReason": str(item.get("state_reason") or "").upper()}


def get_issue(repo: str, number: int) -> dict[str, Any]:
    result = run_cmd(["gh", "api", f"repos/{repo}/issues/{int(number)}"], timeout_s=60)
    if result.get("exit_code") != 0:
        raise RuntimeError(f"direct issue read failed: {repo}#{number}: {result.get('stderr')}")
    item = json.loads(result["stdout"])
    if "pull_request" in item:
        raise RuntimeError("target is a pull request, not a ticket")
    return _rest_issue(item)


def list_issues(repo: str, *, state: str, label: str) -> list[dict[str, Any]]:
    """All REST pages, oldest first. Failed/partial responses are NOT an empty queue."""
    from urllib.parse import urlencode
    query = urlencode({"state": state, "labels": label, "sort": "created",
                       "direction": "asc", "per_page": 100})
    result = run_cmd(["gh", "api", "--paginate", "--slurp",
                      f"repos/{repo}/issues?{query}"], timeout_s=120)
    if result.get("exit_code") != 0:
        raise RuntimeError(f"complete issue scan failed for {repo}: {result.get('stderr')}")
    pages = json.loads(result["stdout"])
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise RuntimeError("issue scan did not return complete paginated arrays")
    by_number = {}
    for page in pages:
        for raw in page:
            if not isinstance(raw, dict):
                raise RuntimeError("invalid GitHub issue page entry")
            if "pull_request" in raw:
                continue
            item = _rest_issue(raw)
            by_number[int(item["number"])] = item
    return sorted(by_number.values(), key=lambda i: (str(i.get("createdAt") or ""), i["number"]))
