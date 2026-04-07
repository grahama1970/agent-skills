"""Format reward function for GRPO training.

Rewards well-formed QuerySpec JSON with correct structure and valid fields.
This is a fast, deterministic reward that doesn't require execution.
"""

import json
from typing import Any

from loguru import logger


# Valid values for QuerySpec fields
VALID_ACTIONS = {"QUERY", "CLARIFY", "NO_MATCH"}
VALID_LANES = {"bm25", "dense", "entity", "hybrid"}
VALID_TIER0 = {"Precision", "Resilience", "Safety", "Security", "Sustainability"}
VALID_TIER1 = {"Detect", "Prevent", "Mitigate", "Recover", "Assess", "Monitor"}


def format_reward(
    completions: list[list[dict]],
    **kwargs,
) -> list[float]:
    """Compute reward based on QuerySpec format validity.

    Args:
        completions: List of completion groups containing QuerySpec JSON
        **kwargs: Additional args from TRL trainer

    Returns:
        List of reward scores, one per completion

    Reward scale:
        -2.0: Not valid JSON
        -1.0: JSON but missing required fields
         0.0: Minimal valid structure
         0.5: Good structure with valid enums
         1.0: Complete structure with all optional fields
    """
    scores = []

    for completion in completions:
        # Extract content
        if isinstance(completion, list) and len(completion) > 0:
            content = completion[0].get("content", "")
        elif isinstance(completion, dict):
            content = completion.get("content", "")
        elif isinstance(completion, str):
            content = completion
        else:
            scores.append(-2.0)
            continue

        score = compute_format_score(content)
        scores.append(score)

    return scores


def compute_format_score(content: str) -> float:
    """Compute format score for a single QuerySpec string."""
    # Try to parse JSON
    spec = None
    try:
        spec = json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown
    if spec is None and "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        if end > start:
            try:
                spec = json.loads(content[start:end].strip())
            except json.JSONDecodeError:
                pass

    # Try extracting any JSON object
    if spec is None:
        import re
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if match:
            try:
                spec = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    if spec is None:
        return -2.0

    if not isinstance(spec, dict):
        return -2.0

    score = 0.0

    # Required field: action
    action = spec.get("action")
    if action is None:
        return -1.0
    if action in VALID_ACTIONS:
        score += 0.3
    else:
        score -= 0.2

    # Check lanes
    lanes = spec.get("lanes", [])
    if isinstance(lanes, list):
        score += 0.1
        if all(lane in VALID_LANES for lane in lanes):
            score += 0.1

    # Check entities (should be list of strings)
    entities = spec.get("entities", [])
    if isinstance(entities, list):
        score += 0.1
        # Bonus for well-formed entity IDs (T-xxxx, CWE-xxx, CM-xxxx)
        import re
        entity_pattern = re.compile(r'^(T\d{4}(\.\d{3})?|CWE-\d+|CM-\d{4})$')
        valid_entities = sum(1 for e in entities if entity_pattern.match(str(e)))
        if valid_entities > 0:
            score += 0.1 * min(1.0, valid_entities / 3)

    # Check tier0
    tier0 = spec.get("tier0", [])
    if isinstance(tier0, list):
        score += 0.05
        if all(t in VALID_TIER0 for t in tier0):
            score += 0.1

    # Check tier1
    tier1 = spec.get("tier1", [])
    if isinstance(tier1, list):
        score += 0.05
        if all(t in VALID_TIER1 for t in tier1):
            score += 0.1

    # Check k (should be positive integer)
    k = spec.get("k")
    if isinstance(k, int) and 1 <= k <= 50:
        score += 0.1

    # Check min_grounding (should be float 0-1)
    min_grounding = spec.get("min_grounding")
    if isinstance(min_grounding, (int, float)) and 0 <= min_grounding <= 1:
        score += 0.1

    # Check keywords
    keywords = spec.get("keywords", [])
    if isinstance(keywords, list) and all(isinstance(kw, str) for kw in keywords):
        score += 0.1

    # NO_MATCH should have minimal other fields
    if action == "NO_MATCH":
        if not entities and not tier0 and not tier1:
            score += 0.2  # Correct NO_MATCH structure

    # CLARIFY should have a clarification question
    if action == "CLARIFY":
        if spec.get("clarify_question") or spec.get("clarification"):
            score += 0.2

    return min(1.0, max(-2.0, score))


def format_reward_weighted(
    completions: list[list[dict]],
    weight: float = 0.2,
    **kwargs,
) -> list[float]:
    """Format reward with configurable weight."""
    raw_scores = format_reward(completions, **kwargs)
    return [score * weight for score in raw_scores]
