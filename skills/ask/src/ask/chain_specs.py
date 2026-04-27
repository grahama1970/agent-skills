"""Saved review-chain specs for /ask."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .run_state import ASK_ROOT

DEFAULT_CHAIN_SPEC_DIR = ASK_ROOT / "docs" / "chains"


def load_chain_specs(chain_dir: str | Path | None = None) -> dict[str, dict[str, Any]]:
    directory = Path(chain_dir) if chain_dir else DEFAULT_CHAIN_SPEC_DIR
    specs: dict[str, dict[str, Any]] = {}
    if not directory.exists():
        return specs
    for path in sorted(directory.glob("*.chain.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"Chain spec must be a mapping: {path}")
        name = str(payload.get("name") or path.name.removesuffix(".chain.yaml"))
        specs[name] = {**payload, "name": name, "path": str(path)}
    return specs


def validate_chain_spec(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not spec.get("name"):
        errors.append("missing name")
    stages = spec.get("stages")
    if not isinstance(stages, list) or not stages:
        errors.append("stages must be a non-empty list")
        return errors
    seen = set()
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            errors.append(f"stage {index} must be a mapping")
            continue
        stage_name = stage.get("name")
        if not stage_name:
            errors.append(f"stage {index} missing name")
        elif stage_name in seen:
            errors.append(f"duplicate stage name: {stage_name}")
        else:
            seen.add(stage_name)
        if not stage.get("type"):
            errors.append(f"stage {stage_name or index} missing type")
        if "requires" in stage and not isinstance(stage["requires"], list):
            errors.append(f"stage {stage_name or index} requires must be a list")
        if "produces" in stage and not isinstance(stage["produces"], list):
            errors.append(f"stage {stage_name or index} produces must be a list")
    return errors


def get_chain_spec(name: str, chain_dir: str | Path | None = None) -> dict[str, Any]:
    specs = load_chain_specs(chain_dir)
    if name not in specs:
        raise KeyError(f"Unknown chain spec: {name}")
    errors = validate_chain_spec(specs[name])
    if errors:
        raise ValueError(f"Invalid chain spec {name}: {', '.join(errors)}")
    return specs[name]
