#!/usr/bin/env python3
"""
Session Analysis Pipeline for Episodic Archiver.

Performs deep LLM-powered analysis of archived agent sessions:
- Assessment: What was solved, what failed, what was incompetent
- Cross-session edges: contradicts/bolsters/resolves prior sessions
- Memory-first check: Was this problem already solved?
- Federated Taxonomy: Bridge attributes for Horus cross-collection traversal
- Dogpile: Research unresolved gaps (budget-limited)

All LLM calls go through scillm (contract-compliant, no raw HTTP).
"""

import asyncio
import hashlib
import json
import os
import subprocess
import sys

import httpx
import time
from pathlib import Path
from typing import Any, Dict, List

import typer
from dotenv import load_dotenv, find_dotenv
from loguru import logger

load_dotenv(find_dotenv(usecwd=True))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

# Ensure skills common is on path for taxonomy imports
_SKILLS_DIR = SCRIPT_DIR.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

# Use centralized _memory_cmd from memory_helpers (no duplicate)
from memory_helpers import _memory_cmd

from analysis_llm import (
    get_embedding,
    _get_llm_config,
    _llm_completion,
    _llm_batch,
    _format_turns_for_llm,
    assess_session,
    profile_user_from_session,
)
from analysis_edges import (
    OPTIMAL_FAILURE_K,
    verify_cross_session_edges,
    check_already_solved,
    search_similar_failures,
    get_failure_context,
)
from analysis_integrations import (
    apply_session_taxonomy,
    dogpile_gaps,
    _detect_scope_from_session,
    store_lessons_to_memory,
    update_user_priors,
)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def analyze_archived_session(
    session_id: str,
    enable_dogpile: bool = True,
    max_dogpile: int = 3,
    dry_run: bool = False,
    json_stream: bool = False,
    user_id: str = None,
    persona_id: str = None,
    high_fidelity: bool = False,
) -> dict:
    """Full analysis pipeline for one archived session."""

    def emit(msg: str):
        if json_stream:
            print(json.dumps({"event": "log", "msg": msg}), flush=True)
        else:
            print(f"[session-analysis] {msg}", flush=True)

    # 1. Load turns from archived agent_conversations
    emit(f"Loading turns for {session_id}...")
    try:
        raw = _memory_cmd([
            "sample", "--collection", "agent_conversations",
            "--filter", f'doc.session_id=="{session_id}"',
        ])
        # _memory_cmd returns a dict with "items" key, not a bare list
        turns = raw.get("items", raw) if isinstance(raw, dict) else raw
    except Exception as e:
        emit(f"ERROR: Failed to load turns: {e}")
        return {"error": str(e)}

    if not turns:
        emit(f"No turns found for session {session_id}")
        return {"error": "no turns found"}

    emit(f"Found {len(turns)} turns")

    # Extract user_id from turns if not provided
    if not user_id:
        for t in turns[:5]:
            if t.get("user_id"):
                user_id = t["user_id"]
                break
        if not user_id:
            user_id = os.getenv("PI_USER_ID", "graham")
    if not persona_id:
        for t in turns[:5]:
            if t.get("persona_id"):
                persona_id = t["persona_id"]
                break

    if dry_run:
        emit("DRY RUN - skipping LLM analysis")
        return {
            "session_id": session_id,
            "turn_count": len(turns),
            "dry_run": True,
            "sample_turn": turns[0] if turns else {},
        }

    # 2. Assess via LLM
    emit("Running LLM assessment...")
    assessment = await assess_session(turns, session_id)
    emit(f"Assessment: resolution={assessment.get('resolution_status')}, quality={assessment.get('quality_score')}")

    # 3. Check memory-first
    emit("Checking memory for prior solutions...")
    prior_solutions = await check_already_solved(
        assessment.get("problems_addressed", [])
    )
    if prior_solutions:
        emit(f"Found {len(prior_solutions)} prior solutions in memory")

    # 4. Apply taxonomy (with participants for persona-scoped recall)
    emit("Applying federated taxonomy...")
    taxonomy_result = apply_session_taxonomy(
        assessment,
        high_fidelity=high_fidelity,
        user_id=user_id or "",
        persona_id=persona_id or "",
        participants=[p for p in [user_id, persona_id] if p],
    )
    emit(f"Bridge attributes: {taxonomy_result.get('bridge_attributes', [])}")

    # 5. Embed the summary
    summary_text = " ".join(
        assessment.get("problems_addressed", [])
        + assessment.get("solutions_found", [])
        + assessment.get("key_learnings", [])
    )
    embedding = get_embedding(summary_text[:1000]) if summary_text.strip() else []

    # 6. Store session_summary document
    source_name = session_id.split(":")[0] if ":" in session_id else "unknown"
    now = int(time.time())
    doc = {
        "session_id": session_id,
        "source_name": source_name,
        "user_id": user_id,
        "persona_id": persona_id,
        "participants": taxonomy_result.get("participants", {}),
        "turn_count": len(turns),
        "created_at": now,
        "analyzed_at": now,
        "assessment": assessment,
        "prior_solutions": prior_solutions,
        "bridge_attributes": taxonomy_result.get("bridge_attributes", []),
        "taxonomy": taxonomy_result.get("taxonomy", {}),
        "embedding": embedding,
        "dogpile_results": [],
    }

    # Use session_id hash as _key for dedup
    doc_key = hashlib.sha1(session_id.encode()).hexdigest()[:16]
    doc["_key"] = doc_key

    try:
        _memory_cmd(["tag", "--collection", "session_summaries", "--doc", json.dumps(doc)])
        emit(f"Stored session summary: {doc_key}")
    except Exception as e:
        emit(f"ERROR storing summary: {e}")

    # 7. Verify cross-session edges
    emit("Verifying cross-session edges...")
    doc["_key"] = doc_key
    edges = await verify_cross_session_edges(doc)
    emit(f"Created {len(edges)} cross-session edges")

    # 8. Store lessons to memory (resolved sessions with problem/solution pairs)
    #    Multi-POV: detect relevant personas and store lessons to each scope
    emit("Checking for lessons to store in memory...")
    relevant_personas = None
    try:
        from archive_episode import _detect_relevant_personas
        # Build message-like dicts from turns for persona detection
        turn_msgs = [{"content": t.get("body", "")} for t in turns]
        relevant_personas = _detect_relevant_personas(turn_msgs)
        if relevant_personas:
            emit(f"Multi-POV lesson storage for: {', '.join(relevant_personas[:5])}")
    except Exception as e:
        logger.debug(f"Multi-POV persona detection skipped: {e}")

    lessons_stored = store_lessons_to_memory(
        assessment=assessment,
        session_id=session_id,
        bridge_attributes=taxonomy_result.get("bridge_attributes", []),
        emit=emit,
        user_id=user_id or "",
        persona_id=persona_id or "",
        personas=relevant_personas,
    )

    # 9. User behavioral profiling (extract priors and merge)
    user_profile = {}
    if user_id:
        emit(f"Profiling user behavior for {user_id}...")
        user_profile = await profile_user_from_session(turns, session_id, user_id)
        if not user_profile.get("_error"):
            update_user_priors(user_id, user_profile, session_id)
            emit(f"Updated user priors for {user_id}")
        else:
            emit(f"User profiling failed: {user_profile.get('_error')}")

    # 10. Optionally dogpile unresolved gaps
    dogpile_results = []
    if enable_dogpile and assessment.get("dogpile_candidates"):
        emit(f"Running dogpile on {len(assessment['dogpile_candidates'])} gaps (max {max_dogpile})...")
        dogpile_results = await dogpile_gaps(
            assessment["dogpile_candidates"], session_id, max_dogpile
        )
        if dogpile_results:
            emit(f"Dogpile returned {len(dogpile_results)} results")
            # Update doc with dogpile results
            try:
                _memory_cmd(["tag", "--collection", "session_summaries", "--doc",
                             json.dumps({"_key": doc_key, "dogpile_results": dogpile_results})])
            except Exception as e:
                logger.debug("update failed: {}", e)

    result = {
        "session_id": session_id,
        "user_id": user_id,
        "persona_id": persona_id,
        "turn_count": len(turns),
        "assessment": assessment,
        "prior_solutions_count": len(prior_solutions),
        "bridge_attributes": taxonomy_result.get("bridge_attributes", []),
        "edges_created": len(edges),
        "lessons_stored": lessons_stored,
        "user_profile": user_profile if not user_profile.get("_error") else None,
        "dogpile_results_count": len(dogpile_results),
    }

    if json_stream:
        print(json.dumps({"event": "complete", "result": result}), flush=True)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

cli = typer.Typer(help="Session analysis for episodic archiver.")


@cli.command()
def analyze(
    session_id: str = typer.Argument(help="Session ID to analyze"),
    enable_dogpile: bool = typer.Option(True, "--enable-dogpile/--no-dogpile", help="Enable dogpile research on gaps"),
    max_dogpile: int = typer.Option(3, help="Max dogpile calls per session"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Extract turns only, no LLM"),
    json_stream: bool = typer.Option(False, "--json-stream", help="Output NDJSON events"),
):
    """Analyze an archived session."""
    result = asyncio.run(analyze_archived_session(
        session_id=session_id,
        enable_dogpile=enable_dogpile,
        max_dogpile=max_dogpile,
        dry_run=dry_run,
        json_stream=json_stream,
    ))
    if not json_stream:
        print(json.dumps(result, indent=2, default=str))


@cli.command("list-gaps")
def list_gaps(
    status: str = typer.Option("partial,unresolved", help="Filter by resolution status"),
    limit: int = typer.Option(20, help="Max results"),
):
    """List sessions with unresolved gaps suitable for dogpile."""
    statuses = [s.strip() for s in status.split(",")]
    try:
        all_docs = _memory_cmd([
            "sample", "--collection", "session_summaries",
            "--limit", str(limit),
        ])
        results = [
            {
                "session_id": d.get("session_id"),
                "resolution": d.get("assessment", {}).get("resolution_status"),
                "quality": d.get("assessment", {}).get("quality_score"),
                "gaps": d.get("assessment", {}).get("dogpile_candidates", []),
                "created_at": d.get("created_at"),
            }
            for d in all_docs
            if d.get("assessment", {}).get("resolution_status") in statuses
            and d.get("assessment", {}).get("dogpile_candidates")
        ]
        print(json.dumps(results, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    cli()
