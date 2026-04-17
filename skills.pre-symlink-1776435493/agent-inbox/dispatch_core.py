"""
Agent-Inbox Dispatcher - Core helpers: model registry, prompt building, memory recall.

Contains load_model_registry, build_prompt, recall_from_memory, _learn_solution,
and project path resolution.
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from loguru import logger
import httpx


def _memory_post(endpoint: str, body: dict, timeout: float = 30.0) -> httpx.Response:
    """POST to embry-memory daemon via Unix socket."""
    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=timeout) as client:
        return client.post(endpoint, json=body)


# Helper for model registry
def load_model_registry() -> Dict[str, List[str]]:
    """Load model registry from config or defaults."""
    registry_path = Path(os.environ.get("AGENT_INBOX_DIR", Path.home() / ".agent-inbox")) / "models.json"
    defaults = {
        "sonnet": ["claude", "--model", "sonnet"],
        "opus-4.5": ["claude", "--model", "opus"],
        "codex-5.2": ["codex", "--model", "gpt-5.2-codex"],
        "codex-5.2-high": ["codex", "--model", "gpt-5.2-codex", "--reasoning", "high"],
    }

    if registry_path.exists():
        try:
            custom = json.loads(registry_path.read_text())
            defaults.update(custom)
            return defaults
        except Exception as e:
            print(f"Warning: Failed to load models.json: {e}")
            return defaults

    return defaults


# Model to CLI command mapping
MODEL_COMMANDS: Dict[str, List[str]] = load_model_registry()

# Inbox directory configuration
INBOX_DIR = Path(os.environ.get("AGENT_INBOX_DIR", Path.home() / ".agent-inbox"))
REGISTRY_FILE = INBOX_DIR / "projects.json"
LOG_DIR = INBOX_DIR / "logs"


def _load_registry() -> Dict[str, str]:
    """Load project registry."""
    if REGISTRY_FILE.exists():
        try:
            return json.loads(REGISTRY_FILE.read_text())
        except Exception as e:
            logger.debug("JSON parse failed: {}", e)
    return {}


def get_project_path(project_name: str) -> Optional[Path]:
    """Get filesystem path for a registered project.

    Args:
        project_name: Name of the project

    Returns:
        Path to project directory, or None if not registered
    """
    registry = _load_registry()
    path_str = registry.get(project_name)
    if path_str:
        return Path(path_str)
    return None


def recall_from_memory(query: str, project_path: Optional[Path] = None) -> Optional[str]:
    """Query memory for similar bugs and solutions.

    Uses the /memory skill to find relevant lessons learned.

    Args:
        query: Bug description or error message
        project_path: Path to run memory recall from

    Returns:
        Memory recall results as markdown, or None if unavailable
    """
    try:
        recall_query = query[:500] if len(query) > 500 else query
        resp = _memory_post("/recall", {"q": recall_query, "k": 3})
        if resp.status_code == 200:
            data = resp.json()
            output = json.dumps(data, indent=2)
            items = data.get("items", [])
            if items and len(output) > 50:
                print("[dispatcher] Memory recall found relevant lessons")
                return output
            else:
                print("[dispatcher] No relevant lessons found in memory")
                return None
        else:
            print("[dispatcher] Memory recall returned no results")
            return None
    except httpx.TimeoutException:
        print("[dispatcher] Memory recall timed out")
        return None
    except Exception as e:
        print(f"[dispatcher] Memory recall error: {e}")
        return None


def _learn_solution(message: dict, fix_note: str) -> None:
    """Store a successful fix in memory for future agents.

    Closes the recall->fix->learn loop so future dispatches benefit
    from solutions discovered by headless agents.

    Args:
        message: Original message dict (contains bug description)
        fix_note: Completion note describing the fix
    """
    bug_description = message.get("message", "")[:500]
    from_project = message.get("from", "unknown")
    to_project = message.get("to", "unknown")
    solution = f"{fix_note} (from {from_project} to {to_project})"[:500]

    try:
        resp = _memory_post("/learn", {
            "problem": bug_description,
            "solution": solution,
            "tags": ["agent-inbox", to_project],
        })
        if resp.status_code == 200:
            print("[dispatcher] Learned solution for future agents")
        else:
            print(f"[dispatcher] Memory learn returned {resp.status_code}")
    except httpx.TimeoutException:
        print("[dispatcher] Memory learn timed out")
    except Exception as e:
        print(f"[dispatcher] Memory learn error: {e}")


def build_prompt(message: dict, memory_context: Optional[str] = None) -> str:
    """Build a bug-fix prompt from an inbox message.

    Args:
        message: Message dict with id, to, from, message, dispatch, context fields
        memory_context: Optional memory recall results to include

    Returns:
        Formatted prompt string for the agent
    """
    msg_id = message.get("id", "unknown")
    from_project = message.get("from", "unknown")
    to_project = message.get("to", "unknown")
    msg_type = message.get("type", "bug")
    priority = message.get("priority", "normal")
    content = message.get("message", "")
    dispatch = message.get("dispatch", {})
    test_command = dispatch.get("test_command")
    context_files = message.get("context", [])

    prompt_parts = [
        f"# Bug Fix Request from {from_project}",
        "",
        f"**Message ID**: {msg_id}",
        f"**Type**: {msg_type}",
        f"**Priority**: {priority}",
        "",
    ]

    if memory_context:
        prompt_parts.extend([
            "## Prior Solutions from Memory",
            "",
            "The following relevant lessons and solutions were found. Review and adapt as needed:",
            "",
            memory_context,
            "",
        ])

    prompt_parts.extend([
        "## Description",
        "",
        content,
        "",
    ])

    # Add thread history if available
    thread_id = message.get("thread_id") or message.get("id")
    if thread_id:
        try:
            try:
                from . import inbox
            except ImportError:
                import inbox

            thread_msgs = inbox.list_thread(thread_id)

            history_parts = []
            for tm in thread_msgs:
                if tm.get("id") == msg_id:
                    continue

                sender = tm.get("from", "unknown")
                tm_content = tm.get("message", "")
                tm_type = tm.get("type", "info")
                tm_created = tm.get("created_at", "")

                history_parts.append(f"### Reply from {sender} ({tm_created})")
                history_parts.append(f"Type: {tm_type}")
                history_parts.append(tm_content)
                history_parts.append("")

            if history_parts:
                prompt_parts.extend([
                    "## Discussion History / Steering",
                    "Pay attention to these additional messages and guidance:",
                    "",
                ] + history_parts)

        except Exception as e:
            print(f"[dispatcher] Error fetching thread history: {e}")

    if context_files:
        prompt_parts.extend([
            "## Context Files",
            "",
        ])
        for ctx in context_files:
            prompt_parts.extend([
                f"### {ctx.get('file', 'Unknown')}",
                f"Path: `{ctx.get('path', 'N/A')}`",
                "```",
                ctx.get("content", ""),
                "```",
                "",
            ])

    prompt_parts.extend([
        "## Context & State",
        "",
        "1. To understand the current project state, run:",
        "   `.pi/skills/create-context/run.sh generate --minimal`",
        "2. Read the generated `local/docs/CONTEXT.md` to ground your work.",
        "",
        "## Instructions",
        "",
        "1. Review any prior solutions from memory above",
        "2. Analyze the bug described above",
        "3. Find the root cause in the codebase",
        "4. Implement a fix",
        "5. Test your changes",
    ])

    if test_command:
        prompt_parts.extend([
            f"6. Run the verification command: `{test_command}`",
            "7. Only mark complete if verification passes",
        ])
    else:
        prompt_parts.extend([
            "6. Commit your changes with a clear message",
        ])

    prompt_parts.extend([
        "",
        "## Completion",
        "",
        "When done, update the inbox message status:",
        f"```",
        f"agent-inbox update-status {msg_id} done --note 'Fixed: <brief description>'",
        f"```",
    ])

    return "\n".join(prompt_parts)
