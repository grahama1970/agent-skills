"""Retrieval, entity extraction, Tier 1 lookup, and response building for SPARTA.

Handles the full retrieval pipeline: entity extraction, Tier 1 fast lookup,
NLG synthesis, query planning, steering, and skill chain routing.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import find_dotenv, load_dotenv
from loguru import logger

load_dotenv(find_dotenv(usecwd=True))

from sparta_stress_test.models import (
    PI_MONO_SKILLS,
    SKILL_SLASH_PATTERN,
    Tier1Result,
)
from sparta_stress_test.prompts import QUERY_PLAN_PROMPT

# Ensure graph_memory is importable
_src_path = str(Path(__file__).resolve().parents[4] / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# scillm path
_scillm_path = str(
    Path(__file__).resolve().parents[4].parent
    / "pi-mono"
    / ".pi"
    / "skills"
    / "scillm"
)
if _scillm_path not in sys.path:
    sys.path.insert(0, _scillm_path)

# Response quality utilities (entity extraction/validation only — keyword scanning BANNED)
try:
    from sparta_stress_test.response_quality import (
        validate_entities,
        extract_entities,
    )
    _HAS_QUALITY_UTILS = True
except ImportError:
    _HAS_QUALITY_UTILS = False

# /assistant cascade (Tier 0 → 0.5 → 2 GPT rationale)
try:
    _assistant_path = str(PI_MONO_SKILLS / "assistant")
    if _assistant_path not in sys.path:
        sys.path.insert(0, _assistant_path)
    from assistant import classify as _assistant_classify
    _HAS_ASSISTANT = True
except ImportError:
    _HAS_ASSISTANT = False

# ControlCatalog from /extract-controls (Tier 1 fast lookup)
_BACKFILL_SCRIPT = str(
    Path(__file__).resolve().parents[4]
    / "scripts"
    / "backfill_chunk_control_edges.py"
)
try:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("backfill_chunk_control_edges", _BACKFILL_SCRIPT)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    ControlCatalog = _mod.ControlCatalog
    extract_candidates = _mod.extract_candidates
    _HAS_CONTROL_CATALOG = True
except Exception:
    _HAS_CONTROL_CATALOG = False


# --------------------------------------------------------------------------- #
# LLM helpers
# --------------------------------------------------------------------------- #


def _call_scillm(system: str, user_prompt: str, max_tokens: int = 1024) -> str:
    """Call /scillm via batch.quick_completion (the skill's programmatic API).

    Uses CHUTES_API_BASE/CHUTES_API_KEY/CHUTES_MODEL_ID from .env.
    Has built-in Chutes error hook (503 → OpenRouter fallback).
    """
    try:
        from batch import quick_completion
    except ImportError:
        logger.warning("/scillm batch.quick_completion not importable")
        return "{}"

    return quick_completion(
        prompt=user_prompt,
        system=system,
        json_mode=True,
        max_tokens=max_tokens,
        temperature=0.4,
        timeout=60,
    )


def _get_db() -> Any:
    from graph_memory.arango_client import get_db

    return get_db()


# --------------------------------------------------------------------------- #
# Entity extraction and validation
# --------------------------------------------------------------------------- #


def _validate_entities_with_parents(entity_ids: List[str], db) -> Dict[str, bool]:
    """Validate entities with parent-ID fallback.

    ATT&CK sub-techniques (T1489.001 → T1489), ESA variants (ESA-T1489 → T1489),
    and d3f: namespace references are checked against parent IDs when the exact
    ID isn't found.
    """
    if not _HAS_QUALITY_UTILS or not entity_ids:
        return {e: True for e in entity_ids}

    validity = validate_entities(entity_ids, db)
    result = {}
    for eid in entity_ids:
        if validity.get(eid, True):
            result[eid] = True
            continue
        # Check parent IDs
        parent = None
        if re.match(r'^T\d{4}\.\d{3}$', eid):
            parent = eid.split('.')[0]
        elif re.match(r'^ESA-T\d+', eid):
            parent = eid.replace('ESA-', '')
        elif eid.startswith('d3f:'):
            result[eid] = True  # Accept d3f: namespace refs
            continue
        if parent:
            parent_check = validate_entities([parent], db)
            if parent_check.get(parent, False):
                result[eid] = True
                continue
        result[eid] = False
    return result


def _extract_entity_ids(text: str) -> List[str]:
    """Extract SPARTA/NIST/CWE/ATT&CK entity IDs from text using regex.

    Matches the same patterns as /sparta-intent entity extraction.
    """
    ids = []
    # SPARTA native controls: SV-SP-1, REC-0008.03, DE-0010, etc.
    ids.extend(re.findall(r'\b([A-Z]{2,4}-\d{4}(?:\.\d{2})?)\b', text))
    ids.extend(re.findall(r'\b(SV-[A-Z]{2,3}-\d+)\b', text))
    # NIST SP 800-53 style: AU-6, IA-5, SI-4, AC-2(12), etc.
    ids.extend(re.findall(r'\b([A-Z]{2}-\d+(?:\(\d+\))?)\b', text))
    # ATT&CK: T1548.004, T1134, etc.
    ids.extend(re.findall(r'\b(T\d{4}(?:\.\d{3})?)\b', text))
    # CWE: CWE-1089, CWE-26, etc.
    ids.extend(re.findall(r'\b(CWE-\d+)\b', text))
    # ESA: ESA-T2040
    ids.extend(re.findall(r'\b(ESA-T\d+)\b', text))
    # D3FEND: D3-DENCR, d3f:ExceptionHandler
    ids.extend(re.findall(r'\b(D3-[A-Z]+)\b', text))
    ids.extend(re.findall(r'\b(d3f:\w+)\b', text))
    # CM countermeasures: CM0008, CM0042
    ids.extend(re.findall(r'\b(CM\d{4})\b', text))

    # Dedupe: if a short ID (e.g. "AV-5") is a suffix of a longer ID
    # already extracted (e.g. "SV-AV-5"), drop the short one.
    # Same for "WE-1089" inside "CWE-1089".
    unique = list(dict.fromkeys(ids))
    filtered = []
    for eid in unique:
        # Check if this ID is a suffix of any longer ID in the list
        is_suffix = any(
            longer.endswith("-" + eid) or longer.endswith(eid)
            for longer in unique
            if len(longer) > len(eid) and longer != eid
        )
        if not is_suffix:
            filtered.append(eid)
    return filtered


def _extract_keywords(text: str) -> List[str]:
    """Extract BM25-quality keywords from question text.

    Filters stopwords and short words, returns top meaningful terms.
    """
    STOPWORDS = {
        "the", "and", "for", "that", "this", "with", "from", "are", "was",
        "were", "been", "have", "has", "had", "does", "did", "will", "would",
        "could", "should", "may", "might", "can", "shall", "about", "into",
        "through", "during", "before", "after", "above", "below", "between",
        "under", "over", "which", "what", "where", "when", "how", "why",
        "who", "whom", "there", "here", "than", "then", "also", "just",
        "more", "most", "some", "such", "only", "very", "well", "much",
        "being", "each", "other", "these", "those", "their", "your",
        "specific", "ensure", "address", "related", "provide", "given",
    }
    words = []
    for w in text.split():
        clean = w.strip(".,;:!?()[]{}\"'").lower()
        if len(clean) > 2 and clean not in STOPWORDS:
            words.append(clean)
    return words[:15]


# --------------------------------------------------------------------------- #
# NLG synthesis (ground-truth only, NO LLM rewriting)
# --------------------------------------------------------------------------- #


def _nlg_synthesize(
    question: str,
    target_control: Optional[str],
    qras: List[Dict],
) -> str:
    """Ground-truth QRA synthesis: the answer IS the QRA content.

    NO LLM rewriting. The whole point of generating QRAs in /memory is to
    prevent hallucination from next-word prediction. The QRA answer fields
    are already grounded in source text with citation chains.

    The LLM synthesis step was removed because it was the source of
    hallucinated controls (e.g. CM0062) — the LLM added entities that
    weren't in any QRA during "natural language synthesis."

    Format: control ID + QRA answer text, joined with transitions.
    """
    if not qras:
        return "I don't have specific QRA coverage for that query."

    parts = []
    for q in qras:
        control_id = q.get("control_id", "")
        answer_text = q.get("answer", "").strip()
        if not answer_text:
            continue

        techniques = q.get("sparta_techniques") or []
        countermeasures = q.get("sparta_countermeasures") or []

        # Build grounded response segment from QRA fields only
        segment = ""
        if control_id:
            segment += f"Regarding {control_id}: "
        segment += answer_text[:500]

        # Append technique/countermeasure IDs if present in QRA
        tech_ids = [
            (t.get("id", "") if isinstance(t, dict) else str(t))
            for t in techniques if t
        ]
        cm_ids = [
            (c.get("id", "") if isinstance(c, dict) else str(c))
            for c in countermeasures if c
        ]
        if tech_ids:
            segment += f" (Techniques: {', '.join(tech_ids[:5])})"
        if cm_ids:
            segment += f" (Countermeasures: {', '.join(cm_ids[:5])})"

        parts.append(segment)

    if not parts:
        return "I found QRA entries but none contained relevant answer text for your question."

    return "\n\n".join(parts)


def _labeled_synthesize(
    question: str,
    target_control: Optional[str],
    qras: List[Dict],
    related_controls: List[str],
    entities: List[str],
) -> str:
    """Labeled ground-truth synthesis — each segment tagged with provenance.

    Replaces _nlg_synthesize. NO LLM rewriting. Tags each part:
    - [QRA-GROUNDED] — from QRA answer field
    - [GRAPH-INFERRED] — from relationship graph, not from QRA content
    - [NOT IN CORPUS] — entities with no QRA coverage
    """
    parts = []

    # QRA-grounded and memory-recall segments
    covered_entities = set()
    for q in qras:
        control_id = q.get("control_id", "")
        answer_text = q.get("answer", "").strip()
        if not answer_text:
            continue
        if control_id:
            covered_entities.add(control_id)

        techniques = q.get("sparta_techniques") or []
        countermeasures = q.get("sparta_countermeasures") or []

        # Tag based on source for provenance transparency
        source = q.get("_source", "")
        if source == "memory_control":
            label = "[CONTROL-CONTEXT]"
        elif source == "memory_recall":
            label = "[MEMORY-RECALL]"
        else:
            label = "[QRA-GROUNDED]"

        segment = f"{label} "
        if source == "memory_control":
            # Control items provide definitional context, not QRA answers
            ctrl_type = q.get("control_type", "")
            fw = q.get("source_framework", "")
            prefix = f"{control_id}" if control_id else "This control"
            if ctrl_type:
                prefix += f" ({ctrl_type})"
            if fw:
                prefix += f" [{fw}]"
            segment += f"{prefix}: {answer_text[:400]}"
            # Include referencing chunk previews if available
            chunks = q.get("referencing_chunks", [])
            if chunks:
                previews = [c.get("text_preview", "")[:100] for c in chunks[:2] if c.get("text_preview")]
                if previews:
                    segment += " Evidence: " + " | ".join(previews)
        else:
            if control_id:
                segment += f"Regarding {control_id}: "
            segment += answer_text[:700]

        tech_ids = [
            (t.get("id", "") if isinstance(t, dict) else str(t))
            for t in techniques if t
        ]
        cm_ids = [
            (c.get("id", "") if isinstance(c, dict) else str(c))
            for c in countermeasures if c
        ]
        if tech_ids:
            segment += f" (Techniques: {', '.join(tech_ids[:5])})"
        if cm_ids:
            segment += f" (Countermeasures: {', '.join(cm_ids[:5])})"

        parts.append(segment)

    # Graph-inferred segments for related controls not in QRA results
    if related_controls:
        graph_only = [rc for rc in related_controls if rc not in covered_entities]
        if graph_only:
            parts.append(
                f"[GRAPH-INFERRED] Note: I'm inferring a connection here — "
                f"no single QRA covers this directly. "
                f"{', '.join(entities[:3] if entities else ['This topic'])} "
                f"is connected to {', '.join(graph_only[:5])} in the SPARTA "
                f"relationship graph, which suggests related mitigations."
            )

    # Not-in-corpus segments for entities with no QRAs
    if entities:
        uncovered = [e for e in entities if e not in covered_entities]
        if uncovered:
            parts.append(
                f"[NOT IN CORPUS] I don't have blessed QRA coverage for "
                f"{', '.join(uncovered[:3])}. I'd need to consult the SPARTA "
                f"controls and dataset directly to answer this — any response "
                f"would be my inference, not a vetted answer."
            )

    if not parts:
        return "I found QRA entries but none contained relevant answer text for your question."

    return "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# Response building helpers
# --------------------------------------------------------------------------- #


def _build_clarify_response(
    clarify_result: dict,
    question: str,
    target_control: Optional[str],
    db,
) -> Dict:
    """Convert _clarify_direct() output into a Brandon-voice CLARIFY response.

    Uses clarify diagnostics to pick the right tone — Brandon is direct,
    technical, and collaborative. He tells Margaret what he CAN'T find and
    suggests what he CAN look up.
    """
    diag = clarify_result.get("diagnostics", {})
    questions = clarify_result.get("clarify_questions", [])
    first_q = questions[0]["question"] if questions else ""

    if diag.get("entities_without_qras"):
        ents = diag["entities_without_qras"]
        # Try Levenshtein nearest neighbor for each unknown entity
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

    Different from pre-retrieval clarify — Brandon has actually searched and
    can report what he tried and what related info exists.
    """
    parts = []

    if entities:
        # Report what we looked for
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
    """Structured options response — when Brandon has 2-3 specific controls to ask about.

    Uses /interview format instead of free-text clarify.
    """
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


def _rerank_by_bridge_overlap(
    qras: List[Dict],
    question_bridges: List[str],
) -> List[Dict]:
    """Rerank QRAs by taxonomy bridge intersection with the question.

    QRAs whose conceptual_tags overlap most with the question's bridge
    attributes float to the top. Ties broken by grounding_score.
    Controls (_source=memory_control) sort last — they provide context,
    not answers.
    """
    if not question_bridges or not qras:
        return qras

    bridge_set = {b.lower() for b in question_bridges}

    def _score(qra: Dict) -> tuple:
        # 1. Entity coverage: QRAs mentioning more question entities first
        entity_cov = -(qra.get("_entity_coverage", 0))
        # 2. Controls always sort after QRAs
        is_control = 1 if qra.get("_source") == "memory_control" else 0
        # 3. Taxonomy bridge overlap
        tags = qra.get("conceptual_tags") or []
        tag_set = {t.lower() for t in tags} if tags else set()
        overlap = len(bridge_set & tag_set)
        grounding = float(qra.get("grounding_score", 0))
        # Sort: entity coverage DESC, controls last, bridge overlap DESC, grounding DESC
        return (entity_cov, is_control, -overlap, -grounding)

    return sorted(qras, key=_score)


# --------------------------------------------------------------------------- #
# Tier 1: Fast exact lookup (runs BEFORE any LLM call, every turn)
# --------------------------------------------------------------------------- #

# Module-level ControlCatalog singleton (loaded once, reused across turns)
_control_catalog: Optional[Any] = None
_catalog_loaded: bool = False


def _get_control_catalog(db) -> Any:
    """Lazy-load ControlCatalog singleton from /extract-controls."""
    global _control_catalog, _catalog_loaded
    if _catalog_loaded:
        return _control_catalog
    _catalog_loaded = True
    if not _HAS_CONTROL_CATALOG:
        logger.debug("ControlCatalog not available — /extract-controls not importable")
        return None
    try:
        cat = ControlCatalog()
        n = cat.load_from_db(db)
        logger.info(f"ControlCatalog loaded: {n} controls")
        _control_catalog = cat
        return cat
    except Exception as e:
        logger.warning(f"ControlCatalog load failed: {e}")
        return None


def _detect_explicit_skills(text: str) -> List[str]:
    """Extract /skill-name commands from text. Zero ambiguity — direct dispatch."""
    return SKILL_SLASH_PATTERN.findall(text)


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
        # Fallback: individual queries
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


def _graph_neighbors_with_qras(entity_ids: List[str], db) -> List[str]:
    """Find controls connected to entity_ids via relationship graph that have QRAs."""
    neighbors: List[str] = []
    if not entity_ids:
        return neighbors
    try:
        cursor = db.aql.execute(
            """FOR cid IN @cids
                 FOR rel IN sparta_relationships
                   FILTER rel.source_control_id == cid OR rel.target_control_id == cid
                   FILTER rel.relationship_type IN ["related_to", "mitigates", "implements"]
                   LET neighbor = rel.source_control_id == cid ? rel.target_control_id : rel.source_control_id
                   LET has_qra = LENGTH(FOR q IN sparta_qra FILTER q.control_id == neighbor LIMIT 1 RETURN 1) > 0
                   FILTER has_qra
                   RETURN DISTINCT neighbor""",
            bind_vars={"cids": entity_ids[:5]},
        )
        neighbors = list(cursor)
    except Exception as e:
        logger.debug(f"Graph neighbor query failed: {e}")
    return neighbors[:10]


def _skill_suggest_via_memory(question_text: str) -> List[str]:
    """Use /memory recall against skill_descriptions to find matching skills."""
    try:
        from graph_memory.api import MemoryClient
        mc = MemoryClient(scope="sparta", k=5)
        result = mc.recall(
            q=question_text, k=5,
            collections=["skill_descriptions"],
        )
        skills = []
        for item in result.get("items", []):
            name = item.get("name") or item.get("skill_name") or ""
            if name and name not in skills:
                skills.append(name)
        return skills[:3]
    except Exception as e:
        logger.debug(f"Skill suggestion via /memory failed: {e}")
        return []


def _tier1_lookup(
    question_text: str,
    target_control: Optional[str] = None,
    db: Optional[Any] = None,
) -> Tier1Result:
    """Tier 1 fast classification — runs BEFORE any LLM call, every turn.

    Uses ControlCatalog from /extract-controls for O(1) exact match + fuzzy.
    Returns classification + routing metadata for _sparta_answer().
    """
    if db is None:
        db = _get_db()

    # Step 0: Check for explicit /slash commands (highest priority)
    explicit_skills = _detect_explicit_skills(question_text)
    if explicit_skills:
        return Tier1Result(
            classification="SKILL_INVOKE",
            skill_refs=explicit_skills,
            skill_explicit=True,
        )

    # Step 1: Extract entity IDs from question text
    entities = _extract_entity_ids(question_text)
    if target_control and target_control not in entities:
        entities.insert(0, target_control)

    # Step 2: Validate entities via ControlCatalog (fast, in-memory)
    catalog = _get_control_catalog(db)
    valid_entities: List[str] = []
    unknown_entities: List[str] = []
    fuzzy_matches: Dict[str, List[str]] = {}

    if catalog and entities:
        for eid in entities:
            resolved = catalog.resolve(eid)
            if resolved:
                cid, _key, confidence, method = resolved
                valid_entities.append(cid)
            else:
                unknown_entities.append(eid)
                # Try fuzzy with lower threshold for suggestions
                fuzzy = catalog.resolve(eid, threshold=70)
                if fuzzy:
                    fuzzy_matches[eid] = [fuzzy[0]]
    elif entities:
        # Fallback: use existing _validate_entities_with_parents
        if _HAS_QUALITY_UTILS:
            validity = _validate_entities_with_parents(entities, db)
            valid_entities = [e for e in entities if validity.get(e, True)]
            unknown_entities = [e for e in entities if not validity.get(e, True)]
        else:
            valid_entities = entities  # Assume valid if no validation available

    # Step 3: Count QRAs for valid entities
    qra_counts = _qra_count_for_entities(valid_entities, db) if valid_entities else {}

    # Step 4: If some entities have QRAs but others don't, get graph neighbors
    graph_neighbors: List[str] = []
    entities_without_qras = [e for e in valid_entities if qra_counts.get(e, 0) == 0]
    if entities_without_qras:
        graph_neighbors = _graph_neighbors_with_qras(entities_without_qras, db)

    # Step 5: Classify
    if not entities:
        # No control IDs detected — check for implicit skill trigger
        skill_hits = _skill_suggest_via_memory(question_text)
        if skill_hits:
            return Tier1Result(
                classification="SKILL_SUGGEST",
                skill_refs=skill_hits,
                skill_explicit=False,
            )
        return Tier1Result(classification="NO_ENTITIES")

    if unknown_entities and not valid_entities:
        return Tier1Result(
            classification="UNKNOWN_ENTITY",
            unknown_entities=unknown_entities,
            fuzzy_matches=fuzzy_matches,
        )

    has_qras = any(qra_counts.get(e, 0) > 0 for e in valid_entities)
    if has_qras:
        steer_toward = None
        if entities_without_qras and graph_neighbors:
            steer_toward = graph_neighbors[0]
        return Tier1Result(
            classification="HAS_QRAS",
            valid_entities=valid_entities,
            qra_counts=qra_counts,
            unknown_entities=unknown_entities,
            fuzzy_matches=fuzzy_matches,
            graph_neighbors=graph_neighbors,
            steer_toward=steer_toward,
        )

    # All valid entities exist but zero QRAs
    return Tier1Result(
        classification="CONTROL_ONLY",
        valid_entities=valid_entities,
        qra_counts=qra_counts,
        graph_neighbors=graph_neighbors,
        steer_toward=graph_neighbors[0] if graph_neighbors else None,
    )


# --------------------------------------------------------------------------- #
# Re-export routing functions for backwards compatibility
# --------------------------------------------------------------------------- #

from sparta_stress_test.routing import (  # noqa: F401, E402
    _execute_skill_chain,
    _plan_query_heuristic,
    _plan_query_strategy,
    _steer_control_only,
    _steer_unknown_entity,
    _suggest_skill,
)
