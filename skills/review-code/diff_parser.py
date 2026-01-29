"""Diff parsing and extraction for code-review skill.

Contains:
- Unified diff extraction from LLM responses
- Diff validation helpers
"""
from __future__ import annotations

import re
from typing import Optional


def extract_diff(response: str) -> Optional[str]:
    """Extract unified diff/patch block from response.

    Prefers blocks containing unified diff markers (---/+++ or @@ hunks).

    Args:
        response: Raw LLM response text

    Returns:
        Extracted diff text or None if no valid diff found
    """
    blocks = re.findall(r'```(?:diff|patch)?\s*\n(.*?)\n```', response, re.DOTALL)
    for b in blocks:
        text = b.strip()
        # Prefer blocks with file headers
        if re.search(r'^\s*---\s', text, re.MULTILINE) and re.search(r'^\s*\+\+\+\s', text, re.MULTILINE):
            return text
        # Or with hunk headers
        if re.search(r'^\s*@@\s*-\d+', text, re.MULTILINE):
            return text
    # Fall back to first code block if no diff markers found
    if blocks:
        return blocks[0].strip()
    return None


def has_valid_diff_markers(text: str) -> bool:
    """Check if text contains valid unified diff markers.

    Args:
        text: Text to check

    Returns:
        True if text contains --- and +++ headers or @@ hunks
    """
    has_file_headers = (
        re.search(r'^\s*---\s', text, re.MULTILINE) is not None and
        re.search(r'^\s*\+\+\+\s', text, re.MULTILINE) is not None
    )
    has_hunks = re.search(r'^\s*@@\s*-\d+', text, re.MULTILINE) is not None
    return has_file_headers or has_hunks


def count_hunks(diff_text: str) -> int:
    """Count the number of hunks in a diff.

    Args:
        diff_text: Unified diff text

    Returns:
        Number of @@ hunk headers found
    """
    return len(re.findall(r'^@@\s*-\d+', diff_text, re.MULTILINE))


def extract_files_from_diff(diff_text: str) -> list[str]:
    """Extract list of files affected by a diff.

    Args:
        diff_text: Unified diff text

    Returns:
        List of file paths from +++ headers
    """
    files = []
    for match in re.finditer(r'^\+\+\+\s+(?:b/)?(.+?)(?:\s|$)', diff_text, re.MULTILINE):
        file_path = match.group(1).strip()
        if file_path and file_path != "/dev/null":
            files.append(file_path)
    return files
