"""Reward functions for GRPO training.

Provides pluggable reward functions for task-specific GPT training:
- format: JSON Schema validation reward
- task_reward: User-defined pluggable reward
- mock: Mock rewards for testing without GPU
"""

from rewards.format import format_reward
from rewards.mock import mock_reward

__all__ = ["format_reward", "mock_reward"]
