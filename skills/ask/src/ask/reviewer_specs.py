"""Reviewer role specs for /ask review workflows."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


SKILL_ROOT = Path(__file__).resolve().parents[2]
REVIEWER_DIR = SKILL_ROOT / "docs" / "reviewers"

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
BUILTIN_REVIEWERS: dict[str, dict[str, Any]] = {
    "security": {
        "name": "security",
        "protocol_role": "security_reviewer",
        "focus": ["data-loss", "path-validation", "secret-persistence", "fail-closed"],
    },
    "qa": {
        "name": "qa",
        "protocol_role": "test_reviewer",
        "focus": ["failure-path-tests", "cli-behavior", "regression-risk"],
    },
    "runtime": {
        "name": "runtime",
        "protocol_role": "runtime_reviewer",
        "focus": ["state-machine", "events", "watch", "resume", "prune"],
    },
}


def load_reviewer_spec(name: str) -> dict[str, Any]:
    candidate = Path(name).expanduser()
    if candidate.exists():
        return _load_yaml(candidate)
    for suffix in (".yaml", ".yml"):
        path = REVIEWER_DIR / f"{name}{suffix}"
        if path.exists():
            return _load_yaml(path)
    specs = load_reviewer_specs()
    key = FOCUS_ALIASES.get(name.strip().lower(), name.strip())
    if key in specs:
        return specs[key]
    if name in BUILTIN_REVIEWERS:
        return dict(BUILTIN_REVIEWERS[name])
    raise FileNotFoundError(f"Unknown /ask reviewer spec: {name}")


def load_selected_reviewer_specs(names: list[str] | None) -> list[dict[str, Any]]:
    return [load_reviewer_spec(name) for name in names or []]


def focus_from_reviewer_specs(specs: list[dict[str, Any]]) -> str:
    focus: list[str] = []
    for spec in specs:
        values = spec.get("focus", [])
        if isinstance(values, str):
            values = [value.strip() for value in values.split(",")]
        for value in values:
            if value and value not in focus:
                focus.append(str(value))
    return ",".join(focus)


def load_reviewer_specs(spec_dir: str | Path | None = None) -> dict[str, dict[str, Any]]:
    directory = Path(spec_dir) if spec_dir else REVIEWER_DIR
    specs: dict[str, dict[str, Any]] = {}
    if directory.exists():
        for path in sorted(directory.glob("*.md")):
            metadata, prompt = _split_frontmatter(path.read_text(encoding="utf-8"), path)
            name = str(metadata.get("name") or path.stem)
            specs[name] = {**metadata, "name": name, "prompt": prompt, "path": str(path)}
        for path in sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")]):
            data = _load_yaml(path)
            name = str(data.get("name") or path.stem)
            specs.setdefault(name, data)
    for name, spec in BUILTIN_REVIEWERS.items():
        specs.setdefault(name, dict(spec))
    return specs


def get_reviewer_spec(name: str, spec_dir: str | Path | None = None) -> dict[str, Any]:
    specs = load_reviewer_specs(spec_dir)
    key = FOCUS_ALIASES.get(name.strip().lower(), name.strip())
    if key not in specs:
        raise KeyError(f"Unknown reviewer spec: {name}")
    return specs[key]


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


def _split_frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Reviewer spec missing YAML frontmatter: {path}")
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"Reviewer spec frontmatter must be a mapping: {path}")
    return metadata, match.group(2).strip()


def _append_unique(names: list[str], name: str) -> None:
    if name not in names:
        names.append(name)


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Reviewer spec must be a mapping: {path}")
    data.setdefault("name", path.stem)
    data.setdefault("path", str(path))
    return data
