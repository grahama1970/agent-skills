"""
Skill execution helpers for /ask.

Provides functions for running sibling skills via run.sh and parsing their JSON
output. Memory access is routed through the memory skill, not direct imports.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from loguru import logger as log

# Skill paths. This module may run from either a project `.pi/skills/ask`
# checkout or the standalone `agent-skills/skills/ask` repository.
SKILL_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = SKILL_ROOT.parent
AGENT_SKILLS_DIR = SKILLS_DIR.parent / ".agent" / "skills"

def run_skill(name: str, args: list[str], timeout: int = 60) -> dict:
    """Run a skill via its run.sh and capture output."""
    candidates = [
        SKILLS_DIR / name / "run.sh",
        AGENT_SKILLS_DIR / name / "run.sh",
    ]

    script = None
    for c in candidates:
        if c.exists():
            script = c
            break

    if not script:
        log.warning("Skill '%s' not found in %s or %s", name, SKILLS_DIR, AGENT_SKILLS_DIR)
        return {"returncode": -1, "stdout": "", "stderr": f"Skill {name} not found", "skipped": True}

    log.debug("Running skill '%s': %s %s", name, script, args)
    try:
        result = subprocess.run(
            [str(script)] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(script.parent),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        log.debug("Skill '%s' returned code=%d, stdout=%d bytes, stderr=%d bytes",
                   name, result.returncode, len(result.stdout), len(result.stderr))
        if result.returncode != 0:
            log.debug("Skill '%s' stderr: %s", name, result.stderr[:200])
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "skipped": False,
        }
    except subprocess.TimeoutExpired:
        log.error("Skill '%s' timed out after %ds", name, timeout)
        return {"returncode": -2, "stdout": "", "stderr": f"Skill {name} timed out ({timeout}s)", "skipped": False}
    except Exception as e:
        log.error("Skill '%s' failed with exception: %s", name, e)
        return {"returncode": -3, "stdout": "", "stderr": str(e), "skipped": False}


def parse_json_output(stdout: str) -> Optional[dict]:
    """Parse JSON from skill output, handling text headers before JSON."""
    stdout = stdout.strip()
    if not stdout:
        return None

    # Try full parse first
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        pass

    # Try from first '{' (handles text headers before JSON)
    json_start = stdout.find("{")
    if json_start >= 0:
        try:
            return json.loads(stdout[json_start:])
        except json.JSONDecodeError:
            pass

    # Try from first '[' (array output)
    json_start = stdout.find("[")
    if json_start >= 0:
        try:
            return json.loads(stdout[json_start:])
        except json.JSONDecodeError:
            pass

    log.debug("Could not parse JSON from output (%d bytes): %s", len(stdout), stdout[:100])
    return None


def parse_memory_output(stdout: str) -> list[dict]:
    """Parse memory recall output, handling pretty-printed JSON."""
    data = parse_json_output(stdout)
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    if isinstance(data, dict) and ("problem" in data or "solution" in data):
        return [data]
    return []


def run_memory_recall(
    query: str,
    scope: str,
    k: int = 5,
    timeout: int = 15,
    collections: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """Run memory recall through the memory skill.

    Args:
        query: The search query.
        scope: Memory scope to search.
        k: Number of results.
        timeout: Timeout in seconds.
        collections: Comma-separated collection names (lessons, doc_chunks, etc.).
        tags: List of tags to filter by (e.g. ["bridge:Corruption"]).

    Returns:
        dict with returncode, stdout, stderr, skipped.
    """
    args = ["recall", "-q", query, "--scope", scope, "--k", str(k)]
    if collections:
        args.extend(["--collections", collections])
    if tags:
        for tag in tags:
            args.extend(["--tags", tag])

    return run_skill("memory", args, timeout=timeout)


def run_extract_entities(
    text: str,
    *,
    scope: str = "",
    collection: str = "sparta_controls",
    limit: int = 500,
    timeout: int = 20,
) -> dict[str, Any]:
    """Run /extract-entities without duplicating extractor logic.

    /ask calls the sibling skill via run.sh so /extract-entities remains the
    single owner of entity resolution. The current public JSON subcommand accepts
    question text as a positional argument; scope/collection/limit are retained
    in the helper signature for callers and future extractor CLI support.
    """
    _ = (scope, collection, limit)  # documented extension points for extractor CLI parity
    result = run_skill("extract-entities", ["extract", text, "--json"], timeout=timeout)
    result["payload"] = parse_json_output(result.get("stdout", "")) or {"entities": []}
    return result
