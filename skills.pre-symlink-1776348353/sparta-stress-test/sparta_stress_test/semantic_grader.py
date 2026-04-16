"""Two-stage semantic grading: deterministic evidence FIRST, LLM SECOND.

Architecture:
    Stage 1 (runs FIRST, no LLM):
        - /memory trace  → citation verification from ArangoDB lookups
        - /assistant     → trained classifier cascade (heuristic→classifier→GPT→scillm)
        - /lean4-prove   → formal proof of reasoning chain soundness
        - Bridge overlap → taxonomy intersection (computed)
        - Delta tracking → self-correction improvement signal

    Stage 2 (LLM receives Stage 1 as READ-ONLY evidence):
        - Scores ONLY qualitative dimensions: naturalness, coherence, domain accuracy
        - CANNOT override deterministic results
        - Grade = 60% deterministic + 40% LLM qualitative

HARD RULE: Keyword scanning is BANNED. QRA citation is the ONLY valid
quality signal — "good" means cited real QRAs with matching control_ids.

Usage:
    from semantic_grader import grade_response_semantic, collect_evidence

    # Stage 1: collect all deterministic evidence
    evidence = collect_evidence(
        question="What countermeasures apply to SV-MA-3?",
        answer="The relevant countermeasures include...",
        qra_source_keys=["sparta_qra/12345"],
        scope="sparta",
    )

    # Stage 2: grade with evidence anchoring
    result = grade_response_semantic(
        question="What countermeasures apply to SV-MA-3?",
        answer="The relevant countermeasures include...",
        transcript="Turn 1:\\nQ: ...\\nA: ...",
        qra_source_keys=["sparta_qra/12345"],
        target_control="SV-MA-3",
        difficulty="medium",
        expected_action="QUERY",
    )
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# Ensure graph_memory is importable
_src_path = str(Path(__file__).resolve().parents[4] / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# scillm path
_scillm_path = str(
    Path(__file__).resolve().parents[4].parent
    / "pi-mono" / ".pi" / "skills" / "scillm"
)
if _scillm_path not in sys.path:
    sys.path.insert(0, _scillm_path)

# Both student and teacher use DeepSeek V3.
# Qwen3 was too lenient — graded 9/10 sessions A (0.92) on first pass.
# DeepSeek catches real problems. Same model family is fine when the
# deterministic entity gate handles hallucination detection.
# Use env-configured model, falling back to DeepSeek-V3.
# NEVER hardcode a model that differs from scillm proxy's configured default.
STUDENT_MODEL = os.getenv("CHUTES_MODEL_ID") or os.getenv("CHUTES_TEXT_MODEL") or "deepseek-ai/DeepSeek-V3"
TEACHER_MODEL = os.getenv("CHUTES_MODEL_ID") or os.getenv("CHUTES_TEXT_MODEL") or "deepseek-ai/DeepSeek-V3"

# Paths to sibling skills for evidence collection
_SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"
_ASSISTANT_PATH = _SKILLS_DIR / "assistant"
_LEAN4_PATH = _SKILLS_DIR / "lean4-prove"
_MEMORY_VENV = Path(__file__).resolve().parents[4] / ".venv" / "bin" / "python"

_WARNED_KEYS: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    """Emit a warning only once per process for noisy dependency failures."""
    if key in _WARNED_KEYS:
        return
    _WARNED_KEYS.add(key)
    logger.warning(message)


# --------------------------------------------------------------------------- #
# STAGE 1: Deterministic Evidence Collection
# Runs BEFORE the LLM. Gathers hard facts from /memory trace, /assistant,
# /lean4-prove, and taxonomy bridge overlap. No LLM calls here.
# --------------------------------------------------------------------------- #


def _call_memory_trace(
    question: str,
    answer: str,
    scope: str = "sparta",
    mode: str = "fast",
    k: int = 10,
) -> dict:
    """Call /memory trace for citation verification and bridge overlap.

    Uses the memory-agent CLI subprocess (same as lie-detector trace_compose).
    Returns trace result dict or empty dict on failure.
    """
    try:
        cmd = [
            str(_MEMORY_VENV), "-m", "graph_memory.agent_cli",
            "trace",
            "--q", question[:500],
            "--mode", mode,
            "--k", str(k),
            "--json",
        ]
        if answer:
            cmd.extend(["--answer", answer[:1000]])
        if scope:
            cmd.extend(["--scope", scope])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path(__file__).resolve().parents[4]),
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        logger.debug(f"Memory trace unavailable: {e}")
    except Exception as e:
        logger.debug(f"Memory trace failed: {e}")
    return {}


def _call_assistant_validate(
    question: str,
    answer: str,
    scope: str = "brandon_bailey",
) -> dict:
    """Call /assistant validate for trained classifier assessment.

    Uses the 4-tier cascade: heuristic → classifier → GPT → scillm.
    Returns {tier, confidence, result} or empty dict on failure.
    """
    if str(_ASSISTANT_PATH) not in sys.path:
        sys.path.insert(0, str(_ASSISTANT_PATH))
    try:
        from gateway import validate

        tier_result = validate(
            input_data={"question": question, "answer": answer},
            task="qra-assessor",
            scope=scope,
            confidence_threshold=0.75,
        )
        return {
            "tier": tier_result.tier,
            "confidence": tier_result.confidence,
            "source": tier_result.source,
            "result": tier_result.result,
            "latency_ms": tier_result.latency_ms,
        }
    except ImportError:
        _warn_once(
            "assistant_import_unavailable",
            "ASSISTANT_UNAVAILABLE: /assistant skill not importable — classifier weight will be redistributed",
        )
        return {"ASSISTANT_UNAVAILABLE": True}


def _call_lean4_verify(answer_text: str, qra_count: int) -> dict:
    """Call /lean4-prove for formal reasoning verification.

    Returns {score, steps_verified, steps_total} or empty dict on failure.
    """
    if qra_count == 0:
        return {"score": 0.0, "unavailable": False, "skipped": True}

    lean4_url = os.getenv("LEAN4_SERVICE_URL", "http://localhost:8604")
    try:
        import httpx
        health = httpx.get(f"{lean4_url}/health", timeout=2.0)
        if health.status_code != 200:
            _warn_once(
                "lean4_service_unhealthy",
                "LEAN4_UNAVAILABLE: service unhealthy — lean4 weight will be redistributed",
            )
            return {"score": 0.0, "unavailable": True, "LEAN4_UNAVAILABLE": True}
    except Exception:
        _warn_once(
            "lean4_service_unreachable",
            "LEAN4_UNAVAILABLE: service not reachable — lean4 weight will be redistributed",
        )
        return {"score": 0.0, "unavailable": True, "LEAN4_UNAVAILABLE": True}

    try:
        if str(_LEAN4_PATH) not in sys.path:
            sys.path.insert(0, str(_LEAN4_PATH))
        from qra_reasoning import verify_qra_reasoning

        result = verify_qra_reasoning(
            {"reasoning": answer_text, "qra_id": "semantic_grader"},
            timeout=30,
        )
        score = (
            result.steps_verified / max(result.steps_total, 1)
            if result.steps_total > 0
            else 0.5
        )
        return {
            "score": score,
            "steps_total": result.steps_total,
            "steps_verified": result.steps_verified,
            "steps_failed": result.steps_failed,
            "error_taxonomy": result.error_taxonomy,
            "unavailable": False,
        }
    except ImportError:
        _warn_once(
            "lean4_import_unavailable",
            "LEAN4_UNAVAILABLE: qra_reasoning module not importable — lean4 weight will be redistributed",
        )
        return {"score": 0.0, "unavailable": True, "LEAN4_UNAVAILABLE": True}
    except Exception as e:
        _warn_once(
            "lean4_verify_failed",
            f"LEAN4_UNAVAILABLE: verification failed ({e}) — lean4 weight will be redistributed",
        )
        return {"score": 0.0, "unavailable": True, "LEAN4_UNAVAILABLE": True}


def collect_evidence(
    question: str,
    answer: str,
    qra_source_keys: list | None = None,
    scope: str = "sparta",
    process_signals: dict | None = None,
) -> dict:
    """Stage 1: Collect ALL deterministic evidence before LLM grades.

    Calls /memory trace, /assistant validate, /lean4-prove, and merges
    with any caller-provided process_signals (bridge overlap, delta, etc).

    Returns an evidence_packet dict with all deterministic scores.
    This runs FIRST — the LLM receives it as read-only context.
    """
    t0 = time.monotonic()
    qra_source_keys = qra_source_keys or []
    process_signals = process_signals or {}
    evidence: dict[str, Any] = {
        "sources_called": [],
        "collection_latency_ms": 0.0,
        "ASSISTANT_UNAVAILABLE": False,
        "LEAN4_UNAVAILABLE": False,
    }

    # 1. Citation verification (ArangoDB deterministic lookup)
    citation_result = verify_qra_citations(answer, qra_source_keys, scope=scope)
    evidence["citation"] = citation_result
    evidence["citation_ratio"] = (
        citation_result["verified"] / max(citation_result["total"], 1)
        if citation_result["total"] > 0
        else 0.0
    )
    evidence["sources_called"].append("citation_verification")

    # 2. /memory trace (bridge overlap, graph paths, additional citation data)
    trace_result = _call_memory_trace(question, answer, scope=scope)
    if trace_result:
        evidence["trace"] = trace_result
        # Extract bridge overlap from trace retrieval results
        retrieval = trace_result.get("retrieval", {})
        trace_results_list = retrieval.get("results", [])
        if trace_results_list:
            # Count how many results have graph paths (connected evidence)
            graph_connected = sum(
                1 for r in trace_results_list if r.get("graph_hops", 0) > 0
            )
            evidence["graph_connected_count"] = graph_connected
        # Extract verification data if trace did claim checking
        verification = trace_result.get("verification", {})
        if verification:
            evidence["trace_claims_verified"] = verification.get("claims_verified", 0)
            evidence["trace_claims_total"] = verification.get("claims_total", 0)
        evidence["sources_called"].append("memory_trace")

    # 3. /assistant validate (trained classifier cascade)
    try:
        assistant_result = _call_assistant_validate(question, answer, scope="brandon_bailey")
    except Exception as e:
        evidence["ASSISTANT_UNAVAILABLE"] = True
        logger.warning(
            f"ASSISTANT_UNAVAILABLE: validate failed ({e}) — classifier weight will be redistributed"
        )
        assistant_result = {"ASSISTANT_UNAVAILABLE": True}

    if assistant_result:
        if assistant_result.get("ASSISTANT_UNAVAILABLE"):
            evidence["ASSISTANT_UNAVAILABLE"] = True
        else:
            evidence["assistant"] = assistant_result
            evidence["assistant_confidence"] = assistant_result.get("confidence", 0.0)
            evidence["assistant_tier"] = assistant_result.get("tier", 2.0)
            evidence["sources_called"].append("assistant_classifier")

    # 4. /lean4-prove (formal reasoning verification)
    lean4_result = _call_lean4_verify(answer, len(qra_source_keys))
    if lean4_result:
        if lean4_result.get("unavailable") or lean4_result.get("LEAN4_UNAVAILABLE"):
            evidence["LEAN4_UNAVAILABLE"] = True
        else:
            evidence["lean4"] = lean4_result
            evidence["lean4_score"] = lean4_result.get("score", 0.0)
            evidence["sources_called"].append("lean4_proof")

    # 5. Merge caller-provided process signals (bridge overlap, delta, etc.)
    evidence["bridge_overlap_count"] = process_signals.get("bridge_overlap_count", 0)
    evidence["bridge_tags_matched"] = process_signals.get("bridge_tags_matched", [])
    evidence["richness_score"] = process_signals.get("richness_score", 0.0)
    evidence["framework_coverage"] = process_signals.get("framework_coverage", {})
    evidence["delta_improvement"] = process_signals.get("delta_improvement", 0.0)

    evidence["collection_latency_ms"] = (time.monotonic() - t0) * 1000

    logger.debug(
        f"Evidence collected in {evidence['collection_latency_ms']:.0f}ms: "
        f"sources={evidence['sources_called']}, "
        f"citation={evidence['citation_ratio']:.2f}, "
        f"lean4={evidence.get('lean4_score', 'N/A')}, "
        f"assistant={evidence.get('assistant_confidence', 'N/A')}"
    )

    return evidence


from sparta_stress_test.semantic_grader_prompts import (
    GRADING_DIMENSIONS,
    RESPONSE_TYPE_GRADING_RULES,
    RESPONSE_TYPE_TAXONOMY,
    RESPONSE_TYPES,
    SEMANTIC_GRADE_PROMPT,
    deterministic_only_grade as _deterministic_only_grade,
    fallback_grade as _fallback_grade,
)


def _get_quick_completion():
    """Dynamically import quick_completion from scillm."""
    for module_name in ("batch", "scillm_skill.batch", "scillm.batch"):
        try:
            mod = __import__(module_name, fromlist=["quick_completion"])
            if hasattr(mod, "quick_completion"):
                return mod.quick_completion
        except ImportError:
            continue
    return None


def _get_db():
    """Get ArangoDB connection."""
    try:
        from graph_memory.arango_client import get_db
        return get_db()
    except Exception as e:
        logger.debug(f"ArangoDB unavailable: {e}")
        return None


def _fetch_qra_by_key(db, source_key: str) -> Optional[Dict[str, Any]]:
    """Fetch a single QRA document by its _key or _id."""
    if not db:
        return None
    try:
        # Handle both "sparta_qra/12345" and "12345" formats
        key = source_key.split("/")[-1] if "/" in source_key else source_key
        cursor = db.aql.execute(
            "FOR q IN sparta_qra FILTER q._key == @key LIMIT 1 RETURN q",
            bind_vars={"key": key},
        )
        results = list(cursor)
        return results[0] if results else None
    except Exception as e:
        logger.debug(f"QRA fetch failed for {source_key}: {e}")
        return None


def verify_qra_citations(
    answer: str,
    qra_source_keys: list,
    scope: str = "sparta",
) -> dict:
    """Check if answer actually cites/uses retrieved QRAs.

    Uses ArangoDB to fetch each source_key and checks whether
    the answer content aligns with the QRA's control_id and answer.

    Returns:
        {verified: int, total: int, details: [...]}
    """
    if not qra_source_keys:
        return {"verified": 0, "total": 0, "details": []}

    db = _get_db()
    if not db:
        return {"verified": 0, "total": len(qra_source_keys), "details": []}

    answer_lower = answer.lower()
    # Tokenize answer into words for overlap checking
    answer_words = set(answer_lower.split())
    details = []
    verified = 0

    for key in qra_source_keys:
        qra = _fetch_qra_by_key(db, key)
        if not qra:
            details.append({"key": key, "status": "not_found"})
            continue

        control_id = qra.get("control_id", "")

        # Check 1: exact control ID match (e.g. "SV-MA-3" in text)
        cid_cited = control_id.lower() in answer_lower if control_id else False

        # Check 2: content overlap — does the answer use substantive phrases
        # from this QRA's answer text? This catches cases where the system
        # used the QRA content but didn't explicitly name the control ID.
        content_overlap = False
        qra_answer = qra.get("answer", "")
        if qra_answer and len(qra_answer) > 20:
            # Extract 3-word phrases from QRA answer and check overlap
            qra_words = qra_answer.lower().split()
            if len(qra_words) >= 5:
                # Check if any 4+ word sequence from QRA appears in answer
                for i in range(len(qra_words) - 3):
                    phrase = " ".join(qra_words[i:i + 4])
                    if phrase in answer_lower:
                        content_overlap = True
                        break
            # Also check: >30% word overlap (substantive content reuse)
            if not content_overlap:
                qra_content_words = {w for w in qra_words if len(w) > 4}
                if qra_content_words:
                    overlap_ratio = len(answer_words & qra_content_words) / len(qra_content_words)
                    content_overlap = overlap_ratio > 0.30

        is_verified = cid_cited or content_overlap
        if is_verified:
            verified += 1

        # Determine verification method for traceability
        if cid_cited:
            method = "control_id_match"
        elif content_overlap:
            method = "content_overlap"
        else:
            method = "not_found"

        details.append({
            "key": key,
            "control_id": control_id,
            "cid_cited": cid_cited,
            "content_overlap": content_overlap,
            "verified": is_verified,
            "method": method,
            "status": "verified" if is_verified else "not_cited",
        })

    return {
        "verified": verified,
        "total": len(qra_source_keys),
        "details": details,
    }


def _build_qra_ground_truth(qra_source_keys: list) -> str:
    """Fetch QRAs and format as ground truth text for the grading prompt."""
    if not qra_source_keys:
        return "(No QRAs retrieved for this session)"

    db = _get_db()
    if not db:
        return "(ArangoDB unavailable — cannot verify QRA ground truth)"

    lines = []
    for key in qra_source_keys[:10]:  # More ground truth = better citation verification
        qra = _fetch_qra_by_key(db, key)
        if not qra:
            continue
        control_id = qra.get("control_id", "unknown")
        answer_text = qra.get("answer", "")[:300]
        grounding = qra.get("grounding_score", 0)
        lines.append(
            f"- Control {control_id} (grounding={grounding:.2f}): {answer_text}"
        )

    return "\n".join(lines) if lines else "(No QRAs found for provided keys)"


def _compute_deterministic_anchor(
    evidence: dict,
) -> dict:
    """Compute deterministic grade anchor from evidence_packet.

    Consumes the output of collect_evidence(). Returns 60% of the grade
    from COMPUTED signals (no LLM opinion). The LLM controls only 40%.

    Weight allocation (60% total):
        citation_ratio:        30%  — ArangoDB verified/total (most reliable)
        assistant_confidence:  20%  — trained classifier cascade
        lean4_score:            5%  — formal proof bonus (when available)
        bridge_overlap:         5%  — taxonomy intersection
        delta_improvement:      5%  — self-correction signal (additive)

    Lean4 was reduced from 15% because the module import consistently fails
    (qra_reasoning not importable), making it dead weight. Its share moved
    to citation_ratio (+10%) and assistant (+5%) which always work.
    """
    citation_ratio = evidence.get("citation_ratio", 0.0)
    lean4_score = evidence.get("lean4_score", 0.0) or 0.0
    bridge_overlap = min(evidence.get("bridge_overlap_count", 0) / 5.0, 1.0)
    richness = evidence.get("richness_score", 0.0) or 0.0
    delta = evidence.get("delta_improvement", 0.0) or 0.0

    # Assistant classifier: use confidence directly if available, else 0
    assistant = evidence.get("assistant_confidence", 0.0) or 0.0
    # If assistant returned a FAIL result, penalize
    assistant_result = evidence.get("assistant", {}).get("result", {})
    if isinstance(assistant_result, dict) and assistant_result.get("verdict") == "FAIL":
        assistant = max(0.0, assistant * 0.3)  # Heavily penalize FAIL verdict

    # Delta bonus: +0.05 if improved, -0.05 if regressed, 0 otherwise
    delta_bonus = 0.05 if delta > 0.05 else (-0.05 if delta < -0.05 else 0.0)

    # Compute weighted deterministic score
    # Available sources get their full weight; unavailable get 0
    sources_called = evidence.get("sources_called", [])

    # Dynamic weight redistribution based on source availability.
    # Base weights: citation=0.30, assistant=0.20, lean4=0.05, bridge=0.05, richness=0.05
    # When a source is unavailable, its weight goes to citation_ratio (most reliable).
    lean4_unavailable = evidence.get("LEAN4_UNAVAILABLE", False)
    assistant_unavailable = evidence.get("ASSISTANT_UNAVAILABLE", False)

    citation_weight = 0.30
    if lean4_unavailable:
        citation_weight += 0.05  # Absorb lean4's 5%
        _warn_once(
            "lean4_weight_redistributed",
            "LEAN4_UNAVAILABLE: redistributing 0.05 deterministic weight to citation_ratio",
        )
    if assistant_unavailable:
        citation_weight += 0.20  # Absorb assistant's 20%
        _warn_once(
            "assistant_weight_redistributed",
            "ASSISTANT_UNAVAILABLE: redistributing 0.20 deterministic weight to citation_ratio",
        )

    det_score = citation_ratio * citation_weight

    if not lean4_unavailable and "lean4_proof" in sources_called and lean4_score > 0:
        det_score += lean4_score * 0.05
    if not assistant_unavailable and "assistant_classifier" in sources_called:
        det_score += assistant * 0.20

    # Bridge overlap and richness from caller-provided signals
    det_score += bridge_overlap * 0.05
    det_score += richness * 0.05

    det_score += delta_bonus  # Additive, not weighted

    det_score = max(0.0, min(0.60, det_score))

    return {
        "deterministic_score": det_score,
        "citation_ratio": citation_ratio,
        "citation_weight": citation_weight,
        "lean4_score": lean4_score,
        "lean4_unavailable": lean4_unavailable,
        "assistant_confidence": assistant,
        "assistant_unavailable": assistant_unavailable,
        "assistant_tier": evidence.get("assistant_tier", None),
        "bridge_overlap": bridge_overlap,
        "richness_score": richness,
        "delta_bonus": delta_bonus,
        "sources_available": sources_called,
    }


def grade_response_semantic(
    question: str,
    answer: str,
    transcript: str = "",
    qra_source_keys: list | None = None,
    target_control: str = "",
    difficulty: str = "medium",
    expected_action: str = "QUERY",
    model: str = STUDENT_MODEL,
    scope: str = "sparta",
    process_signals: dict | None = None,
    evidence: dict | None = None,
) -> dict:
    """Two-stage grading: deterministic evidence FIRST, LLM qualitative SECOND.

    Stage 1: collect_evidence() gathers hard facts from /memory trace,
             /assistant validate, /lean4-prove, and ArangoDB citations.
             This produces the deterministic anchor (60% of grade).

    Stage 2: LLM receives evidence as read-only context and scores ONLY
             qualitative dimensions (40% of grade): naturalness, domain
             accuracy, coherence, disambiguation.

    The LLM CANNOT override deterministic results. Grade swings are bounded.

    Args:
        evidence: Pre-collected evidence from collect_evidence(). If None,
                  collect_evidence() is called internally. Pass pre-collected
                  evidence to avoid redundant calls in the self-grade loop.
        process_signals: Legacy caller-provided signals (bridge overlap, delta).
                        Merged into evidence if evidence is not pre-collected.
    """
    qra_source_keys = qra_source_keys or []
    process_signals = process_signals or {}

    # ── Stage 1: Collect deterministic evidence ──────────────────────────
    if evidence is None:
        evidence = collect_evidence(
            question=question,
            answer=answer,
            qra_source_keys=qra_source_keys,
            scope=scope,
            process_signals=process_signals,
        )

    # Compute deterministic anchor from evidence (60% of grade)
    anchor = _compute_deterministic_anchor(evidence)
    citation_result = evidence.get("citation", {})

    # Build QRA ground truth for the LLM prompt
    qra_ground_truth = _build_qra_ground_truth(qra_source_keys)

    # ── Stage 2: LLM qualitative assessment (40% of grade) ──────────────
    quick_completion = _get_quick_completion()
    if quick_completion is None:
        logger.warning("scillm unavailable — returning deterministic-only grade")
        return _deterministic_only_grade(anchor, citation_result, model)

    # Format all evidence as read-only context for the LLM
    process_evidence = _format_process_evidence(anchor, evidence)

    # Strip appended evidence section from answer for LLM quality grading.
    # Citation verification already ran on the full text (including evidence).
    # The LLM should only grade the reasoning/analysis part for naturalness.
    answer_for_llm = answer.split("\n\n--- Evidence ---\n")[0] if "\n\n--- Evidence ---\n" in answer else answer

    prompt = SEMANTIC_GRADE_PROMPT.format(
        transcript=transcript[:3000] if transcript else f"Q: {question[:500]}\nA: {answer_for_llm[:500]}",
        question=question[:500],
        answer=answer_for_llm[:1000],
        difficulty=difficulty,
        expected_action=expected_action,
        target_control=target_control or "N/A",
        qra_ground_truth=qra_ground_truth,
        process_evidence=process_evidence,
    )

    try:
        raw = quick_completion(
            prompt=prompt,
            model=model,
            system=(
                "You are a quality auditor for SPARTA space systems. "
                "Score ONLY the qualitative dimensions. Use the full 0.0-1.0 range "
                "with honest calibration. Deterministic signals (citations, proofs, "
                "classifier verdicts, taxonomy) are ALREADY COMPUTED from ArangoDB "
                "lookups, Lean4 formal proofs, and trained classifiers — do NOT "
                "override them. Your role is ONLY to assess naturalness, domain "
                "accuracy, coherence, and disambiguation quality."
            ),
            json_mode=True,
            max_tokens=512,
            temperature=0.1,
            timeout=60,
        )

        logger.debug(f"LLM grader raw text ({len(raw)} chars): {raw[:500]}")
        result = json.loads(raw)
        logger.debug(f"LLM grader parsed keys={list(result.keys())} scores={result.get('scores', 'MISSING')}")

        # Extract LLM qualitative scores (4 core dimensions, 0-3 coarse scale)
        # Fix 4: Normalize from 0-3 integer scale to 0-1 range to reduce variance
        llm_scores = result.get("scores", {})
        qual_dims = ["response_naturalness", "domain_accuracy", "session_coherence", "disambiguation_handling"]
        raw_values = [float(llm_scores.get(d, 1.5)) for d in qual_dims]
        # Normalize: if values are in 0-3 range (coarse scale), divide by 3.
        # If already in 0-1 range (legacy), use as-is.
        qual_values = [v / 3.0 if v > 1.0 else v for v in raw_values]
        llm_qualitative = sum(qual_values) / len(qual_values) * 0.40  # 40% weight

        # Final composite: deterministic anchor (60%) + LLM qualitative (40%)
        composite = anchor["deterministic_score"] + llm_qualitative
        composite = max(0.0, min(1.0, composite))

        # Grade thresholds
        if composite >= 0.90:
            grade = "A+"
        elif composite >= 0.80:
            grade = "A"
        elif composite >= 0.65:
            grade = "B"
        elif composite >= 0.50:
            grade = "C"
        else:
            grade = "F"

        # Build full scores dict (normalize 0-3 coarse scale to 0-1)
        scores = {}
        for d in qual_dims:
            raw = float(llm_scores.get(d, 1.5))
            scores[d] = raw / 3.0 if raw > 1.0 else raw
        # Deterministic dimensions from evidence
        scores["qra_citation_accuracy"] = anchor["citation_ratio"]
        scores["reasoning_chain_soundness"] = anchor["lean4_score"]
        scores["assistant_confidence"] = anchor.get("assistant_confidence", 0.0)
        raw_irq = float(llm_scores.get("initial_response_quality", 1.5))
        scores["initial_response_quality"] = raw_irq / 3.0 if raw_irq > 1.0 else raw_irq
        raw_ed = float(llm_scores.get("error_detection", 1.5))
        scores["error_detection"] = raw_ed / 3.0 if raw_ed > 1.0 else raw_ed
        raw_fuq = float(llm_scores.get("follow_up_quality", 1.5))
        scores["follow_up_quality"] = raw_fuq / 3.0 if raw_fuq > 1.0 else raw_fuq

        logger.debug(
            f"Two-stage grade: {grade} ({composite:.0%}) "
            f"det={anchor['deterministic_score']:.2f} "
            f"(cit={anchor['citation_ratio']:.2f} lean4={anchor['lean4_score']:.2f} "
            f"asst={anchor.get('assistant_confidence', 0):.2f} "
            f"bridge={anchor['bridge_overlap']:.2f} "
            f"delta={anchor['delta_bonus']:+.2f}) "
            f"llm_qual={llm_qualitative:.2f} "
            f"sources={anchor.get('sources_available', [])}"
        )

        return {
            "grade": grade,
            "composite": composite,
            "scores": scores,
            "qra_citations_verified": citation_result.get("verified", 0),
            "qra_citations_total": citation_result.get("total", 0),
            "citation_details": citation_result.get("details", []),
            "rationale": result.get("rationale", ""),
            "model_used": model,
            "reasoning_sound": result.get("reasoning_sound"),
            "taxonomy_correct": result.get("taxonomy_correct"),
            "issues": [],
            "tier": 2,
            "deterministic_anchor": anchor,
            "evidence_sources": evidence.get("sources_called", []),
            "evidence_latency_ms": evidence.get("collection_latency_ms", 0),
        }

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Semantic grading parse failed: {e}, using deterministic-only")
        return _deterministic_only_grade(anchor, citation_result, model)
    except Exception as e:
        logger.warning(f"Semantic grading failed: {e}, using deterministic-only")
        return _deterministic_only_grade(anchor, citation_result, model)


from sparta_stress_test.semantic_grader_prompts import format_process_evidence as _format_process_evidence


