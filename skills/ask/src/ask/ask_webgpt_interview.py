"""Ambiguity resolution via /interview for /ask's webgpt-review dispatch.

When `/ask webgpt /review-X` is parsed but key arguments are missing or
ambiguous, /ask delegates the missing pieces to /interview. The five
ambiguity classes are:

  1. diff_scope     -- "recent code changes" needs to resolve to a git scope
  2. tab_selection  -- multiple chatgpt.com tabs and no --webgpt-tab-id/project
  3. max_rounds     -- "iterate" without a number
  4. skill_prefix   -- /review-X token matched more than one registered skill
  5. project_bind   -- no project name and the agent wants persistent state

Each helper builds a small `questions.json` payload, runs the /interview
skill, and returns the resolved value (or None on cancel/timeout).

Per project conventions: use existing /interview skill; never re-implement
interactive prompting here.
"""

from __future__ import annotations

from .env import load_dotenv_once

load_dotenv_once()

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional


INTERVIEW_RUN = os.environ.get(
    "ASK_INTERVIEW_RUN",
    str(Path.home() / ".claude" / "skills" / "interview" / "run.sh"),
)


def _run_interview(questions: list[dict[str, Any]], *, title: str = "Clarify", timeout: int = 300) -> dict[str, Any]:
    """Spawn /interview with a small questions.json and return its response dict.

    Returns an empty dict on cancel/timeout/failure so the caller can apply a
    safe default rather than crash.
    """
    if not Path(INTERVIEW_RUN).exists():
        return {}
    payload = {"title": title, "questions": questions}
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="ask-interview-", delete=False
    ) as f:
        json.dump(payload, f)
        path = Path(f.name)
    try:
        proc = subprocess.run(
            [INTERVIEW_RUN, "--file", str(path), "--json", "--timeout", str(timeout)],
            capture_output=True,
            text=True,
            timeout=timeout + 30,
        )
    except Exception:
        return {}
    finally:
        try:
            path.unlink()
        except Exception:
            pass
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def _read_choice(response: dict[str, Any], qid: str) -> str:
    """Pull a single choice's label from the /interview response shape."""
    answer = (response.get("responses") or {}).get(qid) or {}
    val = answer.get("value")
    if isinstance(val, str):
        return val
    return ""


def clarify_diff_scope(description: str) -> Optional[str]:
    """Ask the human what 'recent code changes' should map to.

    Returns a git diff scope string like `origin/main..HEAD` or `HEAD~5..HEAD`,
    or None if the human cancelled / timed out (caller should fall back to a
    documented default like `origin/main..HEAD`).
    """
    questions = [{
        "id": "diff_scope",
        "header": "Diff scope",
        "text": (
            f"You asked for a webgpt review of: {description!r}. "
            "Which diff should I review?"
        ),
        "options": [
            {"label": "origin/main..HEAD", "description": "Everything on this branch since main (recommended)"},
            {"label": "HEAD~1..HEAD", "description": "Just the latest commit"},
            {"label": "HEAD~5..HEAD", "description": "The last 5 commits"},
            {"label": "uncommitted (staged + unstaged)", "description": "Working tree changes only, ignoring committed work"},
        ],
        "multi_select": False,
    }]
    resp = _run_interview(questions, title="Webgpt review — clarify diff scope")
    choice = _read_choice(resp, "diff_scope")
    if not choice:
        return None
    if choice.startswith("uncommitted"):
        return ""  # empty scope → git diff with no args (uncommitted only)
    return choice.split(" ", 1)[0]


def clarify_max_rounds(description: str) -> Optional[int]:
    """Ask how many ping-pong rounds to allow when not specified."""
    questions = [{
        "id": "max_rounds",
        "header": "Max rounds",
        "text": (
            f"You asked to iterate on the webgpt review of: {description!r}. "
            "How many rounds maximum? (Halts early on SAFE.)"
        ),
        "options": [
            {"label": "1 (single shot)", "description": "Just one webgpt call, no ping-pong"},
            {"label": "2 (one refinement)", "description": "First verdict, then one targeted follow-up if not SAFE"},
            {"label": "3", "description": "Up to three rounds"},
            {"label": "5", "description": "Up to five rounds"},
        ],
        "multi_select": False,
    }]
    resp = _run_interview(questions, title="Webgpt review — max rounds")
    choice = _read_choice(resp, "max_rounds")
    if not choice:
        return None
    digit = "".join(c for c in choice if c.isdigit())
    try:
        return max(1, min(10, int(digit)))
    except (TypeError, ValueError):
        return None


def clarify_tab_selection(candidates: list[dict[str, str]]) -> Optional[str]:
    """Choose a chatgpt.com tab when auto-resolve found more than one."""
    if not candidates:
        return None
    options = []
    for c in candidates[:8]:  # cap for usability
        label = f"{c.get('id', '?')} — {c.get('title', '')}"[:80]
        desc = c.get("url", "")[:120]
        options.append({"label": label, "description": desc})
    options.append({
        "label": "Create a new background tab",
        "description": "Use --webgpt-create-tab so surf creates a fresh tab autonomously",
    })
    questions = [{
        "id": "tab",
        "header": "ChatGPT tab",
        "text": "Multiple chatgpt.com tabs are open. Which one should webgpt control?",
        "options": options,
        "multi_select": False,
    }]
    resp = _run_interview(questions, title="Webgpt review — choose tab")
    choice = _read_choice(resp, "tab")
    if not choice:
        return None
    if choice.startswith("Create a new"):
        return "__create__"
    # Pull the leading tab id off the label.
    return choice.split(" ", 1)[0].strip()


def clarify_project_bind(default_name: str) -> tuple[bool, str]:
    """Ask whether to bind this run to a project name. Returns (bind?, name)."""
    questions = [{
        "id": "bind",
        "header": "Project bind",
        "text": (
            "Would you like to bind this webgpt review to a project, so the "
            "same ChatGPT conversation tab is reused on follow-up calls?"
        ),
        "options": [
            {"label": f"Bind to '{default_name}'", "description": "Persist tab id at ~/.pi/webgpt-projects/<name>.json"},
            {"label": "Don't bind", "description": "One-shot review; pick a fresh tab next time"},
        ],
        "multi_select": False,
    }]
    resp = _run_interview(questions, title="Webgpt review — project binding")
    choice = _read_choice(resp, "bind")
    if not choice:
        return (False, "")
    if choice.startswith("Bind to"):
        return (True, default_name)
    return (False, "")
