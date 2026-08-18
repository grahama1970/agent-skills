#!/usr/bin/env python3
"""Decide whether a stopped Herdr pane is genuinely stalled.

Inputs: a live Herdr client, a pane record, and the monitor's prior observations.
Outputs: a classification dict carrying the verdict, its reasons, and the evidence
that produced it.
Failure modes: fail-closed -- an unknown or blocked pane is classified
observe-only, and an agent that stated a real blocker is never re-asked.

Split out of monitor_herdr.py to keep every module under the 800-line repo limit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from change_tracking import change_signature, nudge_exhausted, unchanged_since_prompt
from goal_discovery import discover_immutable_goal, path_is_relative_to, project_root_for_cwd
from herdr_socket import HerdrClient, explain_agent, find_patterns, read_pane_text
from monitor_common import EARLY_STOP_PATTERNS, HUMAN_BLOCKER_PATTERNS, TICKET_CACHE_PATH, current_epoch, now_iso
from project_context import resolve_project_context
from prompt_submission import explain_allows_input
from transcript_classifier import completion_claim_present, goal_allows_stop, latest_transcript_region, transcript_goal_claim


def resolve_workspace(client: HerdrClient, space: str) -> dict[str, Any] | list[dict[str, Any]]:
    result = client.call("workspace.list", {})
    workspaces = result.get("workspaces", [])
    if space == "*":
        return workspaces
    for workspace in workspaces:
        if str(workspace.get("workspace_id")) == space:
            return workspace
        if str(workspace.get("label")) == space:
            return workspace
        if str(workspace.get("number")) == space:
            return workspace
    raise RuntimeError(
        f"Herdr workspace not found for --space {space!r}. "
        f"{describe_available_spaces(workspaces)}"
    )
def describe_available_spaces(workspaces: list[dict[str, Any]]) -> str:
    """Render the spaces a caller could have asked for.

    An unknown --space is a caller error, and a caller error should teach the
    caller. Listing the live workspaces turns a dead end into a next step.
    """
    if not workspaces:
        return "No Herdr workspaces are open; start one before running a tick."
    known = []
    for workspace in workspaces:
        label = workspace.get("label")
        number = workspace.get("number")
        parts = [str(workspace.get("workspace_id"))]
        if label:
            parts.append(f"label={label}")
        if number is not None:
            parts.append(f"number={number}")
        known.append(" ".join(parts))
    return (
        "Available spaces (match by workspace_id, label, or number): "
        + "; ".join(known)
        + ". Use --space '*' to scan every workspace."
    )
def update_stopped_observation(observations: dict[str, Any], candidate: dict[str, Any], *, now_epoch: int) -> None:
    pane_id = str(candidate.get("pane_id") or "")
    if not pane_id:
        return
    record = observations.get(pane_id)
    if not isinstance(record, dict):
        record = {
            "first_seen_stopped_epoch": now_epoch,
            "first_seen_stopped_at": now_iso(),
            "consecutive_stopped_ticks": 0,
        }
    record["last_seen_stopped_epoch"] = now_epoch
    record["last_seen_stopped_at"] = now_iso()
    record["consecutive_stopped_ticks"] = int(record.get("consecutive_stopped_ticks", 0) or 0) + 1
    record["agent"] = candidate.get("agent")
    record["agent_status"] = candidate.get("agent_status")
    record["cwd"] = candidate.get("cwd")
    record["classification"] = candidate.get("classification")
    observations[pane_id] = record

    api_age = candidate.get("herdr_stopped_age_seconds")
    if api_age is not None:
        candidate["stopped_age_seconds"] = int(api_age)
        candidate["stopped_age_source"] = candidate.get("herdr_stopped_age_source") or "herdr_api"
        return
    first_seen = int(record.get("first_seen_stopped_epoch", now_epoch) or now_epoch)
    candidate["stopped_age_seconds"] = max(0, now_epoch - first_seen)
    candidate["stopped_age_source"] = "monitor_state"
    candidate["stopped_first_seen_at"] = record.get("first_seen_stopped_at")
    candidate["consecutive_stopped_ticks"] = record.get("consecutive_stopped_ticks")
def prune_stopped_observations(
    observations: dict[str, Any],
    *,
    observed_pane_ids: set[str],
    current_stopped_ids: set[str],
) -> None:
    for pane_id in list(observations):
        if pane_id in observed_pane_ids and pane_id not in current_stopped_ids:
            del observations[pane_id]
def herdr_stopped_age(pane: dict[str, Any], explain: dict[str, Any], *, now_epoch: int) -> tuple[int | None, str | None]:
    for source_name, payload in (("pane", pane), ("explain", explain)):
        if not isinstance(payload, dict):
            continue
        for field in ("idle_seconds", "idle_duration_seconds", "stopped_seconds", "agent_idle_seconds", "state_age_seconds"):
            value = seconds_value(payload.get(field))
            if value is not None:
                return value, f"herdr_api:{source_name}.{field}"
        for field in ("idle_since_unix", "stopped_since_unix", "agent_status_since_unix", "state_since_unix", "last_state_change_unix"):
            value = epoch_age(payload.get(field), now_epoch=now_epoch)
            if value is not None:
                return value, f"herdr_api:{source_name}.{field}"
        for field in ("idle_since", "stopped_since", "agent_status_since", "state_since", "last_state_change_at"):
            value = iso_age(payload.get(field), now_epoch=now_epoch)
            if value is not None:
                return value, f"herdr_api:{source_name}.{field}"
    return None, None
def seconds_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        seconds = int(float(value))
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None
def epoch_age(value: Any, *, now_epoch: int) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        epoch = int(float(value))
    except (TypeError, ValueError):
        return None
    if epoch <= 0 or epoch > now_epoch:
        return None
    return now_epoch - epoch
def iso_age(value: Any, *, now_epoch: int) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    epoch = int(parsed.timestamp())
    if epoch > now_epoch:
        return None
    return now_epoch - epoch
def load_agent_index(client: HerdrClient) -> dict[str, dict[str, Any]]:
    """Map pane_id -> agent record so classification can read `state_change_seq`.

    `pane.list` does not carry the lifecycle counter; only `agent.list` does.
    A failure here degrades change detection to the transcript digest alone.
    """
    try:
        result = client.call("agent.list", {})
    except Exception as exc:  # noqa: BLE001 - never let an optional signal break a tick
        logger.error("Herdr agent.list unavailable; change detection degrades to transcript digest: {}", exc)
        return {}
    agents = result.get("agents", result if isinstance(result, list) else [])
    index: dict[str, dict[str, Any]] = {}
    for item in agents if isinstance(agents, list) else []:
        if isinstance(item, dict) and item.get("pane_id"):
            index[str(item["pane_id"])] = item
    return index
def apply_no_change_suppression(candidate: dict[str, Any], prompt_state: dict[str, Any]) -> None:
    """Downgrade a candidate to observe-only when it did nothing since our last nudge."""
    verdict = unchanged_since_prompt(candidate.get("change_signature", {}), prompt_state)
    candidate["change_verdict"] = verdict
    candidate["no_change_strikes"] = int(prompt_state.get("no_change_strikes", 0) or 0)
    if candidate.get("action") == "observe_only" or not verdict.get("unchanged"):
        return
    exhausted = nudge_exhausted(prompt_state)
    candidate["classification"] = "nudge_exhausted_no_change" if exhausted else "no_change_since_last_prompt"
    candidate["action"] = "observe_only"
    candidate["selection_reasons"] = [
        f"suppressed:{verdict['reason']}",
        *[f"evidence:{item}" for item in verdict.get("evidence", [])],
        f"no_change_strikes:{candidate['no_change_strikes']}",
    ]
def classify_pane(
    client: HerdrClient,
    pane: dict[str, Any],
    *,
    cwd_prefix: str,
    include_agents: set[str],
    stopped_statuses: set[str],
    only_obvious_early_stops: bool,
    agent_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    label = str(pane.get("agent") or "")
    if include_agents and label not in include_agents:
        return None
    status = str(pane.get("agent_status") or "unknown").lower()
    if status not in stopped_statuses:
        return None
    cwd = str(pane.get("foreground_cwd") or pane.get("cwd") or "")
    if cwd_prefix and (not cwd or not path_is_relative_to(cwd, cwd_prefix)):
        return None
    pane_id = str(pane.get("pane_id") or "")
    if not pane_id:
        return None

    text = read_pane_text(client, pane_id)
    current_text = latest_transcript_region(text)
    explain = explain_agent(client, pane_id)
    api_age, api_age_source = herdr_stopped_age(pane, explain, now_epoch=current_epoch())
    early_markers = find_patterns(current_text, EARLY_STOP_PATTERNS)
    human_markers = find_patterns(current_text, HUMAN_BLOCKER_PATTERNS)
    if only_obvious_early_stops and not early_markers:
        return None

    project_root = project_root_for_cwd(cwd, cwd_prefix)
    immutable_goal = discover_immutable_goal(cwd, boundary=project_root)
    goal_claim = transcript_goal_claim(current_text, project_root=project_root)
    has_goal_signal = bool(immutable_goal.get("found")) or goal_claim["state"] in {"achieved", "blocked", "unmet"}
    if status in {"blocked", "unknown"} or not explain_allows_input(explain):
        classification = "blocked_or_unknown_observe_only"
        action = "observe_only"
        reasons = [f"stopped_status:{status}", "unsafe_or_uncertain_state_never_prompted"]
    elif not has_goal_signal and not early_markers:
        classification = "no_immutable_goal"
        action = "observe_only"
        reasons = [f"stopped_status:{status}", "immutable_goal_unknown_stop_allowed"]
    elif goal_allows_stop(current_text, goal_found=has_goal_signal, has_early_markers=bool(early_markers), project_root=project_root):
        classification = "goal_stop_allowed"
        action = "observe_only"
        reasons = [f"stopped_status:{status}", f"goal_claim:{goal_claim['state']}"]
    elif goal_claim["state"] == "unmet" and completion_claim_present(current_text) and not early_markers:
        classification = "completion_claim_unproven_no_restart_signal"
        action = "observe_only"
        reasons = [
            f"stopped_status:{status}",
            "completion_claim_present",
            "no_current_restart_signal",
        ]
    elif human_markers and not early_markers:
        classification = "legitimate_human_blocker"
        action = "needs_human"
        reasons = [f"human_blocker:{item}" for item in human_markers[:5]]
    elif immutable_goal.get("found") and goal_claim["state"] == "none" and not early_markers:
        classification = "immutable_goal_present_no_restart_signal"
        action = "observe_only"
        reasons = [
            f"stopped_status:{status}",
            "immutable_goal_found",
            "no_current_restart_signal",
        ]
    else:
        classification = "stopped_or_early_stop"
        action = "restart_continue"
        reasons = [f"stopped_status:{status}"]
        reasons.extend(f"early_stop:{item}" for item in early_markers[:6])
        if human_markers:
            reasons.extend(f"human_marker_overridden_by_early_stop:{item}" for item in human_markers[:3])
        if immutable_goal.get("found"):
            reasons.append("immutable_goal_found")
        elif goal_claim["state"] != "none":
            reasons.append(f"transcript_goal:{goal_claim['state']}")
        elif early_markers:
            reasons.append("immutable_goal_unknown_but_early_stop_marker")
        else:
            reasons.append("immutable_goal_unknown")

    agent_record = (agent_index or {}).get(pane_id)
    return {
        "pane_id": pane_id,
        "change_signature": change_signature(agent_record, current_text),
        "project_context": resolve_project_context(
            cwd,
            project_root,
            cache_path=TICKET_CACHE_PATH,
            include_tickets=action != "observe_only",
        ),
        "terminal_id": pane.get("terminal_id"),
        "workspace_id": pane.get("workspace_id"),
        "tab_id": pane.get("tab_id"),
        "agent": label,
        "agent_status": status,
        "cwd": cwd,
        "classification": classification,
        "action": action,
        "selection_reasons": reasons,
        "early_stop_markers": early_markers,
        "human_blocker_markers": human_markers,
        "immutable_goal": immutable_goal,
        "project_root": str(project_root) if project_root else None,
        "transcript_goal_claim": goal_claim,
        "recent_excerpt": text[-2400:],
        "analysis_excerpt": current_text[-1200:],
        "explain_state": explain.get("state") if isinstance(explain, dict) else None,
        "herdr_stopped_age_seconds": api_age,
        "herdr_stopped_age_source": api_age_source,
    }
