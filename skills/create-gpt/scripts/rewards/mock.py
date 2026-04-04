"""Mock rewards for testing without GPU.

Provides deterministic rewards based on simple heuristics,
allowing the full training pipeline to be tested without
actual model inference.
"""

from __future__ import annotations

import json
import random
from typing import Any, Dict, Optional


def mock_reward(
    completions: list[list[dict]],
    output_schema: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> list[float]:
    """Mock reward that scores based on JSON validity and length.

    Args:
        completions: List of completion groups (TRL format)
        output_schema: Optional JSON Schema (used for field counting)
        **kwargs: Ignored

    Returns:
        List of mock reward scores
    """
    scores = []
    for completion in completions:
        if isinstance(completion, list) and len(completion) > 0:
            content = completion[0].get("content", "")
        elif isinstance(completion, dict):
            content = completion.get("content", "")
        elif isinstance(completion, str):
            content = completion
        else:
            scores.append(0.0)
            continue

        score = _mock_score(content, output_schema)
        scores.append(score)

    return scores


def _mock_score(content: str, output_schema: Optional[Dict[str, Any]] = None) -> float:
    """Compute a deterministic mock score."""
    # Base: is it valid JSON?
    try:
        parsed = json.loads(content.strip())
    except (json.JSONDecodeError, AttributeError):
        return 0.1 + random.random() * 0.1  # Small noise for non-JSON

    if not isinstance(parsed, dict):
        return 0.2

    score = 0.5  # Valid JSON object

    # Check required fields from schema
    if output_schema:
        required = output_schema.get("required", [])
        if required:
            present = sum(1 for f in required if f in parsed)
            score += 0.3 * (present / len(required))
        else:
            score += 0.15
    else:
        score += 0.1 * min(len(parsed), 5)  # More fields = higher score

    # Add small noise for diversity
    score += random.random() * 0.1

    return min(1.0, max(0.0, score))
