"""
Memory + Taxonomy integration for /create-table-classifier.

Pre-hook: Recalls prior table classifier runs to surface previously achieved
accuracy and avoid redundant training cycles.

Post-hook: Learns table classifier run metadata to memory so future runs can
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
        _spec = importlib.util.spec_from_file_location("create_table_classifier_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


# ---------------------------------------------------------------------------
# Bridge extraction
# ---------------------------------------------------------------------------

_BRIDGE_KEYWORDS = {
    "Precision": ["accuracy", "correct", "predicted", "classified"],
    "Resilience": ["camelot", "tabula", "fallback", "strategy"],
    "Fragility": ["misclassified", "false positive", "ambiguous"],
    "Corruption": ["corrupted", "malformed", "adversarial"],
    "Loyalty": ["extractor", "pipeline", "camelot"],
    "Stealth": ["merged cells", "nested", "spanning", "implicit header"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from table classifier content."""
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
# Pre-hook: Recall prior table classifiers
# ---------------------------------------------------------------------------

def recall_prior_table_classifiers(
    model_name: str = "",
    k: int = 5,
) -> str:
    """
    Recall prior table classifier training runs.

    Returns formatted markdown showing previously achieved accuracy,
    enabling agents to set baselines and avoid redundant training.
    Returns empty string if memory unavailable.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"create_table_classifier {model_name} accuracy camelot tabula",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior table classifier recall failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Post-hook: Learn table classifier run
# ---------------------------------------------------------------------------

def learn_table_classifier_run(
    model_name: str,
    accuracy: float = 0.0,
    confusion_matrix: Optional[Dict[str, Any]] = None,
    dataset_size: int = 0,
) -> List[str]:
    """
    Learn table classifier run to memory.

    Stores:
    1. Run summary (model, accuracy, confusion matrix, dataset)
    2. Model comparison (for cross-run analysis)

    Returns list of learned lesson IDs (empty if memory unavailable).
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping table classifier learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([model_name or "", f"accuracy {accuracy}"])
    bridges = extract_bridges(all_text)
    base_tags = ["create_table_classifier", model_name] + bridges

    # 1. Run summary
    profile = json.dumps({
        "model_name": model_name,
        "accuracy": accuracy,
        "confusion_matrix": confusion_matrix or {},
        "dataset_size": dataset_size,
        "trained_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"Table classifier: {model_name} — accuracy {accuracy}",
            solution=profile,
            tags=base_tags + ["classifier_run"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned table classifier run: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn table classifier run: {e}")

    # 2. Model comparison
    try:
        result = client.learn(
            problem=f"Table classifier model: {model_name} (acc {accuracy})",
            solution=json.dumps({
                "model_name": model_name,
                "accuracy": accuracy,
                "dataset_size": dataset_size,
                "date": now,
            }),
            tags=base_tags + ["model_comparison"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
    except Exception as e:
        logger.warning(f"Failed to learn model comparison: {e}")

    logger.info(f"Table classifier learn complete: {len(learned_ids)} entries stored")
    return learned_ids
