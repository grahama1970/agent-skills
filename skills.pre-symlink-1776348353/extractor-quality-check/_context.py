"""Persona autonomous loop — context-gathering helpers.

Functions that collect external state needed by the persona loop:
scenario loading, project context, session history, datalake state,
memory recall/learn, and /ask execution.
"""
from __future__ import annotations
import os

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from loguru import logger as log

from _config import (
    ASK_RUN_SH,
    MEMORY_AGENT_CLI,
    PROJECT_CONTEXT_FILE,
    SCENARIOS_FILE,
    SESSION_DIR,
    THIS_DIR,
)


def load_scenarios() -> list[dict]:
    """Load the 210 seed scenarios."""
    if not SCENARIOS_FILE.exists():
        log.warning("Scenarios file not found: {}", SCENARIOS_FILE)
        return []
    data = json.loads(SCENARIOS_FILE.read_text())
    return data.get("scenarios", [])


def load_project_context() -> dict:
    """Load the F-35 project context YAML."""
    if not PROJECT_CONTEXT_FILE.exists():
        log.warning("Project context not found: {}", PROJECT_CONTEXT_FILE)
        return {}
    try:
        import yaml
        return yaml.safe_load(PROJECT_CONTEXT_FILE.read_text()) or {}
    except ImportError:
        # Fallback: just note it exists
        return {"_loaded": False, "_path": str(PROJECT_CONTEXT_FILE)}


def count_previous_sessions(persona_id: str) -> int:
    """Count how many sessions this persona has completed."""
    if not SESSION_DIR.exists():
        return 0
    count = 0
    for f in SESSION_DIR.glob("*.jsonl"):
        try:
            data = json.loads(f.read_text().strip().split("\n")[0])
            if data.get("persona_id") == persona_id:
                count += 1
        except (json.JSONDecodeError, IndexError, OSError):
            continue
    return count


def get_previous_queries(persona_id: str, limit: int = 20) -> list[str]:
    """Get recent queries this persona has asked (to avoid repetition)."""
    if not SESSION_DIR.exists():
        return []
    queries: list[str] = []
    files = sorted(SESSION_DIR.glob("*.jsonl"), reverse=True)
    for f in files[:100]:  # scan last 100 sessions
        try:
            data = json.loads(f.read_text().strip().split("\n")[0])
            if data.get("persona_id") != persona_id:
                continue
            for msg in data.get("messages", []):
                if msg.get("from") == "user":
                    queries.append(msg["message"])
        except (json.JSONDecodeError, IndexError, OSError):
            continue
        if len(queries) >= limit:
            break
    return queries[:limit]


def determine_learning_phase(session_count: int) -> str:
    """Map session count to learning phase for scenario weighting.

    Phases reflect the datalake cleanup narrative:
      week_1 (cleanup)    -- datalake is a mess, hunt extraction errors
      week_2 (triage)     -- categorize defects, start fixing patterns
      week_3 (stabilize)  -- integrity improving, start real questions
      week_4 (trust)      -- datalake trustworthy, real engineering work
      ongoing (operate)   -- steady-state, requirements & cross-doc analysis
    """
    if session_count < 10:
        return "week_1"
    elif session_count < 25:
        return "week_2"
    elif session_count < 50:
        return "week_3"
    elif session_count < 100:
        return "week_4"
    return "ongoing"


def collect_datalake_state() -> dict:
    """Run the datalake state collector and return state dict."""
    collector_script = THIS_DIR / "datalake_state_collector.py"
    if not collector_script.exists():
        log.warning("Datalake state collector not found")
        return {}
    try:
        result = subprocess.run(
            [sys.executable, str(collector_script)],
            capture_output=True, text=True, timeout=60,
            cwd=str(THIS_DIR),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        log.error("Datalake state collection failed: {}", e)
    return {}


def recall_memory(query: str, scope: str, k: int = 5) -> list[dict]:
    """Query /memory recall for existing knowledge."""
    if not MEMORY_AGENT_CLI.exists():
        return []
    try:
        result = subprocess.run(
            [str(MEMORY_AGENT_CLI), "recall", "-q", query, "--scope", scope, "--k", str(k)],
            capture_output=True, text=True, timeout=15,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("items", [])
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        pass
    return []


def learn_to_memory(problem: str, solution: str, scope: str, tags: list[str] | None = None) -> bool:
    """Store a finding back to /memory."""
    if not MEMORY_AGENT_CLI.exists():
        log.warning("memory-agent CLI not found, skipping learn-back")
        return False
    cmd = [
        str(MEMORY_AGENT_CLI), "learn",
        "--problem", problem,
        "--solution", solution,
        "--scope", scope,
    ]
    if tags:
        for t in tags:
            cmd.extend(["--tag", t])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def run_ask(query: str, scope: str, persona_id: str, k: int = 5) -> dict:
    """Run /ask and return results."""
    if not ASK_RUN_SH.exists():
        log.error("/ask run.sh not found at {}", ASK_RUN_SH)
        return {"items": [], "answer": ""}

    cmd = [
        str(ASK_RUN_SH), "ask", query,
        "--scope", scope,
        "--persona-id", persona_id,
        "--k", str(k),
        "--json",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            cwd=str(ASK_RUN_SH.parent),
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        log.error("/ask failed: {}", e)
    return {"items": [], "answer": ""}
