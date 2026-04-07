"""
Memory + Taxonomy integration for /train-voice.

Pre-hook: Recalls prior voice training runs to surface previously achieved
quality scores and avoid redundant training cycles.

Post-hook: Learns voice training metadata to memory so future runs can
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
        _spec = importlib.util.spec_from_file_location("train_voice_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["natural", "clear", "intelligible", "prosody"],
    "Resilience": ["robust", "generalize", "diverse"],
    "Fragility": ["artifact", "distortion", "glitch", "metallic", "robotic"],
    "Corruption": ["cloned", "impersonation", "deepfake"],
    "Loyalty": ["persona", "voice", "identity"],
    "Stealth": ["whisper", "soft", "breath"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from voice training content."""
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
# Pre-hook: Recall prior voice training
# ---------------------------------------------------------------------------

def recall_prior_voice_training(
    persona_name: str,
    k: int = 5,
) -> str:
    """
    Recall prior voice training runs.

    Returns formatted markdown showing previously achieved voice quality
    scores, enabling agents to set baselines and avoid redundant cycles.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"train_voice {persona_name} rvc quality epochs dataset",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior voice training recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn voice training
# ---------------------------------------------------------------------------

def learn_voice_training(
    persona_name: str,
    model_type: str = "",
    epochs: int = 0,
    dataset_hours: float = 0.0,
    quality_score: float = 0.0,
) -> List[str]:
    """
    Learn voice training run to memory.

    Stores:
    1. Training summary (persona, model, epochs, dataset, quality)
    2. Voice training history (for longitudinal analysis)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping voice training learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([persona_name or "", model_type or "", f"quality {quality_score}"])
    bridges = extract_bridges(all_text)
    base_tags = ["train_voice", persona_name] + bridges

    # 1. Training summary
    profile = json.dumps({
        "persona_name": persona_name,
        "model_type": model_type,
        "epochs": epochs,
        "dataset_hours": dataset_hours,
        "quality_score": quality_score,
        "trained_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Voice training: {persona_name} — {model_type}, quality {quality_score}",
            solution=profile,
            tags=base_tags + ["training_run"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned voice training: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn voice training: {e}")

    # 2. Training history
    try:
        result = client.learn(
            problem=f"Voice training history: {persona_name} at {now}",
            solution=json.dumps({
                "persona_name": persona_name,
                "quality_score": quality_score,
                "epochs": epochs,
                "date": now,
            }),
            tags=base_tags + ["training_history"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
    except Exception as e:
        logger.warning(f"Failed to learn voice training history: {e}")

    logger.info(f"Voice training learn complete: {len(learned_ids)} entries stored")
    return learned_ids
