"""Federated Taxonomy bridge tagging for table extraction results.

Maps table extraction metrics to the 6 Bridge Attributes (Tier 0)
and collection-specific dimensions (Tier 3) for multi-hop graph
traversal in ArangoDB.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tuner import TuneResult

BRIDGE_TAGS = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}


def tag_extraction_result(tune_result: TuneResult) -> list[str]:
    """Derive bridge tags from tuning results."""
    tags = []
    if tune_result.best_fragmentation == 0 and tune_result.best_cell_count >= 10:
        tags.append("Precision")
    if tune_result.best_fragmentation == 0:
        tags.append("Resilience")
    if tune_result.best_fragmentation > 5:
        tags.append("Fragility")
    # All strategies failed
    all_failed = all(r["total_tables"] == 0 for r in tune_result.all_results)
    if all_failed:
        tags.append("Corruption")
    return tags


def tag_collection_dimensions(tune_result: TuneResult) -> dict[str, str]:
    """Derive collection-specific taxonomy dimensions (Tier 3)."""
    return {
        "function": "Extraction",
        "domain": "PDF",
        "thematic_weight": _classify_severity(tune_result),
        "perspective": "Operational",
    }


def _classify_severity(tune_result: TuneResult) -> str:
    """Classify extraction severity based on metrics."""
    if not tune_result.all_results:
        return "Low"
    all_failed = all(r["total_tables"] == 0 for r in tune_result.all_results)
    if all_failed:
        return "Critical"
    if tune_result.best_fragmentation > 5:
        return "High"
    if tune_result.best_fragmentation > 0:
        return "Medium"
    return "Low"


def format_memory_tags(bridge_tags: list[str], collection_tags: dict) -> dict:
    """Format for /memory learn integration."""
    return {
        "bridge_tags": bridge_tags,
        "collection_tags": collection_tags,
        "taxonomy_version": "federated_v1",
    }
