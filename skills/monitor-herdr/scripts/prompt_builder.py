"""Restart prompt construction for monitor-herdr."""

from __future__ import annotations

from typing import Any


def build_prompt(candidate: dict[str, Any]) -> str:
    reasons = ", ".join(str(item) for item in candidate.get("selection_reasons", [])) or "stopped"
    cwd = candidate.get("cwd") or "unknown"
    pane_id = candidate.get("pane_id") or "unknown"
    agent = candidate.get("agent") or "agent"
    action = candidate.get("action") or "restart_continue"
    goal = candidate.get("immutable_goal") or {}
    goal_line = "not found in project files"
    if goal.get("found"):
        goal_line = f"{goal.get('source')}: {goal.get('excerpt')}"
    if action == "needs_human":
        instruction = (
            "Answer directly first: Are you blocked, why did you stop, and have you completed your immutable goal? "
            "You appear legitimately blocked. Do not bury the blocker in a final answer. "
            "Reply with the exact human decision, credential, authority, or external state you need. "
            "If the blocker is actually research or reviewer uncertainty, use $brave-search, $ask webgpt, or $ask webkimi instead of stopping."
        )
    else:
        instruction = (
            "Answer directly first: Are you blocked, why did you stop early, have you completed your immutable goal, "
            "and do you need $brave-search, $ask webgpt, or $ask webkimi to unblock yourself? "
            "You stopped or went idle while the transcript still shows follow-up work or no real blocker. "
            "Resume the task now. Pick the next concrete remaining action, run it, and continue until a real blocker or deterministic proof exists. "
            "Use $brave-search for current external facts/docs before another stale retry. Use $ask webgpt or $ask webkimi with a concrete bundle when reviewer/oracle help would unblock you. "
            "Ask the human only for a missing decision, credential, authority, acceptance choice, or external state you cannot obtain."
        )
    return (
        "RESTART CHECK FROM monitor-herdr\n\n"
        f"Herdr pane: {pane_id}\n"
        f"Agent: {agent}\n"
        f"Cwd: {cwd}\n"
        f"Immutable goal evidence: {goal_line}\n"
        f"Reason: {reasons}\n\n"
        f"{instruction}\n\n"
        "Respond and act with this operational shape:\n"
        "Status/Phase: <one line>\n"
        "Immutable Goal: <known goal, UNKNOWN, or ACHIEVED_WITH_RECEIPT:path>\n"
        "Now: <current file, command, artifact, or exact blocker>\n"
        "Evidence: <latest concrete command/result/artifact path, or NONE>\n"
        "Unblock Attempts: brave-search=<USED:path | NOT_APPLICABLE:reason>; browser-oracle=<USED:path | NOT_APPLICABLE:reason>\n"
        "Next: <one immediate action you will execute now, or STOP_ALLOWED because no immutable goal exists / goal is achieved>\n"
        "Disposition: <choose exactly one of RESUMING_NOW | BLOCKED_NEEDS_HUMAN | CONFUSED_NEEDS_HUMAN | "
        "CAN_SELF_UNBLOCK_BRAVE_SEARCH | CAN_SELF_UNBLOCK_WEBGPT | DONE_WITH_RECEIPT>\n\n"
        "Strict stop rule: You may use ACHIEVED_WITH_RECEIPT or DONE_WITH_RECEIPT only if Evidence names a concrete "
        "local receipt/artifact path and the command or verification result that proves the immutable goal. If any "
        "human-requested work remains, or if the receipt proves only a partial checkpoint, answer Immutable Goal: NOT_MET "
        "and Disposition: RESUMING_NOW, then immediately run the next critical-path command. "
        "If the immutable goal is known and not achieved, keep going and use available tools until it is met. "
        "Do not claim complete unless you can cite deterministic local proof artifacts and there is no remaining user-requested work."
    )
