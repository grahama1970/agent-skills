"""
Memory + Taxonomy integration for /train-persona.

Pre-hook: Recalls prior persona training runs to surface previously achieved
loss values and avoid redundant training cycles.

Post-hook: Learns training run metadata to memory so future runs can
leverage accumulated knowledge across sessions.

Pattern: Follows discover-contacts/memory_integration.py with graceful degradation.
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

_HAS_MEMORY = False
try:
    from common.memory_client import MemoryClient, MemoryScope, RecallResult
    _HAS_MEMORY = True
except ImportError:
    logger.debug("common.memory_client not available — memory integration disabled")

_taxonomy_extract = None
_TAXONOMY_PATH = _SKILLS_DIR / "taxonomy" / "taxonomy.py"
if _TAXONOMY_PATH.exists():
    try:
        _spec = importlib.util.spec_from_file_location("train_persona_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["converged", "loss", "accuracy", "metric"],
    "Resilience": ["checkpoint", "resume", "stable"],
    "Fragility": ["diverged", "overfit", "nan", "collapsed"],
    "Corruption": ["data poisoning", "contaminated"],
    "Loyalty": ["persona", "character", "voice", "identity"],
    "Stealth": ["subtle", "nuance", "tone shift"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from persona training content."""
    if _taxonomy_extract:
        try:
            result = _taxonomy_extract(text, collection="persona")
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
# Pre-hook: Recall prior training
# ---------------------------------------------------------------------------

def recall_prior_training(
    persona_name: str,
    k: int = 5,
) -> str:
    """
    Recall prior persona training runs.

    Returns formatted markdown showing previously achieved training metrics,
    enabling agents to set baselines and avoid redundant cycles.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.PERSONA)
        result = client.recall(
            f"train_persona {persona_name} lora loss epochs training",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior persona training recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn training run
# ---------------------------------------------------------------------------

def learn_training_run(
    persona_name: str,
    model_type: str = "",
    epochs: int = 0,
    loss: float = 0.0,
    dataset_size: int = 0,
) -> List[str]:
    """
    Learn persona training run to memory.

    Stores:
    1. Training summary (persona, model, epochs, loss, dataset)
    2. Persona training history (for longitudinal analysis)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping persona training learn")
        return []

    client = MemoryClient(scope=MemoryScope.PERSONA)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([persona_name or "", model_type or "", f"loss {loss}"])
    bridges = extract_bridges(all_text)
    base_tags = ["train_persona", persona_name] + bridges

    # 1. Training summary
    profile = json.dumps({
        "persona_name": persona_name,
        "model_type": model_type,
        "epochs": epochs,
        "loss": loss,
        "dataset_size": dataset_size,
        "trained_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Persona training: {persona_name} — {model_type}, loss {loss}",
            solution=profile,
            tags=base_tags + ["training_run"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned persona training: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn persona training: {e}")

    # 2. Training history
    try:
        result = client.learn(
            problem=f"Persona training history: {persona_name} at {now}",
            solution=json.dumps({
                "persona_name": persona_name,
                "loss": loss,
                "epochs": epochs,
                "date": now,
            }),
            tags=base_tags + ["training_history"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
    except Exception as e:
        logger.warning(f"Failed to learn training history: {e}")

    logger.info(f"Persona training learn complete: {len(learned_ids)} entries stored")
    return learned_ids
