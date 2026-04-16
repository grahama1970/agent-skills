"""Remediation logic for the inline review loop.

Persona-driven remediation: RECALL known fixes from /memory, RUN skill
commands, LEARN results back into /memory. Also handles interview dispatch,
supersedes-edge linking, hard-tail classification, and question book deferral.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from memory_bridge import (
    HAS_MEMORY,
    HAS_TAXONOMY,
    ContentType,
    MemoryClient,
    add_edge,
    extract_taxonomy_features,
)
from review_memory import problem_to_title as _problem_to_title

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_REMEDIATION_TIMEOUT = 1800  # 30 min fallback if timeout classifier unavailable
MAX_REMEDIATION_JOBS_PER_ITERATION = 3


def dispatch_to_interview(
    job: Dict[str, Any],
    pdf_path: str,
    verdict: str,
    issue_context: str,
) -> bool:
    """Dispatch a non-auto-executable remediation job to /interview.

    Writes a structured question to the question book so the human can
    decide how to handle it during the next /interview session.
    Returns True if dispatched, False if no question book configured.
    """
    qbook_path = os.environ.get("PDF_LAB_QUESTION_BOOK", "")
    if not qbook_path:
        return False

    skill = job.get("skill", "unknown")
    reason = job.get("reason", "")
    command = job.get("command", "")
    pdf_name = Path(pdf_path).name if pdf_path else "unknown"

    entry = {
        "pdf_path": pdf_path,
        "pdf_name": pdf_name,
        "reason": "non_auto_remediation",
        "skill": skill,
        "command": command,
        "detail": reason,
        "verdict": verdict,
        "issue_context": issue_context,
        "questions": [
            {
                "id": "remediation_decision",
                "text": (
                    f"PDF '{pdf_name}' scored {verdict}.\n"
                    f"The pipeline wants to run /{skill} but it's not auto-executable.\n"
                    f"Reason: {reason}\n"
                    f"Command: {command}\n\n"
                    "How should we proceed?"
                ),
                "type": "choice",
                "options": [
                    f"Run /{skill} now (approve auto-execution)",
                    "Skip -- not worth fixing",
                    "Retry with different strategy",
                    "Needs manual correction",
                ],
            },
            {
                "id": "strategy_hint",
                "text": "Any additional guidance for the remediation?",
                "type": "text",
            },
        ],
        "timestamp": time.time(),
    }

    try:
        qbook = Path(qbook_path)
        qbook.parent.mkdir(parents=True, exist_ok=True)
        with open(qbook, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        logger.info(
            f"Dispatched to /interview: /{skill} for {pdf_name} ({reason})"
        )
        return True
    except OSError as exc:
        logger.warning(f"Failed to dispatch to /interview: {exc}")
        return False


def remediate_with_memory(
    review_result: Dict[str, Any],
    timeout: int = DEFAULT_REMEDIATION_TIMEOUT,
) -> List[Dict[str, Any]]:
    """Persona-driven remediation: RECALL -> FIX -> LEARN.

    For each escalation job the persona identified:
      1. RECALL /memory for known fixes (BM25 + semantic + multi-hop)
      2. RUN the skill (/table-lab, /debug-pdf, /fixture-tricky, etc.)
      3. LEARN the result in /memory with taxonomy tags for graph traversal

    This is the core self-healing loop -- personas identify problems AND fix them.
    Fixes accumulate in ArangoDB so they're recalled and applied automatically
    next time the same pattern is encountered.
    """
    escalation_jobs = review_result.get("escalation_jobs", [])
    pdf_path = review_result.get("pdf_path", "")
    verdict = review_result.get("verdict", "UNKNOWN")
    dimensions = review_result.get("dimensions", {})
    sector = review_result.get("sector", "unknown")
    s00_estimates = review_result.get("estimates", {})

    results: List[Dict[str, Any]] = []
    launched = 0

    # Build issue context for memory recall queries
    worst_dims = sorted(
        dimensions.items(),
        key=lambda x: x[1].get("score", 1.0),
    )[:3]
    issue_context = " ".join(
        f"{d[0]}={d[1].get('score', 0):.2f}" for d in worst_dims
    )
    pdf_name = Path(pdf_path).name if pdf_path else "unknown"

    for job in escalation_jobs:
        if not job.get("auto_executable"):
            # Dispatch to /interview for human decision instead of silently skipping
            dispatch_to_interview(
                job=job,
                pdf_path=pdf_path,
                verdict=verdict,
                issue_context=issue_context,
            )
            results.append({
                "command": job.get("command", ""),
                "skill": job.get("skill", ""),
                "status": "deferred_to_interview",
                "reason": job.get("reason", ""),
            })
            continue

        if launched >= MAX_REMEDIATION_JOBS_PER_ITERATION:
            results.append({
                "command": job.get("command", ""),
                "skill": job.get("skill", ""),
                "status": "skipped_max_reached",
            })
            continue

        skill = job.get("skill", "")
        reason = job.get("reason", "")
        command = job.get("command", "")

        # -- Step 1: RECALL -- check /memory for known fixes ----------------
        known_fix = None
        if HAS_MEMORY != "unavailable":
            try:
                client = MemoryClient(scope="extractor")
                recall_query = f"extraction fix {skill} {reason} {issue_context}"
                recall_result = client.recall(recall_query)
                if recall_result.get("found"):
                    items = recall_result.get("items", [])
                    if items:
                        known_fix = items[0]
                        logger.info(
                            f"Memory recall found known fix for /{skill}: "
                            f"{known_fix.get('solution', '')[:120]}"
                        )
            except Exception as exc:
                logger.debug(f"Memory recall failed (non-fatal): {exc}")

        # -- Step 2: FIX -- run the skill command ---------------------------
        logger.info(
            f"Remediation: /{skill} reason='{reason}' "
            f"known_fix={'yes' if known_fix else 'no'} (timeout={timeout}s)"
        )

        try:
            proc = subprocess.run(
                ["bash", "-lc", command],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                start_new_session=True,
            )
            launched += 1
            success = proc.returncode == 0
            stdout_tail = (proc.stdout or "")[-500:]
            stderr_tail = (proc.stderr or "")[-300:]

            result_entry: Dict[str, Any] = {
                "command": command,
                "skill": skill,
                "reason": reason,
                "status": "completed" if success else "failed",
                "returncode": proc.returncode,
                "known_fix_applied": known_fix is not None,
                "memory_learned": False,
            }

            # -- Step 3: LEARN -- store the fix in /memory ------------------
            if HAS_MEMORY != "unavailable":
                try:
                    problem = (
                        f"Extraction {verdict} for {pdf_name}: "
                        f"{reason} ({issue_context})"
                    )
                    if success:
                        # For table-lab, parse JSON to store params in
                        # regex-friendly format so S05 _query_memory_for_params
                        # can extract line_scale=N, edge_tol=N, flavor=X
                        _solution_detail = f"Output: {stdout_tail[:300]}"
                        if skill == "table-lab":
                            try:
                                import json as _json
                                _dt_out = _json.loads(stdout_tail.strip().split("\n")[-1])
                                _params = []
                                if _dt_out.get("best_flavor"):
                                    _params.append(f"flavor={_dt_out['best_flavor']}")
                                if _dt_out.get("best_line_scale"):
                                    _params.append(f"line_scale={_dt_out['best_line_scale']}")
                                if _dt_out.get("best_edge_tol"):
                                    _params.append(f"edge_tol={_dt_out['best_edge_tol']}")
                                if _params:
                                    _solution_detail = (
                                        f"Best params: {', '.join(_params)}. "
                                        f"Raw: {stdout_tail[:200]}"
                                    )
                            except Exception as e:
                                logger.debug("review loop output parsing failed: {}", e)
                        solution = (
                            f"Fixed via /{skill}. "
                            f"{_solution_detail}"
                        )
                    else:
                        solution = (
                            f"Attempted /{skill} but failed (rc={proc.returncode}). "
                            f"Error: {stderr_tail[:200]}. "
                            f"May need different approach."
                        )

                    # Taxonomy tags for multi-hop graph traversal
                    # Include S00 metadata so /memory recall can find fixes
                    # for similar document types (domain, layout, content-type)
                    tags = [
                        f"remediation_{'success' if success else 'failure'}",
                        skill,
                        verdict.lower(),
                        sector,
                    ]
                    # S00 metadata enrichment
                    _domain = s00_estimates.get("domain", "unknown")
                    if _domain and _domain != "unknown":
                        tags.append(f"domain:{_domain}")
                    if s00_estimates.get("has_tables"):
                        tags.append("has_tables")
                    if s00_estimates.get("has_formulas"):
                        tags.append("has_formulas")
                    if s00_estimates.get("layout_columns", 1) >= 2:
                        tags.append("multi_column")
                    _table_count = s00_estimates.get("estimated_table_count", 0)
                    if _table_count >= 10:
                        tags.append("table_heavy")
                    _page_count = s00_estimates.get("page_count", 0)
                    if _page_count >= 50:
                        tags.append("large_document")
                    if HAS_TAXONOMY:
                        try:
                            features = extract_taxonomy_features(
                                content_type=ContentType.OPERATIONAL,
                                description=(
                                    f"extraction remediation {skill} {reason} "
                                    f"{issue_context}"
                                )[:500],
                                high_fidelity=False,
                            )
                            tags.extend(features.get("bridge_attributes", []))
                        except Exception as e:
                            logger.debug("value lookup failed: {}", e)

                    mem_client = MemoryClient(scope="extractor")
                    learn_result = mem_client.learn(
                        problem=problem,
                        solution=solution,
                        tags=tags,
                    )
                    result_entry["memory_learned"] = (
                        learn_result.get("meta", {}).get("ok", False)
                    )
                    if result_entry["memory_learned"]:
                        logger.info(
                            f"Stored remediation fix in /memory: "
                            f"/{skill} -> {verdict}"
                        )
                except Exception as exc:
                    logger.debug(f"Memory learn failed (non-fatal): {exc}")

            results.append(result_entry)

        except subprocess.TimeoutExpired:
            launched += 1
            # Learn the timeout too -- next time we can skip or increase timeout
            if HAS_MEMORY != "unavailable":
                try:
                    mem_client = MemoryClient(scope="extractor")
                    mem_client.learn(
                        problem=(
                            f"Extraction {verdict} for {pdf_name}: {reason}"
                        ),
                        solution=(
                            f"Remediation via /{skill} timed out after "
                            f"{timeout}s. Needs longer timeout or different "
                            f"approach."
                        ),
                        tags=["remediation_timeout", skill, sector],
                    )
                except Exception as e:
                    logger.debug("value lookup failed: {}", e)

            results.append({
                "command": command,
                "skill": skill,
                "reason": reason,
                "status": "timeout",
                "memory_learned": True,
            })

        except Exception as e:
            results.append({
                "command": command,
                "skill": skill,
                "reason": reason,
                "status": "error",
                "error": str(e),
            })

    return results


def link_review_iterations(
    current_problem: str,
    previous_problem: str,
    pdf_path: str,
) -> Optional[str]:
    """Create a 'supersedes' edge between review iterations in /memory.

    Uses problem text (not _key) because add_edge() resolves by exact
    title match on problem[:60]+"...".
    """
    if HAS_MEMORY == "unavailable" or not current_problem or not previous_problem:
        return None

    try:
        result = add_edge(
            from_title=_problem_to_title(current_problem),
            to_title=_problem_to_title(previous_problem),
            type="supersedes",
            from_scope="extractor",
            to_scope="extractor",
            weight=0.9,
            rationale=f"Review iteration supersedes previous for {Path(pdf_path).name}",
        )
        if result.get("meta", {}).get("ok"):
            items = result.get("items", [])
            if items:
                # add_edge() items have from/to/type but no _key;
                # construct identifier from the edge endpoints
                return f"{items[0].get('from', '')}->{items[0].get('to', '')}"
            return None
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    return None


def mark_hard_tail(
    pdf_path: str,
    pdf_hash: str,
    final_score: float,
    score_trajectory: Optional[List[float]] = None,
) -> None:
    """Mark a PDF as hard_tail in /memory with improving/degrading classification.

    Score trajectory distinguishes:
    - hard_tail_improving (0.60 -> 0.62): worth retrying after pipeline improvements
    - hard_tail_degrading (0.60 -> 0.50): needs fundamentally different approach
    - hard_tail (no trajectory): unknown direction
    """
    if HAS_MEMORY == "unavailable":
        return

    # Classify hard-tail direction from score trajectory
    direction = "unknown"
    if score_trajectory and len(score_trajectory) >= 2:
        delta = score_trajectory[-1] - score_trajectory[0]
        if delta > 0.01:
            direction = "improving"
        elif delta < -0.01:
            direction = "degrading"
        else:
            direction = "plateau"

    tags = ["hard_tail", pdf_hash[:8]]
    if direction != "unknown":
        tags.append(f"hard_tail_{direction}")

    try:
        client = MemoryClient(scope="extractor")
        client.learn(
            problem=(
                f"Hard tail PDF: {pdf_path} "
                f"(score={final_score:.3f}, direction={direction}, "
                f"max iterations reached)"
            ),
            solution=(
                f"Score trajectory: {score_trajectory or []}. "
                f"Direction: {direction}. "
                + (
                    "Scores are improving -- worth retrying after pipeline improvements."
                    if direction == "improving"
                    else "Scores are degrading -- needs fundamentally different approach."
                    if direction == "degrading"
                    else "This PDF consistently fails persona review after max iterations. "
                    "Likely a complex document (100+ page MIL-STD, NIST SP, or NASA standard). "
                    "Needs manual review or pipeline improvements before re-attempting."
                )
            ),
            tags=tags,
        )
    except Exception as e:
        logger.debug("scoring failed: {}", e)


def defer_to_question_book(
    question_book: Path,
    pdf_path: str,
    final_score: float,
    score_trajectory: List[float],
    worst_dims: List[str],
    last_review: Dict[str, Any],
    iterations: int,
    max_iterations: int,
) -> bool:
    """Write a deferred question to the JSONL book for morning human review.

    Returns True if successfully written, False otherwise.
    """
    estimate_delta = last_review.get("estimate_delta", {})
    margaret = last_review.get("margaret", {})
    jennifer = last_review.get("jennifer", {})

    # Build human-readable gap summary for /interview
    gap_lines = []
    for name in ("sections", "tables", "figures", "requirements", "equations"):
        d = estimate_delta.get(name, {})
        label = d.get("label", "")
        if label and label not in ("match", "none expected", "none expected, none found"):
            gap_lines.append(f"  {name}: S00 estimated {d.get('estimated')}, got {d.get('actual')} ({label})")

    # Pre-built /interview questions the human will see
    questions = [
        {
            "id": "assessment",
            "text": (
                f"This PDF scored {final_score:.3f} after {iterations} iterations.\n"
                f"Score trajectory: {' -> '.join(f'{s:.3f}' for s in score_trajectory)}\n"
                f"Worst dimensions: {', '.join(dict.fromkeys(worst_dims))}\n\n"
                + ("S00 estimate gaps:\n" + "\n".join(gap_lines) + "\n\n" if gap_lines else "No S00 estimate gaps detected.\n\n")
                + f"Margaret says: {margaret.get('says', 'N/A')}\n"
                f"Jennifer says: {jennifer.get('says', 'N/A')}\n\n"
                "What should we do with this PDF?"
            ),
            "type": "choice",
            "options": [
                "Skip -- not worth fixing",
                "Retry with different strategy",
                "Needs manual correction",
                "Re-scan source document",
            ],
        },
        {
            "id": "strategy_hint",
            "text": "If retrying, what extraction strategy should we try?",
            "type": "text",
        },
    ]

    entry = {
        "pdf_path": pdf_path,
        "pdf_name": Path(pdf_path).name,
        "reason": "hard_tail",
        "best_delta": final_score,
        "score_trajectory": score_trajectory,
        "worst_dimensions": list(dict.fromkeys(worst_dims)),
        "estimate_delta": {
            k: v for k, v in estimate_delta.items() if k != "_summary"
        },
        "margaret_verdict": margaret.get("verdict", "UNKNOWN"),
        "jennifer_verdict": jennifer.get("verdict", "UNKNOWN"),
        "iterations": iterations,
        "max_iterations": max_iterations,
        "questions": questions,
        "timestamp": time.time(),
    }

    try:
        question_book.parent.mkdir(parents=True, exist_ok=True)
        with open(question_book, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        logger.info(f"Deferred to question book: {pdf_path} (score={final_score:.3f})")
        return True
    except OSError as exc:
        logger.warning(f"Failed to write question book: {exc}")
        return False


def get_worst_dimension(review_result: Dict[str, Any]) -> str:
    """Get the name of the worst-scoring dimension from a review result."""
    dims = review_result.get("dimensions", {})
    if not dims:
        return ""
    return min(dims.items(), key=lambda x: x[1].get("score", 1.0))[0]
