"""Memory + Taxonomy integration for /create-gpt.

Pre-hook: Recalls prior GPT training runs to surface previously achieved metrics.
Post-hook: Learns GPT training metadata to memory for cross-session knowledge.

Pattern: Follows create-classifier/memory_integration.py with graceful degradation.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

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
        _spec = importlib.util.spec_from_file_location("create_gpt_taxonomy", _TAXONOMY_PATH)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _taxonomy_extract = getattr(_mod, "extract_taxonomy", None)
    except Exception as e:
        logger.debug(f"Taxonomy module load failed: {e}")


_BRIDGE_KEYWORDS = {
    "Precision": ["accuracy", "f1", "precision", "threshold", "quality"],
    "Resilience": ["generalize", "robust", "holdout", "cross-validation"],
    "Fragility": ["overfit", "collapse", "degenerate"],
    "Loyalty": ["pipeline", "production", "tier-1.5", "confidence"],
    "Stealth": ["edge case", "ambiguous", "low-confidence"],
}


def extract_bridges(text: str) -> List[str]:
    """Extract taxonomy bridge attributes from training content."""
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


def recall_prior_gpt_runs(
    task_name: str,
    base_model: str = "",
    k: int = 5,
) -> str:
    """Recall prior GPT training runs.

    Returns formatted markdown showing previously achieved metrics,
    enabling agents to set baselines and avoid redundant training.
    """
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"create_gpt {task_name} {base_model} accuracy training tier-1.5",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior GPT recall failed: {e}")
        return ""


def learn_gpt_run(
    task_name: str,
    base_model: str = "",
    accuracy: float = 0.0,
    format_valid: float = 0.0,
    training_type: str = "sft",
    config: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Learn GPT training run to memory.

    Stores run summary and task association for cross-run recall.
    """
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping GPT learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    all_text = " ".join([
        task_name or "", base_model or "",
        f"accuracy {accuracy} format_valid {format_valid}",
        training_type,
    ])
    bridges = extract_bridges(all_text)
    base_tags = ["create_gpt", task_name, training_type] + bridges

    profile = json.dumps({
        "task_name": task_name,
        "base_model": base_model,
        "accuracy": accuracy,
        "format_valid": format_valid,
        "training_type": training_type,
        "config": config or {},
        "trained_at": now,
        "bridges": bridges,
    })

    try:
        result = client.learn(
            problem=f"GPT: {task_name} — {base_model}, acc {accuracy}, fmt {format_valid}",
            solution=profile,
            tags=base_tags + ["gpt_run"],
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned GPT run: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn GPT run: {e}")

    logger.info(f"GPT learn complete: {len(learned_ids)} entries stored")
    return learned_ids
