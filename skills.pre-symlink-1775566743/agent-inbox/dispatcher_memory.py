#!/usr/bin/env python3
"""Memory integration for agent-inbox dispatcher.

Handles querying memory for similar bugs/solutions (recall)
and storing successful fixes for future agents (learn).
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

_MEMORY_SOCK = "/run/user/1000/embry/memory.sock"


def _memory_post(endpoint: str, body: dict, timeout: float = 30.0) -> httpx.Response:
    """POST to embry-memory daemon via Unix socket."""
    transport = httpx.HTTPTransport(uds=_MEMORY_SOCK)
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=timeout) as client:
        return client.post(endpoint, json=body)


def recall_from_memory(query: str, project_path: Optional[Path] = None) -> Optional[str]:
    """Query memory for similar bugs and solutions.

    Uses the embry-memory daemon via Unix socket.

    Args:
        query: Bug description or error message
        project_path: Unused (kept for API compat)

    Returns:
        Memory recall results as JSON string, or None if unavailable
    """
    try:
        recall_query = query[:500] if len(query) > 500 else query
        resp = _memory_post("/recall", {"q": recall_query, "k": 3})
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            if items:
                logger.info("Memory recall found relevant lessons")
                return json.dumps(data, indent=2)
            else:
                logger.info("No relevant lessons found in memory")
                return None
        else:
            logger.info("Memory recall returned no results")
            return None
    except httpx.TimeoutException:
        logger.warning("Memory recall timed out")
        return None
    except Exception as e:
        logger.error(f"Memory recall error: {e}")
        return None


def _find_checkpoint_skill() -> Optional[Path]:
    """Find the checkpoint skill run.sh."""
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / ".pi" / "skills" / "checkpoint" / "run.sh",
        Path.home() / ".claude" / "skills" / "checkpoint" / "run.sh",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def checkpoint_fix(message: dict, fix_note: str) -> None:
    """Save a checkpoint of the completed fix for future reference.

    Stores the full fix context (message, project, severity, fix note)
    via /checkpoint save.

    Args:
        message: Original message dict
        fix_note: Completion note describing the fix
    """
    cp_skill = _find_checkpoint_skill()
    if not cp_skill:
        logger.debug("Checkpoint skill not found, skipping")
        return

    msg_id = message.get("id", "unknown")
    to_project = message.get("to", "unknown")
    dispatch = message.get("dispatch", {})
    triage = message.get("triage", {})

    summary = (
        f"Fix for {msg_id} in {to_project}. "
        f"Severity: {triage.get('severity', 'unknown')}. "
        f"Model: {dispatch.get('model', 'unknown')}. "
        f"Retries: {dispatch.get('retry_count', 0)}. "
        f"{fix_note}"
    )[:1000]

    try:
        subprocess.run(
            [
                "bash", str(cp_skill), "save",
                "--topic", f"inbox-fix {msg_id}",
                "--summary", summary,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        logger.info("Checkpoint saved for {}", msg_id)
    except Exception as e:
        logger.warning("Checkpoint save failed: {}", e)


def learn_solution(message: dict, fix_note: str) -> None:
    """Store a successful fix in memory for future agents.

    Closes the recall->fix->learn loop so future dispatches benefit
    from solutions discovered by headless agents. Stores severity,
    dispatch tier, retry count, test command, and model used.

    Args:
        message: Original message dict (contains bug description)
        fix_note: Completion note describing the fix
    """
    bug_description = message.get("message", "")[:500]
    from_project = message.get("from", "unknown")
    to_project = message.get("to", "unknown")
    dispatch = message.get("dispatch", {})
    triage = message.get("triage", {})
    severity = triage.get("severity", "unknown")
    model = dispatch.get("model", "unknown")
    retry_count = dispatch.get("retry_count", 0)
    test_command = dispatch.get("test_command", "none")

    solution = (
        f"{fix_note} | severity={severity} model={model} "
        f"retries={retry_count} test={test_command} "
        f"(from {from_project} to {to_project})"
    )[:800]

    tags = ["agent-inbox", "autonomous-fix", to_project, severity]

    try:
        resp = _memory_post("/learn", {
            "problem": bug_description,
            "solution": solution,
            "tags": tags,
        })
        if resp.status_code == 200:
            logger.info("Learned solution for future agents (severity={}, retries={})",
                       severity, retry_count)
        else:
            logger.warning("Memory learn returned {}", resp.status_code)
    except httpx.TimeoutException:
        logger.warning("Memory learn timed out")
    except Exception as e:
        logger.error("Memory learn error: {}", e)
