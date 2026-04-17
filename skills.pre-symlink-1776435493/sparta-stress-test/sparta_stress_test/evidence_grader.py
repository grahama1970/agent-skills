"""Evidence-based grading for SPARTA stress test shadow comparison.

Replaces subjective A/B/C/F LLM grading with deterministic 4-state
evidence assessment: Pass, Ambiguous, Fail, Absurd.

Decision tree (zero LLM calls, ~800ms total):
  1. /extract-entities → grounding_ok, fabricated_id warnings  (~200ms)
  2. /memory recall → QRA coverage per component               (~500ms)
  3. Technique bridge → tactical_tags overlap                   (~0ms)
  4. /lean4-prove → does the compliance claim compile?          (~100ms warm)

Grade mapping:
  Absurd    — fabricated entity IDs or framework misspellings
  Fail      — grounding fails OR no QRAs match the question
  Ambiguous — partial grounding, components don't bridge, or proof fails
  Pass      — grounded, QRAs found, technique bridge holds, proof OK/skipped
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger


# 4-state evidence vocabulary
EVIDENCE_GRADES = ("Pass", "Ambiguous", "Fail", "Absurd")
EVIDENCE_GRADE_ORDER = {"Pass": 0, "Ambiguous": 1, "Fail": 2, "Absurd": 3}

# Minimum QRAs needed for a question to be considered "covered"
MIN_QRA_COVERAGE = 2

# Minimum technique groups that must overlap for bridge confirmation
MIN_TECHNIQUE_BRIDGE = 1


@dataclass
class EvidenceResult:
    """Result of evidence-based grading."""

    grade: str = "Fail"
    grounding_ok: bool = False
    fabricated_ids: List[str] = field(default_factory=list)
    qra_count: int = 0
    technique_groups: Dict[str, int] = field(default_factory=dict)
    technique_bridge: bool = False
    lean4_compiled: Optional[bool] = None  # None = skipped/unavailable
    lean4_steps_verified: int = 0
    lean4_steps_total: int = 0
    signals: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "grade": self.grade,
            "grounding_ok": self.grounding_ok,
            "fabricated_ids": self.fabricated_ids,
            "qra_count": self.qra_count,
            "technique_groups": self.technique_groups,
            "technique_bridge": self.technique_bridge,
            "lean4_compiled": self.lean4_compiled,
            "lean4_steps_verified": self.lean4_steps_verified,
            "lean4_steps_total": self.lean4_steps_total,
        }


def evidence_grades_agree(grade_a: str, grade_b: str) -> bool:
    """Exact match agreement for evidence-based grades.

    Unlike fuzzy A/B/C/F agreement, evidence grades are deterministic
    categories with clear boundaries — exact match is correct.
    """
    return grade_a == grade_b


def grade_evidence(
    question: str,
    answer: str,
    target_control: str = "",
    difficulty: str = "medium",
    skip_lean4: bool = False,
) -> EvidenceResult:
    """Grade a question+answer pair using deterministic evidence signals.

    Returns an EvidenceResult with one of: Pass, Ambiguous, Fail, Absurd.
    Total latency ~800ms (no LLM calls).
    """
    result = EvidenceResult()

    # --- Step 1: Entity extraction + grounding check (~200ms) ---
    entities = _collect_entities(question)
    if entities:
        result.grounding_ok = entities.get("grounding_ok", False)
        result.fabricated_ids = [
            w["term"] for w in entities.get("warnings", [])
            if w.get("category") == "fabricated_id"
        ]
        result.signals["entity_method"] = entities.get("method", "unknown")
        result.signals["n_controls"] = len(entities.get("controls", []))
        result.signals["n_warnings"] = len(entities.get("warnings", []))

    # --- Step 2: QRA recall (~500ms) ---
    # Use extracted controls for targeted search (not blind BM25)
    extracted_controls = []
    if entities:
        extracted_controls = [
            c.get("id", c) if isinstance(c, dict) else c
            for c in entities.get("controls", [])
        ]
    qra_items = _collect_recall(question, extracted_controls=extracted_controls)
    result.qra_count = len(qra_items)

    # --- Step 3: Technique bridge (~0ms) ---
    result.technique_groups = _group_by_technique(qra_items)
    result.technique_bridge = len(result.technique_groups) >= MIN_TECHNIQUE_BRIDGE

    # --- Step 4: Lean4 formal verification (~100ms warm) ---
    if not skip_lean4 and result.qra_count > 0:
        lean4 = _try_lean4(answer, result.qra_count)
        if lean4 is not None:
            result.lean4_compiled = lean4["score"] > 0.0
            result.lean4_steps_verified = lean4.get("steps_verified", 0)
            result.lean4_steps_total = lean4.get("steps_total", 0)

    # --- Decision tree ---
    if result.fabricated_ids:
        result.grade = "Absurd"
    elif not result.grounding_ok and result.qra_count == 0:
        result.grade = "Fail"
    elif result.qra_count < MIN_QRA_COVERAGE:
        result.grade = "Fail"
    elif not result.technique_bridge:
        result.grade = "Ambiguous"
    elif result.lean4_compiled is False:
        # Formalizable claim that failed proof — evidence gap
        result.grade = "Ambiguous"
    else:
        # grounding OK, QRAs found, technique bridge holds,
        # proof succeeded or was skipped (not formalizable)
        result.grade = "Pass"

    return result


# ---------------------------------------------------------------------------
# Data collection (direct imports, no subprocess overhead)
# ---------------------------------------------------------------------------


def _collect_entities(question: str) -> Optional[dict]:
    """Extract entities via direct import, with ArangoDB fallback (~200ms)."""
    # Tier 1: Full entity extraction via graph_memory
    try:
        from graph_memory.entity_extraction import extract_entities
        result = extract_entities(question[:500])
        agent_dict = result.agent_view()
        full_dict = result.to_dict()
        agent_dict["controls"] = agent_dict.get("controls", [])
        agent_dict["warnings"] = agent_dict.get("warnings", [])
        agent_dict["related_pairs"] = full_dict.get("related_pairs", [])
        return agent_dict
    except Exception as exc:
        logger.debug(f"graph_memory entity extraction unavailable: {exc}")

    # Tier 2: Regex + ArangoDB validation fallback
    return _extract_entities_fallback(question)


import re

# Regex for SPARTA-style control IDs: SV-XX-N, SV-XXX-N, etc.
_CONTROL_ID_RE = re.compile(r"\b(SV-[A-Z]{2,4}-\d{1,3})\b", re.IGNORECASE)

# Regex for framework misspellings (common fabrication signal)
_MISSPELLING_RE = re.compile(
    r"\b(SPRTA|SPATRTA|SPARTTA|SPARTS|DSIFEND|D4FEND|CISSA|NIST\s*900)\b",
    re.IGNORECASE,
)


def _extract_entities_fallback(question: str) -> Optional[dict]:
    """Lightweight entity extraction using regex + ArangoDB validation.

    Falls back to this when graph_memory is not importable.
    Detects control IDs via regex and validates against sparta_controls.
    """
    result: dict = {
        "controls": [],
        "warnings": [],
        "grounding_ok": False,
        "method": "regex_fallback",
    }

    # Check for framework misspellings (strong fabrication signal)
    misspellings = _MISSPELLING_RE.findall(question)
    for ms in misspellings:
        result["warnings"].append({"term": ms, "category": "fabricated_id"})

    # Extract control IDs from question
    candidate_ids = _CONTROL_ID_RE.findall(question)
    if not candidate_ids:
        return result

    # Validate against ArangoDB sparta_controls
    try:
        from arango import ArangoClient
        client = ArangoClient(hosts=os.getenv("ARANGO_URL", "http://127.0.0.1:8529"))
        db = client.db(
            os.getenv("ARANGO_DB", "memory"),
            username=os.getenv("ARANGO_USER", "root"),
            password=os.getenv("ARANGO_PASS", "openSesame"),
        )
        # Normalize to uppercase for comparison
        normalized = [cid.upper() for cid in candidate_ids]
        aql = """
        FOR doc IN sparta_controls
        FILTER doc.control_id IN @ids
        RETURN doc.control_id
        """
        valid_ids = set(db.aql.execute(aql, bind_vars={"ids": normalized}))

        for cid in normalized:
            if cid in valid_ids:
                result["controls"].append({"id": cid})
            else:
                result["warnings"].append({"term": cid, "category": "fabricated_id"})

        result["grounding_ok"] = len(result["controls"]) > 0

    except Exception as exc:
        logger.debug(f"ArangoDB control validation failed: {exc}")
        # If DB unavailable, still flag obvious fabrications
        # (ZZ, XX, QQ, etc. are not valid SPARTA sub-families)
        _INVALID_FAMILIES = {"ZZ", "XX", "QQ", "WW", "YY", "JJ", "KK", "LL",
                             "MM", "NN", "PP", "RR", "SS", "TT", "UU", "VV",
                             "FF", "GG", "HH", "AB", "00"}
        for cid in candidate_ids:
            parts = cid.upper().split("-")
            if len(parts) >= 2 and parts[1] in _INVALID_FAMILIES:
                result["warnings"].append({"term": cid, "category": "fabricated_id"})

    return result


def _collect_recall(
    question: str,
    k: int = 15,
    extracted_controls: list[str] | None = None,
    min_bm25_score: float = 22.0,
) -> list[dict]:
    """Recall QRAs via ArangoDB BM25 search with relevance filtering.

    Two-tier approach:
      1. If entity extraction found valid controls, search by control_id (precise)
      2. Fall back to BM25 text search with minimum score threshold (broad)

    The min_bm25_score threshold (default 22.0) filters out noise:
      - Relevant SPARTA queries score 25-35
      - Irrelevant queries (WordPress, pizza) score 18-21
      - Ambiguous/borderline queries score 21-25
    """
    items: list[dict] = []

    try:
        from arango import ArangoClient
        client = ArangoClient(hosts=os.getenv("ARANGO_URL", "http://127.0.0.1:8529"))
        db = client.db(
            os.getenv("ARANGO_DB", "memory"),
            username=os.getenv("ARANGO_USER", "root"),
            password=os.getenv("ARANGO_PASS", "openSesame"),
        )

        # Tier 1: Targeted control_id lookup (if entities found controls)
        if extracted_controls:
            aql_control = """
            FOR doc IN sparta_qra
            FILTER doc.control_id IN @controls
            LIMIT @k
            RETURN {
                _key: doc._key,
                question: doc.question,
                answer: doc.answer,
                control_id: doc.control_id,
                tactical_tags: doc.tactical_tags,
                score: 100.0
            }
            """
            for item in db.aql.execute(aql_control, bind_vars={
                "controls": extracted_controls[:10],
                "k": k,
            }):
                items.append(item)

        # Tier 2: BM25 text search with score threshold
        if len(items) < MIN_QRA_COVERAGE:
            aql_bm25 = """
            FOR doc IN sparta_qra_search
            SEARCH ANALYZER(
                doc.question IN TOKENS(@query, 'text_en') OR
                doc.answer IN TOKENS(@query, 'text_en'),
                'text_en'
            )
            LET bm25 = BM25(doc)
            FILTER bm25 >= @min_score
            SORT bm25 DESC
            LIMIT @k
            RETURN {
                _key: doc._key,
                question: doc.question,
                answer: doc.answer,
                control_id: doc.control_id,
                tactical_tags: doc.tactical_tags,
                score: bm25
            }
            """
            seen = {item.get("_key") for item in items}
            for item in db.aql.execute(aql_bm25, bind_vars={
                "query": question[:400],
                "min_score": min_bm25_score,
                "k": k,
            }):
                if item.get("_key") not in seen:
                    seen.add(item["_key"])
                    items.append(item)

    except Exception as exc:
        logger.debug(f"ArangoDB QRA search failed: {exc}")

    # Filter out meta/empty items
    return [
        item for item in items
        if len(item.get("answer", item.get("solution", item.get("text", "")))) > 20
    ]


def _group_by_technique(items: list[dict]) -> dict[str, int]:
    """Group QRA items by tactical_tags, return technique → count."""
    groups: dict[str, int] = {}
    for item in items:
        tags = item.get("tactical_tags", [])
        if tags and isinstance(tags, list):
            for tag in tags:
                if tag:
                    groups[tag] = groups.get(tag, 0) + 1
    return groups


def _try_lean4(answer_text: str, qra_count: int) -> Optional[dict]:
    """Attempt Lean4 formal verification (~100ms warm Docker)."""
    if qra_count == 0:
        return None

    lean4_url = os.getenv("LEAN4_SERVICE_URL", "http://localhost:8604")

    try:
        import httpx
        health = httpx.get(f"{lean4_url}/health", timeout=2.0)
        if health.status_code != 200:
            return None
    except Exception:
        return None

    try:
        import sys
        from pathlib import Path
        lean4_skill = Path(__file__).resolve().parents[1] / "lean4-prove"
        if str(lean4_skill) not in sys.path:
            sys.path.insert(0, str(lean4_skill))

        from qra_reasoning import verify_qra_reasoning
        result = verify_qra_reasoning(
            {"reasoning": answer_text, "qra_id": "evidence_grader"},
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
        }
    except Exception as e:
        logger.debug(f"Lean4 verification failed: {e}")
        return None
