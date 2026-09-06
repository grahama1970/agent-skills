"""Pydantic first-gate for every persona-dream pipeline step boundary.

Operator directive (2026-09-06): every pipeline step validates its data with
Pydantic as the FIRST deterministic test, no exceptions. This module is the
single enforcement point. `dag_step.py` (the shim every Tau spine step routes
through) calls `validate_artifact` on every consumed JSON artifact BEFORE the
step runs, and on every produced JSON artifact after it runs. A violation
yields Pydantic `errors()` data (`type`, `loc`, `ctx`) as the steering signal
per best-practices-python `correctness-pydantic-steering` — never prose.

Inputs: artifact paths. Outputs: [] on pass, or a list of pydantic error dicts.
Failure modes: unreadable file, non-object JSON, missing/blank `schema` field,
or a registered per-schema model rejecting the payload. Fail-closed: unknown
schemas still must satisfy the envelope; registered schemas get the strict
model. Extend the REGISTRY as schemas migrate off jsonschema (ticket tracks
the full migration).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ArtifactEnvelope(BaseModel):
    """Minimum contract every persona-dream JSON artifact must satisfy."""

    model_config = ConfigDict(extra="allow")

    schema_name: str = Field(alias="schema", min_length=1)


class StoryboardPacket(ArtifactEnvelope):
    schema_name: Literal["persona_dream.storyboard_packet.v1"] = Field(alias="schema")
    accepted: Literal[True]
    status: Literal["PASS_PANEL_REVIEWED"]
    panels: list[dict[str, Any]] = Field(min_length=1)


class NodeReceipt(ArtifactEnvelope):
    schema_name: Literal["tau.generic_dag_node_receipt.v1"] = Field(alias="schema")
    node_id: str = Field(min_length=1)
    status: Literal["PASS", "BLOCKED"]
    verdict: Literal["PASS", "BLOCKED"]
    errors: list[str]


# schema field value -> strict model. Envelope applies to everything else.
REGISTRY: dict[str, type[ArtifactEnvelope]] = {
    "persona_dream.storyboard_packet.v1": StoryboardPacket,
    "tau.generic_dag_node_receipt.v1": NodeReceipt,
}


def validate_artifact(path: Path) -> list[dict[str, Any]]:
    """Return pydantic-style error dicts; empty list means PASS."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [{"type": "artifact_missing", "loc": [str(path)], "msg": "file not found"}]
    except (OSError, json.JSONDecodeError) as exc:
        return [{"type": "artifact_unreadable", "loc": [str(path)], "msg": str(exc)}]
    if not isinstance(raw, dict):
        return [{"type": "artifact_not_object", "loc": [str(path)], "msg": "JSON object required"}]
    model = REGISTRY.get(raw.get("schema", ""), ArtifactEnvelope)
    try:
        model.model_validate(raw)
    except ValidationError as exc:
        return [
            {**e, "loc": [str(path), *e["loc"]]}
            for e in exc.errors(include_url=False, include_input=False)
        ]
    return []


def validate_artifacts(paths: list[Path], json_only: bool = True) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for path in paths:
        if json_only and path.suffix != ".json":
            continue
        errors.extend(validate_artifact(path))
    return errors
