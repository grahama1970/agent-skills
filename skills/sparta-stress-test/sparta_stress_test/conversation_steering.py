"""Conversation steering, skill-chain routing, and QRA promotion.

Handles the response-building functions that steer conversations when
Tier 1 classification identifies special cases (unknown entities,
control-only, skill invocations, etc.), and QRA promotion for
satisfactory synthesized answers.
"""

from __future__ import annotations
import os

import hashlib
import json
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from sparta_stress_test.conversation_models import (
    PI_MONO_SKILLS,
    _HAS_BRIDGES,
    _HAS_QRA_BRIDGE,
    _HAS_QUALITY_UTILS,
    Tier1Result,
    _call_scillm,
    _get_db,
)

# Conditional imports
try:
    from graph_memory.qra_bridge import QRABridge
except ImportError:
    QRABridge = None

try:
    from graph_memory.lessons.store import extract_bridges_fast
except ImportError:
    extract_bridges_fast = None

try:
    from sparta_stress_test.response_quality import validate_entities
except ImportError:
    validate_entities = None


# --------------------------------------------------------------------------- #
# Response builders
# --------------------------------------------------------------------------- #


def _build_clarify_response(
    clarify_result: dict,
    question: str,
    target_control: Optional[str],
    db,
) -> Dict:
    """Convert _clarify_direct() output into a Brandon-voice CLARIFY response.

    Uses clarify diagnostics to pick the right tone -- Brandon is direct,
    technical, and collaborative.
    """
    diag = clarify_result.get("diagnostics", {})
    questions = clarify_result.get("clarify_questions", [])
    first_q = questions[0].get("question", "") if questions else ""

    if diag.get("entities_without_qras"):
        ents = diag["entities_without_qras"]
        suggestions = []
        if db:
            for inv_id in ents[:3]:
                try:
                    prefix = inv_id.split("-")[0] if "-" in inv_id else inv_id[:2]
                    neighbors = list(db.aql.execute(
                        """FOR doc IN sparta_controls
                           FILTER STARTS_WITH(doc.control_id, @prefix)
                           SORT LEVENSHTEIN_DISTANCE(doc.control_id, @target) ASC
                           LIMIT 3
                           RETURN doc.control_id""",
                        bind_vars={"prefix": prefix, "target": inv_id},
                    ))
                    if neighbors:
                        suggestions.append(
                            f"I don't recognize '{inv_id}'. The closest I have is {neighbors[0]}."
                        )
                except Exception:
                    pass
        text = " ".join(suggestions) if suggestions else f"I don't recognize {', '.join(ents[:3])} in the SPARTA knowledge base."
        text += f" {first_q}" if first_q else " Could you verify the control ID?"
    elif diag.get("intent_says_clarify"):
        text = f"Let me be precise about what I need to look up. {first_q}" if first_q else "Could you be more specific about what you're looking for?"
    elif diag.get("zero_bridges"):
        text = f"What aspect of space systems security are you interested in? {first_q}" if first_q else "What aspect of space systems security are you interested in?"
    elif diag.get("low_recall_confidence") is not None:
        text = f"I found partial matches but I'm not confident. {first_q}" if first_q else "Could you narrow down your question to a specific control or system component?"
    elif diag.get("low_bridge_correlation") is not None:
        query_bridges = clarify_result.get("taxonomy", {}).get("merged_bridges", [])
        text = f"Your question touches on {', '.join(query_bridges[:3]) or 'multiple areas'}, but my coverage focuses elsewhere. {first_q}" if first_q else "Could you rephrase to target a specific threat or control?"
    else:
        text = first_q or "Could you provide more details about what you're looking for?"

    return {
        "answered": False,
        "action": "CLARIFY",
        "answer_text": text,
        "clarify_detail": {
            "diagnostics": diag,
            "questions": questions,
        },
        "qra_count": 0,
        "sparta_techniques": [],
        "sparta_countermeasures": [],
        "source_keys": [],
    }


def _build_no_coverage_response(
    question: str,
    target_control: Optional[str],
    entities: List[str],
    related_controls: List[str],
    db,
) -> Dict:
    """Post-retrieval honest response when all AQL lanes returned empty.

    Different from pre-retrieval clarify -- Brandon has actually searched and
    can report what he tried and what related info exists.
    """
    parts = []

    if entities:
        parts.append(f"The SPARTA corpus doesn't have QRA coverage for {', '.join(entities[:3])} yet.")

    if related_controls:
        parts.append(f"I found related controls in the relationship graph: {', '.join(related_controls[:5])}. I can look those up if they help.")

    if target_control and not entities:
        parts.append(f"I searched for '{target_control}' but found no matching QRAs.")

    if not parts:
        parts.append("I searched the SPARTA knowledge base but couldn't find QRA coverage for your question.")

    parts.append("Could you narrow down to a specific SPARTA control ID, or ask about a related area?")

    return {
        "answered": False,
        "action": "CLARIFY",
        "answer_text": " ".join(parts),
        "qra_count": 0,
        "related_controls": related_controls,
        "sparta_techniques": [],
        "sparta_countermeasures": [],
        "source_keys": [],
    }


def _build_interview_response(
    question: str,
    options: List[str],
    db,
) -> Dict:
    """Structured options response -- when Brandon has 2-3 specific controls to ask about."""
    options_text = ", ".join(options[:5])
    text = (
        f"I found {len(options)} related controls that might answer your question. "
        f"Which are you asking about? Options: {options_text}"
    )

    return {
        "answered": False,
        "action": "INTERVIEW",
        "answer_text": text,
        "options": options[:5],
        "qra_count": 0,
        "sparta_techniques": [],
        "sparta_countermeasures": [],
        "source_keys": [],
    }


# --------------------------------------------------------------------------- #
# Steering functions (replace bare CLARIFY with conversation guidance)
# --------------------------------------------------------------------------- #


def _qra_count_for_entities(entity_ids: List[str], db) -> Dict[str, int]:
    """Fast AQL: count QRAs per entity. O(1) per entity via indexed lookup."""
    counts: Dict[str, int] = {}
    if not entity_ids:
        return counts
    try:
        cursor = db.aql.execute(
            """FOR cid IN @cids
                 LET cnt = LENGTH(
                   FOR doc IN sparta_qra
                     FILTER doc.control_id == cid
                     RETURN 1
                 )
                 RETURN {cid: cid, cnt: cnt}""",
            bind_vars={"cids": entity_ids},
        )
        for row in cursor:
            counts[row["cid"]] = row["cnt"]
    except Exception as e:
        logger.debug(f"QRA count query failed: {e}")
        for cid in entity_ids:
            try:
                cnt = db.aql.execute(
                    "RETURN LENGTH(FOR d IN sparta_qra FILTER d.control_id == @c RETURN 1)",
                    bind_vars={"c": cid},
                ).next()
                counts[cid] = cnt
            except Exception:
                counts[cid] = 0
    return counts


def _steer_control_only(tier1: Tier1Result, question: str, db) -> Dict:
    """Control exists but zero QRAs. Guide toward answerable territory."""
    entity = tier1.valid_entities[0] if tier1.valid_entities else "unknown"

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

    neighbors_with_qras = [
        n for n in tier1.graph_neighbors
        if tier1.qra_counts.get(n, 0) > 0
    ]
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
        # answered=False because we're offering alternatives, not giving a real answer
        return {
            "answered": False,
            "action": "CLARIFY",
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
    # answered=False because this is a gap acknowledgment, not a real answer
    return {
        "answered": False,
        "action": "CLARIFY",
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
    """Execute an explicit /skill command via subprocess."""
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
    """Suggest a skill match from trigger phrases -- confirm before executing."""
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
# QRA Promotion (satisfactory answer -> new sparta_qra)
# --------------------------------------------------------------------------- #


def _check_promotion_eligible(
    session: Any,
    sparta_result: Dict,
    evaluation: str,
    final_composite: float,
) -> bool:
    """Check if a synthesized answer should be promoted to a new sparta_qra."""
    if evaluation not in ("satisfactory", "flaw_caught"):
        return False
    if final_composite < 0.85:
        return False
    answer = sparta_result.get("answer_text", "")
    is_synthesis = (
        sparta_result.get("steering")
        or "[GRAPH-INFERRED]" in answer
        or sparta_result.get("_source") == "multi_turn_conversation"
    )
    if not is_synthesis:
        return False
    if "[NOT IN CORPUS]" in answer and sparta_result.get("qra_count", 0) == 0:
        return False
    return True


def _promote_to_qra(
    question: str,
    answer: str,
    entities: List[str],
    session_id: str,
    persona: str,
    composite: float,
    turn_num: int = 0,
) -> Optional[str]:
    """Promote a satisfactory synthesized answer to a new sparta_qra.

    Returns the QRA key if promoted, None if failed.
    """
    if not _HAS_QRA_BRIDGE:
        logger.debug("QRABridge not available — skipping promotion")
        return None

    try:
        db = _get_db()
        bridge = QRABridge(db)

        target_control = entities[0] if entities else ""
        query_hash = hashlib.md5(question.encode()).hexdigest()[:12]
        synth_hash = hashlib.md5(f"{question}{answer}".encode()).hexdigest()[:12]

        bridge_tags = []
        conceptual_tags = []
        tactical_tags = []
        if _HAS_BRIDGES and extract_bridges_fast:
            try:
                bridges = extract_bridges_fast(f"{question} {answer}")
                bridge_tags = bridges if isinstance(bridges, list) else list(bridges.keys()) if isinstance(bridges, dict) else []
            except Exception:
                pass

        try:
            tax_result = subprocess.run(
                [
                    sys.executable, "-m", "graph_memory.agent_cli",
                    "taxonomy-extract",
                    "--text", f"{question} {answer}"[:500],
                    "--vocabulary", "sparta",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if tax_result.returncode == 0:
                tax_data = json.loads(tax_result.stdout)
                conceptual_tags = tax_data.get("conceptual_tags", [])
                tactical_tags = tax_data.get("tactical_tags", [])
        except Exception:
            pass

        qra_doc = {
            "_key": f"qra__persona-conv__{synth_hash}",
            "qra_id": f"synth_persona_{query_hash}",
            "run_id": "persona-conversation",
            "control_id": target_control,
            "question": question,
            "answer": answer,
            "reasoning": (
                f"Promoted from conversation {session_id}, turn {turn_num}. "
                f"Persona '{persona}' evaluated 'satisfactory' (composite={composite:.2f})."
            ),
            "grounding_score": composite,
            "conceptual_tags": conceptual_tags,
            "tactical_tags": tactical_tags,
            "bridge_attributes": bridge_tags,
            "_source": "persona_conversation_promotion",
            "_scope": "sparta",
            "created_at": time.time(),
        }

        try:
            from graph_memory.quality.assess import assess_qra
            assessment = assess_qra(qra_doc)
        except ImportError:
            assessment = {"grade": "PASS", "notes": ["assess_qra not available"]}
        except Exception as _assess_err:
            logger.warning(f"assess_qra() failed for {target_control}: {_assess_err}")
            assessment = {"grade": "WARN", "notes": [f"assess_qra error: {_assess_err}"]}

        if assessment["grade"] == "FAIL":
            try:
                from graph_memory.candidate_bridge import CandidateBridge
                CandidateBridge(db).log_rejected(qra_doc, assessment)
            except Exception:
                pass
            logger.info(
                f"Rejected QRA for {target_control} (grade=FAIL, "
                f"notes={assessment.get('notes', [])})"
            )
            return None
        elif assessment["grade"] == "WARN":
            try:
                from graph_memory.candidate_bridge import CandidateBridge
                CandidateBridge(db).stage(qra_doc, assessment)
            except Exception as stage_err:
                logger.debug(f"Failed to stage WARN candidate: {stage_err}")
            logger.info(
                f"Staged QRA {qra_doc['_key']} for review (grade=WARN, "
                f"notes={assessment.get('notes', [])})"
            )
            return f"staged:{qra_doc['_key']}"
        else:  # PASS
            bridge.upsert_qra(qra_doc)
            logger.info(
                f"Promoted QRA {qra_doc['_key']} for {target_control} "
                f"(composite={composite:.2f}, session={session_id})"
            )
            return qra_doc["_key"]

    except Exception as e:
        logger.warning(f"QRA promotion failed: {e}")
        return None
