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
from .run_state import AskRunState, make_run_id
from .scillm_runtime import CITATION_SCHEMA_VERSION, build_source_bundle, memory_citations_from_items, render_citations_markdown

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
    run_state: Optional[AskRunState] = None,
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
    if run_state:
        run_state.step_started("os_memory_recall", k=k, tags=tags or [])
    items = recall_os(question, k=k, tags=tags)
    result["items"] = items
    if run_state:
        run_state.step_finished("os_memory_recall", items_count=len(items))

    # Auto-learn if no results
    if not items and auto_learn:
        if run_state:
            run_state.step_started("os_auto_learn")
        log.info("No OS knowledge found — triggering os_learn (quick)")
        print("  No OS knowledge found. Running quick OS learn...")
        from .os_learn import learn_os
        learn_stats = learn_os(depth="quick", run_state=run_state)
        result["auto_learned"] = True
        result["learn_stats"] = learn_stats

        # Re-query
        if learn_stats.get("stored", 0) > 0:
            import time as t
            t.sleep(2)  # Wait for ArangoDB indexing
            items = recall_os(question, k=k, tags=tags)
            result["items"] = items
        if run_state:
            run_state.step_finished("os_auto_learn", items_count=len(result["items"]), stored=learn_stats.get("stored", 0))

    # Synthesize answer
    if run_state:
        run_state.step_started("os_synthesis")
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
        source_bundle = build_source_bundle(question=question, context_items=result["items"][:k])
        result["citation_schema_version"] = CITATION_SCHEMA_VERSION
        result["source_bundle"] = {
            "source_bundle_id": source_bundle["source_bundle_id"],
            "citation_schema_version": source_bundle.get("citation_schema_version", CITATION_SCHEMA_VERSION),
            "source_ids": [source["source_id"] for source in source_bundle["sources"]],
            "sources": source_bundle["sources"],
        }
        result["citations"] = memory_citations_from_items(result["items"], limit=k, supports="os_answer")
        result["citation_status"] = {
            "status": "PASS" if result["citations"] else "DEGRADED",
            "basis": "memory",
            "rule": "memory citations support OS knowledge answers but not code/review safety claims",
        }
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
    if run_state:
        run_state.step_finished("os_synthesis", answer_chars=len(result["answer"]), items_count=len(result["items"]))

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
            if result.get("citations"):
                print("  Citations:")
                for line in render_citations_markdown(result.get("citations", [])).splitlines():
                    print(f"   {line}")
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
    run_state: Optional[AskRunState] = None,
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
        if run_state:
            run_state.step_started("os_health_detect_subsystem")
        subsystem = detect_subsystem(question)
        result["subsystem"] = subsystem
        if run_state:
            run_state.step_finished("os_health_detect_subsystem", subsystem=subsystem or "")

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
    if run_state:
        run_state.step_started("os_health_dispatch", subsystem=subsystem)
    health_data = get_health_data(subsystem)
    result["health_data"] = health_data
    if run_state:
        run_state.step_finished("os_health_dispatch", subsystem=subsystem, status=health_data.get("status", ""), error=health_data.get("error", ""))

    # Get static knowledge about this subsystem
    if run_state:
        run_state.step_started("os_health_knowledge_recall", subsystem=subsystem)
    knowledge = recall_os(f"{subsystem} architecture purpose", k=3)
    result["knowledge"] = knowledge
    if run_state:
        run_state.step_finished("os_health_knowledge_recall", items_count=len(knowledge))

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
    source_bundle = build_source_bundle(question=question, context_items=knowledge[:3])
    result["citation_schema_version"] = CITATION_SCHEMA_VERSION
    result["source_bundle"] = {
        "source_bundle_id": source_bundle["source_bundle_id"],
        "citation_schema_version": source_bundle.get("citation_schema_version", CITATION_SCHEMA_VERSION),
        "source_ids": [source["source_id"] for source in source_bundle["sources"]],
        "sources": source_bundle["sources"],
    }
    result["citations"] = [
        {
            "source_id": "RUNTIME.HEALTH",
            "source_kind": "runtime_health",
            "quote_or_summary": json.dumps(health_data, sort_keys=True, default=str)[:280],
            "supports": "runtime_status",
        },
        *memory_citations_from_items(knowledge, limit=3, supports="os_health_architecture"),
    ]
    result["citation_status"] = {
        "status": "PASS",
        "basis": "runtime_health+memory",
        "rule": "runtime health cites live dispatch output; memory supports architecture context only",
    }

    # Output
    if as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"   Subsystem: {subsystem}")
        print()
        for line in result["answer"].split("\n"):
            print(f"   {line}")
        if result.get("citations"):
            print("   Citations:")
            for line in render_citations_markdown(result.get("citations", [])).splitlines():
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
    ask_id: Optional[str] = typer.Option(None, "--ask-id", help="Stable runtime artifact id for this OS ask call"),
    run_output_root: Optional[str] = typer.Option(None, "--run-output-root", help="Directory for runtime artifacts"),
    overwrite_run: bool = typer.Option(False, "--overwrite", help="Replace an existing run directory for --ask-id"),
    resume_run: bool = typer.Option(False, "--resume", help="Resume a non-terminal existing run directory for --ask-id"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
):
    """Query OS knowledge from memory."""
    if debug:
        log.remove()
        log.add(sys.stderr, level="DEBUG")

    run_state = AskRunState(
        ask_id or make_run_id(f"os ask {question}"),
        output_root=run_output_root,
        overwrite=overwrite_run,
        resume=resume_run,
    )
    run_state.write_request({"command": "os ask", "question": question, "k": k, "auto_learn": auto_learn})
    try:
        result = ask_os(question, k=k, auto_learn=auto_learn, as_json=as_json, run_state=run_state)
    except Exception as exc:
        run_state.fail(exc)
        raise
    run_state.finish(result)
    raise SystemExit(0 if result["items"] else 1)


@app.command("health")
def cmd_health(
    question: str = typer.Argument(help="Health question"),
    subsystem: Optional[str] = typer.Option(None, help="Override subsystem detection"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    ask_id: Optional[str] = typer.Option(None, "--ask-id", help="Stable runtime artifact id for this OS health call"),
    run_output_root: Optional[str] = typer.Option(None, "--run-output-root", help="Directory for runtime artifacts"),
    overwrite_run: bool = typer.Option(False, "--overwrite", help="Replace an existing run directory for --ask-id"),
    resume_run: bool = typer.Option(False, "--resume", help="Resume a non-terminal existing run directory for --ask-id"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
):
    """Query runtime health of an OS subsystem."""
    if debug:
        log.remove()
        log.add(sys.stderr, level="DEBUG")

    run_state = AskRunState(
        ask_id or make_run_id(f"os health {question}"),
        output_root=run_output_root,
        overwrite=overwrite_run,
        resume=resume_run,
    )
    run_state.write_request({"command": "os health", "question": question, "subsystem": subsystem})
    try:
        result = ask_os_health(question, subsystem=subsystem, as_json=as_json, run_state=run_state)
    except Exception as exc:
        run_state.fail(exc)
        raise
    run_state.finish(result, state="completed" if "error" not in result.get("health_data", {}) else "failed")
    raise SystemExit(0 if "error" not in result.get("health_data", {}) else 1)


if __name__ == "__main__":
    app()
