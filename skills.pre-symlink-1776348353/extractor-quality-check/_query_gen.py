"""Persona autonomous loop — query generation.

Generates queries for the persona loop, both seed-adapted (from the
210 scenario corpus) and organic (synthesized from accumulated context,
datalake state, and memory).
"""
from __future__ import annotations

import random

from loguru import logger as log


def generate_query_from_seed(
    scenario: dict,
    persona_config: dict,
    datalake_state: dict,
    phase: str = "week_1",
) -> str:
    """Adapt a seed scenario into a contextual query.

    The seed provides the pattern; the persona's concerns and datalake
    state provide the specifics. Early phases inject extraction-error
    concerns; later phases inject real engineering questions.
    """
    base_query = scenario["query"]
    level = scenario.get("level", "discovery")

    # Pick concerns based on phase: early = extraction bugs, later = engineering
    is_early = phase in ("week_1", "week_2")
    concerns = (
        persona_config.get("early_concerns", []) if is_early
        else persona_config.get("key_concerns", [])
    )

    # For discovery/table_ops/quality: inject domain-specific concerns
    if level in ("discovery", "table_ops", "quality", "corrective"):
        if concerns:
            concern = random.choice(concerns)
            return f"{base_query} Specifically checking for: {concern}"

    # For requirements/cross_doc: reference actual datalake metrics
    if level in ("requirements", "cross_doc") and datalake_state:
        arango = datalake_state.get("datalake_arango") or {}
        chunk_count = arango.get("datalake_chunks_count", 0)
        if chunk_count > 0:
            return f"{base_query} (datalake has {chunk_count} chunks to search)"

    return base_query


def generate_organic_query(
    persona_config: dict,
    datalake_state: dict,
    previous_queries: list[str],
    memory_items: list[dict],
    phase: str = "week_1",
) -> str:
    """Generate an entirely new query based on accumulated context.

    Early phases focus on extraction defects -- broken tables, garbled
    values, fragmented sections. The datalake is a mess when they arrive.
    Later phases shift to real engineering questions as integrity improves.
    """
    concerns = persona_config.get("key_concerns", [])
    early_concerns = persona_config.get("early_concerns", [])
    vendor_queries = persona_config.get("vendor_queries", [])
    focus = persona_config.get("focus", "general")
    is_early = phase in ("week_1", "week_2")

    # ── Early phase: hunt extraction defects ──
    if is_early:
        strategies: list[str] = []

        # Strategy 1: Probe for a specific extraction error type
        if early_concerns:
            defect = random.choice(early_concerns)
            strategies.extend([
                f"Show me examples of: {defect}",
                f"Find chunks where this extraction problem occurred: {defect}",
                f"How many documents are affected by: {defect}",
                f"Is this defect consistent across documents or isolated: {defect}",
            ])

        # Strategy 2: Datalake integrity checks
        if datalake_state:
            arango = datalake_state.get("datalake_arango") or {}
            embed = arango.get("embedding_quality") or {}
            dist = arango.get("asset_type_distribution") or {}
            tax = arango.get("taxonomy_coverage") or {}

            if embed.get("zero_embed", 0) > 0:
                strategies.append(
                    f"Find chunks with missing embeddings -- {embed['zero_embed']} "
                    f"have zero-vectors. Which documents? Which pipeline stage failed?"
                )
            if tax.get("without_tags", 0) > 0:
                total = tax.get("total", 1)
                pct = 100 * tax["without_tags"] / total
                strategies.append(
                    f"{pct:.0f}% of chunks have no taxonomy tags. "
                    f"Find examples -- are they from specific sectors or document types?"
                )
            if dist and "table" not in str(dist).lower():
                strategies.append(
                    "No table chunks in the datalake. Were tables extracted at all? "
                    "Check if S05 ran and produced output."
                )

        # Strategy 3: Follow up on a previous defect finding
        if memory_items:
            item = random.choice(memory_items)
            text = item.get("text", item.get("problem", ""))[:150]
            if text:
                strategies.extend([
                    f"Has this extraction defect been fixed: {text}",
                    f"Find other documents with the same extraction error: {text}",
                ])

        if strategies:
            return random.choice(strategies)

    # ── Later phases: real engineering questions ──

    # Strategy: Follow up on accumulated knowledge
    if memory_items:
        item = random.choice(memory_items)
        text = item.get("text", item.get("problem", ""))[:200]
        if text:
            templates = [
                f"What other documents discuss the same topic as: {text}",
                f"Are there tables related to this finding: {text}",
                f"Find requirements that trace back to: {text}",
                f"Cross-reference this with vendor deliverables: {text}",
            ]
            return random.choice(templates)

    # Strategy: Vendor-specific investigation
    if vendor_queries:
        return random.choice(vendor_queries)

    # Strategy: Domain concern deep-dive
    if concerns:
        concern = random.choice(concerns)
        templates = [
            f"Show me all content related to: {concern}",
            f"Build a traceability chain for: {concern}",
            f"Compare extractions across documents for: {concern}",
        ]
        return random.choice(templates)

    # Fallback
    return f"What are the most recent extraction results in the {focus} domain?"
