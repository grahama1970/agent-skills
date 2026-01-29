#!/usr/bin/env python3
"""
Memory storage and edge verification for arxiv-learn skill.

Handles storing Q&A pairs to graph memory and scheduling edge verification.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from config import (
    SKILLS_DIR,
    MEMORY_LEARN_TIMEOUT,
    DEFAULT_MAX_EDGES,
    EDGE_VERIFIER_K,
    EDGE_VERIFIER_TOP,
    EDGE_VERIFIER_MAX_LLM,
    EDGE_VERIFIER_TIMEOUT,
    get_memory_root,
)
from utils import (
    log,
    run_skill,
    QAPair,
    LearnSession,
    HAS_MEMORY_CLIENT,
    MemoryClient,
    with_retries,
    get_memory_limiter,
)

# =============================================================================
# Interview Stage
# =============================================================================

def run_interview(session: LearnSession) -> tuple[list[QAPair], list[QAPair]]:
    """Run human review via interview skill.

    Args:
        session: Learn session with qa_pairs

    Returns:
        Tuple of (approved_pairs, dropped_pairs)
    """
    log("Opening interview form...", style="bold", stage=3)

    if session.skip_interview:
        log("Skipping interview (--skip-interview)", style="yellow")
        approved = [q for q in session.qa_pairs if q.recommendation == "keep"]
        dropped = [q for q in session.qa_pairs if q.recommendation == "drop"]
        return approved, dropped

    # Prepare interview questions
    interview_data = {
        "title": f"Review Q&As from {session.paper.title[:50]}",
        "context": f"Reviewing extracted knowledge for {session.scope} scope",
        "questions": [q.to_interview_question() for q in session.qa_pairs],
    }

    # Write to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(interview_data, f, indent=2)
        questions_file = f.name

    try:
        log(f"Mode: {session.mode}")

        result = run_skill("interview", [
            "--file", questions_file,
            "--mode", session.mode,
            "--json",
        ])

        if not isinstance(result, dict):
            log("Interview returned non-JSON; auto-accepting recommendations", style="yellow")
            approved = [q for q in session.qa_pairs if q.recommendation == "keep"]
            dropped = [q for q in session.qa_pairs if q.recommendation == "drop"]
            return approved, dropped

        responses = result.get("responses", {})

        # Process responses
        approved = []
        dropped = []

        for pair in session.qa_pairs:
            resp = responses.get(pair.id, {})
            decision = resp.get("decision", "skip")

            if decision == "accept":
                # User accepted agent recommendation
                if pair.recommendation == "keep":
                    approved.append(pair)
                else:
                    dropped.append(pair)
            elif decision == "override":
                # User overrode agent recommendation
                if pair.recommendation == "keep":
                    dropped.append(pair)
                else:
                    approved.append(pair)
            else:  # skip
                dropped.append(pair)

            # Check for refinements
            note = resp.get("note")
            if note:
                pair.answer = note

        log(f"Accepted: {len(approved)} pairs", style="green")
        log(f"Dropped: {len(dropped)} pairs", style="dim")

        return approved, dropped

    finally:
        Path(questions_file).unlink(missing_ok=True)

# =============================================================================
# Memory Storage
# =============================================================================

def store_to_memory(session: LearnSession) -> int:
    """Store approved Q&As to memory.

    Args:
        session: Learn session with approved_pairs

    Returns:
        Number of successfully stored pairs
    """
    log("Storing to memory...", style="bold", stage=4)

    if session.dry_run:
        log(f"DRY RUN - would store {len(session.approved_pairs)} pairs", style="yellow")
        return 0

    if not session.approved_pairs:
        log("No pairs to store", style="yellow")
        return 0

    # Build tags
    tags = ["distilled"]
    if session.arxiv_id and session.arxiv_id != "local":
        tags.append(f"arxiv:{session.arxiv_id}")
    if session.paper:
        # Add author tag (first author surname)
        if session.paper.authors:
            first_author = session.paper.authors[0].split()[-1].lower()
            tags.append(f"author:{first_author}")

    stored = 0
    memory_root = get_memory_root()

    # Use common MemoryClient if available
    if HAS_MEMORY_CLIENT:
        stored = _store_with_client(session, tags, memory_root)
    else:
        stored = _store_with_subprocess(session, tags, memory_root)

    log(f"Stored: {stored} lessons", style="green")
    log(f"Scope: {session.scope}", style="dim")
    log(f"Tags: {', '.join(tags)}", style="dim")

    return stored


def _store_with_client(session: LearnSession, tags: list[str], memory_root: str) -> int:
    """Store pairs using MemoryClient.

    Args:
        session: Learn session
        tags: Tags to apply
        memory_root: Memory root path

    Returns:
        Number stored
    """
    stored = 0
    client = MemoryClient(scope=session.scope, memory_root=memory_root)

    for pair in session.approved_pairs:
        try:
            result = client.learn(
                problem=pair.question,
                solution=pair.answer,
                tags=tags
            )
            if result.success:
                pair.lesson_id = result.lesson_id
                pair.stored = True
                stored += 1
            else:
                log(f"Failed to store: {result.error}", style="red")
        except Exception as e:
            log(f"Failed to store: {e}", style="red")

    return stored


def _store_with_subprocess(session: LearnSession, tags: list[str], memory_root: str) -> int:
    """Store pairs using subprocess with retry logic.

    Args:
        session: Learn session
        tags: Tags to apply
        memory_root: Memory root path

    Returns:
        Number stored
    """
    limiter = get_memory_limiter()

    @with_retries(max_attempts=3, base_delay=0.5)
    def _store_lesson(question: str, answer: str, scope: str, lesson_tags: list) -> dict:
        limiter.acquire()
        cmd = [
            "python3", "-m", "graph_memory.agent_cli", "learn",
            "--problem", question,
            "--solution", answer,
            "--scope", scope,
        ]
        for tag in lesson_tags:
            cmd.extend(["--tag", tag])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=MEMORY_LEARN_TIMEOUT,
            env={**os.environ, "PYTHONPATH": f"{memory_root}/src:{os.environ.get('PYTHONPATH', '')}"},
        )

        if result.returncode != 0:
            raise RuntimeError(f"Memory learn failed: {result.stderr}")

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"success": True}

    stored = 0
    for pair in session.approved_pairs:
        try:
            output = _store_lesson(pair.question, pair.answer, session.scope, tags)
            pair.lesson_id = output.get("_key", "")
            pair.stored = True
            stored += 1
        except Exception as e:
            log(f"Failed to store after retries: {e}", style="red")

    return stored

# =============================================================================
# Edge Verification
# =============================================================================

def schedule_edge_verification(session: LearnSession) -> int:
    """Schedule edge verification for new lessons.

    Args:
        session: Learn session with stored pairs

    Returns:
        Number of verified edges
    """
    log("Scheduling edge verification...", style="bold", stage=5)

    if session.dry_run:
        log(f"DRY RUN - would queue {len(session.approved_pairs)} lessons", style="yellow")
        return 0

    # Only process pairs that were stored
    to_verify = [p for p in session.approved_pairs if p.stored and p.lesson_id]

    if not to_verify:
        log("No lessons to verify", style="yellow")
        return 0

    log(f"Queued: {len(to_verify)} lessons for verification")

    verified = 0
    inline_limit = min(session.max_edges, len(to_verify))

    for idx, pair in enumerate(to_verify[:inline_limit]):
        try:
            result = subprocess.run([
                "bash", str(SKILLS_DIR / "edge-verifier" / "run.sh"),
                "--source_id", f"lessons/{pair.lesson_id}",
                "--text", f"{pair.question} {pair.answer}",
                "--scope", session.scope,
                "--k", str(EDGE_VERIFIER_K),
                "--verify-top", str(EDGE_VERIFIER_TOP),
                "--max-llm", str(EDGE_VERIFIER_MAX_LLM),
            ], capture_output=True, text=True, timeout=EDGE_VERIFIER_TIMEOUT)

            if result.returncode == 0:
                verified += 1
                log(f"Verified {idx+1}/{inline_limit}: {pair.question[:40]}...", style="dim")
        except Exception as e:
            log(f"Verification failed: {e}", style="red")

    remaining = len(to_verify) - verified

    log(f"Inline verified: {verified} (--max-edges limit)", style="green")
    if remaining > 0:
        log(f"Remaining: {remaining} (scheduled for batch)", style="yellow")

    return verified

# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "run_interview",
    "store_to_memory",
    "schedule_edge_verification",
]
