"""Interview skill integration helper for ambiguous search handling."""

import os
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def create_interview_session(
    title: str,
    question: str,
    options: list[dict],
    context: Optional[str] = None,
) -> dict:
    """
    Create interview session for ambiguous search results.

    Args:
        title: Session title
        question: Question to ask user
        options: List of option dicts with 'label' and 'description'
        context: Optional context text

    Returns:
        Interview session dict for JSON file
    """
    session = {
        "title": title,
        "questions": [
            {
                "id": "selection",
                "header": "Select",
                "text": question,
                "type": "select",
                "options": options,
            }
        ],
    }

    if context:
        session["context"] = context

    return session


def invoke_interview(session: dict, mode: str = "auto") -> Optional[str]:
    """
    Invoke /interview skill with session data.

    Args:
        session: Interview session dict
        mode: Interview mode (html, tui, simple, auto)

    Returns:
        Selected value from user, or None if cancelled

    Raises:
        FileNotFoundError: If interview skill not found
        subprocess.SubprocessError: If interview skill fails
    """
    interview_skill = Path.home() / ".pi" / "skills" / "interview"
    run_script = interview_skill / "run.sh"

    if not run_script.exists():
        raise FileNotFoundError(f"Interview skill not found at {interview_skill}")

    # Create temporary JSON file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(session, f, indent=2)
        temp_file = Path(f.name)

    try:
        # Invoke interview skill
        result = subprocess.run(
            ["bash", str(run_script), "--file", str(temp_file), "--mode", mode, "--json"],
            cwd=interview_skill,
            capture_output=True,
            text=True,
            timeout=300,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"Interview failed: {result.stderr or result.stdout}"
            )

        # Parse response
        response = json.loads(result.stdout)

        if not response.get("completed"):
            return None  # User cancelled

        # Extract selection
        responses = response.get("responses", {})
        selection = responses.get("selection", {})
        value = selection.get("value")

        return value

    finally:
        # Clean up temp file
        temp_file.unlink(missing_ok=True)


def handle_multiple_results(
    query: str,
    results: list[dict],
    max_options: int = 10,
) -> Optional[dict]:
    """
    Handle multiple search results via interview.

    Args:
        query: Original search query
        results: List of search result dicts
        max_options: Maximum options to show (default: 10)

    Returns:
        Selected result dict, or None if cancelled
    """
    if not results:
        return None

    if len(results) == 1:
        return results[0]  # Only one result, return it

    # Limit results to max_options
    limited_results = results[:max_options]

    # Create interview options
    options = []
    for i, result in enumerate(limited_results):
        title = result.get("title", "Unknown")
        size = result.get("size", 0)
        size_gb = size / (1024 ** 3) if size > 0 else 0
        pub_date = result.get("pubDate", "Unknown date")

        label = title[:60] + ("..." if len(title) > 60 else "")
        description = f"{size_gb:.2f} GB | {pub_date}"

        options.append({
            "label": label,
            "description": description,
        })

    session = create_interview_session(
        title=f"Multiple results for '{query}'",
        question="Which release would you like to download?",
        options=options,
        context=f"Found {len(results)} results. Showing top {len(limited_results)}.",
    )

    try:
        selected_label = invoke_interview(session)

        if not selected_label:
            return None  # User cancelled

        # Find matching result by label
        for i, opt in enumerate(options):
            if opt["label"] == selected_label:
                return limited_results[i]

        # Fallback: return first result if no exact match
        return limited_results[0]

    except (FileNotFoundError, subprocess.SubprocessError) as e:
        # Interview failed - log error and return first result as fallback
        print(f"Warning: Interview failed ({e}), using first result")
        return limited_results[0]
