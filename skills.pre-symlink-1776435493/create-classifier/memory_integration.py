"""
Memory + Taxonomy integration for /create-classifier.

Pre-hook: Recalls prior classifier runs to surface previously achieved metrics
and avoid redundant training cycles.

Post-hook: Learns classifier run metadata to memory so future runs can
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
        _spec = importlib.util.spec_from_file_location("create_classifier_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["accuracy", "f1", "precision", "recall", "threshold"],
    "Resilience": ["generalize", "robust", "cross-validation"],
    "Fragility": ["overfit", "bias", "class imbalance", "noisy"],
    "Corruption": ["mislabeled", "poisoned", "adversarial"],
    "Loyalty": ["pipeline", "extractor", "production"],
    "Stealth": ["edge case", "corner case", "ambiguous"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from classifier content."""
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
# Pre-hook: Recall prior classifiers
# ---------------------------------------------------------------------------

def recall_prior_classifiers(
    task_type: str,
    model_name: str = "",
    k: int = 5,
) -> str:
    """
    Recall prior classifier training runs.

    Returns formatted markdown showing previously achieved metrics,
    enabling agents to set baselines and avoid redundant training.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"create_classifier {task_type} {model_name} accuracy f1 training",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior classifier recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn classifier run
# ---------------------------------------------------------------------------

def learn_classifier_run(
    task_type: str,
    model_name: str = "",
    accuracy: float = 0.0,
    f1: float = 0.0,
    dataset_size: int = 0,
    config: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Learn classifier run to memory.

    Stores:
    1. Run summary (task, model, accuracy, f1, dataset)
    2. Task type association (for cross-run recall)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping classifier learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([task_type or "", model_name or "", f"accuracy {accuracy} f1 {f1}"])
    bridges = extract_bridges(all_text)
    base_tags = ["create_classifier", task_type] + bridges

    # 1. Run summary
    profile = json.dumps({
        "task_type": task_type,
        "model_name": model_name,
        "accuracy": accuracy,
        "f1": f1,
        "dataset_size": dataset_size,
        "config": config or {},
        "trained_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Classifier: {task_type} — {model_name}, acc {accuracy}, f1 {f1}",
            solution=profile,
            tags=base_tags + ["classifier_run"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned classifier run: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn classifier run: {e}")

    # 2. Task type association
    try:
        result = client.learn(
            problem=f"Classifier task: {task_type} — {model_name} (acc {accuracy})",
            solution=json.dumps({
                "task_type": task_type,
                "model_name": model_name,
                "accuracy": accuracy,
                "f1": f1,
                "date": now,
            }),
            tags=base_tags + ["task_association", task_type],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
    except Exception as e:
        logger.warning(f"Failed to learn task association: {e}")

    logger.info(f"Classifier learn complete: {len(learned_ids)} entries stored")
    return learned_ids
