"""Thunderdome manifest loader and Pydantic models for tournament configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from loguru import logger
from pydantic import BaseModel, Field


class ScoringConfig(BaseModel):
    metric_path: str = "$.selected_metrics.macro_f1"
    gate_threshold: float = 0.90
    direction: str = "higher_better"


class ConvergenceConfig(BaseModel):
    max_rounds: int = 5
    n_strategies: int = 3
    plateau_window: int = 3
    plateau_epsilon: float = 0.02


class Reviewer(BaseModel):
    name: str
    role: Optional[str] = None


class Strategy(BaseModel):
    name: str
    modality: str = "paired"
    backbones: str = "efficientnet_b0"
    epochs: int = 20
    lr: float = 2e-4
    batch_size: int = 32
    mixup_alpha: float = 0.0
    cutmix_alpha: float = 0.0
    random_erasing: float = 0.0
    dropout: float = 0.1
    weight_decay: float = 1e-4
    label_smoothing: float = 0.0
    extra_flags: dict[str, Any] = Field(default_factory=dict)


class ThunderdomeManifest(BaseModel):
    name: str
    description: str = ""
    data_dir: Path
    skill: str = "classifier-lab"
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    convergence: ConvergenceConfig = Field(default_factory=ConvergenceConfig)
    reviewers: list[Reviewer] = Field(default_factory=list)
    strategies: list[Strategy] = Field(default_factory=list)
    dogpile_on_failure: bool = True
    memory_scope: str = "classifier-lab"


def load_manifest(path: str | Path) -> ThunderdomeManifest:
    path = Path(path)
    logger.info(f"Loading manifest: {path}")
    with path.open() as f:
        raw = yaml.safe_load(f)
    manifest = ThunderdomeManifest.model_validate(raw)
    logger.debug(f"Manifest loaded: name={manifest.name}, data_dir={manifest.data_dir}")
    return manifest
