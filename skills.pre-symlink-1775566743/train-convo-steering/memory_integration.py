"""
Memory + Taxonomy integration for /train-convo-steering.

Pre-hook: Recalls per-user conversation priors from memory so that
learned preferences persist across sessions and nightly runs.

Post-hook: Learns conversation priors to memory after training — user
preferences, confidence levels, and steering decisions.

Pattern: Follows create-context/memory_integration.py with graceful degradation.
"""

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Lazy imports with graceful degradation
# ---------------------------------------------------------------------------
_SKILLS_DIR = Path(__file__).parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

# Memory client
_HAS_MEMORY = False
try:
    from common.memory_client import MemoryClient, MemoryScope, RecallResult
    _HAS_MEMORY = True
except ImportError:
    logger.debug("common.memory_client not available — memory integration disabled")

# Taxonomy (loaded dynamically to avoid name conflicts)
_taxonomy_extract = None
_TAXONOMY_PATH = _SKILLS_DIR / "taxonomy" / "taxonomy.py"
if _TAXONOMY_PATH.exists():
    try:
        _spec = importlib.util.spec_from_file_location("steering_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["preference", "explicit", "specific", "exact", "particular", "configured"],
    "Resilience": ["consistent", "stable", "reliable", "steady", "proven", "established"],
    "Fragility": ["conflicting", "unclear", "ambiguous", "inconsistent", "volatile", "confused"],
    "Corruption": ["manipulation", "deception", "gaming", "exploit", "adversarial"],
    "Loyalty": ["trust", "rapport", "relationship", "familiar", "returning", "loyal"],
    "Stealth": ["implicit", "inferred", "unspoken", "latent", "behavioral", "pattern"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from steering content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="operational")
            bridges = result.get("bridge_tags", []) if isinstance(result, dict) else []
            if bridges:
                return bridges
        except Exception as e:
            logger.debug(f"Taxonomy extraction failed, using keyword fallback: {e}")

    text_lower = text.lower()
    found = []
    for bridge, keywords in _BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found or ["Precision"]


# ---------------------------------------------------------------------------
# Pre-hook: Recall user priors for cross-session persistence
# ---------------------------------------------------------------------------

def recall_user_priors(
    user_id: str,
    k: int = 10,
) -> str:
    """
    Recall conversation priors for a user from memory.

    Returns formatted context showing prior steering preferences,
    confidence levels, and historical patterns — enabling priors to
    persist across sessions and nightly training runs.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"conversation steering prior {user_id} preference preset confidence",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior recall failed for user {user_id}: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn conversation prior to memory
# ---------------------------------------------------------------------------

def learn_conversation_prior(
    user_id: str,
    prior_type: str,
    value: str,
    confidence: float = 0.5,
    context: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Learn a conversation prior to memory.

    Prior types:
    - "preset_preference": User's preferred steering preset
    - "state_policy": Best preset for a given state bucket
    - "nightly_summary": Aggregated nightly training results

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping prior learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    # Build content for bridge extraction
    all_text = " ".join([
        prior_type or "",
        value or "",
        json.dumps(context) if context else "",
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["convo_steering", user_id] + bridges

    # Store the prior
    prior_data = json.dumps({
        "user_id": user_id,
        "prior_type": prior_type,
        "value": value,
        "confidence": confidence,
        "context": context or {},
        "bridges": bridges,
        "learned_at": now,
    })

    try:
        result = client.learn(
            problem=f"Conversation prior for {user_id}: {prior_type} = {value[:80]}",
            solution=prior_data,
            tags=base_tags + [prior_type],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned conversation prior: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn conversation prior: {e}")

    logger.info(f"Prior learn complete for {user_id}: {len(learned_ids)} entries stored")
    return learned_ids


def learn_nightly_summary(
    user_id: str,
    global_best_preset: str,
    training_rows: int,
    judge_labels_used: int,
    state_policy: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Learn nightly training summary to memory.

    Captures the aggregated results of a nightly training run for a user,
    enabling cross-session persistence of learned priors.

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping nightly summary learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    bridges = ["Precision", "Resilience"]  # Nightly training is precise + stable
    base_tags = ["convo_steering", user_id] + bridges

    summary = json.dumps({
        "user_id": user_id,
        "global_best_preset": global_best_preset,
        "training_rows": training_rows,
        "judge_labels_used": judge_labels_used,
        "state_policy_keys": list((state_policy or {}).keys()),
        "trained_at": now,
    })

    try:
        result = client.learn(
            problem=f"Nightly steering summary for {user_id}: best={global_best_preset}, rows={training_rows}",
            solution=summary,
            tags=base_tags + ["nightly_summary"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned nightly summary: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn nightly summary: {e}")

    # Also store individual state policies if confident
    if state_policy:
        for state_key, policy in state_policy.items():
            if not isinstance(policy, dict):
                continue
            conf = float(policy.get("confidence", 0.0))
            if conf < 0.5:
                continue  # Only persist confident priors
            try:
                result = client.learn(
                    problem=f"Steering policy for {user_id} state {state_key}: {policy.get('best_preset', 'unknown')}",
                    solution=json.dumps({
                        "user_id": user_id,
                        "state_key": state_key,
                        "best_preset": policy.get("best_preset"),
                        "confidence": conf,
                        "total_samples": policy.get("total_samples", 0),
                    }),
                    tags=base_tags + ["state_policy"],
                )
                if result.success:
                    learned_ids.append(result.lesson_id)
            except Exception as e:
                logger.warning(f"Failed to learn state policy: {e}")

    logger.info(f"Nightly summary learn complete for {user_id}: {len(learned_ids)} entries stored")
    return learned_ids
