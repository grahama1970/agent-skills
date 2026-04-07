"""Thin wrapper around shared TaskClient for train-convo-steering.

Preserves the SteeringTaskClient interface used by cli.py and pipeline.py.
"""
from common.task_monitor import TaskClient


class SteeringTaskClient(TaskClient):
    """Drop-in replacement backed by the shared TaskClient."""

    def __init__(self, task_name: str, total_items: int):
        super().__init__(
            skill_name=f"train-convo-steering:{task_name}",
            total=total_items,
            description=f"Convo Steering: {task_name}",
        )

    def update(self, count: int = 1, status: str = "running"):  # type: ignore[override]
        """Increment progress, ignoring status (shared client tracks it internally)."""
        super().update(n=count)
