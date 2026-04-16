#!/usr/bin/env python3
"""Escalation logic for agent-inbox dispatcher.

Handles human escalation via /interview with /ops-discord fallback
when automated bug fixes fail verification.
"""

import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from loguru import logger


def _find_skill_path(skill_name: str) -> Optional[Path]:
    """Find a skill's run.sh by checking canonical and symlink paths.

    Args:
        skill_name: Skill directory name (e.g. "interview", "ops-discord")

    Returns:
        Path to run.sh if found, None otherwise
    """
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        repo_root / ".pi" / "skills" / skill_name / "run.sh",
        Path.home() / ".claude" / "skills" / skill_name / "run.sh",
        Path.home() / ".pi" / "agent" / "skills" / skill_name / "run.sh",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _build_interview_questions(message: dict, test_output: str) -> dict:
    """Build structured /interview question JSON for escalation.

    Args:
        message: Message dict with full bug context
        test_output: Combined stdout/stderr from failed verification

    Returns:
        Interview questions dict
    """
    msg_id = message.get("id", "unknown")
    to_project = message.get("to", "unknown")
    from_project = message.get("from", "unknown")
    dispatch = message.get("dispatch", {})
    retry_count = dispatch.get("retry_count", 0)
    test_command = dispatch.get("test_command", "N/A")
    model = dispatch.get("model", "sonnet")
    bug_description = message.get("message", "")

    truncated_output = test_output[-2000:] if len(test_output) > 2000 else test_output

    return {
        "title": f"Escalation: Bug Fix Failed — {msg_id}",
        "context": (
            f"An automated agent ({model}) attempted to fix a bug in {to_project} "
            f"(reported by {from_project}) but failed verification after {retry_count + 1} "
            f"attempt(s). Human decision needed."
        ),
        "questions": [
            {
                "id": "action",
                "header": "Action",
                "text": (
                    f"**Bug**: {bug_description[:500]}\n\n"
                    f"**Test command**: `{test_command}`\n\n"
                    f"**Test output** (last 2000 chars):\n```\n{truncated_output}\n```\n\n"
                    f"What should we do?"
                ),
                "options": [
                    {"label": "Retry with different model",
                     "description": f"Current: {model}. Try opus-4.5 or codex-5.2-high."},
                    {"label": "Retry with manual hints",
                     "description": "Re-dispatch with your guidance appended to the prompt."},
                    {"label": "I'll fix it manually",
                     "description": "Mark as needs_review. No more automated attempts."},
                    {"label": "Deprioritize",
                     "description": "Mark as stale and move on. Not critical right now."},
                    {"label": "Reassign to different project",
                     "description": "The bug may belong to a different codebase."},
                ],
                "multi_select": False,
            },
        ],
    }


def _process_interview_response(response: dict, message: dict, inbox) -> bool:
    """Process /interview response and take the appropriate action.

    Args:
        response: Parsed JSON response from /interview
        message: Original inbox message
        inbox: Imported inbox module for status updates

    Returns:
        True if response was processed successfully
    """
    msg_id = message.get("id", "unknown")
    dispatch = message.get("dispatch", {})
    model = dispatch.get("model", "sonnet")

    action = response.get("responses", {}).get("action", {}).get("value", "")
    logger.info("Interview response for {}: {}", msg_id, action)

    if "different model" in action.lower():
        new_model = "opus-4.5" if model != "opus-4.5" else "codex-5.2-high"
        updated_msg = message.copy()
        updated_msg["status"] = "pending"
        updated_msg["dispatch"]["model"] = new_model
        updated_msg["dispatch"]["retry_count"] = 0
        inbox.save_message(updated_msg)
        inbox.update_status(msg_id, "pending", note=f"Escalation: retry with {new_model}")
        return True

    if "manual hints" in action.lower():
        other_text = response.get("responses", {}).get("action", {}).get("other_text", "")
        if other_text:
            updated_msg = message.copy()
            updated_msg["status"] = "pending"
            updated_msg["dispatch"]["retry_count"] = 0
            updated_msg["message"] += f"\n\n[Human Guidance]: {other_text}"
            inbox.save_message(updated_msg)
            inbox.update_status(msg_id, "pending", note="Escalation: retry with human hints")
            return True

    if "manually" in action.lower():
        inbox.update_status(msg_id, "needs_review", note="Escalation: human will fix manually")
        return True

    if "deprioritize" in action.lower():
        inbox.update_status(msg_id, "stale", note="Escalation: deprioritized by human")
        return True

    if "reassign" in action.lower():
        inbox.update_status(msg_id, "needs_review", note="Escalation: needs reassignment")
        return True

    return False


def _try_interview(message: dict, test_output: str, inbox) -> bool:
    """Attempt escalation via /interview skill.

    Args:
        message: Message dict with full bug context
        test_output: Combined stdout/stderr from failed verification
        inbox: Imported inbox module for status updates

    Returns:
        True if interview succeeded, False to fall back to Discord
    """
    msg_id = message.get("id", "unknown")
    interview_path = _find_skill_path("interview")
    if not interview_path:
        logger.warning("/interview skill not found")
        return False

    questions = _build_interview_questions(message, test_output)
    questions_file = Path(tempfile.mktemp(suffix=".json", prefix="escalation_"))

    try:
        questions_file.write_text(json.dumps(questions, indent=2))
        logger.info("Launching /interview for escalation of {}", msg_id)

        result = subprocess.run(
            [str(interview_path), "--mode", "tui", "--file", str(questions_file)],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        if result.returncode == 0 and result.stdout.strip():
            try:
                response = json.loads(result.stdout)
                return _process_interview_response(response, message, inbox)
            except json.JSONDecodeError:
                logger.warning("Could not parse /interview response for {}", msg_id)
        else:
            logger.warning("/interview returned exit {} for {}", result.returncode, msg_id)

    except subprocess.TimeoutExpired:
        logger.warning("/interview timed out after 10 min for {}", msg_id)
    except Exception as e:
        logger.error("/interview failed for {}: {}", msg_id, e)
    finally:
        if questions_file.exists():
            questions_file.unlink()

    return False


def _notify_discord(message: dict, test_output: str) -> None:
    """Send Discord notification as escalation fallback.

    Args:
        message: Message dict with bug context
        test_output: Combined stdout/stderr from failed verification
    """
    msg_id = message.get("id", "unknown")
    to_project = message.get("to", "unknown")
    from_project = message.get("from", "unknown")
    dispatch = message.get("dispatch", {})
    retry_count = dispatch.get("retry_count", 0)
    test_command = dispatch.get("test_command", "N/A")
    model = dispatch.get("model", "sonnet")
    bug_description = message.get("message", "")

    truncated_output = test_output[-500:] if len(test_output) > 500 else test_output

    discord_path = _find_skill_path("ops-discord")
    if not discord_path:
        logger.warning("ops-discord skill not found — no notification channel")
        return

    discord_msg = (
        f"**Escalation: Bug fix failed** — `{msg_id}`\n"
        f"Project: {to_project} (from {from_project})\n"
        f"Model: {model} | Retries: {retry_count + 1}\n"
        f"Test: `{test_command}`\n"
        f"Bug: {bug_description[:300]}\n"
        f"Error: {truncated_output}"
    )
    try:
        subprocess.run(
            [str(discord_path), "notify", "--channel", "agent-alerts",
             "--message", discord_msg],
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        logger.info("Discord notification sent for {}", msg_id)
    except Exception as e:
        logger.error("Discord notification failed: {}", e)


def escalate_to_human(message: dict, test_output: str, inbox) -> None:
    """Escalate a failed fix to human via /interview, falling back to /ops-discord.

    Generates a structured /interview question JSON with bug context, test output,
    and decision options. If /interview is unavailable or times out, falls back
    to /ops-discord notification.

    Args:
        message: Message dict with full bug context
        test_output: Combined stdout/stderr from the failed verification
        inbox: Imported inbox module for status updates
    """
    msg_id = message.get("id", "unknown")
    dispatch = message.get("dispatch", {})
    retry_count = dispatch.get("retry_count", 0)

    # Try /interview first
    if not _try_interview(message, test_output, inbox):
        # Fallback to Discord
        logger.info("Falling back to /ops-discord for {}", msg_id)
        _notify_discord(message, test_output)

    # Set status to escalated
    inbox.update_status(
        msg_id, "escalated",
        note=f"Auto-fix failed after {retry_count + 1} attempts. Awaiting human.",
    )
