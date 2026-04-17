#!/usr/bin/env python3
"""Energy model — metabolic cost of skill composition.

Extracted from bond_predictor.py to keep files under 800 lines.

Provides:
- ENERGY_COSTS: base energy cost per skill (ATP units)
- estimate_skill_energy(): energy cost for a single skill
- compute_chain_energy(): total metabolic cost of a skill chain
- compute_elegance(): elegance score (success / energy)
- update_learned_energy(): learn energy from execution traces
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
STATE_DIR = SCRIPTS_DIR.parent / "state"
STATE_DIR.mkdir(exist_ok=True)

LEARNED_ENERGY_FILE = STATE_DIR / "learned_energy.json"
ATTRACTORS_FILE = STATE_DIR / "attractors.json"
TRACES_FILE = STATE_DIR / "execution_traces.jsonl"

# ---------------------------------------------------------------------------
# Base energy cost per skill (ATP units)
# Measured/estimated from: script count, typical compute time, subprocess overhead
# Lower = more efficient. Skills with run.sh + many scripts cost more.
# ---------------------------------------------------------------------------

ENERGY_COSTS: dict[str, float] = {
    # Lightweight (1-2 ATP) — simple, fast, low overhead
    "memory":         1.0,
    "taxonomy":       1.0,
    "normalize":      1.0,
    "edge-verifier":  1.5,
    "embedding":      1.5,
    "task-monitor":   1.0,

    # Medium (3-5 ATP) — moderate compute, some I/O
    "extractor":      4.0,
    "brave-search":   3.0,
    "arxiv":          3.0,
    "fetcher":        3.5,
    "review-pdf":     5.0,
    "plan":           3.0,
    "orchestrate":    3.0,
    "interview":      2.0,

    # Heavy (6-10 ATP) — significant compute, LLM calls, Docker
    "doc2qra":        7.0,
    "extractor":      7.0,
    "dogpile":        8.0,
    "scillm":         6.0,
    "codex":          8.0,
    "hack":           9.0,
    "battle":        10.0,
    "anvil":          8.0,

    # Lab skills (5-8 ATP) — creation is expensive
    "prompt-lab":     5.0,
    "gpt-lab":        6.0,
    "classifier-lab": 7.0,
    "create-gpt":     8.0,
    "create-classifier": 7.0,
}

# Default for unknown skills
DEFAULT_ENERGY = 4.0

# Elegance thresholds
ELEGANCE_THRESHOLDS = {
    "brilliant":  0.80,  # top tier — minimal energy, high success
    "elegant":    0.60,  # good — efficient and effective
    "adequate":   0.40,  # acceptable — gets the job done
    "wasteful":   0.20,  # inefficient — too many steps
    "bloated":    0.00,  # anti-pattern — Rube Goldberg
}


def update_learned_energy() -> dict:
    """Learn energy costs from execution trace data.

    BFF alignment: No explicit fitness — energy emerges from execution dynamics.

    Formula:
        learned_energy(skill) = base_from_latency + failure_penalty + depth_penalty

    where:
        base_from_latency = log2(mean_latency_ms + 1)    # 100ms → 6.6 ATP
        failure_penalty   = (1 - success_rate) * 5         # 50% fail → +2.5 ATP
        depth_penalty     = len(composes) * 0.3            # 10 deps → +3.0 ATP
    """
    if not TRACES_FILE.exists():
        return {"status": "no_traces", "skills": {}}

    # Aggregate traces per skill
    skill_stats: dict[str, dict] = {}
    for line in TRACES_FILE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            # Skip reverse traces for energy calculation (avoid double counting)
            if entry.get("direction") == "reverse":
                continue
            pair = entry.get("pair", "")
            if "+" not in pair:
                continue
            for skill in pair.split("+"):
                if skill not in skill_stats:
                    skill_stats[skill] = {"latencies": [], "successes": 0, "total": 0}
                skill_stats[skill]["total"] += 1
                if entry.get("success"):
                    skill_stats[skill]["successes"] += 1
                lat = entry.get("latency_ms", 0)
                if lat > 0:
                    skill_stats[skill]["latencies"].append(lat)
        except (json.JSONDecodeError, KeyError):
            continue

    # Compute learned energy per skill
    learned: dict[str, float] = {}
    for skill, stats in skill_stats.items():
        if stats["total"] < 2:
            continue  # Need at least 2 data points

        # Base from latency: log2(mean_latency_ms + 1)
        mean_latency = (
            sum(stats["latencies"]) / len(stats["latencies"])
            if stats["latencies"] else 100.0
        )
        base_from_latency = math.log2(mean_latency + 1)

        # Failure penalty: (1 - success_rate) * 5
        success_rate = stats["successes"] / stats["total"] if stats["total"] else 0.5
        failure_penalty = (1 - success_rate) * 5

        # Depth penalty: approximated from composes count (if graph available)
        # For now, use 0 — will be enriched by caller with graph data
        depth_penalty = 0.0

        energy = base_from_latency + failure_penalty + depth_penalty
        learned[skill] = round(energy, 2)

    # Save learned energy
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "skills": learned,
        "source_traces": sum(s["total"] for s in skill_stats.values()),
    }
    LEARNED_ENERGY_FILE.write_text(json.dumps(result, indent=2))

    return result


def _load_learned_energy() -> dict[str, float]:
    """Load learned energy values from file."""
    if not LEARNED_ENERGY_FILE.exists():
        return {}
    try:
        data = json.loads(LEARNED_ENERGY_FILE.read_text())
        return data.get("skills", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def estimate_skill_energy(skill_name: str, graph: dict | None = None) -> float:
    """Estimate energy cost (ATP) for a single skill.

    BFF alignment: Checks learned energy from real execution data FIRST,
    falls back to hand-tuned ENERGY_COSTS when no trace data exists.

    Factors:
    1. Learned energy from execution traces (preferred)
    2. Base cost from ENERGY_COSTS table (fallback)
    3. Script count (more scripts = more complexity)
    4. Composition depth (skills that compose many others are heavier)
    """
    # Check learned energy first (BFF: implicit fitness from dynamics)
    learned = _load_learned_energy()
    if skill_name in learned:
        base = learned[skill_name]
    else:
        base = ENERGY_COSTS.get(skill_name, DEFAULT_ENERGY)

    if graph:
        info = graph.get("skills", {}).get(skill_name, {})

        # Depth penalty for composition count (transitive dependencies)
        composes_count = len(info.get("composes", []))
        if composes_count > 5:
            base += (composes_count - 5) * 0.5  # +0.5 per extra dependency

        # Script count proxy (from path — count .py/.sh files)
        skill_path = info.get("path", "")
        if skill_path:
            p = Path(skill_path)
            if p.exists():
                scripts = list(p.glob("scripts/*.py")) + list(p.glob("scripts/*.sh"))
                if len(scripts) > 5:
                    base += (len(scripts) - 5) * 0.3  # +0.3 per extra script

    return round(base, 1)


def compute_chain_energy(skills: list[str], graph: dict | None = None) -> dict:
    """Compute total metabolic cost of a skill chain.

    Returns energy breakdown and elegance score.
    """
    per_skill = []
    total_energy = 0.0

    for skill in skills:
        energy = estimate_skill_energy(skill, graph)
        per_skill.append({"skill": skill, "energy": energy})
        total_energy += energy

    # Chain overhead: each handoff costs 0.5 ATP (serialization, subprocess)
    handoff_cost = (len(skills) - 1) * 0.5 if len(skills) > 1 else 0
    total_energy += handoff_cost

    # Length penalty: exponential cost for chains > 3 skills
    # Biology: long metabolic pathways are fragile and wasteful
    length_penalty = 0.0
    if len(skills) > 3:
        length_penalty = (len(skills) - 3) ** 1.5  # Superlinear penalty
        total_energy += length_penalty

    # Granularity penalty: coarse-grained skills cost more to compose
    # BFF SUBLEQ lesson: instruction density matters for effective composition
    granularity_penalty = 0.0
    if graph:
        for skill in skills:
            score = graph.get("skills", {}).get(skill, {}).get("composability_score", 1.0)
            if score < 0.3:
                granularity_penalty += 2.0  # +2 ATP per coarse skill
        total_energy += granularity_penalty

    return {
        "total_energy": round(total_energy, 1),
        "per_skill": per_skill,
        "handoff_cost": round(handoff_cost, 1),
        "length_penalty": round(length_penalty, 1),
        "granularity_penalty": round(granularity_penalty, 1),
        "skill_count": len(skills),
    }


def compute_elegance(
    chain_energy: "dict | float",
    success_probability: float,
) -> dict:
    """Score the elegance of a skill composition.

    Elegance = success_probability / normalized_energy

    Like biological fitness: maximize output, minimize metabolic cost.
    The most elegant solution achieves the goal with minimum energy.

    Args:
        chain_energy: Either the full dict from compute_chain_energy() (preferred),
            or a bare float total_energy value (legacy call sites — handled defensively).
        success_probability: Chain success probability in [0, 1].
    """
    from loguru import logger

    if isinstance(chain_energy, (int, float)):
        # Caller passed total_energy directly instead of the full dict.
        # Reconstruct a minimal dict so downstream logic stays consistent.
        logger.warning(
            "compute_elegance received a float ({}) instead of a dict — "
            "wrapping defensively. Fix the call site.",
            chain_energy,
        )
        chain_energy = {
            "total_energy": float(chain_energy),
            "skill_count": 1,
        }

    total_energy = chain_energy["total_energy"]
    skill_count = chain_energy["skill_count"]

    # Normalize energy to 0-1 scale (30 ATP = max reasonable pipeline)
    normalized_energy = min(total_energy / 30.0, 1.0)

    # Elegance = success / energy (higher = better)
    # A 2-skill chain with 90% success is more elegant than
    # a 6-skill chain with 95% success
    if normalized_energy > 0:
        raw_elegance = success_probability / (normalized_energy + 0.1)
    else:
        raw_elegance = success_probability

    # Clamp to 0-1
    elegance_score = min(1.0, max(0.0, raw_elegance))

    # Brevity bonus: reward shorter chains that achieve similar success
    # 2 skills = 1.2x, 3 skills = 1.0x, 4+ skills = diminishing
    brevity_multiplier = max(0.5, 1.0 + (3 - skill_count) * 0.1)
    elegance_score = min(1.0, elegance_score * brevity_multiplier)

    # Determine grade
    grade = "bloated"
    for label, threshold in ELEGANCE_THRESHOLDS.items():
        if elegance_score >= threshold:
            grade = label
            break

    return {
        "elegance_score": round(elegance_score, 3),
        "grade": grade,
        "total_energy_atp": chain_energy["total_energy"],
        "normalized_energy": round(normalized_energy, 3),
        "brevity_multiplier": round(brevity_multiplier, 2),
        "success_probability": round(success_probability, 3),
    }
