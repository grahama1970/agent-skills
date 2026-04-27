"""Reviewer-role frontmatter specs for /ask protocols."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .run_state import ASK_ROOT

DEFAULT_REVIEWER_SPEC_DIR = ASK_ROOT / "docs" / "reviewers"

FOCUS_ALIASES = {
    "auditability": "evidence-auditor",
    "evidence": "evidence-auditor",
    "correctness": "failure-mode",
    "failure": "failure-mode",
    "failure-mode": "failure-mode",
    "fail-closed": "fail-closed",
    "tests": "test-proof",
    "test": "test-proof",
    "test-proof": "test-proof",
    "maintainability": "complexity-minimizer",
    "complexity": "complexity-minimizer",
    "security": "security-data-risk",
    "data-risk": "security-data-risk",
}

DEFAULT_DYNAMIC_ORDER = [
    "evidence-auditor",
    "failure-mode",
    "fail-closed",
    "test-proof",
    "complexity-minimizer",
    "security-data-risk",
]


def _split_frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Reviewer spec missing YAML frontmatter: {path}")
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"Reviewer spec frontmatter must be a mapping: {path}")
    return metadata, match.group(2).strip()


def load_reviewer_specs(spec_dir: str | Path | None = None) -> dict[str, dict[str, Any]]:
    directory = Path(spec_dir) if spec_dir else DEFAULT_REVIEWER_SPEC_DIR
    specs: dict[str, dict[str, Any]] = {}
    if not directory.exists():
        return specs
    for path in sorted(directory.glob("*.md")):
        metadata, prompt = _split_frontmatter(path.read_text(encoding="utf-8"), path)
        name = str(metadata.get("name") or path.stem)
        specs[name] = {
            **metadata,
            "name": name,
            "prompt": prompt,
            "path": str(path),
        }
    return specs


def get_reviewer_spec(name: str, spec_dir: str | Path | None = None) -> dict[str, Any]:
    specs = load_reviewer_specs(spec_dir)
    key = FOCUS_ALIASES.get(name.strip().lower(), name.strip())
    if key not in specs:
        raise KeyError(f"Unknown reviewer spec: {name}")
    return specs[key]


def _append_unique(names: list[str], name: str) -> None:
    if name not in names:
        names.append(name)


def select_reviewer_angles(
    question: str,
    *,
    focus: str | None = None,
    count: int = 3,
    spec_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    specs = load_reviewer_specs(spec_dir)
    if not specs:
        return []

    selected: list[str] = []
    for item in [part.strip().lower() for part in (focus or "").split(",") if part.strip()]:
        _append_unique(selected, FOCUS_ALIASES.get(item, item))

    lowered = question.lower()
    _append_unique(selected, "evidence-auditor")
    _append_unique(selected, "failure-mode")
    if any(term in lowered for term in ["safe", "proceed", "failure", "timeout", "partial", "empty"]):
        _append_unique(selected, "fail-closed")
    if any(term in lowered for term in ["test", "coverage", "sanity", "e2e", "regression"]):
        _append_unique(selected, "test-proof")
    if any(term in lowered for term in ["security", "secret", "credential", "memory", "data"]):
        _append_unique(selected, "security-data-risk")
    _append_unique(selected, "complexity-minimizer")

    for name in DEFAULT_DYNAMIC_ORDER:
        _append_unique(selected, name)

    resolved = [specs[name] for name in selected if name in specs]
    return resolved[: max(1, count)]


def spec_to_participant(spec: dict[str, Any], *, turn_index: int = 0) -> dict[str, Any]:
    return {
        "persona": str(spec.get("label") or spec.get("name") or "Reviewer"),
        "protocol_role": str(spec.get("protocol_role") or spec.get("name") or "reviewer").replace("-", "_"),
        "role_label": str(spec.get("label") or spec.get("name") or "Reviewer"),
        "scope": str(spec.get("scope") or spec.get("prompt") or "Review the target."),
        "prohibitions": str(spec.get("prohibitions") or "Do not freeform outside the assigned protocol role."),
        "turn_index": turn_index,
        "reviewer_spec": {
            key: spec.get(key)
            for key in ["name", "model", "reasoning", "fallback_models", "tools", "write_policy", "path"]
            if key in spec
        },
    }
