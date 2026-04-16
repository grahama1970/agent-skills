"""
Prompt Provenance — SHA256-based prompt verification via /memory daemon.

Task 1+2 of 07_SENSAI_CASCADE_V2_PIVOT: Unforgeable prompt provenance ledger.

After /prompt-lab eval passes threshold, record_prompt_provenance() stores
the SHA256 hash + eval metadata in /memory scope=prompt_provenance.

verify_prompt_provenance() checks whether a prompt's content hash exists
in the ledger — agents cannot fabricate recall results.

Usage:
    from provenance import record_prompt_provenance, verify_prompt_provenance

    # After eval passes:
    record_prompt_provenance(prompt_content, prompt_name, eval_f1, model_name)

    # Before using a prompt in /assistant:
    result = verify_prompt_provenance(prompt_content)
    if not result["verified"]:
        raise ValueError(f"Unvalidated prompt: {result['reason']}")
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

# Import memory client (standard skill integration pattern)
SKILLS_DIR = Path(__file__).parent.parent
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

_HAS_MEMORY = False
try:
    from common.memory_client import MemoryClient
    _HAS_MEMORY = True
except ImportError:
    pass

# Scope is a raw string — no need to add to MemoryScope enum
PROVENANCE_SCOPE = "prompt_provenance"


def compute_prompt_hash(content: str) -> str:
    """SHA256 hash of prompt content (normalized whitespace)."""
    normalized = content.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _get_client() -> "MemoryClient | None":
    """Get a memory client for prompt_provenance scope."""
    if not _HAS_MEMORY:
        logger.warning("memory_client not available — provenance disabled")
        return None
    try:
        return MemoryClient(scope=PROVENANCE_SCOPE)
    except Exception as e:
        logger.warning("Failed to create memory client: {}", e)
        return None


def record_prompt_provenance(
    prompt_content: str,
    prompt_name: str,
    eval_f1: float,
    model_tested: str,
    ground_truth_file: str = "",
    task_name: str = "",
) -> bool:
    """
    Record a validated prompt's hash + metadata in /memory.

    Called after /prompt-lab eval passes threshold.

    Args:
        prompt_content: Full prompt text
        prompt_name: Human-readable prompt identifier
        eval_f1: F1 score from evaluation
        model_tested: Model used during eval
        ground_truth_file: Path to ground truth used
        task_name: Associated task name

    Returns:
        True if successfully stored
    """
    client = _get_client()
    if client is None:
        return False

    sha256 = compute_prompt_hash(prompt_content)
    now = datetime.now(timezone.utc).isoformat()

    metadata = {
        "sha256": sha256,
        "eval_f1": round(eval_f1, 4),
        "model_tested": model_tested,
        "ground_truth_file": ground_truth_file,
        "task_name": task_name,
        "passed_at": now,
        "prompt_lab_version": "v2",
    }

    # Problem must be descriptive enough to pass memory daemon quality gate
    # (short metadata strings get rejected as AMBIGUOUS)
    prompt_preview = prompt_content.strip()[:200].replace("\n", " ")
    problem = (
        f"Validated prompt provenance record for {prompt_name} "
        f"(sha256={sha256[:16]}…). "
        f"Evaluated with F1={eval_f1:.3f} on model {model_tested}. "
        f"Prompt preview: {prompt_preview}"
    )
    solution = json.dumps(metadata)
    tags = ["validated_prompt", prompt_name]
    if task_name:
        tags.append(task_name)

    try:
        result = client.learn(
            problem=problem,
            solution=solution,
            scope=PROVENANCE_SCOPE,
            tags=tags,
        )
        logger.info(
            "Recorded provenance for '{}' sha256={}… f1={:.3f}",
            prompt_name, sha256[:16], eval_f1,
        )
        return result.success if hasattr(result, "success") else True
    except Exception as e:
        logger.error("Failed to record provenance: {}", e)
        return False


def verify_prompt_provenance(prompt_content: str) -> dict[str, Any]:
    """
    Check whether a prompt has been validated through /prompt-lab.

    Args:
        prompt_content: Full prompt text to verify

    Returns:
        {verified: True, eval_f1: float, passed_at: str, sha256: str}
        or {verified: False, reason: str, sha256: str}
    """
    sha256 = compute_prompt_hash(prompt_content)

    client = _get_client()
    if client is None:
        return {
            "verified": False,
            "reason": "memory_client unavailable",
            "sha256": sha256,
        }

    try:
        # Query with descriptive text matching the learn problem format
        result = client.recall(
            query=f"Validated prompt provenance record sha256={sha256[:16]}",
            scope=PROVENANCE_SCOPE,
            k=5,
        )

        items = result.items if hasattr(result, "items") else []
        if not items:
            # Fallback: try with full hash
            result = client.recall(
                query=sha256,
                scope=PROVENANCE_SCOPE,
                k=5,
            )
            items = result.items if hasattr(result, "items") else []

        # Search through results for matching hash
        for item in items:
            solution = item.get("solution", "") if isinstance(item, dict) else str(item)
            try:
                meta = json.loads(solution) if isinstance(solution, str) else solution
            except (json.JSONDecodeError, TypeError):
                continue

            if isinstance(meta, dict) and meta.get("sha256") == sha256:
                return {
                    "verified": True,
                    "eval_f1": meta.get("eval_f1", 0.0),
                    "passed_at": meta.get("passed_at", ""),
                    "model_tested": meta.get("model_tested", ""),
                    "sha256": sha256,
                }

        return {
            "verified": False,
            "reason": "no matching provenance record found",
            "sha256": sha256,
        }

    except Exception as e:
        logger.error("Provenance check failed: {}", e)
        return {
            "verified": False,
            "reason": f"recall error: {e}",
            "sha256": sha256,
        }
