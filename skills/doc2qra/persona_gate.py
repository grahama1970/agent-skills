"""Persona-driven QRA quality gate for doc2qra.

Provides:
- select_persona(): auto-select best persona from monitor-personas registry
- select_persona_by_bridges(): route via taxonomy bridge tags (preferred)
- resolve_persona_context(): load persona profile → extraction context string
- gate_qras(): quality + relevance check on extracted QRAs
- log_shadow_feedback(): log results for co-evolutionary learning
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .utils import log
from loguru import logger

SKILLS_DIR = Path(__file__).parent.parent
PERSONAS_YAML = SKILLS_DIR / "monitor-personas" / "personas.yaml"


def _load_persona_entry(persona_name: str) -> Optional[Dict[str, Any]]:
    """Load a persona's full entry from personas.yaml by name or id."""
    if not PERSONAS_YAML.exists():
        return None
    try:
        import yaml
        with open(PERSONAS_YAML) as f:
            data = yaml.safe_load(f) or {}
        name_lower = persona_name.lower()
        for _category, entries in data.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if (str(entry.get("name", "")).lower() == name_lower
                        or str(entry.get("id", "")).lower() == name_lower):
                    entry["_category"] = _category
                    return entry
    except Exception as e:
        logger.debug("persona load failed: {}", e)
    return None


def _extract_persona_keywords(entry: Dict[str, Any]) -> Set[str]:
    """Extract domain keywords from a persona entry for relevance matching.

    Pulls from: interests (primary, cross_domain), taxonomy_hints, notes.
    Returns lowercased keyword tokens.
    """
    keywords: Set[str] = set()

    # taxonomy_hints (e.g. ["Corruption", "Stealth"])
    for hint in entry.get("taxonomy_hints", []):
        keywords.add(str(hint).lower())

    # interests.primary, interests.cross_domain
    interests = entry.get("curate_content", {}).get("interests", {})
    for category in ("primary", "cross_domain"):
        for phrase in interests.get(category, []):
            # Split phrases into individual tokens
            for word in str(phrase).lower().split():
                if len(word) > 3:  # skip short words
                    keywords.add(word)

    # notes field — extract significant words
    notes = str(entry.get("notes", ""))
    for word in notes.lower().split():
        word = re.sub(r'[^\w]', '', word)
        if len(word) > 4:
            keywords.add(word)

    return keywords


def select_persona(scope: str, content_summary: str) -> Optional[str]:
    """Find best persona from monitor-personas registry.

    Matches persona by scope overlap. Falls back to None if no match.

    Args:
        scope: Memory scope (e.g. 'sparta', 'research')
        content_summary: Brief content hint for matching

    Returns:
        Persona name or None
    """
    try:
        from common.persona_router import route_personas_for_task
        matches = route_personas_for_task(
            task="qra-quality-gate",
            input_data={"description": content_summary, "scope": scope},
            top_k=1,
        )
        if matches:
            return matches[0].name
    except ImportError:
        pass

    # Fallback: try loading personas.yaml directly
    if not PERSONAS_YAML.exists():
        return None

    try:
        import yaml
        with open(PERSONAS_YAML) as f:
            data = yaml.safe_load(f) or {}

        scope_lower = scope.lower()
        for _category, entries in data.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                persona_scope = str(entry.get("scope", "")).lower()
                if persona_scope and persona_scope in scope_lower:
                    return entry.get("name", entry.get("id", ""))
    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    return None


def select_persona_by_bridges(bridge_tags: List[str]) -> Optional[str]:
    """Route to the best persona via taxonomy bridge tag overlap.

    Uses persona_router's Jaccard similarity. This is the preferred
    entry point when taxonomy has already been extracted from the document.

    Args:
        bridge_tags: Bridge tags extracted from document content

    Returns:
        Persona name or None
    """
    if not bridge_tags:
        return None
    try:
        from common.persona_router import route_personas
        matches = route_personas(bridge_tags, top_k=1)
        if matches:
            return matches[0].name
    except ImportError:
        pass
    return None


def resolve_persona_context(persona_name: str) -> Optional[str]:
    """Load persona profile and build an LLM extraction context string.

    Reads the persona's interests, taxonomy_hints, and notes from
    personas.yaml and composes a focused context string that can be
    passed to build_qra_system_prompt() to guide what gets extracted.

    Args:
        persona_name: Persona name or id (e.g. 'horus', 'brandon_bailey')

    Returns:
        Context string like "cybersecurity expert focused on offensive operations,
        autonomous weapons, C2 exploitation" — or None if persona not found.
    """
    entry = _load_persona_entry(persona_name)
    if not entry:
        return None

    parts: List[str] = []

    # Build role description from notes
    notes = str(entry.get("notes", "")).strip()
    if notes:
        # Use first sentence of notes as role description
        first_sentence = notes.split(".")[0].strip()
        if first_sentence:
            parts.append(first_sentence)

    # Add primary interests
    interests = entry.get("curate_content", {}).get("interests", {})
    primary = interests.get("primary", [])
    if primary:
        parts.append(f"focused on {', '.join(primary[:4])}")

    # Add cross-domain interests
    cross = interests.get("cross_domain", [])
    if cross:
        parts.append(f"with cross-domain expertise in {', '.join(cross[:3])}")

    # Add taxonomy bridge context
    hints = entry.get("taxonomy_hints", [])
    if hints:
        parts.append(f"(taxonomy: {', '.join(str(h) for h in hints)})")

    if not parts:
        return None

    context = ". ".join(parts)
    log(f"Persona context resolved for '{persona_name}': {context[:80]}...", style="cyan")
    return context


def _relevance_score(text: str, keywords: Set[str]) -> float:
    """Score how relevant a text is to a set of persona keywords.

    Returns 0.0-1.0 based on fraction of persona keywords found in text.
    """
    if not keywords:
        return 1.0  # no keywords = everything is relevant
    text_lower = text.lower()
    text_words = set(re.findall(r'\w{4,}', text_lower))
    hits = keywords & text_words
    # Also check for multi-word phrases (partial match)
    for kw in keywords:
        if kw in text_lower and kw not in hits:
            hits.add(kw)
    return min(1.0, len(hits) / max(3, len(keywords) * 0.3))


def gate_qras(
    qras: List[Dict[str, Any]],
    persona: str,
    scope: str,
) -> Dict[str, Any]:
    """Quality + relevance gate on QRA pairs.

    Two scoring axes:
    - Structural quality: problem/solution length, reasoning, metadata
    - Domain relevance: keyword overlap with persona's interests/taxonomy

    The same book read by Horus vs Brandon vs Embry should produce
    different QRAs because each persona's domain keywords filter
    for what matters to THEM.

    Args:
        qras: List of QRA dicts
        persona: Persona name (for logging)
        scope: Memory scope

    Returns:
        Dict with verdict, accepted, rejected, says
    """
    # Load persona keywords for relevance scoring
    entry = _load_persona_entry(persona)
    keywords = _extract_persona_keywords(entry) if entry else set()
    has_relevance = bool(keywords)

    accepted = []
    rejected = []

    for qa in qras:
        problem = qa.get("problem", "")
        solution = qa.get("solution", "")
        reasoning = qa.get("reasoning", "")

        # === Structural quality (0-4) ===
        struct_score = 0.0

        # Grounding: problem is specific (not generic filler)
        if len(problem) > 20 and not problem.startswith("[") or len(problem) > 30:
            struct_score += 1.0

        # Solution substantiveness
        if len(solution) > 50:
            struct_score += 1.0
        elif len(solution) > 20:
            struct_score += 0.5

        # Reasoning present
        if reasoning and len(reasoning) > 10:
            struct_score += 1.0

        # Metadata present (section context)
        if qa.get("section_title") or qa.get("source"):
            struct_score += 1.0

        struct_norm = struct_score / 4.0

        # === Domain relevance (0-1) ===
        if has_relevance:
            combined_text = f"{problem} {solution} {reasoning}"
            relevance = _relevance_score(combined_text, keywords)
        else:
            relevance = 1.0  # no keywords = pass through

        # Combined score: 60% structural, 40% relevance
        combined = (struct_norm * 0.6) + (relevance * 0.4)

        if combined >= 0.4:
            accepted.append(qa)
        else:
            rejected.append(qa)

    total = len(qras)
    n_accepted = len(accepted)
    n_rejected = len(rejected)

    if n_rejected == 0:
        verdict = "PASS"
    elif n_accepted >= total * 0.7:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    relevance_note = f", {len(keywords)} domain keywords" if has_relevance else ""
    says = (
        f"{persona} reviewed {total} QRAs for scope '{scope}': "
        f"{n_accepted} accepted, {n_rejected} rejected{relevance_note}"
    )

    return {
        "verdict": verdict,
        "accepted": accepted,
        "rejected": rejected,
        "says": says,
        "persona": persona,
        "scope": scope,
    }


def log_shadow_feedback(
    persona: str,
    qras: List[Dict[str, Any]],
    verdict: str,
) -> None:
    """Log persona gate feedback for co-evolutionary learning.

    Computes actual grounding stats from QRAs and logs to subgraph_feedback.jsonl.
    This feeds into summarize_subgraph_feedback() for promotion decisions.
    """
    try:
        from common.subgraph_feedback import log_subgraph_feedback

        # Compute actual grounding stats from QRA data
        grounded = [q for q in qras if q.get("grounding_score")]
        avg_grounding = (
            sum(q["grounding_score"] for q in grounded) / len(grounded)
            if grounded else 0.0
        )

        log_subgraph_feedback(
            classifier_name=f"persona_gate:{persona}",
            seeds=[qa.get("problem", "")[:60] for qa in qras[:5]],
            subgraph_qra_count=len(qras),
            avg_grounding=avg_grounding,
            baseline_qra_count=len(qras),
            baseline_grounding=0.6,  # grounding threshold as baseline
            confidence=avg_grounding,  # use grounding as confidence signal
        )
    except ImportError:
        pass
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
