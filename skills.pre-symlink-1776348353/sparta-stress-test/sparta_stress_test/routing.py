"""Steering, skill chain routing, and query planning for SPARTA conversations.

Contains functions that route questions to the appropriate response strategy:
steering for unknown/control-only entities, skill chain execution,
and query strategy planning (LLM + heuristic fallback).
"""

from __future__ import annotations
import os

import json
import subprocess
from typing import Any, Dict, List

from loguru import logger

from sparta_stress_test.models import (
    PI_MONO_SKILLS,
    Tier1Result,
)
from sparta_stress_test.prompts import QUERY_PLAN_PROMPT


# --------------------------------------------------------------------------- #
# Steering functions (replace bare CLARIFY with conversation guidance)
# --------------------------------------------------------------------------- #


def _steer_control_only(tier1: Tier1Result, question: str, db) -> Dict:
    """Control exists but zero QRAs. Guide toward answerable territory."""
    from sparta_stress_test.retrieval import _qra_count_for_entities

    entity = tier1.valid_entities[0] if tier1.valid_entities else "unknown"

    # Fetch control definition
    ctrl_def = None
    try:
        cursor = db.aql.execute(
            "FOR c IN sparta_controls FILTER c.control_id == @cid LIMIT 1 RETURN c",
            bind_vars={"cid": entity},
        )
        ctrl_def = next(cursor, None)
    except Exception:
        pass

    parts = []
    if ctrl_def:
        name = ctrl_def.get("name", entity)
        desc = ctrl_def.get("description", "")[:300]
        parts.append(f"[CONTROL-CONTEXT] {name}: {desc}")

    parts.append(
        f"I have the control definition but no vetted Q&A pairs for {entity} yet."
    )

    # Find neighbors that DO have QRAs
    neighbors_with_qras = [
        n for n in tier1.graph_neighbors
        if tier1.qra_counts.get(n, 0) > 0
    ]
    # Also check neighbor QRA counts if not already in tier1.qra_counts
    if not neighbors_with_qras and tier1.graph_neighbors:
        try:
            extra_counts = _qra_count_for_entities(tier1.graph_neighbors[:5], db)
            neighbors_with_qras = [n for n in tier1.graph_neighbors if extra_counts.get(n, 0) > 0]
        except Exception:
            pass

    if neighbors_with_qras:
        parts.append(
            f"Related controls with vetted answers: {', '.join(neighbors_with_qras[:5])}. "
            f"I can synthesize from those — would that help?"
        )
        return {
            "answered": True,
            "action": "QUERY",
            "answer_text": "\n".join(parts),
            "qra_count": 0,
            "steering": True,
            "steered_from": entity,
            "related_controls": neighbors_with_qras[:5],
            "sparta_techniques": [],
            "sparta_countermeasures": [],
            "source_keys": [],
        }

    parts.append(
        "This is a gap in our corpus. I can attempt an inference from the control definition."
    )
    return {
        "answered": True,
        "action": "QUERY",
        "answer_text": "\n".join(parts),
        "qra_count": 0,
        "steering": True,
        "steered_from": entity,
        "related_controls": [],
        "sparta_techniques": [],
        "sparta_countermeasures": [],
        "source_keys": [],
    }


def _steer_unknown_entity(tier1: Tier1Result, question: str) -> Dict:
    """Entity not in corpus. Offer fuzzy matches."""
    parts = []
    for unk in tier1.unknown_entities[:3]:
        matches = tier1.fuzzy_matches.get(unk, [])
        if matches:
            parts.append(f"I don't recognize '{unk}'. Did you mean: {', '.join(matches[:3])}?")
        else:
            parts.append(f"'{unk}' isn't in the SPARTA framework. Could you verify the control ID?")
    return {
        "answered": False,
        "action": "CLARIFY",
        "answer_text": "\n".join(parts) if parts else "I couldn't find that control in the SPARTA framework.",
        "qra_count": 0,
        "steering": True,
        "related_controls": [],
        "sparta_techniques": [],
        "sparta_countermeasures": [],
        "source_keys": [],
    }


# --------------------------------------------------------------------------- #
# Skill-chain routing (explicit /slash + implicit trigger)
# --------------------------------------------------------------------------- #


def _execute_skill_chain(skill_refs: List[str], question: str, session_id: str = "") -> Dict:
    """Execute an explicit /skill command via subprocess. Tested code, not LLM improvisation."""
    skill_name = skill_refs[0] if skill_refs else "unknown"
    skill_dir = PI_MONO_SKILLS / skill_name
    run_sh = skill_dir / "run.sh"

    if not run_sh.exists():
        return {
            "answered": False,
            "action": "CLARIFY",
            "answer_text": f"Skill /{skill_name} not found. Available skills are in /memory.",
            "qra_count": 0,
            "sparta_techniques": [],
            "sparta_countermeasures": [],
            "source_keys": [],
        }

    try:
        result = subprocess.run(
            [str(run_sh), question],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(skill_dir),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        output = result.stdout.strip() or result.stderr.strip()
        if not output:
            output = f"/{skill_name} completed with no output."
        return {
            "answered": True,
            "action": "QUERY",
            "answer_text": f"[SKILL-OUTPUT /{skill_name}] {output[:2000]}",
            "qra_count": 0,
            "sparta_techniques": [],
            "sparta_countermeasures": [],
            "source_keys": [],
            "skill_invoked": skill_name,
        }
    except subprocess.TimeoutExpired:
        return {
            "answered": False,
            "action": "CLARIFY",
            "answer_text": f"/{skill_name} timed out after 120s.",
            "qra_count": 0,
            "sparta_techniques": [],
            "sparta_countermeasures": [],
            "source_keys": [],
        }
    except Exception as e:
        return {
            "answered": False,
            "action": "CLARIFY",
            "answer_text": f"/{skill_name} failed: {e}",
            "qra_count": 0,
            "sparta_techniques": [],
            "sparta_countermeasures": [],
            "source_keys": [],
        }


def _suggest_skill(skill_refs: List[str], question: str) -> Dict:
    """Suggest a skill match from trigger phrases — confirm before executing."""
    suggestions = ", ".join(f"/{s}" for s in skill_refs[:3])
    return {
        "answered": True,
        "action": "QUERY",
        "answer_text": (
            f"That sounds like a task for {suggestions}. "
            f"Want me to run it? (Say '/{skill_refs[0]}' to confirm.)"
        ),
        "qra_count": 0,
        "steering": True,
        "skill_suggested": skill_refs,
        "sparta_techniques": [],
        "sparta_countermeasures": [],
        "source_keys": [],
    }


# --------------------------------------------------------------------------- #
# Query planning
# --------------------------------------------------------------------------- #


def _plan_query_strategy(
    question: str,
    entities: List[str],
    bridges: List[str],
    episodic_context: str,
) -> Dict[str, Any]:
    """Brandon decides which AQL calls + skills to compose for this question.

    Uses /scillm for the decision. /assistant shadows every call so classifiers
    learn the pattern via Shadow-LEGO. Eventually a Tier 0 classifier replaces
    the LLM call entirely.

    Returns:
        {"strategy": [...], "primary_lane": "...", "needs_graph": bool, ...}
    """
    from sparta_stress_test.retrieval import _call_scillm, _HAS_ASSISTANT

    prompt = QUERY_PLAN_PROMPT.format(
        question=question[:500],
        entities=", ".join(entities[:10]) if entities else "(none)",
        bridges=", ".join(bridges[:6]) if bridges else "(none)",
        episodic_summary=episodic_context[:300] if episodic_context else "(no prior answers found)",
    )

    # --- Try /scillm for the planning decision ---
    plan = None
    try:
        raw = _call_scillm(
            system="You are a query planner for SPARTA space systems cybersecurity. Return JSON only.",
            user_prompt=prompt,
            max_tokens=256,
        )
        plan = json.loads(raw)
    except Exception as e:
        logger.debug(f"Query planner /scillm call failed: {e}")

    # --- Shadow via /assistant so classifiers learn this decision ---
    if _HAS_ASSISTANT and plan:
        try:
            from sparta_stress_test.retrieval import _assistant_classify
            _assistant_classify(
                text=f"Q: {question[:300]}\nEntities: {', '.join(entities[:5])}\nBridges: {', '.join(bridges[:3])}",
                task="query_plan",
                scope="sparta",
                confidence_threshold=0.75,
            )
        except Exception:
            pass

    # --- Fallback: deterministic heuristics if /scillm unavailable ---
    if not plan:
        plan = _plan_query_heuristic(question, entities, bridges, episodic_context)

    return plan


def _plan_query_heuristic(
    question: str,
    entities: List[str],
    bridges: List[str],
    episodic_context: str,
) -> Dict[str, Any]:
    """Deterministic fallback query planner — no LLM needed.

    This is the Tier 0 heuristic that runs when /scillm is unavailable.
    Shadow-LEGO classifiers will eventually replace this too.
    """
    q_lower = question.lower()
    strategy = []
    needs_graph = False
    needs_memory_recall = False
    reuse_episodic = False

    # If we have a strong episodic match, consider reuse
    if episodic_context and len(episodic_context) > 100:
        strategy.append("EPISODIC_REUSE")
        reuse_episodic = True

    # Entity-anchored QRA lookup is always first when we have entities
    if entities:
        strategy.append("QRA_LOOKUP")

    # Relationship/connection questions need graph traversal
    if any(w in q_lower for w in (
        "related", "connected", "mapped", "attack chain", "path",
        "relationship", "linked", "associated", "impacts", "affects",
        "neighbor", "adjacent", "upstream", "downstream",
    )):
        strategy.append("GRAPH_TRAVERSAL")
        needs_graph = True

    # Broad/vague questions need hybrid search
    if not entities or any(w in q_lower for w in (
        "overview", "summary", "explain", "describe", "what is",
        "how does", "why", "compare", "difference",
    )):
        strategy.append("MEMORY_RECALL")
        needs_memory_recall = True

    # Always include BM25 as fallback
    if "QRA_LOOKUP" not in strategy:
        strategy.append("BM25_SEARCH")

    if not strategy:
        strategy = ["QRA_LOOKUP", "BM25_SEARCH"]

    return {
        "strategy": strategy,
        "reasoning": "heuristic fallback",
        "primary_lane": strategy[0] if strategy else "QRA_LOOKUP",
        "needs_graph": needs_graph,
        "needs_memory_recall": needs_memory_recall,
        "reuse_episodic": reuse_episodic,
        "needs_clarify": False,
    }
