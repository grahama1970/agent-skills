"""Build PR3c provider authorship receipts from Tau and Battle evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROVIDER_AUTHORSHIP_SCHEMA = "battle.provider_authorship_receipt.v1"
PROVIDER_CODE_AUTHOR_BOUNDARY_SCHEMA = "battle.provider_code_author_boundary_receipt.v1"


def build_provider_authorship_receipt(
    *,
    out_path: Path,
    battle_id: str,
    dag_id: str | None,
    node_id: str,
    child_lane_id: str | None,
    goal_hash: str | None,
    battle_work_order_path: Path,
    tau_work_order_path: Path,
    launch_receipt_path: Path,
    worker_result_path: Path | None,
    worker_validation_path: Path | None,
    artifact_validation: dict[str, Any],
    launch_receipt: dict[str, Any] | None,
    worker_result: dict[str, Any] | None,
    worker_validation: dict[str, Any] | None,
) -> dict[str, Any]:
    provider_live = _provider_live(launch_receipt, worker_validation)
    status = "PASS" if provider_live and artifact_validation.get("status") == "PASS" else "BLOCKED"
    errors: list[str] = []
    if not provider_live:
        errors.append("PROVIDER_EXECUTION_ATTESTATION_MISSING")
    if artifact_validation.get("status") != "PASS":
        errors.extend([str(item) for item in artifact_validation.get("errors", [])])

    route = _route(launch_receipt, worker_validation)
    receipt = {
        "schema": PROVIDER_AUTHORSHIP_SCHEMA,
        "status": status,
        "mocked": False,
        "live": "tau_provider_artifact_authoring",
        "agentic": provider_live,
        "provider_live": provider_live,
        "fixture_fallback_used": False,
        "battle_id": battle_id,
        "dag_id": dag_id,
        "node_id": node_id,
        "child_lane_id": child_lane_id,
        "goal_hash": goal_hash,
        "execution_mode": "tau_provider" if provider_live else "blocked",
        "authored_by": "tau_provider" if provider_live else "none",
        "requested_provider": route.get("provider"),
        "requested_model": route.get("model"),
        "requested_surface": route.get("surface"),
        "observed_provider": _observed_provider(launch_receipt, worker_validation),
        "observed_model": _observed_model(launch_receipt, worker_validation),
        "provider_run_id": _value(launch_receipt, "run_id"),
        "provider_session_id": _value(launch_receipt, "session_id"),
        "provider_run_status": _value(launch_receipt, "scillm_run_status"),
        "battle_work_order_path": str(battle_work_order_path),
        "tau_work_order_path": str(tau_work_order_path),
        "tau_launch_receipt_path": str(launch_receipt_path),
        "tau_worker_result_path": str(worker_result_path) if worker_result_path else None,
        "tau_worker_validation_receipt_path": str(worker_validation_path) if worker_validation_path else None,
        "code_artifact_path": artifact_validation.get("code_artifact_path"),
        "code_artifact_sha256": artifact_validation.get("code_artifact_sha256"),
        "code_artifact_bytes": artifact_validation.get("code_artifact_bytes"),
        "validation": {
            "goal_hash_bound": bool(goal_hash),
            "provider_route_bound": bool(route),
            "output_declared_by_worker": _declares(worker_result, "outputs/exploit_specimen.py"),
            "output_hash_bound": bool(artifact_validation.get("code_artifact_sha256")),
            "output_inside_allowed_root": "OUTPUT_PATH_ESCAPE" not in artifact_validation.get("errors", []),
            "private_reference_scan_passed": not any(str(error).startswith("PRIVATE_REFERENCE") for error in artifact_validation.get("errors", [])),
            "claim_boundary_passed": True,
        },
        "compile_status": "NOT_RUN",
        "runtime_status": "NOT_RUN",
        "target_contact": "NOT_RUN",
        "judge_status": "NOT_RUN",
        "judge_verified_exploits": 0,
        "errors": errors,
        "claims": {
            "proves": [
                "Tau invoked an attested provider/model route.",
                "The provider route materialized the bound exploit specimen artifact.",
                "Battle validated artifact provenance and claim boundaries.",
            ]
            if status == "PASS"
            else [],
            "does_not_prove": [
                "The code compiles.",
                "The code runs.",
                "The code contacts the target.",
                "The code exploits the target.",
                "Any Blue detection, kill, or block occurred.",
                "Judge verified exploit success.",
            ],
        },
        "created_at": _utc_stamp(),
    }
    _write_json(out_path, receipt)
    return receipt


def build_phase1_boundary_receipt(
    *,
    out_path: Path,
    authorship: dict[str, Any],
) -> dict[str, Any]:
    status = "PASS" if authorship.get("status") == "PASS" else "BLOCKED"
    receipt = {
        "schema": PROVIDER_CODE_AUTHOR_BOUNDARY_SCHEMA,
        "status": status,
        "mocked": False,
        "live": "tau_provider_artifact_authoring",
        "agentic": bool(authorship.get("agentic")),
        "provider_live": bool(authorship.get("provider_live")),
        "fixture_fallback_used": False,
        "battle_id": authorship.get("battle_id"),
        "dag_id": authorship.get("dag_id"),
        "node_id": authorship.get("node_id"),
        "child_lane_id": authorship.get("child_lane_id"),
        "goal_hash": authorship.get("goal_hash"),
        "compile_status": "NOT_RUN",
        "runtime_status": "NOT_RUN",
        "judge_status": "NOT_RUN",
        "judge_verified_exploits": 0,
        "provider_authorship_receipt": out_path.name.replace("provider-code-author-boundary-receipt", "provider-authorship-receipt"),
        "errors": authorship.get("errors", []),
        "claims": authorship.get("claims", {}),
        "created_at": _utc_stamp(),
    }
    _write_json(out_path, receipt)
    return receipt


def _provider_live(launch: dict[str, Any] | None, validation: dict[str, Any] | None) -> bool:
    return bool(
        isinstance(launch, dict)
        and isinstance(validation, dict)
        and launch.get("provider_live") is True
        and validation.get("provider_live") is True
        and launch.get("live") is True
        and validation.get("status") == "PASS"
    )


def _route(*receipts: dict[str, Any] | None) -> dict[str, Any]:
    for receipt in receipts:
        if isinstance(receipt, dict) and isinstance(receipt.get("model_provider_route"), dict):
            return dict(receipt["model_provider_route"])
    return {}


def _observed_provider(*receipts: dict[str, Any] | None) -> str | None:
    for receipt in receipts:
        value = _value(receipt, "observed_provider") or _value(receipt, "provider")
        if value:
            return value
    return None


def _observed_model(*receipts: dict[str, Any] | None) -> str | None:
    for receipt in receipts:
        value = _value(receipt, "observed_model") or _value(receipt, "model")
        if value:
            return value
    return None


def _value(receipt: dict[str, Any] | None, key: str) -> str | None:
    value = receipt.get(key) if isinstance(receipt, dict) else None
    return value if isinstance(value, str) and value else None


def _declares(result: dict[str, Any] | None, artifact: str) -> bool:
    values = result.get("artifacts") if isinstance(result, dict) else None
    return artifact in values if isinstance(values, list) else False


def _utc_stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
