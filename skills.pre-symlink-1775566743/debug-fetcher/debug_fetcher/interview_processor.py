"""Interview response processor.

Parses responses from /interview and converts them into
actionable recovery steps.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .memory_schema import RecoveryAction


def process_response(response: Dict[str, Any]) -> List[RecoveryAction]:
    """Process /interview response into recovery actions.

    Args:
        response: Response dict from /interview skill

    Returns:
        List of RecoveryAction to execute
    """
    actions = []

    if not response.get("completed", False):
        return actions

    responses = response.get("responses", {})

    for question_id, answer in responses.items():
        action = _parse_answer(question_id, answer)
        if action:
            actions.append(action)

    return actions


def _parse_answer(question_id: str, answer: Dict[str, Any]) -> Optional[RecoveryAction]:
    """Parse a single answer into a RecoveryAction.

    Args:
        question_id: The question ID (url_xxxx or domain_xxxx)
        answer: The answer dict with decision and value

    Returns:
        RecoveryAction or None
    """
    decision = answer.get("decision", "")
    value = answer.get("value", "")
    other_text = answer.get("other_text", "")

    # Extract URL from question_id if possible
    # For domain questions, we'll handle multiple URLs
    url = answer.get("url", question_id)

    # Determine action type based on selected option
    if "credentials" in value.lower():
        return RecoveryAction(
            url=url,
            action_type="credentials",
            credentials=_parse_credentials(other_text),
            notes=other_text,
        )

    elif "mirror" in value.lower() or "alternate" in value.lower():
        mirror_url = _extract_url(other_text)
        return RecoveryAction(
            url=url,
            action_type="mirror",
            mirror_url=mirror_url,
            notes=other_text,
        )

    elif "download" in value.lower() or "manually" in value.lower():
        file_path = other_text.strip() if other_text else None
        return RecoveryAction(
            url=url,
            action_type="manual_file",
            file_path=file_path,
            notes=other_text,
        )

    elif "skip" in value.lower():
        return RecoveryAction(
            url=url,
            action_type="skip",
            notes=other_text or "User chose to skip",
        )

    elif "retry" in value.lower() or "later" in value.lower():
        return RecoveryAction(
            url=url,
            action_type="retry",
            retry_after=3600,  # Default: 1 hour
            notes=other_text,
        )

    elif "different strategy" in value.lower():
        # User suggested a specific approach
        return RecoveryAction(
            url=url,
            action_type="custom_strategy",
            notes=other_text,
        )

    elif "individually" in value.lower():
        # User wants per-URL questions instead of grouped
        return RecoveryAction(
            url=url,
            action_type="expand_domain",
            notes="User requested individual URL handling",
        )

    return None


def _parse_credentials(text: str) -> Optional[Dict[str, str]]:
    """Parse credentials from user input.

    Looks for patterns like:
    - username: xxx, password: yyy
    - user=xxx pass=yyy
    - xxx / yyy

    Args:
        text: User-provided text

    Returns:
        Dict with username/password or None
    """
    if not text:
        return None

    text = text.strip()

    # Pattern: username: xxx, password: yyy
    import re

    patterns = [
        r"username[:\s]+([^\s,]+).*password[:\s]+([^\s,]+)",
        r"user[=:\s]+([^\s,]+).*pass(?:word)?[=:\s]+([^\s,]+)",
        r"login[:\s]+([^\s,]+).*password[:\s]+([^\s,]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return {"username": match.group(1), "password": match.group(2)}

    # Pattern: xxx / yyy (simple two-part)
    if " / " in text:
        parts = text.split(" / ", 1)
        if len(parts) == 2:
            return {"username": parts[0].strip(), "password": parts[1].strip()}

    # Could not parse - return raw text as hint
    return {"hint": text}


def _extract_url(text: str) -> Optional[str]:
    """Extract a URL from user input.

    Args:
        text: User-provided text

    Returns:
        URL string or None
    """
    if not text:
        return None

    import re

    # Look for URLs
    url_pattern = r"https?://[^\s<>\"{}|\\^`\[\]]+"
    match = re.search(url_pattern, text)
    if match:
        return match.group(0)

    # Check if the whole text looks like a URL
    text = text.strip()
    if text.startswith(("http://", "https://", "www.")):
        return text if text.startswith("http") else f"https://{text}"

    return None


def group_actions_by_type(actions: List[RecoveryAction]) -> Dict[str, List[RecoveryAction]]:
    """Group recovery actions by their type.

    Useful for batch processing similar actions.

    Args:
        actions: List of RecoveryAction

    Returns:
        Dict mapping action_type to list of actions
    """
    grouped: Dict[str, List[RecoveryAction]] = {}

    for action in actions:
        if action.action_type not in grouped:
            grouped[action.action_type] = []
        grouped[action.action_type].append(action)

    return grouped
