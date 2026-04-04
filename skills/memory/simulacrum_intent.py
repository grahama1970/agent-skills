"""Intent detection and entity extraction for the Brandon Simulacrum.

Provides cascade-based and heuristic intent mapping for SPARTA queries,
including entity extraction for SPARTA/NIST/CWE/ATT&CK/D3FEND identifiers
and /memory clarify integration for disambiguation.
"""

import re
import sys
from pathlib import Path
from typing import Any

from loguru import logger


def extract_entities(query: str) -> list[str]:
    """Extract SPARTA/NIST/CWE/ATT&CK/D3FEND entities from query.

    Args:
        query: User's question

    Returns:
        List of entity IDs found in the query
    """
    entities = []
    patterns = [
        # SPARTA native: SV-SP-1, SV-MA-3, SV-AC-1.02
        r"SV-[A-Z]{2}-\d+(?:\.\d+)?",
        # SPARTA categories: REC-0008, DE-0010, EX-0002.03, IA-0005
        r"(?:REC|DE|EX|IA|PE|CP|PM|IR|MA|RA|AT|SR|PL|SA|SI|SC|RD|LM|EXF|IMP|PER)-\d{4}(?:\.\d+)?",
        # ESA: ESA-T2040
        r"ESA-T\d{4}",
        # SPARTA countermeasures: CM0008, CM-0042, CM0001
        r"CM-?\d{4}",
        # NIST SP 800-53: AC-2, AU-6, SI-4, SC-13, AC-2(12)
        r"(?:AC|AT|AU|CA|CM|CP|IA|IR|MA|MP|PE|PL|PM|PS|PT|RA|SA|SC|SI|SR)-\d+(?:\(\d+\))?",
        # CWE: CWE-787, CWE-1089
        r"CWE-\d+",
        # ATT&CK: T1548, T1548.004, T1134
        r"T\d{4}(?:\.\d{3})?",
        # D3FEND: D3-DENCR, d3f:ExceptionHandler
        r"D3-[A-Z]+",
        r"d3f:[A-Za-z]+",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, query)
        entities.extend(matches)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for e in entities:
        if e.upper() not in seen:
            seen.add(e.upper())
            unique.append(e)
    return unique


def get_intent_heuristic(query: str) -> dict[str, Any]:
    """Fallback heuristic-based intent detection.

    Args:
        query: User's question

    Returns:
        Intent result
    """
    query_lower = query.lower()

    # Out-of-scope detection
    ood_keywords = ["weather", "recipe", "stock", "sports", "movie", "music"]
    if any(kw in query_lower for kw in ood_keywords):
        return {"action": "NO_MATCH", "confidence": 0.0, "entities": []}

    # SPARTA-relevant detection
    sparta_keywords = [
        "sparta", "satellite", "spacecraft", "uplink", "downlink",
        "rf", "jamming", "spoofing", "ground station", "command",
        "telemetry", "control", "technique", "threat", "attack",
        "cm-", "t-", "payload", "bus", "orbital",
    ]
    if any(kw in query_lower for kw in sparta_keywords):
        return {
            "action": "QUERY",
            "confidence": 0.85,
            "entities": extract_entities(query),
            "tier1": [],
            "lanes": ["bm25", "dense"],
        }

    # Clarification needed
    if len(query.split()) < 4:
        return {
            "action": "CLARIFY",
            "confidence": 0.5,
            "clarify_question": (
                "Could you be more specific about what aspect of "
                "space systems you're asking about?"
            ),
        }

    # Default to query with medium confidence
    return {"action": "QUERY", "confidence": 0.6, "entities": [], "tier1": []}


def get_intent_cascade(
    query: str,
    classifier_available: bool,
    classify_query_fn: Any,
    ollama_available: bool,
    ollama_get_intent_fn: Any,
    has_cascade: bool,
    cascade_imports: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Intent detection via shared CascadeRunner.

    Args:
        query: User's question
        classifier_available: Whether the space classifier is available
        classify_query_fn: The classify_query callable (or None)
        ollama_available: Whether Ollama intent mapper is available
        ollama_get_intent_fn: The ollama_get_intent callable (or None)
        has_cascade: Whether CascadeRunner is importable
        cascade_imports: Dict with TierResult, TierDef, CascadeRunner classes

    Returns:
        Intent result with action, confidence, entities
    """
    # Fast path: if SPARTA entities are in the query, skip classifier entirely
    entities = extract_entities(query)
    if entities:
        logger.debug(f"Entity fast-path: found {entities} -- skipping space classifier")
        return {
            "action": "QUERY",
            "confidence": 0.95,
            "entities": entities,
            "tier1": [],
            "lanes": ["bm25", "dense"],
            "k": 12,
            "scope": "sparta",
            "original_query": query,
            "_intent_source": "entity_extraction",
        }

    if not has_cascade or cascade_imports is None:
        return get_intent_manual(
            query, classifier_available, classify_query_fn,
            ollama_available, ollama_get_intent_fn,
        )

    TierResult = cascade_imports["TierResult"]
    TierDef = cascade_imports["TierDef"]
    CascadeRunner = cascade_imports["CascadeRunner"]

    tiers = []

    # Tier 0: Space classifier (reject non-space queries)
    if classifier_available and classify_query_fn:
        def _classifier_tier(inp, **kw):
            classification = classify_query_fn(str(inp))
            if not classification["is_space"]:
                return TierResult(
                    result={
                        "action": "NO_MATCH",
                        "confidence": 0.0,
                        "entities": [],
                        "reason": "generic IT query",
                        "_classifier": classification,
                    },
                    confidence=classification["confidence"],
                    prediction="NO_MATCH",
                )
            return None  # In-scope -> escalate to intent mapper

        tiers.append(
            TierDef(tier=0, name="space_classifier", fn=_classifier_tier, threshold=0.8)
        )

    # Tier 1: Ollama intent mapper
    if ollama_available and ollama_get_intent_fn:
        def _ollama_tier(inp, **kw):
            result = ollama_get_intent_fn(str(inp))
            return TierResult(
                result=result,
                confidence=result.get("confidence", 0.5),
                prediction=result.get("action", ""),
            )

        tiers.append(TierDef(tier=1, name="ollama_intent", fn=_ollama_tier))

    # Tier 2: Heuristic fallback (always available)
    def _heuristic_tier(inp, **kw):
        result = get_intent_heuristic(str(inp))
        return TierResult(
            result=result,
            confidence=result.get("confidence", 0.5),
            prediction=result.get("action", ""),
        )

    tiers.append(TierDef(tier=2, name="heuristic", fn=_heuristic_tier))

    runner = CascadeRunner(tiers=tiers)
    tier_result = runner.run(query, task="sparta-intent", scope="brandon_bailey")
    return tier_result.result


def get_intent_manual(
    query: str,
    classifier_available: bool,
    classify_query_fn: Any,
    ollama_available: bool,
    ollama_get_intent_fn: Any,
) -> dict[str, Any]:
    """Fallback intent detection without CascadeRunner.

    Args:
        query: User's question
        classifier_available: Whether the space classifier is available
        classify_query_fn: The classify_query callable (or None)
        ollama_available: Whether Ollama intent mapper is available
        ollama_get_intent_fn: The ollama_get_intent callable (or None)

    Returns:
        Intent result
    """
    # Step 1: Pre-filter with classifier if available
    if classifier_available and classify_query_fn:
        try:
            classification = classify_query_fn(query)
            if not classification["is_space"] and classification["confidence"] > 0.8:
                return {
                    "action": "NO_MATCH",
                    "confidence": 0.0,
                    "entities": [],
                    "reason": "Query classified as generic IT (not space-specific)",
                    "_classifier": classification,
                }
        except Exception as e:
            logger.debug("Classifier lookup failed: {}", e)

    # Step 2: Use Ollama intent mapper if available
    if ollama_available and ollama_get_intent_fn:
        try:
            return ollama_get_intent_fn(query)
        except Exception as e:
            logger.debug("Ollama intent failed: {}", e)

    # Step 3: Fallback to simple heuristics
    return get_intent_heuristic(query)


def run_clarify(query: str, intent: dict[str, Any]) -> dict | None:
    """Run /memory clarify for richer disambiguation.

    Uses intent mapping + taxonomy extraction + QRA corpus correlation
    to generate specific clarifying questions.

    Args:
        query: User's question
        intent: Intent mapping result

    Returns:
        Clarify result dict or None on failure
    """
    try:
        _src = str(Path(__file__).resolve().parents[2] / "src")
        if _src not in sys.path:
            sys.path.insert(0, _src)
        from graph_memory.agent_cli import _clarify_direct

        return _clarify_direct(
            q=query,
            persona="embry",
            scope="sparta",
            k=5,
        )
    except Exception as e:
        logger.debug(f"Clarify failed, using fallback: {e}")
        return None
