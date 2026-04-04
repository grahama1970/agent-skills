"""Entity extraction, validation, and NLG synthesis for SPARTA conversations.

Contains functions for extracting SPARTA/NIST/CWE/ATT&CK entity IDs from text,
validating them against the knowledge graph, synthesizing ground-truth answers
from QRA content, and reranking QRAs by taxonomy bridge overlap.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

_PROMPT_DIR = Path(__file__).resolve().parent
while _PROMPT_DIR.name != "skills" and _PROMPT_DIR != _PROMPT_DIR.parent:
    _PROMPT_DIR = _PROMPT_DIR.parent
_PROMPT_DIR = _PROMPT_DIR / "prompt-lab" / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' not found at {path}")
    return path.read_text().strip()

from sparta_stress_test.conversation_models import (
    _HAS_QUALITY_UTILS,
)

# Conditional imports
try:
    from sparta_stress_test.response_quality import validate_entities
except ImportError:
    validate_entities = None


# --------------------------------------------------------------------------- #
# Entity extraction and validation
# --------------------------------------------------------------------------- #


def _clean_entity_id(eid: str) -> str:
    """Clean entity ID of common extraction artifacts.

    Fixes: unbalanced parens like 'RA-3(1' → 'RA-3(1)',
    trailing punctuation, whitespace.
    """
    eid = eid.strip().rstrip(".,;:")
    # Fix unbalanced opening paren: RA-3(1 → RA-3(1)
    if "(" in eid and ")" not in eid:
        eid = eid + ")"
    # Strip wrapping parens if entire ID is wrapped: (SV-SP-1) → SV-SP-1
    if eid.startswith("(") and eid.endswith(")") and eid.count("(") == 1:
        eid = eid[1:-1]
    return eid


def _validate_entities_with_parents(entity_ids: List[str], db) -> Dict[str, bool]:
    """Validate entities with parent-ID fallback.

    ATT&CK sub-techniques (T1489.001 -> T1489), ESA variants (ESA-T1489 -> T1489),
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
        elif re.match(r'^[A-Z]{2}-\d+\(\d+\)$', eid):
            # NIST enhancement: RA-3(1) → RA-3
            parent = re.sub(r'\(\d+\)$', '', eid)
        if parent:
            parent_check = validate_entities([parent], db)
            if parent_check.get(parent, False):
                result[eid] = True
                continue
        result[eid] = False
    return result


def _extract_entity_ids(text: str) -> List[str]:
    """Extract SPARTA/NIST/CWE/ATT&CK entity IDs from text via /scillm LLM.

    Uses quick_completion() through the scillm proxy — the same path the
    stress test already uses for grading and synthesis. The LLM understands
    context and can distinguish real entity IDs from truncated or hallucinated
    ones — something regex cannot do with unbounded human text.

    Falls back to regex when scillm is unavailable (offline, rate limited).
    """
    if not text or len(text) < 5:
        return []
    try:
        from batch import quick_completion  # scillm batch module
        import json as _json

        prompt = _load_prompt("sparta_entity_extraction_v1").format(
            text=text[:2000],
        )
        raw = quick_completion(prompt, json_mode=True, timeout=10)
        if raw:
            data = _json.loads(raw) if isinstance(raw, str) else raw
            entities = data.get("entities", [])
            ids = []
            for e in entities:
                if isinstance(e, dict):
                    fw = e.get("framework", "")
                    eid = e.get("id", "")
                    if fw == "TRUNCATED" or not eid:
                        continue  # skip truncated/empty
                    eid = _clean_entity_id(eid)
                    if eid:
                        ids.append(eid)
                elif isinstance(e, str) and e:
                    cleaned = _clean_entity_id(e)
                    if cleaned:
                        ids.append(cleaned)
            if ids:
                return list(dict.fromkeys(ids))
    except Exception as exc:
        logger.debug(f"LLM entity extraction failed, using regex fallback: {exc}")

    # Fallback: regex for when scillm is unavailable
    return _extract_entity_ids_regex(text)


def _extract_entity_ids_regex(text: str) -> List[str]:
    """Regex fallback for entity extraction when /assistant is unavailable."""
    ids = []
    ids.extend(re.findall(r'\b([A-Z]{2,4}-\d{4}(?:\.\d{2})?)\b', text))
    ids.extend(re.findall(r'\b(SV-[A-Z]{2,3}-\d+)\b', text))
    ids.extend(re.findall(r'\b([A-Z]{2}-\d{2,}(?:\(\d+\))?)\b', text))
    ids.extend(re.findall(r'\b(T\d{4}(?:\.\d{3})?)\b', text))
    ids.extend(re.findall(r'\b(CWE-\d+)\b', text))
    ids.extend(re.findall(r'\b(ESA-T\d+)\b', text))
    ids.extend(re.findall(r'\b(D3-[A-Z]+)\b', text))
    ids.extend(re.findall(r'\b(d3f:\w+)\b', text))
    ids.extend(re.findall(r'\b(CM\d{4})\b', text))
    unique = list(dict.fromkeys(ids))
    filtered = []
    for eid in unique:
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
# NLG synthesis (ground-truth only, no LLM rewriting)
# --------------------------------------------------------------------------- #


def _nlg_synthesize(
    question: str,
    target_control: Optional[str],
    qras: List[Dict],
) -> str:
    """Ground-truth QRA synthesis: the answer IS the QRA content.

    NO LLM rewriting. QRA answer fields are already grounded in source text
    with citation chains.
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

        segment = ""
        if control_id:
            segment += f"Regarding {control_id}: "
        segment += answer_text[:500]

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
    """Labeled ground-truth synthesis -- each segment tagged with provenance.

    Tags each part:
    - [QRA-GROUNDED] -- from QRA answer field
    - [GRAPH-INFERRED] -- from relationship graph, not from QRA content
    - [NOT IN CORPUS] -- entities with no QRA coverage
    """
    parts = []

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

        source = q.get("_source", "")
        if source == "memory_control":
            label = "[CONTROL-CONTEXT]"
        elif source == "memory_recall":
            label = "[MEMORY-RECALL]"
        else:
            label = "[QRA-GROUNDED]"

        segment = f"{label} "
        if source == "memory_control":
            ctrl_type = q.get("control_type", "")
            fw = q.get("source_framework", "")
            prefix = f"{control_id}" if control_id else "This control"
            if ctrl_type:
                prefix += f" ({ctrl_type})"
            if fw:
                prefix += f" [{fw}]"
            segment += f"{prefix}: {answer_text[:400]}"
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
# LLM-powered reasoning synthesis
# --------------------------------------------------------------------------- #

_REASONING_SYSTEM = _load_prompt("sparta_reasoning_system_v1")


def _reasoning_synthesize(
    question: str,
    labeled_evidence: str,
    bridges: List[str],
    entities: List[str],
    related_controls: List[str],
) -> str:
    """LLM-powered reasoning synthesis over retrieved evidence.

    Takes the labeled evidence from _labeled_synthesize() and asks the LLM
    to reason about the connections, producing a coherent expert answer.

    Falls back to the raw labeled evidence if the LLM call fails.
    """
    try:
        from sparta_stress_test.conversation_models import _call_scillm
    except ImportError:
        logger.debug("_call_scillm not available, falling back to template synthesis")
        return labeled_evidence

    bridge_str = ", ".join(bridges[:6]) if bridges else "none identified"
    entity_str = ", ".join(entities[:5]) if entities else "none"
    related_str = ", ".join(related_controls[:5]) if related_controls else "none"

    user_prompt = f"""QUESTION: {question}

BRIDGE TAGS: {bridge_str}
ENTITIES: {entity_str}
RELATED CONTROLS: {related_str}

RETRIEVED EVIDENCE:
{labeled_evidence}

Write 3-5 sentences of expert analysis connecting the evidence to the question.
QUOTE exact phrases from the evidence — do NOT paraphrase. Keep all control IDs and provenance labels."""

    try:
        raw = _call_scillm(
            system=_REASONING_SYSTEM,
            user_prompt=user_prompt,
            max_tokens=512,
            json_mode=False,
        )

        if raw and len(raw.strip()) > 30:
            # Prepend reasoning, then append full labeled evidence for citation verification
            reasoning = raw.strip()
            logger.debug(f"LLM reasoning synthesis: {len(reasoning)} chars")
            return f"{reasoning}\n\n--- Evidence ---\n{labeled_evidence}"
        else:
            logger.debug("LLM reasoning synthesis returned empty/short, using template")
            return labeled_evidence

    except Exception as e:
        logger.debug(f"LLM reasoning synthesis failed: {e}, using template")
        return labeled_evidence


def _rerank_by_bridge_overlap(
    qras: List[Dict],
    question_bridges: List[str],
) -> List[Dict]:
    """Rerank QRAs by taxonomy bridge intersection with the question.

    QRAs whose conceptual_tags overlap most with the question's bridge
    attributes float to the top. Ties broken by grounding_score.
    Controls (_source=memory_control) sort last.
    """
    if not question_bridges or not qras:
        return qras

    bridge_set = {b.lower() for b in question_bridges}

    def _score(qra: Dict) -> tuple:
        entity_cov = -(qra.get("_entity_coverage", 0))
        is_control = 1 if qra.get("_source") == "memory_control" else 0
        tags = qra.get("conceptual_tags") or []
        tag_set = {t.lower() for t in tags} if tags else set()
        overlap = len(bridge_set & tag_set)
        grounding = float(qra.get("grounding_score", 0))
        return (entity_cov, is_control, -overlap, -grounding)

    return sorted(qras, key=_score)
