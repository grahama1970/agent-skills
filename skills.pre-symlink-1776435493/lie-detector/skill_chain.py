"""Layer 0: Skill chain routing via /recommend-skill-chain.

Purpose:
    Determine which verification layers to run for a given iteration context.
    The audited agent does NOT choose its own auditors — /memory routes the
    skill chain based on what changed, not on the agent's preference.

Inputs:
    - Iteration context dict (summary, files_modified, score_delta)

Outputs:
    - Ordered list of layer names to execute

Failure modes:
    - /memory unavailable → return all layers (conservative default)
    - Skill routing returns empty → return all layers
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from dotenv import find_dotenv, load_dotenv
from loguru import logger

load_dotenv(find_dotenv(usecwd=True), override=False)

MEMORY_PATH = Path(os.getenv(
    "MEMORY_SKILL_PATH",
    str(Path(__file__).resolve().parents[1] / "memory"),
))

ALL_LAYERS = ["seal", "prove", "conform", "taxonomy", "classify", "llm_audit"]

# Heuristic routing rules when /memory is unavailable
ROUTING_RULES: list[tuple[str, list[str]]] = [
    # (condition_keyword, layers_to_include)
    ("scoring", ALL_LAYERS),
    ("grading", ALL_LAYERS),
    ("eval", ALL_LAYERS),
    ("threshold", ["seal", "prove", "conform", "llm_audit"]),
    ("extraction", ["seal", "conform", "classify"]),
    ("table", ["seal", "conform", "classify"]),
    ("section", ["seal", "conform", "classify"]),
    ("re-ran", ["seal"]),
    ("re-run", ["seal"]),
    ("no changes", ["seal"]),
]


def _call_memory_routing(context_summary: str) -> list[str] | None:
    """Ask /memory for skill routing based on iteration context."""
    query = f"verify grading integrity: {context_summary}"
    try:
        result = subprocess.run(
            ["bash", str(MEMORY_PATH / "run.sh"), "recall",
             "--q", query, "--scope", "lie_detection"],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode != 0:
            return None

        stdout = result.stdout.strip()
        idx = stdout.find("{")
        if idx < 0:
            return None

        data = json.loads(stdout[idx:])
        skill_route = data.get("skill_route", [])
        if not skill_route:
            return None

        # Map skill names to layer names
        layer_map = {
            "lie-detector/sealed_grading": "seal",
            "lean4-prove": "prove",
            "lie-detector/delta_analysis": "conform",
            "lie-detector/taxonomy_check": "taxonomy",
            "lie-detector/classifier": "classify",
            "assistant validate": "llm_audit",
        }
        layers = []
        for skill in skill_route:
            for skill_name, layer_name in layer_map.items():
                if skill_name in skill.lower() or layer_name in skill.lower():
                    if layer_name not in layers:
                        layers.append(layer_name)
        return layers if layers else None

    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        logger.warning("skill chain routing failed: {}", e)
        return None


def _heuristic_routing(context_summary: str) -> list[str]:
    """Fallback: route based on keyword matching in context."""
    summary_lower = context_summary.lower()
    for keyword, layers in ROUTING_RULES:
        if keyword in summary_lower:
            return layers
    # Default: run seal + conform + classify (medium path)
    return ["seal", "conform", "classify"]


def get_verification_chain(context: dict[str, Any]) -> list[str]:
    """Determine which verification layers to run for this iteration.

    First tries /memory routing. Falls back to heuristic rules. Falls back
    to running all layers (conservative).
    """
    summary = context.get("summary", "")
    files_modified = context.get("files_modified", [])
    score_delta = context.get("score_delta", 0.0)

    # Enrich summary with file and score info
    enriched = summary
    if files_modified:
        enriched += f" | files: {', '.join(str(f) for f in files_modified[:5])}"
    if score_delta:
        enriched += f" | score_delta: {score_delta:+.2f}"

    # Try /memory routing
    layers = _call_memory_routing(enriched)
    if layers:
        logger.info("skill chain from /memory: {}", layers)
        return layers

    # Heuristic fallback
    layers = _heuristic_routing(enriched)
    logger.info("skill chain from heuristics: {}", layers)

    # Force-include "seal" for any scoring-related changes
    if any("scor" in str(f).lower() or "grad" in str(f).lower() for f in files_modified):
        if "prove" not in layers:
            layers.insert(1, "prove")
        if "llm_audit" not in layers:
            layers.append("llm_audit")

    # Force-include all layers for large score jumps
    if abs(score_delta) > 0.10:
        layers = ALL_LAYERS
        logger.warning("large score delta ({:+.2f}) → running ALL layers", score_delta)

    return layers
