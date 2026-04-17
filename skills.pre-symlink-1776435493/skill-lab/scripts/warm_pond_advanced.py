#!/usr/bin/env python3
"""Advanced warm pond features — convergence, curriculum, mutation, archive wiring.

Extracted to keep warm_pond.py under 800 lines. Houses:
- 3-signal convergence detection with tiered restart
- BADGE-lite active learning (uncertainty + diversity)
- Automatic curriculum (unlock chain lengths by success rate)
- Directed mutation via scillm failure analysis
- Archive integration (MAP-Elites, skill library, cost surrogate)

Usage:
    from warm_pond_advanced import (
from loguru import logger
        detect_convergence_signals, tiered_restart,
        badge_sample, CurriculumTracker,
        directed_mutation, update_archives, should_skip_chain,
    )
"""
from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).parent
STATE_DIR = SCRIPTS_DIR.parent / "state"
STATE_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Priority 3: 3-signal convergence + tiered restart
# ---------------------------------------------------------------------------

def detect_convergence_signals(
    session_results: list[dict],
    window: int = 20,
    initial_diversity: float | None = None,
) -> dict:
    """3-signal convergence detection.

    Signal A: Fitness stall — success rate change < 1% over window
    Signal B: Population diversity drop below 20% of initial
    Signal C: Component sharing — top-5 chains share > 80% skills

    Returns dict with signal states and recommended restart tier.
    """
    if len(session_results) < window:
        return {
            "signals": {"fitness_stall": False, "diversity_drop": False, "component_sharing": False},
            "active_count": 0,
            "restart_tier": "none",
            "rolling_success_rate": 0.0,
            "chain_diversity": 1.0,
        }

    recent = session_results[-window:]
    prior = (
        session_results[-2 * window:-window]
        if len(session_results) >= 2 * window
        else session_results[:window]
    )

    # Signal A: fitness stall
    recent_rate = sum(1 for r in recent if r.get("success")) / len(recent)
    prior_rate = sum(1 for r in prior if r.get("success")) / len(prior)
    fitness_stall = abs(recent_rate - prior_rate) < 0.01

    # Chain diversity (Shannon entropy)
    chain_sigs = ["+".join(sorted(r.get("chain", []))) for r in recent]
    sig_counts: dict[str, int] = {}
    for sig in chain_sigs:
        sig_counts[sig] = sig_counts.get(sig, 0) + 1
    total = len(chain_sigs)
    diversity = 0.0
    for count in sig_counts.values():
        p = count / total
        if p > 0:
            diversity -= p * math.log2(p)

    # Signal B: diversity drop
    diversity_threshold = (initial_diversity or 3.0) * 0.2
    diversity_drop = diversity < diversity_threshold

    # Signal C: component sharing in top-5
    successful = [r for r in recent if r.get("success")]
    component_sharing = False
    if len(successful) >= 5:
        top5_chains = [set(r["chain"]) for r in successful[-5:]]
        all_skills = set()
        for c in top5_chains:
            all_skills |= c
        if all_skills:
            shared = set.intersection(*top5_chains) if top5_chains else set()
            sharing_ratio = len(shared) / len(all_skills)
            component_sharing = sharing_ratio > 0.8

    signals = {
        "fitness_stall": fitness_stall,
        "diversity_drop": diversity_drop,
        "component_sharing": component_sharing,
    }
    active_count = sum(signals.values())

    # Determine restart tier
    if active_count >= 3:
        restart_tier = "severe"
    elif active_count == 2:
        restart_tier = "moderate"
    elif active_count == 1:
        restart_tier = "mild"
    else:
        restart_tier = "none"

    return {
        "signals": signals,
        "active_count": active_count,
        "restart_tier": restart_tier,
        "rolling_success_rate": round(recent_rate, 4),
        "chain_diversity": round(diversity, 4),
    }


def tiered_restart(
    restart_tier: str,
    session_results: list[dict],
    skill_names: list[str],
    mutation_rate: float,
) -> dict[str, Any]:
    """Apply tiered restart response to combat convergence.

    Tiers:
    - mild: 2x mutation rate
    - moderate: inject 30% random immigrants, 3x mutation rate
    - severe: full restart preserving Pareto front members

    Returns updated parameters.
    """
    if restart_tier == "mild":
        return {
            "mutation_rate": min(1.0, mutation_rate * 2),
            "immigrants": [],
            "reset_results": False,
        }
    elif restart_tier == "moderate":
        # Inject random immigrants (30% of population)
        n_immigrants = max(1, len(skill_names) // 3)
        immigrants = []
        for _ in range(n_immigrants):
            chain_len = random.randint(2, min(4, len(skill_names)))
            immigrants.append(random.sample(skill_names, chain_len))
        return {
            "mutation_rate": min(1.0, mutation_rate * 3),
            "immigrants": immigrants,
            "reset_results": False,
        }
    elif restart_tier == "severe":
        # Full restart — preserve Pareto front entries from archives
        return {
            "mutation_rate": mutation_rate,
            "immigrants": [],
            "reset_results": True,
        }
    return {
        "mutation_rate": mutation_rate,
        "immigrants": [],
        "reset_results": False,
    }


# ---------------------------------------------------------------------------
# Priority 4: BADGE-lite active learning
# ---------------------------------------------------------------------------

def badge_sample(
    skill_names: list[str],
    chain_len: int,
    batch_size: int = 5,
) -> list[str] | None:
    """BADGE-lite: uncertainty + diversity sampling.

    1. Compute predict_proba entropy for candidate pairs (uncertainty)
    2. Select diverse batch via k-means++ initialization in feature space
    3. Return one chain from the diverse batch

    Falls back to None if no classifier available.
    """
    classifier_path = STATE_DIR / "bond_classifier.pkl"
    if not classifier_path.exists():
        return None

    try:
        import pickle
        import numpy as np
        from bond_predictor import extract_features

        with open(classifier_path, "rb") as f:
            model = pickle.load(f)

        # Sample candidate pairs
        sample_skills = random.sample(skill_names, min(25, len(skill_names)))
        candidates: list[tuple[float, list[float], list[str]]] = []

        for i, a in enumerate(sample_skills):
            for b in sample_skills[i + 1:]:
                features = extract_features(a, b)
                vector = features.to_vector()
                proba = model.predict_proba([vector])[0]
                entropy = -sum(p * np.log2(p + 1e-10) for p in proba)
                candidates.append((entropy, vector, [a, b]))

        if not candidates:
            return None

        # Sort by entropy descending
        candidates.sort(key=lambda x: -x[0])

        # Take top-20 most uncertain for diversity selection
        pool = candidates[:20]
        if len(pool) <= batch_size:
            chosen = random.choice(pool)
            return _extend_chain(chosen[2], skill_names, chain_len)

        # k-means++ style diversity selection in feature space
        selected_indices = [0]  # Start with most uncertain
        vectors = np.array([c[1] for c in pool])

        for _ in range(batch_size - 1):
            # Compute min distance to already-selected
            min_dists = np.full(len(pool), np.inf)
            for idx in selected_indices:
                dists = np.sum((vectors - vectors[idx]) ** 2, axis=1)
                min_dists = np.minimum(min_dists, dists)

            # Zero out already selected
            for idx in selected_indices:
                min_dists[idx] = 0.0

            # Select point with max min-distance (farthest from selected)
            if min_dists.max() > 0:
                next_idx = int(np.argmax(min_dists))
                selected_indices.append(next_idx)

        # Pick random from diverse batch
        chosen_idx = random.choice(selected_indices)
        pair = pool[chosen_idx][2]
        return _extend_chain(pair, skill_names, chain_len)

    except Exception:
        return None


def _extend_chain(pair: list[str], skill_names: list[str], chain_len: int) -> list[str]:
    """Extend a 2-skill pair to desired chain length."""
    chain = list(pair)
    remaining = [s for s in skill_names if s not in chain]
    while len(chain) < chain_len and remaining:
        chain.append(remaining.pop(random.randint(0, len(remaining) - 1)))
    return chain


# ---------------------------------------------------------------------------
# Priority 5: Automatic curriculum
# ---------------------------------------------------------------------------

class CurriculumTracker:
    """Track success rates per chain length to auto-unlock complexity.

    Only unlock chain_length k+1 when success_rate(k) > threshold.
    """

    def __init__(self, threshold: float = 0.6, initial_max: int = 2) -> None:
        self.threshold = threshold
        self.initial_max = initial_max
        self.stats: dict[int, dict[str, int]] = {}  # {length: {success: N, total: N}}
        self.unlocked_max: int = initial_max

    def record(self, chain_length: int, success: bool) -> None:
        """Record an observation."""
        if chain_length not in self.stats:
            self.stats[chain_length] = {"success": 0, "total": 0}
        self.stats[chain_length]["total"] += 1
        if success:
            self.stats[chain_length]["success"] += 1

    def update_unlocked(self, absolute_max: int) -> int:
        """Recompute unlocked max chain length.

        Returns the new unlocked_max.
        """
        current = self.initial_max
        while current < absolute_max:
            s = self.stats.get(current)
            if s and s["total"] >= 10:
                rate = s["success"] / s["total"]
                if rate >= self.threshold:
                    current += 1
                else:
                    break
            else:
                break  # Not enough data at this length
        self.unlocked_max = current
        return current

    def summary(self) -> dict:
        """Return curriculum state."""
        per_length = {}
        for length, s in sorted(self.stats.items()):
            rate = s["success"] / max(1, s["total"])
            per_length[length] = {
                "success_rate": round(rate, 4),
                "total": s["total"],
                "unlocked": length <= self.unlocked_max,
            }
        return {
            "unlocked_max": self.unlocked_max,
            "threshold": self.threshold,
            "per_length": per_length,
        }


# ---------------------------------------------------------------------------
# Priority 6: Directed mutation via scillm
# ---------------------------------------------------------------------------

def directed_mutation(
    chain: list[str],
    error_output: str,
    skill_names: list[str],
) -> list[str] | None:
    """Use scillm to analyze failure and suggest specific mutation.

    Calls the local scillm skill to ask: "Given this chain failed with
    this error, which skill should be replaced and with what?"

    Returns mutated chain, or None if scillm unavailable.
    """
    if not error_output or len(chain) < 2:
        return None

    try:
        from scillm_bridge import scillm_complete

        prompt = (
            f"A skill composition failed. Analyze and suggest a fix.\n\n"
            f"Chain: {' → '.join(chain)}\n"
            f"Error: {error_output[:300]}\n"
            f"Available skills: {', '.join(skill_names[:30])}\n\n"
            f"Respond with ONLY a JSON object:\n"
            f'{{"replace_index": <int>, "replacement": "<skill_name>", "reason": "<brief>"}}'
        )

        response = scillm_complete(prompt, max_tokens=150, temperature=0.3)
        if not response:
            return None

        # Parse response
        data = json.loads(response.strip())
        idx = data.get("replace_index", -1)
        replacement = data.get("replacement", "")

        if 0 <= idx < len(chain) and replacement in skill_names:
            mutated = list(chain)
            mutated[idx] = replacement
            return mutated

    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    return None


# ---------------------------------------------------------------------------
# Archive integration — MAP-Elites, skill library, cost surrogate
# ---------------------------------------------------------------------------

def should_skip_chain(chain: list[str], budget_atp: float = 12.0) -> bool:
    """Pre-filter expensive compositions using cost surrogate."""
    try:
        from cost_surrogate import CostSurrogate
        surrogate = CostSurrogate.load_or_create()
        return surrogate.should_skip(chain, budget_atp)
    except Exception:
        return False


def update_archives(
    chain: list[str],
    success: bool,
    energy: float,
    quality: float,
    elegance_score: float,
    elegance_grade: str,
    task_type: str = "",
) -> dict[str, bool]:
    """Update MAP-Elites archive and skill library after evaluation.

    Returns dict of which archives were updated.
    """
    updated = {"map_elites": False, "skill_library": False}

    # MAP-Elites: insert regardless of success (archives all regions)
    try:
        from map_elites import MAPElitesArchive
        archive = MAPElitesArchive.load_or_create()
        inserted = archive.try_insert(
            chain=chain,
            energy=energy,
            quality=quality,
            elegance_score=elegance_score,
            elegance_grade=elegance_grade,
            metadata={"task_type": task_type},
        )
        if inserted:
            archive.save()
            updated["map_elites"] = True
    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    # Skill library: only successful compositions
    if success:
        try:
            from skill_library import SkillLibrary
            lib = SkillLibrary.load_or_create()
            added = lib.add_success(
                chain=chain,
                quality=quality,
                energy=energy,
                elegance_score=elegance_score,
                elegance_grade=elegance_grade,
                task_type=task_type,
            )
            if added:
                lib.save()
                updated["skill_library"] = True
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    return updated


def retrieve_library_context(
    chain: list[str],
    task_type: str | None = None,
    k: int = 5,
) -> list[list[str]]:
    """Retrieve similar successful chains from skill library for context."""
    try:
        from skill_library import SkillLibrary
        lib = SkillLibrary.load_or_create()
        if not lib.entries:
            return []
        similar = lib.retrieve_similar(chain, k=k, task_type=task_type)
        return [e.chain for e in similar]
    except Exception:
        return []


def record_execution_trace(chain: list[str], duration_ms: float) -> None:
    """Append execution trace for cost surrogate training."""
    try:
        traces_file = STATE_DIR / "execution_traces.jsonl"
        entry = {
            "chain": chain,
            "duration_ms": round(duration_ms, 1),
            "timestamp": time.time(),
        }
        with open(traces_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug("file write failed: {}", e)


# ---------------------------------------------------------------------------
# Sampling strategies (moved from warm_pond.py for 800-line compliance)
# ---------------------------------------------------------------------------

def transition_guided_sample(
    skill_names: list[str],
    chain_len: int,
    task_type: str | None,
    session_results: list[dict],
) -> list[str]:
    """Use transition matrix probabilities to guide chain construction.

    If a task_type is specified, loads the task-specific matrix.
    Falls back to global matrix, then to session-weighted sampling.
    """
    try:
        from transition_matrix import load_matrix, TASK_MATRICES_FILE
        matrix = None
        if task_type and TASK_MATRICES_FILE.exists():
            task_matrices = json.loads(TASK_MATRICES_FILE.read_text())
            matrix = task_matrices.get("matrices", {}).get(task_type)
        if not matrix:
            matrix = load_matrix()
        if matrix and matrix.get("skills"):
            available = [s for s in skill_names if s in matrix.get("skills", [])]
            if len(available) >= chain_len:
                chain = [random.choice(available)]
                transitions = matrix.get("transitions", {})
                for _ in range(chain_len - 1):
                    current = chain[-1]
                    next_probs = transitions.get(current, {})
                    candidates = {
                        s: p for s, p in next_probs.items()
                        if s in available and s not in chain
                    }
                    if candidates:
                        skills_list = list(candidates.keys())
                        weights = [candidates[s] for s in skills_list]
                        total_w = sum(weights)
                        if total_w > 0:
                            weights = [w / total_w for w in weights]
                            chosen = random.choices(skills_list, weights=weights, k=1)[0]
                            chain.append(chosen)
                        else:
                            remaining = [s for s in available if s not in chain]
                            if remaining:
                                chain.append(random.choice(remaining))
                    else:
                        remaining = [s for s in available if s not in chain]
                        if remaining:
                            chain.append(random.choice(remaining))
                if len(chain) >= 2:
                    return chain
    except (ImportError, Exception):
        pass

    # Fallback: use session success data for weighted sampling
    if session_results:
        successful_skills: dict[str, int] = {}
        for r in session_results:
            if r.get("success"):
                for s in r.get("chain", []):
                    successful_skills[s] = successful_skills.get(s, 0) + 1

        if successful_skills:
            weighted = []
            for s in skill_names:
                weight = successful_skills.get(s, 1)
                weighted.append((s, weight))
            skills_list = [s for s, _ in weighted]
            weights = [w for _, w in weighted]
            total_w = sum(weights)
            weights = [w / total_w for w in weights]
            chain: list[str] = []
            for _ in range(chain_len):
                remaining = [(s, w) for s, w in zip(skills_list, weights) if s not in chain]
                if not remaining:
                    break
                rs, rw = zip(*remaining)
                tw = sum(rw)
                rw_norm = [w / tw for w in rw]
                chain.append(random.choices(list(rs), weights=rw_norm, k=1)[0])
            if len(chain) >= 2:
                return chain

    return random.sample(skill_names, chain_len)


def replay_with_mutation(
    skill_names: list[str],
    chain_len: int,
    session_results: list[dict],
) -> list[str]:
    """Replay top-performing chains from this session with single-skill mutation."""
    successful = [r for r in session_results if r.get("success")]
    if not successful:
        return random.sample(skill_names, chain_len)

    weights = [i + 1 for i in range(len(successful))]
    base_chain = random.choices(successful, weights=weights, k=1)[0]["chain"]

    chain = list(base_chain)
    if len(chain) > 1:
        mut_idx = random.randint(0, len(chain) - 1)
        candidates = [s for s in skill_names if s not in chain]
        if candidates:
            chain[mut_idx] = random.choice(candidates)

    if len(chain) > chain_len:
        chain = chain[:chain_len]
    elif len(chain) < chain_len:
        extras = [s for s in skill_names if s not in chain]
        while len(chain) < chain_len and extras:
            chain.append(extras.pop(random.randint(0, len(extras) - 1)))

    return chain if len(chain) >= 2 else random.sample(skill_names, chain_len)
