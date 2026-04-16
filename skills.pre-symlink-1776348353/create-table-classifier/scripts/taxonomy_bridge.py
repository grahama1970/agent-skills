"""
Federated Taxonomy integration for Table Strategy Classifier.

Maps extraction strategies to bridge attributes for preset-aware predictions:
- Precision → lattice_sensitive (precise line detection for thin borders)
- Fragility → stream (handles degraded/fragile tables)
- Resilience → lattice (robust extraction for clear tables)

Uses the taxonomy skill for cross-collection multi-hop traversal in /memory.
"""

import sys
from pathlib import Path
from typing import Any

# Try to import taxonomy skill
_TAXONOMY_PATH = Path(__file__).parent.parent.parent / "taxonomy"
if _TAXONOMY_PATH.exists():
    sys.path.insert(0, str(_TAXONOMY_PATH))

try:
    from taxonomy import extract_taxonomy, BRIDGE_TAGS, validate_tags
except ImportError:
    # Minimal fallback if taxonomy skill not available
    BRIDGE_TAGS = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}

    def extract_taxonomy(text: str, collection: str = "operational", fast: bool = True) -> dict:
        return {"bridge_tags": [], "collection_tags": {}, "confidence": 0.0, "worth_remembering": False}

    def validate_tags(raw: dict, collection: str) -> dict:
        bridge = [t for t in raw.get("bridge_tags", []) if t in BRIDGE_TAGS]
        return {"bridge_tags": bridge, "collection_tags": {}, "confidence": 0.5}


# Strategy-to-Bridge Mapping
# Based on extraction characteristics and failure patterns
STRATEGY_BRIDGE_MAP = {
    "lattice": {
        "primary_bridge": "Resilience",
        "characteristics": ["robust", "structured", "clear borders"],
        "best_for": ["formal documents", "requirements specs", "engineering tables"],
    },
    "stream": {
        "primary_bridge": "Fragility",
        "characteristics": ["flexible", "handles degraded", "whitespace-based"],
        "best_for": ["scanned documents", "OCR output", "faded borders"],
    },
    "lattice_sensitive": {
        "primary_bridge": "Precision",
        "characteristics": ["precise", "thin lines", "high resolution"],
        "best_for": ["scientific papers", "arxiv", "LaTeX documents"],
    },
}

# Preset-to-Strategy recommendations based on taxonomy
PRESET_STRATEGY_RECOMMENDATIONS = {
    "arxiv_scientific": {
        "recommended_strategy": "lattice_sensitive",
        "bridge_hints": ["Precision"],
        "line_scale_range": (12, 18),
        "edge_tol_range": (200, 400),
    },
    "requirements_spec": {
        "recommended_strategy": "lattice",
        "bridge_hints": ["Resilience", "Loyalty"],
        "line_scale_range": (20, 30),
        "edge_tol_range": (300, 500),
    },
    "archive_scanned": {
        "recommended_strategy": "stream",
        "bridge_hints": ["Fragility"],
        "line_scale_range": (35, 45),
        "edge_tol_range": (100, 300),
    },
    "government_report": {
        "recommended_strategy": "lattice",
        "bridge_hints": ["Resilience", "Loyalty"],
        "line_scale_range": (18, 25),
        "edge_tol_range": (250, 450),
    },
    "academic_thesis": {
        "recommended_strategy": "lattice_sensitive",
        "bridge_hints": ["Precision"],
        "line_scale_range": (14, 20),
        "edge_tol_range": (200, 400),
    },
}


def get_strategy_bridges(strategy: str) -> list[str]:
    """Get bridge tags associated with a strategy."""
    mapping = STRATEGY_BRIDGE_MAP.get(strategy, {})
    primary = mapping.get("primary_bridge")
    return [primary] if primary else []


def get_preset_recommendation(preset: str) -> dict[str, Any]:
    """Get strategy recommendation for a preset."""
    return PRESET_STRATEGY_RECOMMENDATIONS.get(preset, {
        "recommended_strategy": "lattice",
        "bridge_hints": [],
        "line_scale_range": (15, 30),
        "edge_tol_range": (200, 400),
    })


def compute_preset_match_reward(
    predicted_strategy: str,
    predicted_line_scale: int,
    predicted_edge_tol: int,
    preset: str,
    domain: str | None = None,
) -> float:
    """
    Compute reward for how well prediction matches preset expectations.

    Returns:
        Float reward in [0, 1] range.
    """
    if preset not in PRESET_STRATEGY_RECOMMENDATIONS:
        return 0.5  # Neutral for unknown presets

    rec = PRESET_STRATEGY_RECOMMENDATIONS[preset]

    # Strategy match: 0.6 weight
    strategy_match = 1.0 if predicted_strategy == rec["recommended_strategy"] else 0.0

    # Line scale in range: 0.25 weight
    ls_min, ls_max = rec["line_scale_range"]
    if ls_min <= predicted_line_scale <= ls_max:
        line_scale_match = 1.0
    else:
        distance = min(abs(predicted_line_scale - ls_min), abs(predicted_line_scale - ls_max))
        line_scale_match = max(0.0, 1.0 - distance / 10.0)

    # Edge tolerance in range: 0.15 weight
    et_min, et_max = rec["edge_tol_range"]
    if et_min <= predicted_edge_tol <= et_max:
        edge_tol_match = 1.0
    else:
        distance = min(abs(predicted_edge_tol - et_min), abs(predicted_edge_tol - et_max))
        edge_tol_match = max(0.0, 1.0 - distance / 100.0)

    reward = (
        0.6 * strategy_match +
        0.25 * line_scale_match +
        0.15 * edge_tol_match
    )

    return reward


def extract_table_taxonomy(table_description: str, preset: str | None = None) -> dict[str, Any]:
    """
    Extract taxonomy tags for a table extraction context.

    Uses sparta collection for extraction/reliability focus.
    """
    # Build context string
    context = table_description
    if preset:
        rec = get_preset_recommendation(preset)
        context += f"\nPreset: {preset}, Strategy: {rec.get('recommended_strategy', 'unknown')}"

    return extract_taxonomy(text=context, collection="sparta", fast=True)


def bridge_overlap_reward(predicted_bridges: list[str], actual_bridges: list[str]) -> float:
    """
    Compute reward based on overlap between predicted and actual bridges.

    Used in GRPO to encourage taxonomy-aligned predictions.
    """
    if not predicted_bridges or not actual_bridges:
        return 0.5  # Neutral when no bridges

    pred_set = set(predicted_bridges)
    actual_set = set(actual_bridges)

    # Jaccard similarity
    intersection = len(pred_set & actual_set)
    union = len(pred_set | actual_set)

    return intersection / union if union > 0 else 0.0
