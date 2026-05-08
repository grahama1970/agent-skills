"""LogAct-inspired recovery and introspection for code-runner.

Implements:
1. Crash recovery via log replay (determine state after unexpected termination)
2. Semantic failure diagnosis (LLM analyzes execution history)
3. Pre-execution voters (check intents before execution)

Based on Meta's LogAct paper (arXiv:2604.07988): "Enabling Agentic Reliability via Shared Logs"
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger


def normalize_scillm_chat_url(raw_url: str | None) -> str:
    """Return the concrete OpenAI-compatible chat completions endpoint."""
    url = (raw_url or "http://localhost:4001/v1/chat/completions").strip().rstrip("/")
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path in ("", "/"):
        return f"{url}/v1/chat/completions"
    if path == "/v1":
        return f"{url}/chat/completions"
    return url


class RecoveryAction(str, Enum):
    """Recovery actions after crash detection."""
    START_FRESH = "start_fresh"           # No prior state, start from beginning
    CONTINUE_NEXT_ROUND = "continue"      # Last round complete, continue to next
    RETRY_CURRENT_ROUND = "retry_round"   # Round incomplete, retry from start
    REVERT_AND_RETRY = "revert_retry"     # Partial write detected, revert then retry
    ABORT = "abort"                       # Unrecoverable state, abort run


@dataclass
class RecoveryResult:
    """Result of crash recovery analysis."""
    action: RecoveryAction
    resume_round: int
    reason: str
    last_event_type: str | None = None
    partial_files: list[str] | None = None


@dataclass
class FailureDiagnosis:
    """Semantic diagnosis of repeated failures."""
    pattern: str                    # e.g., "repeated_import_error", "stuck_on_same_file"
    root_cause: str                 # Human-readable explanation
    recommendation: str             # Suggested fix approach
    tool_failure_rate: float        # % of tool calls that failed
    stuck_file: str | None = None   # File that keeps failing
    error_types: dict[str, int] | None = None


# ── Voters ────────────────────────────────────────────────────────────────────
# Pluggable pre-execution checks. Return (approved, reason).


def allowlist_voter(
    tool_name: str,
    args: dict,
    allowlist: list[str] | None,
    cwd: str,
) -> tuple[bool, str]:
    """Vote on whether a file write should proceed based on allowlist.

    Returns (approved, reason). If not approved, reason explains why.
    """
    if tool_name not in ("write_file", "edit_file"):
        return True, ""

    if allowlist is None:
        return True, ""  # No allowlist = all writes allowed

    path = args.get("path", "")
    if not path:
        return False, "No path specified"

    # Normalize path relative to cwd
    try:
        abs_path = Path(cwd) / path if not Path(path).is_absolute() else Path(path)
        rel_path = str(abs_path.relative_to(Path(cwd)))
    except ValueError:
        return False, f"Path {path} is outside working directory"

    # Check against allowlist
    for allowed in allowlist:
        allowed = allowed.rstrip("/")
        # Exact match
        if rel_path == allowed:
            return True, ""
        # Directory scope: "scripts/" allows "scripts/foo.py"
        if allowed.endswith("/") or Path(cwd, allowed).is_dir():
            if rel_path.startswith(allowed.rstrip("/") + "/") or rel_path.startswith(allowed):
                return True, ""
        # File in allowed directory
        if rel_path.startswith(allowed + "/"):
            return True, ""

    return False, f"Path '{rel_path}' not in allowlist: {allowlist}"


def denylist_voter(
    tool_name: str,
    args: dict,
    denylist: set[str],
) -> tuple[bool, str]:
    """Vote on whether a tool call should proceed based on denylist."""
    if tool_name not in ("write_file", "edit_file"):
        return True, ""

    path = args.get("path", "")
    if not path:
        return True, ""

    filename = Path(path).name
    if filename in denylist:
        return False, f"File '{filename}' is in denylist (protected file)"

    # Check parent dirs
    for part in Path(path).parts:
        if part in denylist:
            return False, f"Path contains denylisted component: {part}"

    return True, ""


# ── Crash Recovery ────────────────────────────────────────────────────────────


def load_events(events_file: Path) -> list[dict]:
    """Load events from events.jsonl."""
    events = []
    if not events_file.exists():
        return events

    try:
        with events_file.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed event line")
    except IOError as e:
        logger.warning("Could not read events file: {}", e)

    return events


def analyze_crash_state(output_dir: Path, cwd: Path) -> RecoveryResult:
    """Analyze events.jsonl to determine recovery action after crash.

    This is LogAct's "semantic recovery via log introspection" - instead of
    blindly retrying, we inspect the execution history to understand state.
    """
    events_file = output_dir / "events.jsonl"
    events = load_events(events_file)

    if not events:
        return RecoveryResult(
            action=RecoveryAction.START_FRESH,
            resume_round=1,
            reason="No prior events found",
        )

    last_event = events[-1]
    event_type = last_event.get("event", "")
    last_round = last_event.get("round") or 0

    # Terminal states - don't recover
    if event_type in ("run_passed", "run_failed", "preflight_failed"):
        return RecoveryResult(
            action=RecoveryAction.ABORT,
            resume_round=last_round,
            reason=f"Run already completed with status: {event_type}",
            last_event_type=event_type,
        )

    # Check for partial tool execution
    if event_type == "tool_intent":
        # Crashed DURING tool execution - check if write happened
        payload = last_event.get("payload", {})
        tool = payload.get("tool", "")
        args = payload.get("args", {})

        if tool in ("write_file", "edit_file"):
            path = args.get("path", "")
            if path:
                full_path = cwd / path if not Path(path).is_absolute() else Path(path)
                if full_path.exists():
                    # File was written but result not logged - need to revert
                    return RecoveryResult(
                        action=RecoveryAction.REVERT_AND_RETRY,
                        resume_round=last_round,
                        reason=f"Crashed after writing {path} but before logging result",
                        last_event_type=event_type,
                        partial_files=[str(path)],
                    )

        # Tool didn't write or write didn't complete - retry the round
        return RecoveryResult(
            action=RecoveryAction.RETRY_CURRENT_ROUND,
            resume_round=last_round,
            reason=f"Crashed during {tool} execution",
            last_event_type=event_type,
        )

    # Round completed successfully - continue to next
    if event_type in ("round_scored", "round_kept", "round_discarded"):
        return RecoveryResult(
            action=RecoveryAction.CONTINUE_NEXT_ROUND,
            resume_round=last_round + 1,
            reason=f"Round {last_round} completed, continuing to round {last_round + 1}",
            last_event_type=event_type,
        )

    # Run started but no rounds completed
    if event_type == "run_started":
        return RecoveryResult(
            action=RecoveryAction.CONTINUE_NEXT_ROUND,
            resume_round=1,
            reason="Run started but no rounds completed",
            last_event_type=event_type,
        )

    # Default: retry current round
    return RecoveryResult(
        action=RecoveryAction.RETRY_CURRENT_ROUND,
        resume_round=max(1, last_round),
        reason=f"Unknown state after {event_type}, retrying round {last_round}",
        last_event_type=event_type,
    )


# ── Semantic Failure Diagnosis ────────────────────────────────────────────────


def diagnose_failure_pattern(
    events: list[dict],
    task_title: str,
    dod_command: str,
    dod_assertion: str,
) -> FailureDiagnosis:
    """Analyze execution history to diagnose why the task keeps failing.

    This is LogAct's "agentic introspection" - the agent analyzes its own
    execution history using LLM inference.
    """
    # Extract statistics from events
    tool_intents = [e for e in events if e.get("event") == "tool_intent"]
    tool_results = [e for e in events if e.get("event") == "tool_result"]
    round_scores = [e for e in events if e.get("event") == "round_scored"]

    # Calculate tool failure rate
    total_tools = len(tool_results)
    failed_tools = sum(1 for r in tool_results if not r.get("payload", {}).get("ok", True))
    tool_failure_rate = failed_tools / total_tools if total_tools > 0 else 0.0

    # Find stuck file (file that appears most in failed tool calls)
    failed_files: dict[str, int] = {}
    for r in tool_results:
        if not r.get("payload", {}).get("ok", True):
            path = r.get("payload", {}).get("path", "")
            if path:
                failed_files[path] = failed_files.get(path, 0) + 1

    stuck_file = max(failed_files, key=failed_files.get) if failed_files else None

    # Extract error types from tool results
    error_types: dict[str, int] = {}
    for r in tool_results:
        payload = r.get("payload", {})
        if not payload.get("ok", True):
            error_type = payload.get("error_type", "unknown")
            error_types[error_type] = error_types.get(error_type, 0) + 1

    # Score progression
    scores = [e.get("payload", {}).get("score", 0) for e in round_scores]

    # Detect patterns
    pattern = "unknown"
    root_cause = "Could not determine root cause"
    recommendation = "Try a different approach"

    # Pattern: Scores stuck (no improvement across rounds)
    if len(scores) >= 3 and max(scores) - min(scores) < 0.05:
        pattern = "score_plateau"
        root_cause = f"Score stuck around {scores[-1]:.2f} for {len(scores)} rounds"
        recommendation = "The current approach isn't working. Try a fundamentally different solution."

    # Pattern: Same file keeps failing
    elif stuck_file and failed_files.get(stuck_file, 0) >= 3:
        pattern = "stuck_on_file"
        root_cause = f"File '{stuck_file}' has failed {failed_files[stuck_file]} times"
        recommendation = f"Stop modifying {stuck_file}. Read it first to understand the structure, then make minimal changes."

    # Pattern: High tool failure rate
    elif tool_failure_rate > 0.5:
        pattern = "high_tool_failure"
        most_common_error = max(error_types, key=error_types.get) if error_types else "unknown"
        root_cause = f"{int(tool_failure_rate * 100)}% of tool calls failed. Most common: {most_common_error}"
        recommendation = f"Address the {most_common_error} errors before continuing."

    # Pattern: Permission/allowlist issues
    elif error_types.get("PERMISSION", 0) >= 2:
        pattern = "permission_blocked"
        root_cause = f"{error_types['PERMISSION']} writes blocked by allowlist"
        recommendation = "Only write to files in the allowlist. Read the task spec to see which files are allowed."

    return FailureDiagnosis(
        pattern=pattern,
        root_cause=root_cause,
        recommendation=recommendation,
        tool_failure_rate=tool_failure_rate,
        stuck_file=stuck_file,
        error_types=error_types,
    )


def generate_diagnosis_prompt(
    events: list[dict],
    task_title: str,
    dod_command: str,
    dod_assertion: str,
    max_events: int = 20,
) -> str:
    """Generate a prompt for LLM-based failure diagnosis.

    This can be called via /scillm for deeper analysis when pattern
    matching isn't sufficient.
    """
    # Get recent events
    recent = events[-max_events:] if len(events) > max_events else events

    # Extract key info
    tool_calls = [e for e in recent if e.get("event") in ("tool_intent", "tool_result")]
    scores = [e for e in recent if e.get("event") == "round_scored"]

    prompt = f"""Analyze this code-runner execution that failed to pass its Definition of Done.

## Task
{task_title}

## Definition of Done
Command: {dod_command}
Expected: {dod_assertion}

## Score Progression
{json.dumps([{"round": e.get("round"), "score": e.get("payload", {}).get("score")} for e in scores], indent=2)}

## Recent Tool Calls (last {len(tool_calls)})
{json.dumps([{
    "event": e.get("event"),
    "tool": e.get("payload", {}).get("tool"),
    "ok": e.get("payload", {}).get("ok"),
    "error": e.get("payload", {}).get("error_type"),
    "path": e.get("payload", {}).get("path") or e.get("payload", {}).get("args", {}).get("path"),
} for e in tool_calls], indent=2)}

## Analysis Required
1. What pattern caused the repeated failures?
2. What is the root cause?
3. What specific change would fix this?

Respond in JSON:
{{"pattern": "...", "root_cause": "...", "recommendation": "...", "confidence": 0.0-1.0}}
"""
    return prompt


async def call_diagnosis_llm(prompt: str) -> dict:
    """Call /scillm for LLM-based diagnosis."""
    scillm_url = normalize_scillm_chat_url(os.environ.get("SCILLM_API_BASE"))
    scillm_key = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                scillm_url,
                headers={
                    "Authorization": f"Bearer {scillm_key}",
                    "X-Caller-Skill": "code-runner:diagnosis",
                },
                json={
                    "model": "text",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:
        logger.warning("LLM diagnosis failed: {}", e)
        return {"pattern": "unknown", "root_cause": str(e), "recommendation": "Retry", "confidence": 0.0}
