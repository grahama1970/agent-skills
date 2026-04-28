"""Saved review chain specs for deterministic /ask workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


SKILL_ROOT = Path(__file__).resolve().parents[2]
CHAIN_DIR = SKILL_ROOT / "docs" / "chains"

BUILTIN_CHAINS: dict[str, dict[str, Any]] = {
    "deep-review-safety": {
        "name": "deep-review-safety",
        "description": "Read-only safety review with independent reviewers and deep-review artifacts.",
        "ask_options": {
            "deep_review": True,
            "parallel_review": True,
            "parallel_reviewers": 5,
            "deep_reviewers": 5,
            "deep_review_focus": "filesystem,fail-closed,tests,auditability,privacy",
            "parallel_review_focus": "filesystem,fail-closed,tests,auditability,privacy",
            "oracle_backend": "subagent-runner",
            "oracle_reasoning": "xhigh",
        },
    }
}


def load_chain_specs(chain_dir: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Load saved review-chain specs, including runtime option presets."""

    directory = Path(chain_dir).expanduser() if chain_dir else CHAIN_DIR
    chains: dict[str, dict[str, Any]] = {}
    for path in sorted({*directory.glob("*.chain.yaml"), *directory.glob("*.yaml"), *directory.glob("*.yml")}):
        spec = _load_yaml(path)
        spec["path"] = str(path)
        chains[str(spec["name"])] = spec
    for name, spec in BUILTIN_CHAINS.items():
        chains.setdefault(name, {**spec, "path": "builtin"})
    return chains


def validate_chain_spec(spec: dict[str, Any]) -> list[str]:
    """Return validation errors for a saved chain spec."""

    errors: list[str] = []
    if not isinstance(spec.get("name"), str) or not spec["name"]:
        errors.append("name is required")

    if "ask_options" in spec:
        if not isinstance(spec["ask_options"], dict):
            errors.append("ask_options must be a mapping")
        return errors

    stages = spec.get("stages")
    if not isinstance(stages, list) or not stages:
        errors.append("stages must be a non-empty list")
        return errors

    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            errors.append(f"stages[{index}] must be a mapping")
            continue
        if not stage.get("name"):
            errors.append(f"stages[{index}].name is required")
        if not stage.get("type"):
            errors.append(f"stages[{index}].type is required")
    return errors


def get_chain_spec(name: str, chain_dir: Path | str | None = None) -> dict[str, Any]:
    chains = load_chain_specs(chain_dir)
    if name not in chains:
        raise FileNotFoundError(f"Unknown /ask chain spec: {name}")
    return chains[name]


def load_chain_spec(name: str) -> dict[str, Any]:
    candidate = Path(name).expanduser()
    if candidate.exists():
        return _load_yaml(candidate)
    for suffix in (".chain.yaml", ".yaml", ".yml"):
        path = CHAIN_DIR / f"{name}{suffix}"
        if path.exists():
            return _load_yaml(path)
    if name in BUILTIN_CHAINS:
        return dict(BUILTIN_CHAINS[name])
    raise FileNotFoundError(f"Unknown /ask chain spec: {name}")


def apply_chain_options(current: dict[str, Any], chain_name: str | None) -> dict[str, Any]:
    if not chain_name:
        return current
    spec = load_chain_spec(chain_name)
    options = dict(spec.get("ask_options", {}))
    merged = dict(current)
    for key, value in options.items():
        if value is None:
            continue
        if key.endswith("reviewers"):
            merged[key] = max(int(merged.get(key, 0) or 0), int(value))
        elif not merged.get(key):
            merged[key] = value
    merged["chain"] = spec.get("name", chain_name)
    merged["chain_spec"] = spec
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Chain spec must be a mapping: {path}")
    data.setdefault("name", path.stem)
    return data
