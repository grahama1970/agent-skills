"""Stale Herdr workspace sweep.

Eval and sanity runs leave disposable workspaces behind; they accumulate until
the sidebar is mostly debris and real stalled agents are hard to see. Herdr's
own guidance is that an agent must not close workspaces it did not create unless
the human explicitly asked, so this sweep is fail-closed in both directions: a
workspace must match a caller-supplied disposable label pattern AND carry no
live agent work AND not be focused before it is even a candidate, and nothing is
closed without `--apply`.
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

# Labels Herdr assigns to workspaces created by this repo's own eval/sanity runs.
DEFAULT_STALE_LABEL_PATTERNS = (
    r"^rw-sanity-",
    r"^monitor-herdr-disposable$",
    r"^autoupdate$",
    r"-disposable$",
    r"^tmp-",
)

# An agent in any of these states is doing or holding real work.
LIVE_AGENT_STATUSES = frozenset({"working", "blocked", "idle"})


def classify_workspace(
    workspace: dict[str, Any],
    *,
    stale_patterns: tuple[str, ...] = DEFAULT_STALE_LABEL_PATTERNS,
    max_pane_count: int = 8,
) -> dict[str, Any]:
    """Decide whether one workspace is a safe disposable-cleanup candidate."""
    workspace_id = str(workspace.get("workspace_id") or "")
    label = str(workspace.get("label") or "")
    status = str(workspace.get("agent_status") or "unknown").lower()
    focused = bool(workspace.get("focused"))
    pane_count = int(workspace.get("pane_count") or 0)

    verdict: dict[str, Any] = {
        "workspace_id": workspace_id,
        "label": label,
        "agent_status": status,
        "pane_count": pane_count,
        "focused": focused,
        "stale": False,
        "reasons": [],
    }
    if not workspace_id:
        verdict["reasons"].append("missing_workspace_id")
        return verdict

    matched = next((pattern for pattern in stale_patterns if re.search(pattern, label)), None)
    if not matched:
        verdict["reasons"].append("label_not_disposable")
        return verdict
    verdict["matched_pattern"] = matched

    if focused:
        verdict["reasons"].append("focused_workspace_never_closed")
        return verdict
    if status in LIVE_AGENT_STATUSES:
        verdict["reasons"].append(f"live_agent_status:{status}")
        return verdict
    if pane_count > max_pane_count:
        verdict["reasons"].append(f"pane_count_above_disposable_limit:{pane_count}")
        return verdict

    verdict["stale"] = True
    verdict["reasons"].append(f"disposable_label_match:{matched}")
    verdict["reasons"].append(f"no_live_agent:{status}")
    return verdict


def sweep_workspaces(
    workspaces: list[dict[str, Any]],
    *,
    stale_patterns: tuple[str, ...] = DEFAULT_STALE_LABEL_PATTERNS,
    max_pane_count: int = 8,
    max_closes: int = 25,
) -> dict[str, Any]:
    """Classify every workspace and return the bounded close list."""
    verdicts = [
        classify_workspace(item, stale_patterns=stale_patterns, max_pane_count=max_pane_count)
        for item in workspaces
    ]
    stale = [item for item in verdicts if item["stale"]]
    selected = stale[:max_closes]
    return {
        "workspaces_total": len(verdicts),
        "stale_total": len(stale),
        "selected_total": len(selected),
        "truncated": len(stale) > len(selected),
        "verdicts": verdicts,
        "selected": selected,
    }


def close_workspaces(client: Any, selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Close each selected workspace, recording per-workspace outcome."""
    results: list[dict[str, Any]] = []
    for item in selected:
        workspace_id = item["workspace_id"]
        record = {"workspace_id": workspace_id, "label": item.get("label"), "closed": False}
        try:
            client.call("workspace.close", {"workspace_id": workspace_id})
            record["closed"] = True
        except RuntimeError as exc:
            logger.error("workspace.close failed for {}: {}", workspace_id, exc)
            record["error"] = str(exc)
        results.append(record)
    return results
