"""Embry OS query and health dispatch commands backed by memory and monitor skills."""

#!/usr/bin/env python3
"""
/ask os query — Query embry-os internal knowledge and runtime health.

Two modes:
  ask_os()        — Static knowledge query against scope=os memory
  ask_os_health() — Runtime health query via monitor/ops skill dispatch
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from loguru import logger as log

log.remove()
if os.environ.get("ASK_DEBUG"):
    log.add(sys.stderr, level="DEBUG")
else:
    log.add(sys.stderr, level="INFO")

from .skills_exec import run_skill, parse_json_output, parse_memory_output

SKILLS_DIR = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Memory Recall (scope=os)
# ---------------------------------------------------------------------------

def recall_os(
    query: str,
    k: int = 5,
    tags: Optional[list[str]] = None,
    timeout: int = 15,
) -> list[dict]:
    """Recall from memory with scope=os."""
    args = ["recall", "-q", query, "--scope", "os", "--k", str(k)]
    if tags:
        for tag in tags:
            args.extend(["--tags", tag])

    result = run_skill("memory", args, timeout=timeout)
    if result["returncode"] == 0:
        return parse_memory_output(result["stdout"])

    log.error("OS recall failed: %s", result["stderr"][:200])
    return []


# ---------------------------------------------------------------------------
# Health Dispatch
# ---------------------------------------------------------------------------

HEALTH_DISPATCH = {
    "memory":       ("monitor-memory",       ["health", "--json"]),
    "skills":       ("monitor-skills",       ["check", "--json"]),
    "skill-health": ("monitor-skill-health", ["status", "--json"]),
    "security":     ("monitor-security",     ["status", "--json"]),
    "sparta":       ("monitor-sparta",       ["status", "--json"]),
    "personas":     ("monitor-personas",     ["status", "--json"]),
    "taxonomy":     ("monitor-taxonomy",     ["status", "--json"]),
    "workstation":  ("ops-workstation",      ["check", "--json"]),
    "arango":       ("ops-arango",           ["health", "--json"]),
    "docker":       ("ops-docker",           ["status", "--json"]),
    "llm":          ("ops-llm",              ["health", "--json"]),
    "chutes":       ("ops-chutes",           ["status", "--json"]),
}

# Keywords to match subsystems from natural language
SUBSYSTEM_KEYWORDS = {
    "memory": ["memory", "arango", "arangodb", "recall", "vector"],
    "skills": ["skill", "skills", "skill list"],
    "skill-health": ["skill health", "sanity", "skill quality"],
    "security": ["security", "hack", "vulnerability", "vulns"],
    "sparta": ["sparta", "knowledge graph", "d3fend", "att&ck", "cwe"],
    "personas": ["persona", "personas", "character", "characters"],
    "taxonomy": ["taxonomy", "bridge", "bridges", "federated"],
    "workstation": ["workstation", "disk", "nvme", "storage", "cache", "disk space"],
    "arango": ["arango", "arangodb", "database", "db"],
    "docker": ["docker", "container", "containers", "compose"],
    "llm": ["llm", "ollama", "model", "inference", "local model"],
    "chutes": ["chutes", "chutes.ai", "scillm", "deepseek", "api"],
}


def detect_subsystem(query: str) -> Optional[str]:
    """Detect which subsystem a health query targets."""
    query_lower = query.lower()
    best = None
    best_score = 0

    for subsystem, keywords in SUBSYSTEM_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > best_score:
            best_score = score
            best = subsystem

    return best


def get_health_data(subsystem: str, timeout: int = 30) -> dict:
    """Get runtime health data for a subsystem via its monitor/ops skill."""
    if subsystem == "memory":
        result = run_skill("memory", ["recall", "--q", "memory health", "--k", "1"], timeout=15)
        return {
            "subsystem": "memory",
            "skill": "memory",
            "status": "ok" if result["returncode"] == 0 else "error",
            "returncode": result["returncode"],
            "stderr": result["stderr"][:200],
        }

    if subsystem not in HEALTH_DISPATCH:
        return {"error": f"Unknown subsystem: {subsystem}", "available": list(HEALTH_DISPATCH.keys())}

    skill_name, args = HEALTH_DISPATCH[subsystem]
    log.info("Health dispatch: %s %s", skill_name, args)

    result = run_skill(skill_name, args, timeout=timeout)

    if result.get("skipped"):
        return {"error": f"Skill {skill_name} not available", "subsystem": subsystem}

    if result["returncode"] != 0:
        return {
            "error": f"{skill_name} returned code {result['returncode']}",
            "stderr": result["stderr"][:200],
            "subsystem": subsystem,
        }

    # Parse JSON output
    parsed = parse_json_output(result["stdout"])
    if parsed:
        parsed["subsystem"] = subsystem
        parsed["skill"] = skill_name
        return parsed

    # Return raw output if not JSON
    return {
        "subsystem": subsystem,
        "skill": skill_name,
        "raw_output": result["stdout"][:1000],
    }


# ---------------------------------------------------------------------------
# OS Query (Static Knowledge)
# ---------------------------------------------------------------------------

def ask_os(
    question: str,
    k: int = 5,
    auto_learn: bool = False,
    as_json: bool = False,
    tags: Optional[list[str]] = None,
) -> dict:
    """Query OS knowledge from memory (scope=os).

    Args:
        question: The question about embry-os
        k: Number of results
        auto_learn: If no results, trigger os_learn
        as_json: Return JSON format
        tags: Optional filter tags

    Returns:
        dict with items, answer, auto_learned
    """
    result = {
        "question": question,
        "scope": "os",
        "items": [],
        "answer": "",
        "auto_learned": False,
    }

    # Recall from memory
    items = recall_os(question, k=k, tags=tags)
    result["items"] = items

    # Auto-learn if no results
    if not items and auto_learn:
        log.info("No OS knowledge found — triggering os_learn (quick)")
        print("  No OS knowledge found. Running quick OS learn...")
        from .os_learn import learn_os
        learn_stats = learn_os(depth="quick")
        result["auto_learned"] = True
        result["learn_stats"] = learn_stats

        # Re-query
        if learn_stats.get("stored", 0) > 0:
            import time as t
            t.sleep(2)  # Wait for ArangoDB indexing
            items = recall_os(question, k=k, tags=tags)
            result["items"] = items

    # Synthesize answer
    if result["items"]:
        parts = []
        for item in result["items"][:k]:
            solution = (
                item.get("solution")
                or item.get("description")
                or item.get("text")
                or item.get("answer")
                or ""
            )
            if solution:
                parts.append(solution)
        result["answer"] = "\n\n".join(parts) if parts else "No answer could be synthesized."
    else:
        if auto_learn:
            result["answer"] = (
                f"No OS knowledge found for \"{question}\" even after indexing. "
                f"Try: ./run.sh os learn --depth standard"
            )
        else:
            result["answer"] = (
                f"No OS knowledge found for \"{question}\". "
                f"Try: ./run.sh os learn --depth quick"
            )

    # Output
    if as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\n── OS Query: \"{question}\" ──")
        print(f"   Results: {len(result['items'])}", end="")
        if result.get("auto_learned"):
            print(" | Auto-indexed: yes", end="")
        print("\n")

        if result["items"]:
            for i, item in enumerate(result["items"][:k], 1):
                problem = item.get("problem", "")
                solution = item.get("solution", "")
                print(f"  {i}. {problem}")
                if solution:
                    for line in solution.split("\n")[:4]:
                        print(f"     {line}")
                    sol_lines = solution.split("\n")
                    if len(sol_lines) > 4:
                        print(f"     ... ({len(sol_lines) - 4} more lines)")
                print()
        else:
            print("  No OS knowledge found.")
            if not auto_learn:
                print("  Run: ./run.sh os learn --depth quick")
        print()

    return result


# ---------------------------------------------------------------------------
# OS Health Query
# ---------------------------------------------------------------------------

def ask_os_health(
    question: str,
    subsystem: Optional[str] = None,
    as_json: bool = False,
) -> dict:
    """Query runtime health of an OS subsystem.

    Combines real-time health data with static knowledge from memory.

    Args:
        question: The health question
        subsystem: Override subsystem detection
        as_json: JSON output

    Returns:
        dict with health_data, knowledge, answer
    """
    result = {
        "question": question,
        "subsystem": subsystem,
        "health_data": {},
        "knowledge": [],
        "answer": "",
    }

    # Detect subsystem if not provided
    if not subsystem:
        subsystem = detect_subsystem(question)
        result["subsystem"] = subsystem

    if not subsystem:
        # Can't determine subsystem — provide overview
        result["answer"] = (
            "Could not determine which subsystem to check. "
            f"Available: {', '.join(sorted(HEALTH_DISPATCH.keys()))}"
        )
        if as_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"\n  {result['answer']}\n")
        return result

    print(f"\n── OS Health: {subsystem} ──")

    # Get runtime health data
    print(f"   Checking {subsystem}...")
    health_data = get_health_data(subsystem)
    result["health_data"] = health_data

    # Get static knowledge about this subsystem
    knowledge = recall_os(f"{subsystem} architecture purpose", k=3)
    result["knowledge"] = knowledge

    # Synthesize answer
    parts = []

    # Runtime status
    if "error" in health_data:
        parts.append(f"Health check error: {health_data['error']}")
    else:
        # Format health data nicely
        status = health_data.get("status", health_data.get("healthy", "unknown"))
        parts.append(f"Status: {status}")

        # Include key metrics if present
        for key in ["checks_passed", "checks_failed", "uptime", "version", "connections"]:
            if key in health_data:
                parts.append(f"  {key}: {health_data[key]}")

        # Include raw output if no structured data
        if "raw_output" in health_data:
            parts.append(health_data["raw_output"][:500])

    # Static knowledge
    if knowledge:
        parts.append("\nArchitecture:")
        for item in knowledge[:2]:
            sol = item.get("solution", "")
            if sol:
                parts.append(f"  {sol[:200]}")

    result["answer"] = "\n".join(parts)

    # Output
    if as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"   Subsystem: {subsystem}")
        print()
        for line in result["answer"].split("\n"):
            print(f"   {line}")
        print()

    return result


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

app = typer.Typer(help="/ask os — Query embry-os knowledge and health")


@app.command("ask")
def cmd_ask(
    question: str = typer.Argument(help="Question about embry-os"),
    k: int = typer.Option(5, help="Number of results"),
    auto_learn: bool = typer.Option(False, help="Auto-index if no knowledge found"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
):
    """Query OS knowledge from memory."""
    if debug:
        log.remove()
        log.add(sys.stderr, level="DEBUG")

    result = ask_os(question, k=k, auto_learn=auto_learn, as_json=as_json)
    raise SystemExit(0 if result["items"] else 1)


@app.command("health")
def cmd_health(
    question: str = typer.Argument(help="Health question"),
    subsystem: Optional[str] = typer.Option(None, help="Override subsystem detection"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
):
    """Query runtime health of an OS subsystem."""
    if debug:
        log.remove()
        log.add(sys.stderr, level="DEBUG")

    result = ask_os_health(question, subsystem=subsystem, as_json=as_json)
    raise SystemExit(0 if "error" not in result.get("health_data", {}) else 1)


if __name__ == "__main__":
    app()
