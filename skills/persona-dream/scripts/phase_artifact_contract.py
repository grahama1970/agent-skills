"""Shared Persona Dream Phase 01-10 artifact contract and semantic checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "contracts"
    / "persona_dream_phase_artifacts.v1.json"
)


@dataclass(frozen=True)
class ArtifactValidation:
    artifact_id: str
    path: Path | None
    status: str
    blockers: tuple[str, ...]


def load_phase_artifact_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract.get("schema") != "persona_dream.phase_artifacts.v1":
        raise ValueError("unsupported phase artifact contract")
    return contract


def resolve_required_artifact(
    revision_root: Path, requirement: dict[str, Any]
) -> Path | None:
    basenames = {str(name).lower() for name in requirement.get("basenames", [])}
    matches = [
        path
        for path in revision_root.rglob("*")
        if path.is_file() and path.name.lower() in basenames
    ]
    return sorted(matches, key=lambda path: str(path.relative_to(revision_root)))[0] if matches else None


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def _validate_storyboard_packet(value: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if value.get("schema") != "persona_dream.storyboard_packet.v1":
        blockers.append("BLOCKED_PHASE_ARTIFACT_SCHEMA_INVALID")
    if value.get("accepted") is not True:
        blockers.append("BLOCKED_PHASE_ARTIFACT_SEMANTIC_INVALID:accepted")
    if value.get("status") != "PASS_PANEL_REVIEWED":
        blockers.append("BLOCKED_PHASE_ARTIFACT_SEMANTIC_INVALID:status")
    panels = value.get("panels")
    if not isinstance(panels, list) or not panels:
        blockers.append("BLOCKED_PHASE_ARTIFACT_SEMANTIC_INVALID:panels")
        return blockers
    if value.get("panel_count") != len(panels):
        blockers.append("BLOCKED_PHASE_ARTIFACT_SEMANTIC_INVALID:panel_count")
    panel_ids = [panel.get("panel_id") for panel in panels if isinstance(panel, dict)]
    if len(panel_ids) != len(panels) or any(not panel_id for panel_id in panel_ids):
        blockers.append("BLOCKED_PHASE_ARTIFACT_SEMANTIC_INVALID:panel_ids")
    elif len(set(panel_ids)) != len(panel_ids):
        blockers.append("BLOCKED_PHASE_ARTIFACT_SEMANTIC_INVALID:duplicate_panel_ids")
    return blockers


SEMANTIC_VALIDATORS = {"storyboard_packet_v1": _validate_storyboard_packet}


def validate_required_artifact(
    revision_root: Path, requirement: dict[str, Any]
) -> ArtifactValidation:
    artifact_id = str(requirement["artifact_id"])
    path = resolve_required_artifact(revision_root, requirement)
    if path is None:
        return ArtifactValidation(
            artifact_id, None, "MISSING", ("BLOCKED_PHASE_ARTIFACT_MISSING",)
        )
    try:
        value = _read_object(path) if requirement.get("kind") == "json" else {}
    except (json.JSONDecodeError, ValueError):
        return ArtifactValidation(
            artifact_id,
            path,
            "SCHEMA_INVALID",
            ("BLOCKED_PHASE_ARTIFACT_SCHEMA_INVALID",),
        )
    validator_name = requirement.get("semantic_validator")
    blockers = (
        SEMANTIC_VALIDATORS[str(validator_name)](value) if validator_name else []
    )
    return ArtifactValidation(
        artifact_id,
        path,
        "SEMANTIC_INVALID" if blockers else "CURRENT",
        tuple(blockers),
    )


def validate_revision_artifacts(revision_root: Path) -> dict[str, dict[str, Any]]:
    contract = load_phase_artifact_contract()
    results: dict[str, dict[str, Any]] = {}
    for phase_id, phase in contract["phases"].items():
        validations = [
            validate_required_artifact(revision_root, requirement)
            for requirement in phase["required_artifacts"]
        ]
        results[phase_id] = {
            "required": [item.artifact_id for item in validations],
            "artifacts": [
                {
                    "artifact_id": item.artifact_id,
                    "path": str(item.path.relative_to(revision_root)) if item.path else None,
                    "status": item.status,
                    "blockers": list(item.blockers),
                }
                for item in validations
            ],
            "status": "CURRENT"
            if all(item.status == "CURRENT" for item in validations)
            else "BLOCKED",
        }
    return results
