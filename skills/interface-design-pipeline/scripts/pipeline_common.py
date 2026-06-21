#!/usr/bin/env python3
"""Shared schemas, validation, and artifact helpers for interface-design-pipeline."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "interface_design_pipeline.v1"
REVIEW_SCHEMA = "interface_design_pipeline.review.v1"
RECEIPT_SCHEMA = "interface_design_pipeline.receipt.v1"
PHASES = (
    "research",
    "reference_adjudication",
    "mockup_tournament",
    "component_inventory",
    "implementation_tournament",
    "final_adjudication",
    "human_promotion",
)
TERMINAL = {"PASS", "BLOCKED", "NEEDS_CHANGES"}

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def compact_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return value[:64] or "interface"


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_event(run_dir: Path, event: str, **fields: Any) -> None:
    path = run_dir / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"ts": utc_now(), "event": event, **fields}, sort_keys=True) + "\n")


def require_str(value: Any, label: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label}: expected non-empty string")
        return ""
    return value.strip()


def require_str_list(value: Any, label: str, errors: list[str], *, minimum: int = 1) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        errors.append(f"{label}: expected list of non-empty strings")
        return []
    normalized = [item.strip() for item in value]
    if len(normalized) < minimum:
        errors.append(f"{label}: expected at least {minimum} item(s)")
    return normalized


def require_competitors(value: Any, label: str, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) < 2:
        errors.append(f"{label}: expected at least two competitors")
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}]: expected object")
            continue
        competitor_id = require_str(item.get("id"), f"{label}[{index}].id", errors)
        require_str(item.get("strategy"), f"{label}[{index}].strategy", errors)
        if competitor_id in seen:
            errors.append(f"{label}: duplicate competitor id {competitor_id!r}")
        seen.add(competitor_id)
        out.append(item)
    return out


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema") != SCHEMA:
        errors.append(f"schema: expected {SCHEMA!r}")
    require_str(manifest.get("name"), "name", errors)
    require_str(manifest.get("brief"), "brief", errors)

    surface = manifest.get("surface")
    if not isinstance(surface, dict):
        errors.append("surface: expected object")
    else:
        for key in ("kind", "user_job", "primary_object", "primary_decision"):
            require_str(surface.get(key), f"surface.{key}", errors)
        require_str_list(surface.get("constraints", []), "surface.constraints", errors)
        require_str_list(surface.get("anti_goals", []), "surface.anti_goals", errors)

    research = manifest.get("research")
    if not isinstance(research, dict):
        errors.append("research: expected object")
    else:
        require_str_list(research.get("github_queries"), "research.github_queries", errors)
        require_str_list(research.get("brave_queries"), "research.brave_queries", errors)
        required_sources = require_str_list(
            research.get("required_sources", ["github", "brave"]),
            "research.required_sources",
            errors,
        )
        for required in ("github", "brave"):
            if required not in required_sources:
                errors.append(f"research.required_sources: must include {required!r}")

    mockups = manifest.get("mockups")
    if not isinstance(mockups, dict):
        errors.append("mockups: expected object")
    else:
        require_competitors(mockups.get("competitors"), "mockups.competitors", errors)
        require_str(mockups.get("reviewer_agent"), "mockups.reviewer_agent", errors)
        rounds = mockups.get("max_rounds", 3)
        if not isinstance(rounds, int) or rounds < 1 or rounds > 5:
            errors.append("mockups.max_rounds: expected integer from 1 through 5")
        threshold = mockups.get("minimum_score", 85)
        if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 100:
            errors.append("mockups.minimum_score: expected number from 0 through 100")
        require_str_list(mockups.get("required_states", []), "mockups.required_states", errors)

    implementation = manifest.get("implementation")
    if not isinstance(implementation, dict):
        errors.append("implementation: expected object")
    else:
        require_str(implementation.get("target_repo"), "implementation.target_repo", errors)
        require_str(implementation.get("target_surface"), "implementation.target_surface", errors)
        require_str_list(implementation.get("component_roots"), "implementation.component_roots", errors)
        stack = require_str_list(implementation.get("stack"), "implementation.stack", errors)
        if "react" not in {item.lower() for item in stack}:
            errors.append("implementation.stack: must include React")
        require_competitors(implementation.get("competitors"), "implementation.competitors", errors)
        require_str(implementation.get("reviewer_agent"), "implementation.reviewer_agent", errors)
        require_str_list(implementation.get("allowed_globs"), "implementation.allowed_globs", errors)
        require_str_list(implementation.get("required_changed_globs"), "implementation.required_changed_globs", errors)
        require_str_list(implementation.get("checks"), "implementation.checks", errors)
        if implementation.get("worktree_policy", "disposable") != "disposable":
            errors.append("implementation.worktree_policy: must be 'disposable'")

    promotion = manifest.get("promotion")
    if not isinstance(promotion, dict):
        errors.append("promotion: expected object")
    elif promotion.get("human_gate") is not True:
        errors.append("promotion.human_gate: must be true")
    return errors


def resolve_manifest_path(manifest_path: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (manifest_path.parent / path).resolve()


def path_for_node(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def render_brief(manifest: dict[str, Any], brief_text: str) -> str:
    surface = manifest["surface"]
    lines = [
        f"# {manifest['name']} interface brief",
        "",
        f"**User job:** {surface['user_job']}",
        f"**Primary object:** {surface['primary_object']}",
        f"**Primary decision:** {surface['primary_decision']}",
        "",
        "## Constraints",
        *[f"- {item}" for item in surface.get("constraints", [])],
        "",
        "## Anti-goals",
        *[f"- {item}" for item in surface.get("anti_goals", [])],
        "",
        "## Supplied brief",
        brief_text.strip(),
        "",
    ]
    return "\n".join(lines)
