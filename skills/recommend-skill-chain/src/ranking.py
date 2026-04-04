"""Ranking, scoring, and shadow logging for skill chain recommendations.

Extracted from recommender.py to stay under 800 lines per best-practices-python.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger


def detect_orchestrator(chain: list[str], graph: dict | None) -> str | None:
    """Check if an existing skill already composes this chain."""
    if graph is None or "skills" not in graph:
        return None
    chain_set = set(chain)
    for skill_name, skill_info in graph["skills"].items():
        composes = set(skill_info.get("composes", []))
        if chain_set and chain_set.issubset(composes):
            return skill_name
    return None


def rank_candidates(
    candidates: list,
    task: str,
    *,
    graph: dict | None,
    predict_chain_success: Any = None,
    compute_chain_energy: Any = None,
    compute_elegance: Any = None,
) -> list:
    """Score and rank candidates using bond predictor + energy model.

    Returns list of RankedRecommendation (imported lazily to avoid circular deps).
    """
    try:
        from .recommender import ChainCandidate, RankedRecommendation
    except ImportError:
        from recommender import ChainCandidate, RankedRecommendation

    scored: list[tuple[float, RankedRecommendation]] = []

    for cand in candidates:
        if not cand.chain:
            continue

        # Deduplicate: skip if we already have the same chain
        chain_key = tuple(cand.chain)
        if any(tuple(r.chain) == chain_key for _, r in scored):
            continue

        # Bond prediction
        bond_score = cand.confidence
        elegance_grade = "adequate"
        energy_atp = 0.0
        bridge_tags: list[str] = []

        if predict_chain_success is not None and len(cand.chain) >= 2:
            try:
                bond_result = predict_chain_success(skills=cand.chain, graph=graph)
                bond_score = bond_result.get("success_probability", cand.confidence)
                for bond in bond_result.get("bonds", []):
                    bt = bond.get("bond_type", "")
                    if bt == "covalent":
                        bridge_tags.append("Precision")
                    elif bt == "ionic":
                        bridge_tags.append("Resilience")
                energy_data = bond_result.get("energy", {})
                elegance_data = bond_result.get("elegance", {})
                energy_atp = energy_data.get("total_energy", 0.0)
                elegance_grade = elegance_data.get("grade", "adequate")
            except Exception as e:
                logger.warning(f"Bond prediction failed for {cand.chain}: {e}")

        # Fallback: compute energy/elegance directly if bond_predictor didn't
        if energy_atp == 0.0 and compute_chain_energy is not None:
            try:
                energy_data = compute_chain_energy(skills=cand.chain, graph=graph)
                energy_atp = energy_data.get("total_energy", 0.0)
                if compute_elegance is not None:
                    elegance_data = compute_elegance(
                        chain_energy=energy_data,
                        success_probability=bond_score,
                    )
                    elegance_grade = elegance_data.get("grade", "adequate")
            except Exception as e:
                logger.debug(f"Energy computation failed: {e}")

        # Detect orchestrator
        orchestrator = detect_orchestrator(cand.chain, graph)

        # Composite score: bond_strength * elegance_multiplier
        elegance_multipliers = {
            "brilliant": 1.5, "elegant": 1.2, "adequate": 1.0,
            "wasteful": 0.8, "bloated": 0.6,
        }
        elegance_mult = elegance_multipliers.get(elegance_grade, 1.0)
        composite_score = bond_score * elegance_mult

        # Boost if an orchestrator already exists
        if orchestrator:
            composite_score *= 1.1

        rec = RankedRecommendation(
            rank=0,
            chain=cand.chain,
            orchestrator=orchestrator,
            confidence=round(bond_score, 3),
            tier=cand.tier,
            elegance=elegance_grade,
            energy_atp=round(energy_atp, 1),
            reason=cand.reason,
            bridge_tags=list(set(bridge_tags)) if bridge_tags else [],
        )
        scored.append((composite_score, rec))

    # Sort by composite score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    # Assign ranks
    for i, (_, rec) in enumerate(scored):
        rec.rank = i + 1

    return [rec for _, rec in scored]


# ---------------------------------------------------------------------------
# Shadow logging
# ---------------------------------------------------------------------------
def log_recommendation(
    task: str,
    recommendations: list,
    recommendations_log: Path,
    model: str | None = None,
):
    """Log recommendation to recommendations.jsonl for self-improvement."""
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": task,
            "model_requested": model,
            "recommendations": [
                {
                    "rank": r.rank,
                    "chain": r.chain,
                    "confidence": r.confidence,
                    "tier": r.tier,
                    "elegance": r.elegance,
                }
                for r in recommendations
            ],
        }
        with open(recommendations_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug(f"Failed to log recommendation: {e}")


def log_shadow_comparison(
    task: str,
    candidates: list,
    shadow_log: Path,
):
    """Log shadow comparison summary from cascade results."""
    cascade_shadow = Path.home() / ".pi" / "assistant" / "shadow.jsonl"
    if not cascade_shadow.exists():
        return

    try:
        lines = cascade_shadow.read_text().strip().split("\n")
        if not lines:
            return
        last = json.loads(lines[-1])
        if last.get("task") != "skill-chain-router":
            return

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": task,
            "classifier_prediction": last.get("local_grade", last.get("student_prediction")),
            "teacher_prediction": last.get("teacher_grade", last.get("teacher_prediction")),
            "agreement": last.get("agreed", False),
            "cascade_tier": last.get("tier"),
            "source": "cascade_shadow",
        }
        with open(shadow_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug(f"Failed to log shadow comparison: {e}")
