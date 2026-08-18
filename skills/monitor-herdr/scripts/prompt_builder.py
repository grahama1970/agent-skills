"""Restart prompt construction for monitor-herdr."""

from __future__ import annotations

from typing import Any

from project_context import context_lines


def ticket_instruction(candidate: dict[str, Any]) -> str:
    """State the pane's actual open tickets so the agent does not rediscover them."""
    tickets = (candidate.get("project_context") or {}).get("open_tickets") or []
    if not tickets:
        return (
            "If the transcript or project state names a GitHub issue, check it with the real $ticket "
            "runtime; if it is open and in scope, lease it, diagnose it, fix it, attach proof, close it, "
            "and read back the closed state."
        )
    rendered = ", ".join(f"#{item['number']}" for item in tickets if item.get("number"))
    return (
        f"These tickets are already open for this scope: {rendered}. Do not re-triage them from scratch — "
        "use the real $ticket runtime to look up each one that is in scope for your immutable goal, then "
        "lease it, diagnose it, fix it, attach deterministic proof, close it, and read back the closed "
        "state. If a listed ticket is out of scope, say so once with its number and move on."
    )


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
    resolved = context_lines(candidate.get("project_context") or {})
    context_block = ("\n".join(resolved) + "\n") if resolved else ""
    if action == "needs_human":
        instruction = (
            "Answer directly first: Are you blocked, why did you stop, and have you completed your immutable goal? "
            "You appear legitimately blocked. Do not bury the blocker in a final answer. "
            "Reply with the exact human decision, credential, authority, or external state you need. "
            "If the blocker is actually an open project bug ticket, use $ticket to look it up, diagnose it, solve it, attach proof, and close it. "
            "If the blocker is actually research or reviewer uncertainty, use $brave-search, $ask webgpt, or $ask webkimi instead of stopping."
        )
    else:
        instruction = (
            "You stopped or went idle while the transcript still shows follow-up work and no real blocker. "
            "Do not reply with a status essay and do not ask which task to pick — the context above is already resolved for you. "
            "Resume the work now: pick the next concrete remaining action, run it, and keep going until a real blocker or deterministic proof exists. "
            f"{ticket_instruction(candidate)} "
            "Use $brave-search for current external facts/docs before another stale retry. Use $ask webgpt or $ask webkimi with a concrete bundle when reviewer/oracle help would unblock you. "
            "Ask the human only for a missing decision, credential, authority, acceptance choice, or external state you cannot obtain. "
            "State the blocker once, in the Disposition line, and stop — this monitor will not ask you again while nothing changes."
        )
    return (
        "RESTART CHECK FROM monitor-herdr\n\n"
        f"Herdr pane: {pane_id}\n"
        f"Agent: {agent}\n"
        f"Cwd: {cwd}\n"
        f"{context_block}"
        f"Immutable goal evidence: {goal_line}\n"
        f"Reason: {reasons}\n\n"
        f"{instruction}\n\n"
        "Respond and act with this operational shape:\n"
        "Status/Phase: <one line>\n"
        "Immutable Goal: <known goal, UNKNOWN, or ACHIEVED_WITH_RECEIPT:path>\n"
        "Now: <current file, command, artifact, or exact blocker>\n"
        "Evidence: <latest concrete command/result/artifact path, or NONE>\n"
        "Ticket Check: <USED:issue-url-or-number state/action/proof | NOT_APPLICABLE:reason>\n"
        "Unblock Attempts: brave-search=<USED:path | NOT_APPLICABLE:reason>; browser-oracle=<USED:path | NOT_APPLICABLE:reason>\n"
        "Next: <one immediate action you will execute now, or STOP_ALLOWED because no immutable goal exists / goal is achieved>\n"
        "Disposition: <choose exactly one of RESUMING_NOW | BLOCKED_NEEDS_HUMAN | CONFUSED_NEEDS_HUMAN | "
        "CAN_SELF_UNBLOCK_BRAVE_SEARCH | CAN_SELF_UNBLOCK_WEBGPT | DONE_WITH_RECEIPT>\n\n"
        "Strict stop rule: You may use ACHIEVED_WITH_RECEIPT or DONE_WITH_RECEIPT only if Evidence names a concrete "
        "existing local receipt/artifact path from the same status block and the command or verification result that proves the immutable goal. If any "
        "human-requested work remains, or if the receipt proves only a partial checkpoint, answer Immutable Goal: NOT_MET "
        "and Disposition: RESUMING_NOW, then immediately run the next critical-path command. "
        "If the immutable goal is known and not achieved, keep going and use available tools until it is met. "
        "Do not claim complete unless you can cite deterministic local proof artifacts and there is no remaining user-requested work."
    )
