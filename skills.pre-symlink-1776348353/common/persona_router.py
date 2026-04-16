"""Dynamic persona selection via Jaccard similarity on taxonomy bridges.

Routes tasks to the most relevant personas from the monitor-personas
registry based on bridge overlap (taxonomy_hints).

Usage:
    from common.persona_router import route_personas, route_personas_for_task

    # Direct bridge matching
    matches = route_personas(["Corruption", "Stealth"])

    # Task-aware routing (extracts bridges automatically)
    matches = route_personas_for_task("security", {"finding": "CVE-2025-1234"})
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from .paths import PERSONAS_YAML

__all__ = [
    "PersonaMatch",
    "route_personas",
    "route_personas_for_task",
]


@dataclass
class PersonaMatch:
    """A persona matched by bridge overlap."""

    persona_id: str
    name: str
    scope: str
    category: str
    bridge_overlap: float  # Jaccard similarity (0.0-1.0)
    matched_bridges: list[str] = field(default_factory=list)
    taxonomy_hints: list[str] = field(default_factory=list)
    fictional: bool = False


def _load_persona_registry(
    registry_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Load all personas from the YAML registry, flattened."""
    import yaml

    src = registry_path or PERSONAS_YAML
    if not src.exists():
        logger.warning(f"Persona registry not found: {src}")
        return []

    with open(src) as f:
        data = yaml.safe_load(f) or {}

    personas: list[dict[str, Any]] = []
    skip_keys = {"settings"}
    for category, entries in data.items():
        if category in skip_keys:
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry["_category"] = category
            personas.append(entry)
    return personas


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two sets."""
    if not a and not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union) if union else 0.0


def route_personas(
    query_bridges: list[str],
    top_k: int = 3,
    min_overlap: float = 0.1,
    registry_path: Path | None = None,
) -> list[PersonaMatch]:
    """Select personas whose taxonomy_hints best match query bridges.

    Algorithm: Jaccard similarity between query bridge set and each
    persona's taxonomy_hints set, ranked descending.

    Args:
        query_bridges: Bridge attributes to match (e.g. ["Corruption", "Stealth"]).
        top_k: Maximum personas to return.
        min_overlap: Minimum Jaccard score to include.
        registry_path: Override persona registry path.

    Returns:
        Sorted list of PersonaMatch (best first).
    """
    personas = _load_persona_registry(registry_path)
    query_set = {b.strip() for b in query_bridges if b.strip()}

    if not query_set:
        return []

    matches: list[PersonaMatch] = []
    for p in personas:
        hints = p.get("taxonomy_hints", [])
        if not hints:
            continue
        hint_set = {str(h).strip() for h in hints}
        score = _jaccard(query_set, hint_set)
        if score < min_overlap:
            continue
        matched = sorted(query_set & hint_set)
        matches.append(
            PersonaMatch(
                persona_id=p.get("id", ""),
                name=p.get("name", ""),
                scope=p.get("scope", ""),
                category=p.get("_category", ""),
                bridge_overlap=round(score, 4),
                matched_bridges=matched,
                taxonomy_hints=list(hint_set),
                fictional=bool(p.get("fictional", False)),
            )
        )

    matches.sort(key=lambda m: (-m.bridge_overlap, m.persona_id))
    return matches[:top_k]


def route_personas_for_task(
    task: str,
    input_data: dict[str, Any],
    top_k: int = 3,
    registry_path: Path | None = None,
) -> list[PersonaMatch]:
    """Extract bridges from task/input, then route to personas.

    Tries taxonomy extraction first; falls back to task-name heuristics.

    Args:
        task: Task name (e.g. "vulnerability_triage", "qra-assessor").
        input_data: Task input data (may contain bridge hints).
        top_k: Max personas to return.
        registry_path: Override persona registry path.

    Returns:
        Sorted list of PersonaMatch.
    """
    bridges: set[str] = set()

    # Check input_data for explicit bridge tags
    for key in ("bridges", "bridge_tags", "taxonomy_hints"):
        if key in input_data:
            val = input_data[key]
            if isinstance(val, list):
                bridges.update(str(b) for b in val)

    # Task-name heuristic fallback
    if not bridges:
        task_bridge_map = {
            "vulnerability": {"Corruption", "Stealth", "Precision"},
            "security": {"Corruption", "Stealth", "Resilience"},
            "exploit": {"Corruption", "Stealth"},
            "defense": {"Resilience", "Precision"},
            "quality": {"Precision", "Fragility"},
            "qra": {"Precision", "Resilience"},
            "bond": {"Loyalty", "Resilience"},
            "persona": {"Loyalty", "Fragility"},
        }
        task_lower = task.lower()
        for keyword, bridge_set in task_bridge_map.items():
            if keyword in task_lower:
                bridges.update(bridge_set)

    # Try taxonomy extraction if available and still no bridges
    if not bridges:
        try:
            from .taxonomy import extract_taxonomy_features

            text = str(input_data.get("text", input_data.get("description", "")))
            if text:
                result = extract_taxonomy_features(text[:500])
                if result and hasattr(result, "bridges"):
                    bridges.update(result.bridges)
        except Exception as e:
            logger.debug("update failed: {}", e)

    if not bridges:
        bridges = {"Precision", "Resilience"}  # safe default

    return route_personas(
        list(bridges),
        top_k=top_k,
        registry_path=registry_path,
    )
