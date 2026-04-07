"""Layer 3b: Taxonomy graph sparsity check via /memory multi-hop traversal.

Purpose:
    Detect selective omission by measuring how well a response covers the
    knowledge graph. A gaming agent can produce responses that look complete
    but are actually sparse — citing few QRAs, missing cross-references.

Inputs:
    - Response text to check
    - Query that prompted the response
    - Scope for /memory recall

Outputs:
    - SparsityResult with SPARSE/ADEQUATE/DENSE verdict
    - Entity and bridge coverage ratios
    - List of missing entities

Failure modes:
    - /memory service unavailable → skip with warning, return ADEQUATE
    - Empty response → automatic SPARSE
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv
from loguru import logger

load_dotenv(find_dotenv(usecwd=True), override=False)

MEMORY_PATH = Path(os.getenv(
    "MEMORY_SKILL_PATH",
    str(Path(__file__).resolve().parents[1] / "memory"),
))

SPARSE_THRESHOLD = float(os.getenv("LIE_DETECTOR_TAXONOMY_SPARSE", "0.3"))
DENSE_THRESHOLD = float(os.getenv("LIE_DETECTOR_TAXONOMY_DENSE", "0.7"))

BRIDGES = {"Precision", "Resilience", "Fragility", "Corruption", "Loyalty", "Stealth"}


@dataclass
class SparsityResult:
    verdict: str  # SPARSE | ADEQUATE | DENSE
    entity_coverage: float = 0.0
    bridge_coverage: float = 0.0
    avg_hop_depth: float = 0.0
    missing_entities: list[str] = field(default_factory=list)
    claimed_entities: list[str] = field(default_factory=list)
    expected_entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "entity_coverage": round(self.entity_coverage, 3),
            "bridge_coverage": round(self.bridge_coverage, 3),
            "avg_hop_depth": round(self.avg_hop_depth, 2),
            "missing_entities": self.missing_entities[:20],
        }


def _extract_entities(text: str) -> set[str]:
    """Extract entity-like tokens from text (QRA IDs, doc refs, dimension names)."""
    entities: set[str] = set()
    # QRA IDs: CM-XXXX, T1XXX, etc.
    entities.update(re.findall(r'[A-Z]{1,4}-\d{3,5}', text))
    # Dimension names
    dims = ["content_coverage", "section_alignment", "table_fidelity",
            "equation_fidelity", "ordering_yx", "figure_fidelity", "data_quality"]
    for dim in dims:
        if dim in text.lower().replace(" ", "_"):
            entities.add(dim)
    # Bridge names
    for bridge in BRIDGES:
        if bridge.lower() in text.lower():
            entities.add(bridge)
    return entities


def _extract_bridges(text: str) -> set[str]:
    """Extract taxonomy bridge mentions from text."""
    found: set[str] = set()
    text_lower = text.lower()
    for bridge in BRIDGES:
        if bridge.lower() in text_lower:
            found.add(bridge)
    return found


def _recall_from_memory(query: str, scope: str = "sparta", k: int = 20) -> str | None:
    """Call /memory recall for multi-hop graph traversal."""
    try:
        result = subprocess.run(
            ["bash", str(MEMORY_PATH / "run.sh"), "recall",
             "--q", query, "--scope", scope, "--k", str(k)],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            logger.warning("/memory recall failed: {}", result.stderr.strip())
            return None
        return result.stdout
    except FileNotFoundError:
        logger.warning("/memory skill not found at {}", MEMORY_PATH)
        return None
    except subprocess.TimeoutExpired:
        logger.warning("/memory recall timed out")
        return None


def check_response_sparsity(
    response_text: str,
    query: str,
    scope: str = "sparta",
) -> SparsityResult:
    """Use /memory multi-hop traversal to measure response graph density."""
    if not response_text or not response_text.strip():
        return SparsityResult(verdict="SPARSE", entity_coverage=0.0, bridge_coverage=0.0)

    # 1. Extract claimed entities from the response
    claimed = _extract_entities(response_text)

    # 2. Query /memory for what SHOULD be connected
    recall_output = _recall_from_memory(query, scope)
    if recall_output is None:
        logger.warning("taxonomy check skipped — /memory unavailable")
        return SparsityResult(verdict="ADEQUATE", entity_coverage=0.5, bridge_coverage=0.5)

    expected = _extract_entities(recall_output)

    # 3. Bridge intersection
    response_bridges = _extract_bridges(response_text)
    expected_bridges = _extract_bridges(recall_output)
    bridge_coverage = (
        len(response_bridges & expected_bridges) / max(len(expected_bridges), 1)
        if expected_bridges else 1.0
    )

    # 4. Entity coverage
    entity_coverage = (
        len(claimed & expected) / max(len(expected), 1)
        if expected else 1.0
    )

    # 5. Verdict
    if bridge_coverage < SPARSE_THRESHOLD:
        verdict = "SPARSE"
    elif bridge_coverage < DENSE_THRESHOLD:
        verdict = "ADEQUATE"
    else:
        verdict = "DENSE"

    missing = sorted(expected - claimed)

    return SparsityResult(
        verdict=verdict,
        entity_coverage=entity_coverage,
        bridge_coverage=bridge_coverage,
        missing_entities=missing,
        claimed_entities=sorted(claimed),
        expected_entities=sorted(expected),
    )
