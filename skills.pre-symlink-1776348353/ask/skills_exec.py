"""
Skill execution helpers for /ask.

Provides functions for running sibling skills via run.sh, invoking the
memory-agent CLI, and parsing their JSON output.

v5.0: Direct graph_memory imports for memory operations (~5ms vs ~5000ms subprocess).
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from loguru import logger as log

# Skill paths (relative to this file)
SKILLS_DIR = Path(__file__).parent.parent
AGENT_SKILLS_DIR = SKILLS_DIR.parent.parent / ".agent" / "skills"

# Prefer direct CLI for memory-agent (fast) over run.sh (slow uv startup)
MEMORY_AGENT_CLI = Path(os.path.expanduser("~/.local/bin/memory-agent"))

# Lazy-initialized MemoryClient — reuses ArangoDB connection pool
_memory_client = None


def _get_memory_client():
    """Get or create a MemoryClient for direct graph_memory access."""
    global _memory_client
    if _memory_client is None:
        try:
            from graph_memory.api import MemoryClient
            _memory_client = MemoryClient()
        except ImportError:
            return None
    return _memory_client


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
    """Run memory recall — direct import first, subprocess fallback.

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
    # Direct import path — ~5ms vs ~5000ms subprocess
    client = _get_memory_client()
    if client is not None:
        try:
            from graph_memory.api import search
            tag_list = tags if tags else None
            coll_list = collections.split(",") if collections else None
            result = search(q=query, scope=scope, k=k, tags=tag_list, collections=coll_list)
            stdout = json.dumps(result, default=str)
            return {"returncode": 0, "stdout": stdout, "stderr": "", "skipped": False}
        except Exception as exc:
            log.debug("direct graph_memory recall failed: %s", exc)

    # Subprocess fallback
    args = ["recall", "-q", query, "--scope", scope, "--k", str(k)]
    if collections:
        args.extend(["--collections", collections])
    if tags:
        for tag in tags:
            args.extend(["--tags", tag])

    if MEMORY_AGENT_CLI.exists():
        try:
            result = subprocess.run(
                [str(MEMORY_AGENT_CLI)] + args,
                capture_output=True, text=True, timeout=timeout,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "skipped": False,
            }
        except subprocess.TimeoutExpired:
            log.error("memory-agent recall timed out after %ds", timeout)
            return {
                "returncode": -2, "stdout": "",
                "stderr": f"memory-agent timed out ({timeout}s)", "skipped": False,
            }
        except Exception as exc:
            log.error("memory-agent recall failed: %s", exc)
            return {"returncode": -3, "stdout": "", "stderr": str(exc), "skipped": False}

    return run_skill("memory", args, timeout=timeout)
