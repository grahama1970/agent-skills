"""Memory + Taxonomy integration for /gpt-lab.

Pre-hook: Recalls prior benchmark runs.
Post-hook: Learns benchmark results to memory.

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


_BRIDGE_KEYWORDS = {
    "Precision": ["accuracy", "f1", "precision", "benchmark", "quality"],
    "Resilience": ["generalize", "robust", "holdout", "cross-validation"],
    "Fragility": ["overfit", "collapse", "degenerate", "regression"],
    "Loyalty": ["pipeline", "production", "tier-1.5", "confidence"],
    "Stealth": ["edge case", "ambiguous", "low-confidence"],
}


def extract_bridges(text: str) -> list[str]:
    """Extract taxonomy bridge attributes from benchmark content."""
    text_lower = text.lower()
    found = []
    for bridge, keywords in _BRIDGE_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(bridge)
    return found or ["Precision"]


def recall_prior_benchmarks(
    task_name: str,
    k: int = 5,
) -> str:
    """Recall prior benchmark runs for this task."""
    if not _HAS_MEMORY:
        return ""

    try:
        client = MemoryClient(scope=MemoryScope.OPERATIONAL)
        result = client.recall(
            f"gpt_lab benchmark {task_name} accuracy latency model comparison",
            k=k,
        )
        if result.found:
            return result.to_context(max_items=k)
        return ""
    except Exception as e:
        logger.warning(f"Prior benchmark recall failed: {e}")
        return ""


def learn_benchmark_run(
    task_name: str,
    selected_model: str = "",
    accuracy: float = 0.0,
    latency_p50_ms: float = 0.0,
    verdict: str = "",
    config: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Learn benchmark result to memory."""
    if not _HAS_MEMORY:
        logger.info("Memory not available — skipping benchmark learn")
        return []

    client = MemoryClient(scope=MemoryScope.OPERATIONAL)
    now = datetime.now().isoformat()
    learned_ids = []

    profile = json.dumps({
        "task_name": task_name,
        "selected_model": selected_model,
        "accuracy": accuracy,
        "latency_p50_ms": latency_p50_ms,
        "verdict": verdict,
        "config": config or {},
        "benchmarked_at": now,
    })

    tags = ["gpt_lab", "benchmark", task_name]
    if verdict:
        tags.append(f"verdict:{verdict.lower()}")

    try:
        result = client.learn(
            problem=f"GPT-lab: {task_name} — {selected_model}, acc {accuracy}",
            solution=profile,
            tags=tags,
        )
        if result.success:
            learned_ids.append(result.lesson_id)
            logger.info(f"Learned benchmark: {result.lesson_id}")
    except Exception as e:
        logger.warning(f"Failed to learn benchmark: {e}")

    return learned_ids
