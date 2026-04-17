"""Grounding reward function for GRPO training.

Rewards QuerySpecs that retrieve QRAs with high grounding scores,
indicating the results are well-supported by source documents.
"""

from statistics import mean
from typing import Any

from loguru import logger

from .execution import QuerySpec, get_executor


def grounding_reward(
    completions: list[list[dict]],
    prompts: list[str] = None,
    executor: Any = None,
    **kwargs,
) -> list[float]:
    """Compute reward based on grounding scores of retrieved QRAs.

    Args:
        completions: List of completion groups, each containing message dicts
                    with 'content' field containing QuerySpec JSON
        prompts: Original query prompts (unused but required by TRL interface)
        executor: ArangoDB executor instance (auto-created if None)
        **kwargs: Additional args passed by TRL trainer

    Returns:
        List of reward scores, one per completion

    Reward scale:
        -2.0: Invalid JSON (couldn't parse QuerySpec)
        -1.0: No results returned
        -0.5: Results below grounding threshold
         0.0 to 2.0: Scaled by average grounding score
    """
    if executor is None:
        executor = get_executor()

    scores = []

    for completion in completions:
        # Extract QuerySpec from completion
        if isinstance(completion, list) and len(completion) > 0:
            content = completion[0].get("content", "")
        elif isinstance(completion, dict):
            content = completion.get("content", "")
        elif isinstance(completion, str):
            content = completion
        else:
            scores.append(-2.0)
            continue

        # Parse QuerySpec
        spec = QuerySpec.from_json(content)
        if spec is None:
            logger.debug(f"Failed to parse QuerySpec: {content[:100]}...")
            scores.append(-2.0)
            continue

        # Handle non-QUERY actions
        if spec.action == "NO_MATCH":
            # NO_MATCH is valid for out-of-scope queries
            # Reward depends on whether it was correct - handled elsewhere
            scores.append(0.5)  # Neutral-positive for valid NO_MATCH
            continue

        if spec.action == "CLARIFY":
            # CLARIFY is valid for ambiguous queries
            scores.append(0.3)  # Slightly positive for valid CLARIFY
            continue

        # Execute query
        try:
            results = executor.execute(spec)
        except Exception as e:
            logger.warning(f"Execution failed: {e}")
            scores.append(-1.5)
            continue

        if not results:
            scores.append(-1.0)
            continue

        # Calculate average grounding score
        grounding_scores = [r.get("grounding_score", 0.0) for r in results]
        avg_grounding = mean(grounding_scores)

        # Scale reward based on grounding threshold
        # 0.7+ is our target threshold for Brandon simulacrum
        if avg_grounding >= 0.7:
            # Linear scale from 0.7→1.0 maps to 1.0→2.0
            reward = 1.0 + (avg_grounding - 0.7) / 0.3
        elif avg_grounding >= 0.5:
            # Below threshold but decent
            reward = (avg_grounding - 0.5) / 0.2  # 0.0 to 1.0
        else:
            # Poor grounding
            reward = -0.5

        scores.append(reward)

    return scores


def grounding_reward_weighted(
    completions: list[list[dict]],
    weight: float = 0.4,
    **kwargs,
) -> list[float]:
    """Grounding reward with configurable weight.

    For use in multi-reward GRPO training where rewards are combined.
    """
    raw_scores = grounding_reward(completions, **kwargs)
    return [score * weight for score in raw_scores]
