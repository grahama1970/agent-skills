"""Chain prediction, execution trace logging, and memory sync for bond predictor.

Provides:
- predict_chain_success: Predict success probability of a full skill pipeline
- log_execution_trace: Log bidirectional execution traces for training
- sync_bonds_to_memory: Sync top bond metrics to /memory for cross-agent recall
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from bond_types import (
    BondFeatures,
    SKILLS_DIR,
    TRACES_FILE,
    append_jsonl,
    extract_features,
)
from bond_tiers import tier0_heuristic
from energy_model import compute_chain_energy, compute_elegance

# Import CascadeRunner with fallback
sys.path.insert(0, str(SKILLS_DIR / "common"))
try:
    from cascade import CascadeRunner
except ImportError:
    CascadeRunner = None  # type: ignore


# ---------------------------------------------------------------------------
# Chain prediction -- predict success of full skill pipeline
# ---------------------------------------------------------------------------

def predict_chain_success(
    skills: list[str],
    graph: dict | None = None,
    runner: "CascadeRunner | None" = None,
) -> dict:
    """Predict success probability of a skill chain.

    Computes:
    1. Pairwise bond predictions (type + probability)
    2. Chain success probability (product of bonds)
    3. Metabolic energy cost (ATP units)
    4. Elegance score (success / energy -- rewards parsimony)
    """
    if len(skills) < 2:
        energy = compute_chain_energy(skills, graph)
        elegance = compute_elegance(energy, 1.0)
        return {
            "success_probability": 1.0,
            "bonds": [],
            "chain": skills,
            "energy": energy,
            "elegance": elegance,
        }

    bonds = []
    chain_prob = 1.0

    for i in range(len(skills) - 1):
        a, b = skills[i], skills[i + 1]
        features = extract_features(a, b, graph)
        input_data = {"features": features, "graph": graph}

        if runner:
            result = runner.run(input_data, task="bond_predict", scope="skill-lab")
        else:
            result = tier0_heuristic(input_data)

        bond = {
            "from": a,
            "to": b,
            "bond_type": result.result.get("bond_type", "none") if result else "none",
            "success_probability": result.result.get("success_probability", 0.1) if result else 0.1,
            "confidence": result.confidence if result else 0.0,
            "tier": result.tier if result else 0,
        }
        bonds.append(bond)

        # Chain probability = product of pairwise probabilities
        chain_prob *= bond["success_probability"]

    # Compute energy and elegance
    energy = compute_chain_energy(skills, graph)
    elegance = compute_elegance(energy, chain_prob)

    return {
        "chain": skills,
        "success_probability": round(chain_prob, 4),
        "bonds": bonds,
        "weakest_bond": min(bonds, key=lambda b: b["success_probability"]) if bonds else None,
        "energy": energy,
        "elegance": elegance,
    }


# ---------------------------------------------------------------------------
# Execution trace logging -- feeds back into training
# ---------------------------------------------------------------------------

def log_execution_trace(
    skills: list[str],
    success: bool,
    latency_ms: float = 0.0,
    error: str = "",
) -> None:
    """Log a skill chain execution for future training.

    Called after composer.py executes a pipeline.

    BFF alignment: Both A and B are modified during interaction
    (A+B -> exec(AB) -> A'+B'). We log bidirectional pairs -- the
    forward pair (A->B) at full weight, and the reverse pair (B->A)
    at 0.7x weight (B learned from A but didn't drive the chain).
    """
    TRACES_FILE.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    chain_hash = hashlib.md5("->".join(skills).encode()).hexdigest()[:8]

    # Log pairwise traces -- both forward and reverse (bidirectional)
    trace_entries = []
    for i in range(len(skills) - 1):
        a, b = skills[i], skills[i + 1]

        # Forward pair (A->B) -- full weight
        trace_entries.append({
            "pair": f"{a}+{b}",
            "chain": skills,
            "success": success,
            "latency_ms": round(latency_ms, 1),
            "error": error[:200] if error else "",
            "timestamp": now,
            "chain_hash": chain_hash,
            "direction": "forward",
            "bidirectional": True,
        })

        # Reverse pair (B->A) -- 0.7x weight on success
        # B learned from A but didn't drive the interaction
        trace_entries.append({
            "pair": f"{b}+{a}",
            "chain": skills,
            "success": success,
            "latency_ms": round(latency_ms * 0.7, 1),
            "error": error[:200] if error else "",
            "timestamp": now,
            "chain_hash": chain_hash,
            "direction": "reverse",
            "bidirectional": True,
            "weight": 0.7,
        })

    append_jsonl(TRACES_FILE, trace_entries)


# ---------------------------------------------------------------------------
# Bond metrics sync to /memory
# ---------------------------------------------------------------------------

def sync_bonds_to_memory(top_n: int = 20) -> int:
    """Sync top bond metrics to /memory for cross-agent recall.

    Enables queries like: "what composes well with extractor?"
    -> "review-pdf (covalent, 0.92 success, 15 observations)"
    """
    if not TRACES_FILE.exists():
        return 0

    try:
        from scan_soup import _memory_learn
    except ImportError:
        return 0

    # Aggregate traces by pair
    pair_stats: dict[str, dict] = {}
    for line in TRACES_FILE.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("direction") == "reverse":
                continue
            pair = entry.get("pair", "")
            if "+" not in pair:
                continue
            if pair not in pair_stats:
                pair_stats[pair] = {"successes": 0, "total": 0, "latencies": []}
            pair_stats[pair]["total"] += 1
            if entry.get("success"):
                pair_stats[pair]["successes"] += 1
            lat = entry.get("latency_ms", 0)
            if lat > 0:
                pair_stats[pair]["latencies"].append(lat)
        except (json.JSONDecodeError, KeyError):
            continue

    # Sort by (success_rate * observation_count), take top N
    ranked = sorted(
        pair_stats.items(),
        key=lambda kv: (kv[1]["successes"] / max(1, kv[1]["total"])) * kv[1]["total"],
        reverse=True,
    )[:top_n]

    synced = 0
    for pair, stats in ranked:
        if stats["total"] < 2:
            continue
        skills = pair.split("+")
        success_rate = stats["successes"] / stats["total"]
        mean_latency = (
            sum(stats["latencies"]) / len(stats["latencies"])
            if stats["latencies"] else 0
        )
        confidence = min(0.95, 0.4 + stats["total"] * 0.03)

        # Determine bond type from success rate
        if success_rate >= 0.8:
            bond_type = "covalent"
        elif success_rate >= 0.5:
            bond_type = "ionic"
        elif success_rate >= 0.2:
            bond_type = "van_der_waals"
        else:
            bond_type = "none"

        problem = f"bond: {skills[0]} composes well with {skills[1]}"
        solution = json.dumps({
            "bond_type": bond_type,
            "success_rate": round(success_rate, 3),
            "observations": stats["total"],
            "mean_latency_ms": round(mean_latency, 1),
            "confidence": round(confidence, 3),
        })
        tags = ["bond", f"skill:{skills[0]}", f"skill:{skills[1]}", bond_type]

        if _memory_learn(problem, solution, tags):
            synced += 1

    return synced
