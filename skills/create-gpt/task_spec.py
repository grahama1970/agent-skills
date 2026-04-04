#!/usr/bin/env python3
"""TaskSpec — the central abstraction for task-specific GPT training.

A task is fully defined by a YAML file specifying input/output schemas,
reward weights, eval thresholds, and training hyperparameters.

Usage:
    python task_spec.py define --name qra-validator --from-yaml data/tasks/qra-validator.yaml
    python task_spec.py show --name qra-validator
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
import typer
from loguru import logger

app = typer.Typer(add_completion=False)

SKILL_DIR = Path(__file__).resolve().parent
if SKILL_DIR.name == "scripts":
    SKILL_DIR = SKILL_DIR.parent
DATA_DIR = SKILL_DIR / "data"
MODELS_DIR = SKILL_DIR / "models"
PROMPT_DIR = SKILL_DIR.parent / "prompt-lab" / "prompts"


def _resolve_prompt(data: dict) -> str:
    """Resolve system prompt from YAML data.

    Supports two modes:
      1. system_prompt_file: name  → loads from /prompt-lab/prompts/{name}.txt
      2. system_prompt: "..."      → inline text (DEPRECATED, will warn)

    File-based prompts are mandatory per project rules. Inline prompts
    trigger a deprecation warning.
    """
    prompt_file = data.get("system_prompt_file", "")
    if prompt_file:
        path = PROMPT_DIR / f"{prompt_file}.txt"
        if not path.exists():
            raise FileNotFoundError(
                f"Prompt file '{prompt_file}' not found at {path}. "
                f"Run /prompt-lab eval to create and validate it."
            )
        return path.read_text().strip()

    inline = data.get("system_prompt", "")
    if inline and inline.strip():
        logger.warning(
            f"Task '{data.get('name', '?')}' uses inline system_prompt — "
            f"migrate to system_prompt_file per /prompt-lab rules"
        )
    return inline


@dataclass
class TaskSpec:
    """Full specification for a task-specific GPT training run."""

    name: str
    description: str = ""
    base_model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    max_seq_length: int = 512
    system_prompt: str = ""

    # Schemas
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)

    # Reward weights
    reward_weights: Dict[str, float] = field(default_factory=lambda: {
        "format": 0.3,
        "accuracy": 0.5,
        "grounding": 0.2,
    })

    # Evaluation thresholds
    eval_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "accuracy": 0.85,
        "format_valid": 0.95,
        "latency_p50_ms": 500,
    })

    # Training config
    training: Dict[str, Any] = field(default_factory=lambda: {
        "lora_r": 16,
        "lora_alpha": 32,
        "sft_epochs": 1,
        "grpo_steps": 2000,
        "quality_threshold": 0.85,
        "max_iterations": 5,
        "hp_trials": 15,
    })

    @classmethod
    def from_yaml(cls, path: Path) -> "TaskSpec":
        """Load a TaskSpec from a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            base_model=data.get("base_model", "Qwen/Qwen2.5-1.5B-Instruct"),
            max_seq_length=data.get("max_seq_length", 512),
            system_prompt=_resolve_prompt(data),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            reward_weights=data.get("reward_weights", {
                "format": 0.3, "accuracy": 0.5, "grounding": 0.2,
            }),
            eval_thresholds=data.get("eval_thresholds", {
                "accuracy": 0.85, "format_valid": 0.95, "latency_p50_ms": 500,
            }),
            training=data.get("training", {
                "lora_r": 16, "lora_alpha": 32, "sft_epochs": 1,
                "grpo_steps": 2000, "quality_threshold": 0.85,
                "max_iterations": 5, "hp_trials": 15,
            }),
        )

    def to_yaml(self, path: Path) -> None:
        """Save TaskSpec to YAML."""
        data = {
            "name": self.name,
            "description": self.description,
            "base_model": self.base_model,
            "max_seq_length": self.max_seq_length,
            "system_prompt": self.system_prompt,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "reward_weights": self.reward_weights,
            "eval_thresholds": self.eval_thresholds,
            "training": self.training,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "base_model": self.base_model,
            "max_seq_length": self.max_seq_length,
            "system_prompt": self.system_prompt,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "reward_weights": self.reward_weights,
            "eval_thresholds": self.eval_thresholds,
            "training": self.training,
        }

    def task_dir(self) -> Path:
        """Get the task-specific data directory."""
        return DATA_DIR / "tasks"

    def model_dir(self) -> Path:
        """Get the task-specific model directory."""
        return MODELS_DIR / self.name

    def get_training_param(self, key: str, default: Any = None) -> Any:
        """Get a training parameter with fallback."""
        return self.training.get(key, default)


def load_task_spec(task_name: str) -> TaskSpec:
    """Load a TaskSpec by name from the tasks directory."""
    yaml_path = DATA_DIR / "tasks" / f"{task_name}.yaml"
    if not yaml_path.exists():
        raise FileNotFoundError(f"Task spec not found: {yaml_path}")
    return TaskSpec.from_yaml(yaml_path)


@app.command()
def define(
    name: str = typer.Option(..., "--name", "-n", help="Task name"),
    from_yaml: Path = typer.Option(..., "--from-yaml", "-f", help="Source YAML file"),
):
    """Define a task from a YAML specification file."""
    if not from_yaml.exists():
        logger.error(f"YAML file not found: {from_yaml}")
        raise typer.Exit(code=1)

    spec = TaskSpec.from_yaml(from_yaml)
    if spec.name != name:
        logger.warning(f"Overriding task name from '{spec.name}' to '{name}'")
        spec.name = name

    # Save to canonical location
    target = DATA_DIR / "tasks" / f"{name}.yaml"
    spec.to_yaml(target)

    # Create model directory
    spec.model_dir().mkdir(parents=True, exist_ok=True)

    logger.info(f"Task '{name}' defined at {target}")
    logger.info(f"  Base model: {spec.base_model}")
    logger.info(f"  Max seq length: {spec.max_seq_length}")
    logger.info(f"  Quality threshold: {spec.training.get('quality_threshold', 0.85)}")


@app.command()
def show(
    name: str = typer.Option(..., "--name", "-n", help="Task name"),
):
    """Show a task specification."""
    spec = load_task_spec(name)
    print(json.dumps(spec.to_dict(), indent=2))


if __name__ == "__main__":
    app()
