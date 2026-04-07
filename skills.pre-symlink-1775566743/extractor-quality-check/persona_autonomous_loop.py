#!/usr/bin/env python3
"""
Persona autonomous loop — enables Margaret Chen and Jennifer Cheung to
self-direct their datalake exploration and bug discovery.

The loop reads:
  1. Datalake state (via datalake_state_collector.py)
  2. Seed scenarios (210 scenarios for pattern context)
  3. F-35 project context (shared mission narrative)
  4. Previous session history (what has already been asked)
  5. Memory recall (what has already been learned)

From these inputs, the persona generates priority queries, runs them via
/ask, evaluates results, and stores learnings back to /memory.

Usage:
    # Run Margaret Chen for one cycle (default 5 queries)
    python persona_autonomous_loop.py margaret_chen

    # Run Jennifer Cheung for 10 queries
    python persona_autonomous_loop.py jennifer_cheung --queries 10

    # Dry run — show what would be asked without executing
    python persona_autonomous_loop.py margaret_chen --dry-run

    # Run with specific learning level
    python persona_autonomous_loop.py margaret_chen --level discovery

Split into modules:
  _config.py     — constants, paths, persona configs, level weights
  _context.py    — context-gathering helpers (scenarios, sessions, memory, /ask)
  _query_gen.py  — query generation (seed-adapted and organic)
  _teacher.py    — teacher evaluation pipeline (assistant, gateway, scillm)
"""
from __future__ import annotations

import json
import random
import time
from typing import Optional

import typer
from loguru import logger as log

from session_writer import SessionWriter

# ── Import from split modules ──
from _config import (
    LEVEL_WEIGHTS,
    PERSONAS,
    TASK_MAP,
)
from _context import (
    collect_datalake_state,
    count_previous_sessions,
    determine_learning_phase,
    get_previous_queries,
    learn_to_memory,
    load_project_context,
    load_scenarios,
    recall_memory,
    run_ask,
)
from _query_gen import (
    generate_organic_query,
    generate_query_from_seed,
)
from _teacher import (
    count_teacher_labels,
    evaluate_chunks_as_teacher,
    maybe_trigger_training,
    write_teacher_label,
)

# ── Backwards-compatible re-exports (underscore-prefixed names) ──
# Any external code that imported the private helpers from this file
# will continue to work.
_load_scenarios = load_scenarios
_load_project_context = load_project_context
_count_previous_sessions = count_previous_sessions
_get_previous_queries = get_previous_queries
_determine_learning_phase = determine_learning_phase
_collect_datalake_state = collect_datalake_state
_recall_memory = recall_memory
_learn_to_memory = learn_to_memory
_run_ask = run_ask
_generate_query_from_seed = generate_query_from_seed
_generate_organic_query = generate_organic_query
_evaluate_chunks_as_teacher = evaluate_chunks_as_teacher
_write_teacher_label = write_teacher_label
_count_teacher_labels = count_teacher_labels
_maybe_trigger_training = maybe_trigger_training

app = typer.Typer(help="Persona autonomous loop for datalake exploration")


# ── Result evaluation ──

def _evaluate_result(ask_result: dict, query: str, persona_config: dict) -> dict:
    """Evaluate the quality of a query result and decide what to learn."""
    items = ask_result.get("items", [])
    evaluation = {
        "query": query,
        "items_found": len(items),
        "has_answer": bool(ask_result.get("answer", "").strip()),
        "quality": "unknown",
        "learnings": [],
        "follow_ups": [],
    }

    if not items:
        evaluation["quality"] = "no_results"
        evaluation["learnings"].append({
            "problem": f"Query returned no results: {query}",
            "solution": (
                "Either the datalake lacks content matching this query, "
                "or the recall pipeline failed to find relevant chunks. "
                "Check: (1) Are relevant documents extracted? "
                "(2) Are embeddings populated? (3) Is the search view active?"
            ),
            "tags": ["datalake-gap", "recall-failure", persona_config["scope"]],
        })
        evaluation["follow_ups"].append(
            f"Investigate why no results for: {query}"
        )
    elif len(items) < 3:
        evaluation["quality"] = "sparse"
        evaluation["learnings"].append({
            "problem": f"Sparse results ({len(items)} items) for: {query}",
            "solution": (
                f"Found {len(items)} items but expected more. "
                "May indicate incomplete extraction or narrow coverage."
            ),
            "tags": ["sparse-results", persona_config["scope"]],
        })
    else:
        evaluation["quality"] = "good"
        # Check content quality of returned items
        empty_items = sum(1 for i in items if len(i.get("text", i.get("solution", "")).strip()) < 20)
        if empty_items > 0:
            evaluation["learnings"].append({
                "problem": f"{empty_items}/{len(items)} items had very short content for: {query}",
                "solution": "Some datalake chunks have insufficient content. Check extraction stage S07.",
                "tags": ["content-quality", persona_config["scope"]],
            })

    return evaluation


# ── Main cycle ──

def run_cycle(
    persona_id: str,
    num_queries: int = 5,
    level: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Run one autonomous cycle for a persona.

    Returns a summary of queries asked, results found, and learnings stored.
    """
    if persona_id not in PERSONAS:
        log.error("Unknown persona: {} (known: {})", persona_id, list(PERSONAS.keys()))
        return {"error": f"Unknown persona: {persona_id}"}

    persona_config = PERSONAS[persona_id]
    scope = persona_config["scope"]
    log.info("Starting autonomous cycle for {} ({})", persona_config["name"], scope)

    # ── Gather context ──
    session_count = count_previous_sessions(persona_id)
    phase = determine_learning_phase(session_count)
    previous_queries = get_previous_queries(persona_id)
    scenarios = load_scenarios()
    datalake_state = collect_datalake_state()
    project_context = load_project_context()

    # Recall what this persona already knows
    memory_items = recall_memory(
        f"{persona_config['name']} findings extraction quality",
        scope, k=10,
    )

    log.info(
        "Context: phase={}, sessions={}, prev_queries={}, scenarios={}, "
        "memory_items={}, datalake={}",
        phase, session_count, len(previous_queries), len(scenarios),
        len(memory_items), "available" if datalake_state else "unavailable",
    )

    # ── Select queries ──
    queries: list[str] = []
    query_sources: list[str] = []

    # Filter scenarios for this persona
    persona_name = "margaret" if "margaret" in persona_id else "jennifer"
    my_scenarios = [s for s in scenarios if s.get("persona") == persona_name]

    # Apply level filter if specified
    if level:
        my_scenarios = [s for s in my_scenarios if s.get("level") == level]

    # Weight scenarios by learning phase
    if my_scenarios and not level:
        weighted: list[tuple[dict, float]] = []
        for s in my_scenarios:
            s_level = s.get("level", "discovery")
            weight = LEVEL_WEIGHTS.get(s_level, {}).get(phase, 0.1)
            weighted.append((s, weight))

        # Normalize weights
        total_weight = sum(w for _, w in weighted)
        if total_weight > 0:
            weighted = [(s, w / total_weight) for s, w in weighted]
    elif my_scenarios:
        weighted = [(s, 1.0 / len(my_scenarios)) for s in my_scenarios]
    else:
        weighted = []

    # Build query list: mix of seed-adapted and organic
    previous_set = set(q.lower().strip() for q in previous_queries)
    attempts = 0
    max_attempts = num_queries * 5

    while len(queries) < num_queries and attempts < max_attempts:
        attempts += 1

        # 60% seed-adapted, 40% organic (shifts toward organic as sessions grow)
        organic_chance = min(0.4 + (session_count * 0.01), 0.8)

        if weighted and random.random() > organic_chance:
            # Weighted random selection from seed scenarios
            r = random.random()
            cumulative = 0.0
            selected = weighted[0][0]
            for s, w in weighted:
                cumulative += w
                if r <= cumulative:
                    selected = s
                    break

            query = generate_query_from_seed(selected, persona_config, datalake_state, phase)
            source = f"seed:{selected['id']}"
        else:
            query = generate_organic_query(
                persona_config, datalake_state, previous_queries, memory_items, phase,
            )
            source = "organic"

        # Deduplicate against previous queries
        query_key = query.lower().strip()[:100]
        if query_key not in previous_set:
            queries.append(query)
            query_sources.append(source)
            previous_set.add(query_key)

    log.info("Selected {} queries ({} seed, {} organic)",
             len(queries),
             sum(1 for s in query_sources if s.startswith("seed")),
             sum(1 for s in query_sources if s == "organic"))

    if dry_run:
        results = []
        for i, (q, src) in enumerate(zip(queries, query_sources)):
            results.append({"index": i, "query": q, "source": src, "dry_run": True})
            print(f"  [{i+1}] ({src}) {q}")
        return {
            "persona": persona_id,
            "phase": phase,
            "session_count": session_count,
            "queries": results,
            "dry_run": True,
        }

    # ── Execute queries ──
    session = SessionWriter(scope=scope, persona_id=persona_id)
    cycle_results = []
    learnings_stored = 0

    for i, (query, source) in enumerate(zip(queries, query_sources)):
        log.info("[{}/{}] {}: {}", i + 1, len(queries), source, query[:80])

        # Run /ask
        ask_result = run_ask(query, scope, persona_id)

        # Evaluate returned chunks as teacher (persona -> scillm, parallel).
        # These evaluations ARE the training data -- they accumulate as
        # teacher labels in /create-gpt/data/tasks/raw/{task}/teacher_labels.jsonl.
        # When enough labels exist, maybe_trigger_training() fires.
        items_to_evaluate = ask_result.get("items", [])[:5]
        batch_results = evaluate_chunks_as_teacher(items_to_evaluate, persona_config)
        chunk_evaluations = [r for r in batch_results if r is not None]

        # Evaluate result (heuristic: count, sparsity, content length)
        evaluation = _evaluate_result(ask_result, query, persona_config)

        # Enrich evaluation with teacher assessments
        if chunk_evaluations:
            evaluation["teacher_evaluations"] = chunk_evaluations
            fail_count = sum(1 for v in chunk_evaluations if v.get("grade") == "FAIL")
            warn_count = sum(1 for v in chunk_evaluations if v.get("grade") == "WARN")
            all_errors: list[str] = []
            for v in chunk_evaluations:
                all_errors.extend(v.get("error_types", []))

            if fail_count > 0:
                evaluation["learnings"].append({
                    "problem": (
                        f"Teacher flagged {fail_count} FAIL chunks for: {query}"
                    ),
                    "solution": (
                        f"Error types detected: {', '.join(set(all_errors)) or 'unspecified'}. "
                        f"Remediation: {chunk_evaluations[0].get('remediation', 'investigate')}"
                    ),
                    "tags": [
                        "teacher-fail", persona_config["scope"],
                        *[f"error:{e}" for e in list(set(all_errors))[:5]],
                    ],
                })
            if warn_count > 0 and fail_count == 0:
                evaluation["learnings"].append({
                    "problem": f"Teacher flagged {warn_count} WARN chunks for: {query}",
                    "solution": f"Warning error types: {', '.join(set(all_errors))}",
                    "tags": ["teacher-warn", persona_config["scope"]],
                })

        # Store learnings back to /memory
        for learning in evaluation.get("learnings", []):
            stored = learn_to_memory(
                problem=learning["problem"],
                solution=learning["solution"],
                scope=scope,
                tags=learning.get("tags", []),
            )
            if stored:
                learnings_stored += 1
                log.info("Stored learning: {}", learning["problem"][:60])

        # Track in session
        session.add_turn("user", query, metadata={
            "source": source,
            "cycle_index": i,
        })
        # Summarize teacher grades for session metadata
        teacher_summary = {}
        if chunk_evaluations:
            grades = [v.get("grade", "?") for v in chunk_evaluations]
            teacher_summary = {
                "grades": grades,
                "fail_count": grades.count("FAIL"),
                "warn_count": grades.count("WARN"),
                "pass_count": grades.count("PASS"),
                "avg_fidelity": round(
                    sum(v.get("fidelity_score", 0) for v in chunk_evaluations) / len(chunk_evaluations), 3
                ),
                "error_types": list(set(
                    e for v in chunk_evaluations for e in v.get("error_types", [])
                )),
            }

        session.add_turn("assistant", evaluation.get("quality", "unknown"), metadata={
            "items_found": evaluation["items_found"],
            "quality": evaluation["quality"],
            "learnings_count": len(evaluation.get("learnings", [])),
            "follow_ups": evaluation.get("follow_ups", []),
            "teacher_evaluation": teacher_summary,
        })

        cycle_results.append({
            "query": query,
            "source": source,
            "items_found": evaluation["items_found"],
            "quality": evaluation["quality"],
            "learnings": len(evaluation.get("learnings", [])),
            "teacher_evaluation": teacher_summary,
        })

        # Brief pause between queries to avoid overwhelming the system
        time.sleep(1)

    # Write session transcript
    session_path = session.write()

    # Check if this persona has accumulated enough teacher labels to
    # trigger student model training. Probabilistic -- 10% chance per
    # cycle once threshold is met, to avoid concurrent training runs.
    training_triggered = maybe_trigger_training(persona_config)

    summary = {
        "persona": persona_id,
        "persona_name": persona_config["name"],
        "phase": phase,
        "session_count": session_count + 1,
        "queries_asked": len(queries),
        "total_items_found": sum(r["items_found"] for r in cycle_results),
        "learnings_stored": learnings_stored,
        "training_triggered": training_triggered,
        "teacher_labels_count": count_teacher_labels(
            TASK_MAP.get(persona_config["scope"], "unknown")
        ),
        "quality_breakdown": {
            "good": sum(1 for r in cycle_results if r["quality"] == "good"),
            "sparse": sum(1 for r in cycle_results if r["quality"] == "sparse"),
            "no_results": sum(1 for r in cycle_results if r["quality"] == "no_results"),
        },
        "session_path": str(session_path) if session_path else None,
        "results": cycle_results,
    }

    log.info(
        "Cycle complete: {} queries, {} items found, {} learnings stored, "
        "quality: {} good / {} sparse / {} no_results",
        summary["queries_asked"],
        summary["total_items_found"],
        summary["learnings_stored"],
        summary["quality_breakdown"]["good"],
        summary["quality_breakdown"]["sparse"],
        summary["quality_breakdown"]["no_results"],
    )

    return summary


@app.command()
def main(
    persona: str = typer.Argument(help="Persona ID (margaret_chen or jennifer_cheung)"),
    queries: int = typer.Option(5, "--queries", "-n", help="Number of queries per cycle"),
    level: Optional[str] = typer.Option(None, help="Force a specific scenario level"),
    dry_run: bool = typer.Option(False, help="Show queries without executing"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Run one autonomous cycle for a persona."""
    if debug:
        log.enable("")

    result = run_cycle(persona, num_queries=queries, level=level, dry_run=dry_run)

    if output_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if dry_run:
            print(f"\n  Dry run for {result.get('persona', persona)}")
            print(f"  Phase: {result.get('phase', '?')}, Sessions: {result.get('session_count', 0)}")
            print(f"  Queries: {len(result.get('queries', []))}")
        else:
            name = result.get("persona_name", persona)
            print(f"\n  {name} — Autonomous Cycle Complete")
            print(f"  Phase: {result.get('phase', '?')}")
            print(f"  Queries: {result.get('queries_asked', 0)}")
            print(f"  Items found: {result.get('total_items_found', 0)}")
            print(f"  Learnings stored: {result.get('learnings_stored', 0)}")
            qb = result.get("quality_breakdown", {})
            print(f"  Quality: {qb.get('good', 0)} good, {qb.get('sparse', 0)} sparse, {qb.get('no_results', 0)} empty")
            if result.get("session_path"):
                print(f"  Session: {result['session_path']}")
        print()


if __name__ == "__main__":
    app()
