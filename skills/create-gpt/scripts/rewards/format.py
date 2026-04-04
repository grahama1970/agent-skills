"""JSON Schema validation reward for GRPO training.

Generalized from create-intent-map/scripts/rewards/format.py.
Validates model outputs against the task's output_schema using jsonschema.

Reward scale:
    -2.0: Not valid JSON
    -1.0: JSON but fails schema validation
     0.0: Valid JSON, minimal schema compliance
     0.5: Passes schema, has all required fields
     1.0: Complete output with all optional fields
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from loguru import logger


def format_reward(
    completions: list[list[dict]],
    output_schema: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> list[float]:
    """Compute reward based on JSON format validity and schema compliance.

    Args:
        completions: List of completion groups (TRL format)
        output_schema: Optional JSON Schema to validate against
        **kwargs: Additional args from TRL trainer

    Returns:
        List of reward scores, one per completion
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
            scores.append(-2.0)
            continue

        score = compute_format_score(content, output_schema)
        scores.append(score)

    return scores


def _extract_json(content: str) -> Optional[dict]:
    """Extract JSON from content, trying multiple strategies."""
    # Try direct parse
    try:
        parsed = json.loads(content.strip())
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try markdown code block extraction
    if "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        if end > start:
            try:
                parsed = json.loads(content[start:end].strip())
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

    # Try regex extraction of JSON object
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return None


def compute_format_score(content: str, output_schema: Optional[Dict[str, Any]] = None) -> float:
    """Compute format score for a single output string.

    Args:
        content: Raw model output string
        output_schema: Optional JSON Schema to validate against

    Returns:
        Score from -2.0 to 1.0
    """
    parsed = _extract_json(content)

    if parsed is None:
        return -2.0

    score = 0.0

    # Base score: valid JSON object
    score += 0.3

    if output_schema:
        # Schema validation
        try:
            import jsonschema
            jsonschema.validate(parsed, output_schema)
            score += 0.4  # Full schema compliance
        except ImportError:
            # Fallback: check required fields manually
            required = output_schema.get("required", [])
            if required:
                present = sum(1 for f in required if f in parsed)
                score += 0.4 * (present / len(required))
            else:
                score += 0.2
        except jsonschema.ValidationError:
            # Partial credit for required fields
            required = output_schema.get("required", [])
            if required:
                present = sum(1 for f in required if f in parsed)
                score += 0.2 * (present / len(required))

        # Bonus for correct types
        properties = output_schema.get("properties", {})
        type_correct = 0
        type_total = 0
        for key, prop_schema in properties.items():
            if key not in parsed:
                continue
            type_total += 1
            expected_type = prop_schema.get("type")
            value = parsed[key]
            if _type_matches(value, expected_type):
                type_correct += 1

        if type_total > 0:
            score += 0.3 * (type_correct / type_total)
    else:
        # No schema: reward non-empty JSON with string values
        if len(parsed) > 0:
            score += 0.3
        if len(parsed) >= 3:
            score += 0.2

    return min(1.0, max(-2.0, score))


def _type_matches(value: Any, expected_type: Optional[str]) -> bool:
    """Check if a value matches an expected JSON Schema type."""
    if expected_type is None:
        return True
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    expected = type_map.get(expected_type)
    if expected is None:
        return True
    return isinstance(value, expected)
