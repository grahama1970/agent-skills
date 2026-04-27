"""
Federated Taxonomy bridge extraction for /ask learn.

Delegates bridge extraction to the taxonomy skill and aggregates bridge
attributes from content.
"""

from collections import Counter

from loguru import logger as log

from .skills_exec import run_skill


def extract_bridges_from_content(
    text: str,
    content_type: str = "article",
    topic: str = "",
) -> list[str]:
    """Extract Federated Taxonomy bridge attributes from text content.

    Args:
        text: The content text to analyze
        content_type: Type of content (book, video, article)
        topic: Optional topic context for better extraction

    Returns:
        List of bridge attribute names (Precision, Resilience, Fragility, etc.)
    """
    analysis_text = f"{topic}\n\n{text[:2000]}".strip()
    result = run_skill("taxonomy", ["bridges", analysis_text, "--fast"], timeout=15)
    if result["returncode"] != 0:
        log.error("Taxonomy bridge extraction failed: %s", result["stderr"][:200])
        return []

    bridges = [bridge.strip() for bridge in result["stdout"].strip().split(",") if bridge.strip()]
    if bridges:
        log.debug("Extracted bridges from %s: %s", content_type, bridges)
    return bridges


def aggregate_bridges(bridge_lists: list[list[str]], min_count: int = 2) -> list[str]:
    """Aggregate multiple bridge extractions into a consensus set.

    Args:
        bridge_lists: List of bridge attribute lists from different content
        min_count: Minimum occurrences required to include a bridge

    Returns:
        List of bridge attributes that appear frequently enough
    """
    all_bridges = []
    for bridges in bridge_lists:
        all_bridges.extend(bridges)

    counts = Counter(all_bridges)

    # If we have few sources, lower the threshold
    threshold = min(min_count, max(1, len(bridge_lists) // 2))

    result = [bridge for bridge, count in counts.items() if count >= threshold]
    log.debug("Aggregated bridges: %s (threshold=%d)", result, threshold)
    return result
