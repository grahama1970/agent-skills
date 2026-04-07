#!/usr/bin/env python3
"""
/ask ask -- Query accumulated knowledge with bridge-attribute traversal.

Composes: memory recall -> taxonomy bridge traversal -> synthesis.

When --auto-learn is enabled and no knowledge is found, automatically triggers
the learn pipeline to discover, ingest, and extract knowledge, then re-queries.
"""

import json
import os
import sys
from typing import Optional

import typer
from loguru import logger as log

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

from session_writer import SessionWriter
from skills_exec import run_skill, parse_memory_output, run_memory_recall
from persona_routing import (
    extract_bridges,
    extract_persona_from_question,
    find_relevant_personas,
    suggest_persona_consultation,
)
from hybrid import ask_hybrid, learn_back

app = typer.Typer(help="/ask ask - Query accumulated knowledge")


# ---------------------------------------------------------------------------
# Core ask() function
# ---------------------------------------------------------------------------

def ask(
    question: str,
    scope: str = "ask",
    k: int = 5,
    use_bridges: bool = False,
    raw: bool = False,
    as_json: bool = False,
    auto_learn: bool = False,
    collection: str = "behavioral",
    hybrid: bool = False,
    persona_id: Optional[str] = None,
) -> dict:
    """Query accumulated knowledge.

    Args:
        question: The question to ask.
        scope: Memory scope to query.
        k: Number of results to retrieve.
        use_bridges: Also traverse bridge attributes.
        raw: Return raw memory results without synthesis.
        as_json: Format output as JSON.
        auto_learn: If True, trigger learn pipeline when no results found.
        collection: Taxonomy collection (for auto-learn).
        hybrid: Use hybrid RAG+QRA retrieval (separate collection queries).
        persona_id: Persona identifier for session tracking (None for human).

    Returns:
        dict with answer, sources, bridges.
    """
    session = SessionWriter(scope=scope, persona_id=persona_id)
    session.add_turn("user", question)

    result: dict = {
        "question": question,
        "scope": scope,
        "items": [],
        "bridges_found": [],
        "answer": "",
        "auto_learned": False,
        "hybrid_mode": hybrid,
    }

    # Step 1: Memory recall (hybrid or standard)
    if hybrid:
        log.info("Hybrid querying memory: q=%r scope=%r k=%d", question, scope, k)
        hybrid_result = ask_hybrid(question, scope, k, use_bridges=use_bridges)
        result["items"] = hybrid_result["items"]
        result["bridges_found"] = hybrid_result.get("bridges_found", [])
        result["qra_count"] = hybrid_result.get("qra_count", 0)
        result["rag_count"] = hybrid_result.get("rag_count", 0)
        log.info(
            "Hybrid recall: %d QRA + %d RAG -> %d items",
            result.get("qra_count", 0), result.get("rag_count", 0), len(result["items"]),
        )
    else:
        log.info("Querying memory: q=%r scope=%r k=%d", question, scope, k)
        recall_result = run_memory_recall(question, scope, k)

        if recall_result["returncode"] == 0:
            items = parse_memory_output(recall_result["stdout"])
            result["items"].extend(items)
            log.info("Direct recall: %d items found", len(items))
        else:
            log.warning(
                "Memory recall failed: code=%d, stderr=%s",
                recall_result["returncode"], recall_result["stderr"][:100],
            )

        # Step 2: Bridge traversal (optional, standard mode only)
        if use_bridges:
            bridges = extract_bridges(question)
            result["bridges_found"] = bridges
            log.info("Bridge traversal: found bridges %s", bridges)

            for bridge in bridges:
                bridge_query = f"{question} {bridge.lower()}"
                log.debug("Bridge recall: bridge=%s q=%r", bridge, bridge_query)
                bridge_result = run_memory_recall(bridge_query, scope, k=3, timeout=10)

                if bridge_result["returncode"] == 0:
                    bridge_items = parse_memory_output(bridge_result["stdout"])
                    existing_problems = {i.get("problem", "") for i in result["items"]}
                    added = 0
                    for item in bridge_items:
                        if item.get("problem", "") not in existing_problems:
                            item["via_bridge"] = bridge
                            result["items"].append(item)
                            existing_problems.add(item.get("problem", ""))
                            added += 1
                    log.debug("Bridge %s: %d new items (from %d total)", bridge, added, len(bridge_items))
                else:
                    log.warning("Bridge recall for %s failed: code=%d", bridge, bridge_result["returncode"])

    # Step 2b: Evidence-case fallback for non-trivial queries.
    # Fires when: (a) no results at all, OR (b) only meta/irrelevant results.
    # When the question is analytical (not a direct control lookup like "SV-123"),
    # build a structured evidence case BEFORE answering.
    domain_items = [i for i in result["items"] if not _is_meta_item(i)]
    has_domain_answer = _has_relevant_domain_items(domain_items, question)
    # Operational questions (about the pipeline/datalake itself) always use evidence
    # cases — BM25 matches on words like "table" or "extraction" return datalake
    # content about satellites, not pipeline health data.
    is_operational = _is_operational_question(question)
    if (is_operational or not has_domain_answer) and not _is_direct_control_lookup(question):
        evidence_result = _try_evidence_case(question, scope)
        if evidence_result:
            result["evidence_case"] = evidence_result
            verdict = evidence_result.get("verdict", {})
            # Replace irrelevant items with evidence-based answer.
            # The original BM25 results were not relevant to this question —
            # the evidence case is now the primary answer source.
            evidence_items = []
            if verdict.get("score", 0) >= 0.65:
                # Build transparent solution with grounding evidence
                reasoning = verdict.get("reasoning", "")
                solution_parts = [reasoning] if reasoning else []

                # Extract grounding evidence from gate trace
                gate_trace = evidence_result.get("gate_trace", [])
                for step in gate_trace:
                    if step.get("gate") == "step_2_recall":
                        ge = step.get("data", {}).get("grounding_evidence", {})
                        if isinstance(ge, dict):
                            unresolved_id = ge.get("unresolved_id_like", 0)
                            resolved = ge.get("resolved", 0)
                            if unresolved_id > 0:
                                terms = ge.get("unresolved_terms", [])
                                term_names = [t.get("term", "?")
                                              for t in terms
                                              if isinstance(t, dict) and t.get("type") == "id_like"]
                                solution_parts.append(
                                    f"\n[Grounding: {resolved} resolved, "
                                    f"{unresolved_id} UNRESOLVED: {', '.join(term_names)}]"
                                )
                            elif resolved > 0:
                                solution_parts.append(
                                    f"\n[Grounding: {resolved} terms resolved]"
                                )
                    if "technique" in step.get("gate", ""):
                        solution_parts.append(
                            f"\n[Technique: {step.get('detail', '')[:120]}]"
                        )

                evidence_items.append({
                    "problem": question,
                    "solution": "\n".join(solution_parts),
                    "via": "evidence_case",
                    "evidence_case_id": evidence_result.get("claim", {}).get("id", ""),
                    "grade": verdict.get("grade", ""),
                    "score": verdict.get("score", 0),
                })
            # Only include raw evidence nodes when synthesis is absent
            if not evidence_items:
                for ev in evidence_result.get("evidence", []):
                    ev_result = ev.get("result", {})
                    top_item = ev_result.get("top_item", "")
                    if top_item and len(top_item) > 20:
                        evidence_items.append({
                            "problem": f"[{ev.get('layer', '?')}] {ev.get('method', 'EXAMINE')}",
                            "solution": top_item,
                            "via": "evidence_case",
                            "confidence": ev.get("confidence", 0),
                        })
            if evidence_items:
                result["items"] = evidence_items  # Replace, don't append

    # Step 2c: Auto-learn if still no domain results
    if not domain_items and auto_learn:
        result = _auto_learn(result, question, scope, collection, k, use_bridges)

    # Step 3: Synthesise answer
    _synthesise(result, k, raw, as_json, auto_learn)

    # Step 4: Learn-back for persona accumulation
    if persona_id and result["items"]:
        learn_back(result, persona_id, scope)

    # Write session transcript
    session.add_turn("assistant", result.get("answer", ""), metadata={
        "items_count": len(result["items"]),
        "bridges_found": result.get("bridges_found", []),
        "auto_learned": result.get("auto_learned", False),
        "hybrid_mode": result.get("hybrid_mode", False),
    })
    session_path = session.write()
    if session_path:
        result["session_path"] = str(session_path)

    return result


# ---------------------------------------------------------------------------
# Evidence-case fallback (Step 2b) — global default for found=false
# ---------------------------------------------------------------------------

import re as _re


def _is_direct_control_lookup(query: str) -> bool:
    """Detect if a query is a direct control/QRA ID lookup.

    Direct lookups (e.g. "SV-123", "AC-2(1)") just need a corpus search,
    not a full evidence case.
    """
    q = query.strip()
    # STIG/CCI/SRG IDs
    if _re.match(r'^(SV|V|CCI|SRG)-\d', q, _re.IGNORECASE):
        return True
    # NIST control IDs
    if _re.match(r'^[A-Z]{2}-\d', q):
        return True
    # Short lookup (< 5 words, no question mark)
    if len(q.split()) <= 4 and '?' not in q:
        return True
    return False


def _has_relevant_domain_items(domain_items: list[dict], question: str) -> bool:
    """Check if domain items are actually relevant to the question.

    BM25 matches keywords but doesn't guarantee topical relevance — "extraction"
    in a spacecraft QRA is not the same as "extraction" in a pipeline question.
    We check that at least one item contains multiple key terms from the query.
    """
    if not domain_items:
        return False

    # Extract significant terms from question (>3 chars, not stopwords)
    stopwords = {"the", "and", "for", "are", "that", "this", "with", "from", "have", "has",
                 "been", "what", "how", "does", "last", "across", "many", "much"}
    terms = [w.lower().rstrip("?.,!") for w in question.split() if len(w) > 3 and w.lower() not in stopwords]

    if not terms:
        return len(domain_items) > 0  # Can't filter, assume relevant

    # An item is relevant if it contains at least 2 key terms (or 1 if query has few terms)
    min_matches = min(2, len(terms))

    for item in domain_items[:10]:
        text = (
            item.get("solution", "") + " " +
            item.get("text", "") + " " +
            item.get("problem", "") + " " +
            item.get("reasoning", "")
        ).lower()
        matches = sum(1 for t in terms if t in text)
        if matches >= min_matches:
            return True

    return False


def _try_evidence_case(question: str, scope: str) -> dict | None:
    """Try to build a structured evidence case for a non-trivial question.

    Calls /create-evidence-case as a subprocess. Returns the evidence case
    dict on success, None on failure (skill unavailable, timeout, etc.).

    This is the global default behavior when /memory recall returns found=false
    and the question is analytical/reasoning (not a direct control lookup).
    """
    skills_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    evidence_skill = os.path.join(skills_dir, "create-evidence-case", "run.sh")

    if not os.path.exists(evidence_skill):
        log.debug("create-evidence-case skill not installed — skipping evidence fallback")
        return None

    log.info("Building evidence case for: %s", question[:80])
    print(f"\n  No direct knowledge found. Building evidence case...")
    print(f"  (query: {question[:60]})")

    import subprocess
    try:
        proc = subprocess.run(
            [evidence_skill, "create", question, "--quiet", "--json"],
            capture_output=True, text=True, timeout=60,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if proc.returncode != 0:
            log.warning("evidence case failed: rc=%d", proc.returncode)
            return None

        stdout = proc.stdout.strip()
        idx = stdout.find("{")
        if idx < 0:
            return None

        case = json.loads(stdout[idx:])
        verdict = case.get("verdict", {})
        log.info(
            "Evidence case %s: %s (grade=%s, score=%.3f)",
            case.get("claim", {}).get("id", "?"),
            verdict.get("state", "?"),
            verdict.get("grade", "?"),
            verdict.get("score", 0),
        )
        return case

    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        log.warning("evidence case subprocess failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Auto-learn sub-step (extracted from ask() to keep it under 800 lines)
# ---------------------------------------------------------------------------

def _auto_learn(
    result: dict,
    question: str,
    scope: str,
    collection: str,
    k: int,
    use_bridges: bool,
) -> dict:
    """Trigger the learn pipeline when no knowledge is found, then re-query."""
    detected_persona = extract_persona_from_question(question)
    learn_topic = detected_persona if detected_persona else question

    log.info(
        "No knowledge found -- triggering auto-learn for q=%r scope=%r (topic=%r, persona=%s)",
        question, scope, learn_topic, detected_persona is not None,
    )

    if detected_persona:
        print(f"\n  No knowledge found. Detected persona: {detected_persona}")
        print(f'  Auto-learning about "{detected_persona}" (from question)')
    else:
        print(f'\n  No knowledge found. Auto-learning about "{question}"...')
    print(f"  (scope={scope}, collection={collection})")
    print()

    from pipeline import learn as learn_func
    from monitor import AskMonitor
    from persona import detect_persona

    monitor = AskMonitor(
        topic=learn_topic,
        scope=scope,
        name="ask-auto-learn",
    )

    learn_stats = learn_func(
        topic=learn_topic,
        scope=scope,
        collection=collection,
        monitor=monitor,
    )

    result["auto_learned"] = True
    result["detected_persona"] = detected_persona
    result["learn_stats"] = {
        "topic": learn_topic,
        "is_persona": detect_persona(learn_topic),
        "books_discovered": learn_stats.get("books_discovered", 0),
        "youtube_ingested": learn_stats.get("youtube_ingested", 0),
        "qra_extracted": learn_stats.get("qra_extracted", 0),
        "stored": learn_stats.get("stored", 0),
    }

    # Re-query after learning
    if learn_stats.get("stored", 0) > 0:
        log.info("Auto-learn stored %d items -- re-querying memory", learn_stats["stored"])
        print("\n  Re-querying after learning...")

        import time
        time.sleep(2)

        requery_result = run_memory_recall(question, scope, k)
        if requery_result["returncode"] == 0:
            new_items = parse_memory_output(requery_result["stdout"])
            result["items"].extend(new_items)
            log.info("Re-query: %d items found after auto-learn", len(new_items))
        else:
            log.warning("Re-query failed after auto-learn")

        # Bridge traversal on new knowledge
        if use_bridges and result["bridges_found"]:
            for bridge in result["bridges_found"]:
                bridge_query = f"{question} {bridge.lower()}"
                bridge_result = run_memory_recall(bridge_query, scope, k=3, timeout=10)
                if bridge_result["returncode"] == 0:
                    bridge_items = parse_memory_output(bridge_result["stdout"])
                    existing_problems = {i.get("problem", "") for i in result["items"]}
                    for item in bridge_items:
                        if item.get("problem", "") not in existing_problems:
                            item["via_bridge"] = bridge
                            result["items"].append(item)
                            existing_problems.add(item.get("problem", ""))

    return result


# ---------------------------------------------------------------------------
# Output synthesis / formatting
# ---------------------------------------------------------------------------

def _is_operational_question(question: str) -> bool:
    """Detect questions about pipeline/datalake operations (not domain content).

    Nico asks about extraction quality, convergence, scoring dimensions, pipeline
    health — these should route to evidence cases, not BM25 datalake search.
    """
    q = question.lower()
    # Operational signals: pipeline/system health vocabulary
    ops_terms = {
        "extraction", "pipeline", "convergence", "scoring", "quality",
        "table_fidelity", "figure_fidelity", "section_alignment",
        "content_coverage", "equation_fidelity", "data_quality",
        "ordering_yx", "degrading", "improving", "score", "accuracy",
        "fail_pct", "pass rate", "persona", "assessment", "datalake health",
        "learn-datalake", "extracted", "ingest", "remediat",
    }
    # Must also contain a system-referencing term (not just generic words)
    system_refs = {"pipeline", "extraction", "datalake", "extractor", "scoring",
                   "learn-datalake", "convergence", "assessment", "persona",
                   "dimension", "fidelity", "coverage"}
    has_ops = any(t in q for t in ops_terms)
    has_sys = any(t in q for t in system_refs)
    return has_ops and has_sys


_META_TAGS = frozenset({
    "routing", "global_standard", "pi_harness", "found_false_default",
    "evidence_case", "skill_route",
})

_META_SOURCES = frozenset({"skill_descriptions"})


def _is_meta_item(item: dict) -> bool:
    """Detect system meta-knowledge (routing rules, skill descriptions).

    Meta items are useful for the system but should NOT be served as answers
    to domain questions. They pollute synthesis with instructions.
    """
    # Tag-based detection
    tags = item.get("tags", [])
    if isinstance(tags, list) and any(t in _META_TAGS for t in tags):
        return True
    # Source-based detection
    source = item.get("source", item.get("_source", ""))
    if source in _META_SOURCES:
        return True
    # Content heuristic: if solution talks about skill chains / RecallResult
    solution = item.get("solution", "")
    if any(kw in solution for kw in ("RecallResult", "fallback_chain", "should_build_evidence", "run.sh")):
        return True
    return False


def _rank_items(items: list[dict]) -> list[dict]:
    """Rank items by relevance: domain content first, meta filtered out."""
    domain = [i for i in items if not _is_meta_item(i)]
    if domain:
        # Sort by BM25 score descending if available
        domain.sort(key=lambda i: i.get("scores", {}).get("bm25", 0), reverse=True)
        return domain
    # Fallback: return all items if everything is meta (shouldn't happen)
    return items


def _synthesise(
    result: dict,
    k: int,
    raw: bool,
    as_json: bool,
    auto_learn: bool,
) -> None:
    """Build the answer string and print output."""
    question = result["question"]
    scope = result["scope"]

    if result["items"]:
        if raw:
            result["answer"] = "[raw mode -- see items]"
        else:
            ranked = _rank_items(result["items"])
            parts = [
                item.get("solution", item.get("text", ""))
                for item in ranked[:k]
                if item.get("solution") or item.get("text")
            ]
            result["answer"] = "\n\n".join(parts) if parts else "No answer could be synthesized."
            # Track how many meta items were filtered
            meta_count = len(result["items"]) - len(ranked)
            if meta_count > 0:
                log.debug("Filtered %d meta items from synthesis", meta_count)
        log.info("Synthesised answer from %d items", len(result["items"]))
    else:
        if auto_learn:
            result["answer"] = (
                f'No knowledge found for "{question}" even after auto-learning. '
                f'Try providing specific YouTube URLs: ./run.sh learn "{question}" '
                f"--scope {scope} --youtube <url>"
            )
        else:
            result["answer"] = (
                f'No knowledge found for "{question}" in scope \'{scope}\'. '
                f'Try: ./run.sh ask "{question}" --scope {scope} --auto-learn'
            )
        log.info("No knowledge found for question")

    # Print output
    if as_json:
        print(json.dumps(result, indent=2, default=str))
    elif raw:
        print(json.dumps({"items": result["items"]}, indent=2, default=str))
    else:
        _print_human(result, k, auto_learn)


def _print_human(result: dict, k: int, auto_learn: bool) -> None:
    """Pretty-print results for human consumption."""
    question = result["question"]
    scope = result["scope"]

    print(f'\n-- Answer: "{question}" --')
    print(f"   Scope: {scope} | Results: {len(result['items'])}", end="")
    if result.get("hybrid_mode"):
        qra = result.get("qra_count", 0)
        rag = result.get("rag_count", 0)
        print(f" | Hybrid: {qra} QRA + {rag} RAG", end="")
    if result["bridges_found"]:
        print(f" | Bridges: {', '.join(result['bridges_found'])}", end="")
    if result.get("auto_learned"):
        print(" | Auto-learned: yes", end="")
    print("\n")

    ranked_items = _rank_items(result["items"]) if result["items"] else []
    if ranked_items:
        for i, item in enumerate(ranked_items[:k], 1):
            problem = item.get("problem", item.get("text", "")[:120])
            solution = item.get("solution", item.get("text", ""))
            bridge = item.get("via_bridge", "")
            source_type = item.get("source_type", "")
            reasoning = item.get("reasoning", "")

            tags = []
            if bridge:
                tags.append(bridge)
            if source_type:
                tags.append(source_type.upper())
            tag_str = f" [{', '.join(tags)}]" if tags else ""

            print(f"  {i}. {problem}{tag_str}")
            if reasoning:
                print(f"     Reasoning: {reasoning[:200]}...")
            if solution:
                sol_lines = solution.split("\n")
                for line in sol_lines[:5]:
                    print(f"     {line}")
                if len(sol_lines) > 5:
                    print(f"     ... ({len(sol_lines) - 5} more lines)")
            print()
    else:
        if auto_learn:
            print("  No knowledge found even after auto-learning.")
            print(f'  Provide YouTube URLs: ./run.sh learn "{question}" --scope {scope} --youtube <url>')
        else:
            print(f'  No knowledge found. Try: ./run.sh ask "{question}" --scope {scope} --auto-learn')
    print()


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

@app.command()
def main(
    question: str = typer.Argument(help="Question to ask"),
    scope: str = typer.Option(
        os.environ.get("ASK_DEFAULT_SCOPE", "ask"), help="Memory scope to query (default: ask)",
    ),
    k: int = typer.Option(5, help="Number of results (default: 5)"),
    bridges: bool = typer.Option(False, help="Also traverse bridge attributes"),
    raw: bool = typer.Option(False, help="Return raw memory results"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    auto_learn: bool = typer.Option(False, help="Auto-discover and learn if no knowledge found"),
    collection: str = typer.Option("behavioral", help="Taxonomy collection for auto-learn (default: behavioral)"),
    hybrid: bool = typer.Option(False, help="Use hybrid RAG+QRA retrieval (separate collection queries)"),
    consult_personas: bool = typer.Option(False, help="Find and suggest relevant personas to consult"),
    persona_scope: str = typer.Option("personas", help="Scope to search for personas (default: personas)"),
    persona_id: Optional[str] = typer.Option(None, help="Persona identifier for session tracking (None for human)"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
):
    if debug:
        log.enable("")

    result = ask(
        question=question,
        scope=scope,
        k=k,
        use_bridges=bridges,
        raw=raw,
        as_json=as_json,
        auto_learn=auto_learn,
        collection=collection,
        hybrid=hybrid,
        persona_id=persona_id,
    )

    if consult_personas:
        suggestion = suggest_persona_consultation(question, persona_scope)
        if suggestion:
            print(suggestion)
            result["suggested_personas"] = find_relevant_personas(
                question, scope=persona_scope,
            )

    sys.exit(0 if result["items"] else 1)


if __name__ == "__main__":
    app()
