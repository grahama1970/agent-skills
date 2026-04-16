"""Recall proven skill chains from successful session checkpoints.

Queries /memory for checkpoints tagged outcome:success and extracts
the skill chain patterns that led to verified outcomes. These chains
get high confidence (0.75) in the recommendation ranking because
they're backed by evidence, not prediction.
"""
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger


def recall_successful_checkpoints(
    task: str,
    memory_cmd: Any,
) -> list[dict]:
    """Query checkpoints with outcome:success for proven skill chains.

    Args:
        task: The task description to match against
        memory_cmd: Callable that runs /memory CLI commands

    Returns:
        List of candidate dicts with chain, confidence, tier, reason, source_data
    """
    candidates = []
    try:
        result = memory_cmd([
            "recall", "--q", f"CHECKPOINT: {task}",
            "--k", "5", "--scope", "pi-mono",
            "--tag", "outcome:success",
        ])
        for r in result.get("items", result.get("results", [])):
            if not isinstance(r, dict):
                continue
            solution = r.get("solution", "")
            try:
                doc = json.loads(solution) if isinstance(solution, str) else solution
            except (json.JSONDecodeError, TypeError):
                continue

            if doc.get("checkpoint_version") and doc.get("outcome") == "success":
                text = f"{doc.get('summary', '')} {' '.join(doc.get('decisions', []))}"
                skills = _extract_skill_refs(text)
                if skills:
                    candidates.append({
                        "chain": skills,
                        "confidence": 0.75,
                        "tier": "checkpoint",
                        "reason": f"Proven chain from successful session: {doc.get('topic', '')[:60]}",
                        "source_data": {
                            "checkpoint_topic": doc.get("topic"),
                            "checkpoint_outcome": doc.get("outcome"),
                            "evidence_count": len(doc.get("evidence", [])),
                        },
                    })
    except Exception as e:
        logger.debug("Checkpoint recall not available: {}", e)
    return candidates


def _extract_skill_refs(text: str) -> list[str]:
    """Extract /skill-name references from text."""
    matches = re.findall(r'/([a-z][a-z0-9-]{1,30})', text)
    seen: set[str] = set()
    skills: list[str] = []
    for m in matches:
        if m not in seen and m not in ("memory", "checkpoint"):
            seen.add(m)
            skills.append(m)
    return skills
