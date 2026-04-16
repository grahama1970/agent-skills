"""Traceability reporting and synthesis sparsity checking for SPARTA conversations.

Contains the per-turn traceability report builder and the Lie-detector Layer 3b
synthesis sparsity guard, extracted from conversation_runner.py to keep each
module under 800 lines.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger


# --------------------------------------------------------------------------- #
# Per-Turn Traceability Report
# --------------------------------------------------------------------------- #


def build_traceability_report(
    question: str,
    turn_number: int,
    sparta_result: Dict,
    citation_details: List[Dict],
    self_grade_log: List[Dict],
    sparsity_result: Optional[Dict] = None,
) -> str:
    """Build markdown traceability report for one SPARTA answer turn.

    This is the ANTI-OPACITY measure. Every retrieval signal, citation
    verification, and synthesis decision is made visible.
    """
    lines: List[str] = []
    lines.append(f"## Turn {turn_number}: SPARTA Answer -- Traceability Report")
    lines.append("")

    # --- Query ---
    lines.append("### Query")
    lines.append(f"> {question[:200]}")
    lines.append("")

    # --- Retrieval Results ---
    retrieval_cards = sparta_result.get("retrieval_cards", [])
    qra_count = sparta_result.get("qra_count", 0)
    related_controls = sparta_result.get("related_controls", [])

    lines.append(f"### Retrieval Results ({qra_count} QRAs, {len(related_controls)} controls)")
    if retrieval_cards:
        lines.append("| # | Source | Control | BM25 | Dense | Graph | Fresh | Hops | Label |")
        lines.append("|---|--------|---------|------|-------|-------|-------|------|-------|")
        for i, card in enumerate(retrieval_cards, 1):
            r = card.get("retrieval", {})
            lines.append(
                f"| {i} | {card.get('qra_key', '?')[:25]} "
                f"| {card.get('control_id', '\u2014')} "
                f"| {r.get('bm25', 0):.2f} "
                f"| {r.get('dense', 0):.2f} "
                f"| {r.get('graph', 0):.2f} "
                f"| {r.get('freshness', 0):.2f} "
                f"| {r.get('graph_hops', 0)} "
                f"| {card.get('label', '?')} |"
            )
    else:
        lines.append("*(No retrieval cards available)*")
    lines.append("")

    # --- Citation Audit ---
    lines.append("### Citation Audit")
    if citation_details:
        lines.append("| Source Key | Control | Verified? | Method |")
        lines.append("|-----------|---------|-----------|--------|")
        hallucinated_count = 0
        for det in citation_details:
            verified_str = "YES" if det.get("verified") else "NO"
            method = det.get("method", "unknown")
            key = det.get("key", "?")[:30]
            cid = det.get("control_id", "\u2014")
            lines.append(f"| {key} | {cid} | {verified_str} | {method} |")
            if not det.get("verified"):
                hallucinated_count += 1
    else:
        lines.append("*(No citation details available)*")
        hallucinated_count = 0
    lines.append("")

    # --- Provenance Summary ---
    lines.append("### Provenance Summary")
    lanes = sparta_result.get("lanes_used", [])
    lines.append(f"- **Retrieval lanes**: {', '.join(lanes) if lanes else 'none'}")

    bridge_tags = sparta_result.get("bridge_tags_matched", [])
    bridge_count = sparta_result.get("bridge_overlap_count", 0)
    if bridge_tags:
        lines.append(f"- **Bridge overlap**: {bridge_count} tags matched ({', '.join(bridge_tags[:5])})")
    else:
        lines.append(f"- **Bridge overlap**: {bridge_count} tags matched")

    evidence = sparta_result.get("evidence", {})
    richness = evidence.get("richness_score", 0.0)
    lines.append(f"- **Richness score**: {richness:.2f}")

    # Synthesis needed?
    direct_hits = sum(
        1 for c in retrieval_cards
        if c.get("label") == "QRA-GROUNDED" and c.get("retrieval", {}).get("graph_hops", 0) == 0
    )
    if direct_hits >= 2:
        lines.append(f"- **Synthesis needed?**: NO -- {direct_hits} direct QRA hits")
    elif direct_hits == 1:
        lines.append(f"- **Synthesis needed?**: PARTIAL -- 1 direct QRA hit, supplemented by graph")
    else:
        lines.append("- **Synthesis needed?**: YES -- no direct QRA hits, all graph-inferred or synthesized")

    # Hallucinated claims
    if hallucinated_count > 0:
        lines.append(f"- **Unverified claims**: {hallucinated_count}")
    else:
        lines.append("- **Unverified claims**: 0")

    # Sparsity check
    if sparsity_result:
        verdict = sparsity_result.get("verdict", "?")
        lines.append(
            f"- **Sparsity check**: {verdict} "
            f"(bridge={sparsity_result.get('bridge_coverage', 0):.2f}, "
            f"entity={sparsity_result.get('entity_coverage', 0):.2f})"
        )

    # Self-grade iterations
    grade_entries = [e for e in self_grade_log if not e.get("_summary")]
    if grade_entries:
        first_g = grade_entries[0]
        last_g = grade_entries[-1]
        first_str = f"{first_g.get('grade', '?')} ({first_g.get('composite', 0):.2f})"
        last_str = f"{last_g.get('grade', '?')} ({last_g.get('composite', 0):.2f})"
        if len(grade_entries) > 1:
            last_c = last_g.get('composite', 0)
            first_c = first_g.get('composite', 0)
            direction = "improved to" if last_c >= first_c else "regressed to"
            lines.append(f"- **Self-grade**: {first_str} -> {direction} {last_str} over {len(grade_entries)} iterations")
        else:
            lines.append(f"- **Self-grade**: {first_str} (1 iteration)")

    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Lie-detector Layer 3b: Synthesis sparsity guard
# --------------------------------------------------------------------------- #

# Bridge attributes from the Federated Taxonomy
_BRIDGES = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}
_SPARSE_THRESHOLD = 0.3
_DENSE_THRESHOLD = 0.7


def _extract_taxonomy_entities(text: str) -> set:
    """Extract entity-like tokens (control IDs, dimension names, bridges)."""
    entities: set = set()
    entities.update(re.findall(r'[A-Z]{1,4}-\d{3,5}', text))
    for dim in ("content_coverage", "section_alignment", "table_fidelity",
                "equation_fidelity", "ordering_yx", "figure_fidelity", "data_quality"):
        if dim in text.lower().replace(" ", "_"):
            entities.add(dim)
    for bridge in _BRIDGES:
        if bridge.lower() in text.lower():
            entities.add(bridge)
    return entities


def _extract_bridge_mentions(text: str) -> set:
    """Extract taxonomy bridge mentions from text."""
    found: set = set()
    text_lower = text.lower()
    for bridge in _BRIDGES:
        if bridge.lower() in text_lower:
            found.add(bridge)
    return found


def check_synthesis_sparsity(
    answer_text: str,
    query: str,
) -> Dict[str, Any]:
    """Lie-detector Layer 3b: check if a synthesized answer is grounded.

    Only called when NO blessed QRA was found and NO control definition matches.
    Uses graph_memory.api.search() directly (no subprocess overhead).

    Returns dict with verdict (SPARSE/ADEQUATE/DENSE), coverage ratios, missing entities.
    """
    if not answer_text or not answer_text.strip():
        return {"verdict": "SPARSE", "entity_coverage": 0.0, "bridge_coverage": 0.0}

    # Extract what the answer claims
    claimed = _extract_taxonomy_entities(answer_text)

    # Query /memory for what SHOULD be connected
    try:
        from graph_memory.api import search as memory_search
        recall_result = memory_search(q=query, scope="sparta", k=20)
        recall_text = json.dumps(recall_result.get("results", []))
    except Exception as e:
        logger.debug(f"Sparsity check skipped -- /memory unavailable: {e}")
        return {"verdict": "ADEQUATE", "entity_coverage": 0.5, "bridge_coverage": 0.5}

    expected = _extract_taxonomy_entities(recall_text)

    # Bridge intersection
    response_bridges = _extract_bridge_mentions(answer_text)
    expected_bridges = _extract_bridge_mentions(recall_text)
    bridge_coverage = (
        len(response_bridges & expected_bridges) / max(len(expected_bridges), 1)
        if expected_bridges else 1.0
    )

    # Entity coverage
    entity_coverage = (
        len(claimed & expected) / max(len(expected), 1)
        if expected else 1.0
    )

    # Verdict
    if bridge_coverage < _SPARSE_THRESHOLD:
        verdict = "SPARSE"
    elif bridge_coverage < _DENSE_THRESHOLD:
        verdict = "ADEQUATE"
    else:
        verdict = "DENSE"

    missing = sorted(expected - claimed)

    return {
        "verdict": verdict,
        "entity_coverage": round(entity_coverage, 3),
        "bridge_coverage": round(bridge_coverage, 3),
        "missing_entities": missing[:10],
    }
