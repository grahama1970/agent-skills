"""Pluggable user-defined reward loading.

Loads a Python file with a compute_reward() function for custom task-specific
reward computation during GRPO training.

Expected interface for user reward files:
    def compute_reward(output: dict, input: dict, reference: dict = None) -> float:
        '''Return reward score in [0, 1].'''
        ...
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from loguru import logger


def load_task_reward(reward_file: Path) -> Callable:
    """Load a user-defined reward function from a Python file.

    Args:
        reward_file: Path to Python file containing compute_reward()

    Returns:
        The compute_reward callable

    Raises:
        FileNotFoundError: If file doesn't exist
        AttributeError: If file doesn't contain compute_reward()
    """
    if not reward_file.exists():
        raise FileNotFoundError(f"Reward file not found: {reward_file}")

    spec = importlib.util.spec_from_file_location("task_reward_module", reward_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "compute_reward"):
        raise AttributeError(f"Reward file must define compute_reward(): {reward_file}")

    return module.compute_reward


def task_reward(
    completions: list[list[dict]],
    reward_fn: Optional[Callable] = None,
    inputs: Optional[list[str]] = None,
    references: Optional[list[dict]] = None,
    **kwargs,
) -> list[float]:
    """Compute task-specific rewards using a pluggable reward function.

    Args:
        completions: List of completion groups (TRL format)
        reward_fn: User-defined compute_reward(output, input, reference) -> float
        inputs: Original input strings
        references: Optional reference outputs

    Returns:
        List of reward scores
    """
    if reward_fn is None:
        logger.warning("No task reward function provided, returning zeros")
        return [0.0] * len(completions)

    import json

    scores = []
    for i, completion in enumerate(completions):
        if isinstance(completion, list) and len(completion) > 0:
            content = completion[0].get("content", "")
        elif isinstance(completion, dict):
            content = completion.get("content", "")
        elif isinstance(completion, str):
            content = completion
        else:
            scores.append(0.0)
            continue

        # Parse output
        try:
            output = json.loads(content.strip())
        except (json.JSONDecodeError, AttributeError):
            output = {"raw": content}

        # Build input context
        input_text = inputs[i] if inputs and i < len(inputs) else ""
        if isinstance(input_text, str):
            try:
                input_dict = json.loads(input_text)
            except json.JSONDecodeError:
                input_dict = {"text": input_text}
        else:
            input_dict = input_text if isinstance(input_text, dict) else {"text": str(input_text)}

        reference = references[i] if references and i < len(references) else None

        try:
            score = float(reward_fn(output, input_dict, reference))
            score = max(0.0, min(1.0, score))
        except Exception as e:
            logger.warning(f"Task reward computation failed: {e}")
            score = 0.0

        scores.append(score)

    return scores
