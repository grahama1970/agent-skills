#!/usr/bin/env python3
"""
Persona diagnosis: identify gaps and quality issues.

Checks source completeness, relationship connectivity, bridge coverage,
and data freshness for a persona.
"""

from datetime import datetime

from .persona import (
    get_persona,
    get_relationships,
)
from .quality_metrics import PersonaQualityScore


def diagnose_persona(
    name: str,
    scope: str = "personas",
) -> PersonaQualityScore:
    """
    Diagnose a persona's quality and identify gaps.

    Checks:
    - Source completeness (dogpile, books, YouTube, etc.)
    - Colleague/relationship connectivity
    - Bridge attribute coverage
    - Recency of updates

    Args:
        name: Persona name
        scope: Memory scope

    Returns:
        PersonaQualityScore with diagnostic details
    """
    persona = get_persona(name, scope)
    if not persona:
        return PersonaQualityScore(
            name=name,
            scope=scope,
            gaps=["Persona not found"]
        )

    score = PersonaQualityScore(name=name, scope=scope)
    gaps = []

    # -------------------------------------------------------------------------
    # Completeness: Check sources
    # -------------------------------------------------------------------------
    sources = persona.sources or {}
    score.sources_count = sum(sources.values()) if sources else 0
    score.qra_count = persona.qra_count or 0

    # Expected sources by template
    expected_sources = {
        "expert": ["dogpile", "youtube", "books"],
        "coder": ["dogpile", "youtube", "github"],
        "client": ["dogpile"],
        "stakeholder": ["dogpile"],
        "adversary": ["dogpile"],
    }

    template = persona.template or "expert"
    expected = expected_sources.get(template, ["dogpile"])

    for src in expected:
        if src not in sources or sources.get(src, 0) == 0:
            gaps.append(f"Missing source: {src}")

    # Score completeness
    if score.sources_count >= 10:
        score.completeness = 1.0
    elif score.sources_count >= 5:
        score.completeness = 0.7
    elif score.sources_count >= 2:
        score.completeness = 0.4
    elif score.sources_count >= 1:
        score.completeness = 0.2
    else:
        score.completeness = 0.0
        gaps.append("No learning sources - run /ask learn")

    # QRA pairs indicate deep learning
    if score.qra_count == 0:
        gaps.append("No QRA pairs extracted")

    # -------------------------------------------------------------------------
    # Connectivity: Check relationships
    # -------------------------------------------------------------------------
    relationships = get_relationships(name, scope)
    score.colleague_count = len(relationships)

    if score.colleague_count >= 5:
        score.connectivity = 1.0
    elif score.colleague_count >= 3:
        score.connectivity = 0.7
    elif score.colleague_count >= 1:
        score.connectivity = 0.4
    else:
        score.connectivity = 0.0
        gaps.append("No colleague relationships - isolated node")

    # -------------------------------------------------------------------------
    # Bridge coverage
    # -------------------------------------------------------------------------
    bridges = persona.bridge_weights or {}
    score.bridge_count = len(bridges)

    if score.bridge_count == 0:
        gaps.append("No Federated Taxonomy bridges")

    # -------------------------------------------------------------------------
    # Freshness: Check last update
    # -------------------------------------------------------------------------
    try:
        last_updated = datetime.fromisoformat(persona.last_updated.replace("Z", "+00:00"))
        days_old = (datetime.now() - last_updated.replace(tzinfo=None)).days
        score.days_since_update = days_old

        if days_old <= 7:
            score.freshness = 1.0
        elif days_old <= 30:
            score.freshness = 0.7
        elif days_old <= 90:
            score.freshness = 0.4
        else:
            score.freshness = 0.2
            gaps.append(f"Stale data: {days_old} days old")
    except (ValueError, AttributeError):
        score.freshness = 0.5  # Unknown

    # -------------------------------------------------------------------------
    # Additional checks
    # -------------------------------------------------------------------------
    if not persona.domain:
        gaps.append("No domain specified")

    if not persona.expertise:
        gaps.append("No expertise listed")

    if not persona.goals:
        gaps.append("No goals defined")

    score.gaps = gaps

    # Set accuracy to 0.5 (unknown) until validated
    score.accuracy = 0.5

    return score
