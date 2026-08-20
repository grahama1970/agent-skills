"""Deterministic JSON Schema export for checked-in CAPTCHA contracts.

Pydantic models are the source of truth. Checked-in schemas are generated from
those models and ``schemas --check`` fails when they drift.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import CaptchaSkillError, ErrorCode
from .models import (
    AskDag,
    AuthorizationManifest,
    AuthorizationReceipt,
    EvaluationPlan,
    ModelEndpointProof,
    PointerDispatchPlan,
    PointerMotionPlan,
    PointerMotionRequest,
    RunReceipt,
    RunStatusArtifact,
    StatusReport,
    SurfCapabilities,
    SurfTargetProof,
    TargetProof,
)
from .policy import write_json_atomic

_SCHEMA_MODELS = {
    "authorization.schema.json": (
        "captcha.target_authorization.v1",
        AuthorizationManifest,
    ),
    "authorization-receipt.schema.json": (
        "captcha.authorization_receipt.v1",
        AuthorizationReceipt,
    ),
    "evaluation-plan.schema.json": (
        "captcha.evaluation_plan.v1",
        EvaluationPlan,
    ),
    "run-receipt.schema.json": (
        "captcha.run_receipt.v1",
        RunReceipt,
    ),
    "run-status.schema.json": (
        "captcha.run_status.v1",
        RunStatusArtifact,
    ),
    "status.schema.json": (
        "captcha.status.v1",
        StatusReport,
    ),
    "model-endpoint-preflight.schema.json": (
        "captcha.model_endpoint_preflight.v1",
        ModelEndpointProof,
    ),
    "pointer-motion-request.schema.json": (
        "captcha.pointer_motion_request.v1",
        PointerMotionRequest,
    ),
    "pointer-motion-plan.schema.json": (
        "captcha.pointer_motion_plan.v1",
        PointerMotionPlan,
    ),
    "pointer-dispatch-plan.schema.json": (
        "captcha.pointer_dispatch_plan.v1",
        PointerDispatchPlan,
    ),
    "ask-dag.schema.json": (
        "ask.dag.v1.captcha-profile",
        AskDag,
    ),
    "surf-capabilities-subset.schema.json": (
        "surf.capabilities.v1.captcha-subset",
        SurfCapabilities,
    ),
    "surf-target-preflight.schema.json": (
        "captcha.surf_target_preflight.v1",
        SurfTargetProof,
    ),
    "target-preflight.schema.json": (
        "captcha.target_preflight.v1",
        TargetProof,
    ),
}


def schema_documents() -> dict[str, dict[str, Any]]:
    """Return stable JSON Schema documents keyed by output filename."""

    documents: dict[str, dict[str, Any]] = {}
    for filename, (schema_id, model) in _SCHEMA_MODELS.items():
        schema = model.model_json_schema(by_alias=True)
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = schema_id
        documents[filename] = schema
    return documents


def export_schemas(out_dir: Path, *, check: bool) -> dict[str, Any]:
    """Write or verify checked-in schemas."""

    documents = schema_documents()
    drift: list[str] = []
    written: list[str] = []
    for filename, expected in documents.items():
        path = out_dir / filename
        if check:
            try:
                actual = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                drift.append(filename)
                continue
            if actual != expected:
                drift.append(filename)
        else:
            write_json_atomic(path, expected)
            written.append(filename)
    if check and drift:
        raise CaptchaSkillError(
            ErrorCode.RECEIPT_INVALID,
            "checked-in JSON Schemas drift from Pydantic contracts",
            {"drift": sorted(drift)},
        )
    return {
        "schema_version": "captcha.schema_export_receipt.v1",
        "status": "PASS",
        "mode": "check" if check else "write",
        "output_directory": str(out_dir.expanduser().resolve()),
        "files": sorted(documents),
        "written": sorted(written),
        "seam_validation": {
            "kind": "captcha.schema_export",
            "status": "PASS",
        },
    }
